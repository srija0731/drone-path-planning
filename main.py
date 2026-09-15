import json
import math
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import urllib.request
import webbrowser
from functools import lru_cache
from pathlib import Path
DEFAULT_LOCATIONS = {}
def load_locations(path="locations.json"):
    file_path = Path(path)
    data = DEFAULT_LOCATIONS.copy()
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as handle:
            try:
                items = json.load(handle)
            except json.JSONDecodeError:
                items = []

        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict) or "name" not in item:
                    continue

                name = str(item["name"]).strip().lower()

                if "lat" in item and "lon" in item:
                    data[name] = (float(item["lat"]), float(item["lon"]))
                elif "latitude" in item and "longitude" in item:
                    data[name] = (float(item["latitude"]), float(item["longitude"]))
                elif "x" in item and "y" in item:
                    data[name] = (float(item["x"]), float(item["y"]))

    return data

@lru_cache(maxsize=512)
def geocode_place(place_name):
    place_name = place_name.strip()

    queries = [place_name] if "," in place_name else [f"{place_name}, India"]

    def photon_lookup():
        params = urllib.parse.urlencode({"q": place_name, "limit": 1})
        request = urllib.request.Request(
            f"https://photon.komoot.io/api/?{params}",
            headers={"User-Agent": "drone-path-planning/1.0 (route planning demo)"},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            features = json.loads(response.read().decode("utf-8")).get("features", [])
        coordinates = features[0]["geometry"]["coordinates"]
        return (float(coordinates[1]), float(coordinates[0]))

    def nominatim_lookup():
        params = urllib.parse.urlencode({"format": "jsonv2", "limit": 1, "q": queries[0]})
        request = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={
                "User-Agent": "drone-path-planning/1.0 (route planning demo)",
                "Accept-Language": "en",
            },
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (float(data[0]["lat"]), float(data[0]["lon"]))

    executor = ThreadPoolExecutor(max_workers=2)
    futures = [executor.submit(photon_lookup), executor.submit(nominatim_lookup)]
    try:
        for future in as_completed(futures):
            try:
                return future.result()
            except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                continue
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return None

def resolve_location(value, locations=None):
    text = (value or "").strip()
    if not text:
        raise ValueError("point input is empty")

    lookup = load_locations() if locations is None else locations
    key = text.lower().strip()
    if key in lookup:
        return lookup[key]

    cleaned = text.replace("(", "").replace(")", "")
    parts = [part.strip() for part in cleaned.replace(",", " ").split()]
    if len(parts) == 2:
        try:
            return (float(parts[0]), float(parts[1]))
        except ValueError:
            pass

    geocoded = geocode_place(text)
    if geocoded is not None:
        return geocoded

    raise ValueError(
        f"could not find {value!r}. Enter a more specific place, such as 'Kurnool, Andhra Pradesh, India', or use latitude,longitude coordinates"
    )


def parse_point(value, locations=None):
    return resolve_location(value, locations=locations)


def load_obstacles(path="obstacles.json"):
    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    obstacles = []
    for item in data:
        if isinstance(item, dict):
            obstacles.append((float(item["x"]), float(item["y"]), float(item.get("w", 1)), float(item.get("h", 1))))
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            obstacles.append((float(item[0]), float(item[1]), float(item[2]), float(item[3])))

    return obstacles


# -------------------------------
# Path-planning algorithms
# -------------------------------
def distance(first, second):
    return math.hypot(second[0] - first[0], second[1] - first[1])


def point_in_obstacle(point, obstacle, margin=0.0):
    x, y, width, height = obstacle
    return x - margin <= point[0] <= x + width + margin and y - margin <= point[1] <= y + height + margin


def segment_is_clear(start, end, obstacles, samples=24):
    for index in range(samples + 1):
        ratio = index / samples
        point = (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
        if any(point_in_obstacle(point, obstacle, margin=0.002) for obstacle in obstacles):
            return False
    return True


class ImprovedInformedRRTStar:
    def __init__(self, start, goal, map_size, obstacles=(), iterations=350):
        self.start = tuple(start)
        self.goal = tuple(goal)
        self.map_size = map_size
        self.obstacles = list(obstacles)
        self.iterations = iterations
        self.random = random.Random(7)

    def _bounds(self):
        if len(self.map_size) == 4:
            return self.map_size
        width, height = self.map_size
        return (0.0, float(width), 0.0, float(height))

    def _sample(self, bounds, best_cost):
        min_x, max_x, min_y, max_y = bounds
        if best_cost < float("inf"):
            center_x = (self.start[0] + self.goal[0]) / 2
            center_y = (self.start[1] + self.goal[1]) / 2
            radius = best_cost / 2
            for _ in range(20):
                angle = self.random.uniform(0, 2 * math.pi)
                scale = math.sqrt(self.random.random())
                point = (center_x + math.cos(angle) * radius * scale, center_y + math.sin(angle) * radius * scale)
                if min_x <= point[0] <= max_x and min_y <= point[1] <= max_y:
                    return point
        return (self.random.uniform(min_x, max_x), self.random.uniform(min_y, max_y))

    def plan(self):
        if segment_is_clear(self.start, self.goal, self.obstacles):
            return [self.start, self.goal]

        bounds = self._bounds()
        diagonal = math.hypot(bounds[1] - bounds[0], bounds[3] - bounds[2])
        step_size = max(diagonal / 18, 1e-6)
        nodes = [self.start]
        parents = [-1]
        costs = [0.0]
        best_index = None
        best_cost = float("inf")

        for _ in range(self.iterations):
            sample = self._sample(bounds, best_cost)
            nearest_index = min(range(len(nodes)), key=lambda index: distance(nodes[index], sample))
            nearest = nodes[nearest_index]
            length = distance(nearest, sample)
            ratio = min(step_size / length, 1.0) if length else 0.0
            candidate = (nearest[0] + (sample[0] - nearest[0]) * ratio, nearest[1] + (sample[1] - nearest[1]) * ratio)
            if not segment_is_clear(nearest, candidate, self.obstacles):
                continue

            near_indices = [index for index, node in enumerate(nodes) if distance(node, candidate) <= step_size * 2]
            parent_index = nearest_index
            parent_cost = costs[nearest_index] + distance(nearest, candidate)
            for index in near_indices:
                proposed_cost = costs[index] + distance(nodes[index], candidate)
                if proposed_cost < parent_cost and segment_is_clear(nodes[index], candidate, self.obstacles):
                    parent_index = index
                    parent_cost = proposed_cost

            nodes.append(candidate)
            parents.append(parent_index)
            costs.append(parent_cost)
            new_index = len(nodes) - 1
            for index in near_indices:
                rewired_cost = parent_cost + distance(candidate, nodes[index])
                if rewired_cost < costs[index] and segment_is_clear(candidate, nodes[index], self.obstacles):
                    parents[index] = new_index
                    costs[index] = rewired_cost

            if segment_is_clear(candidate, self.goal, self.obstacles):
                total_cost = parent_cost + distance(candidate, self.goal)
                if total_cost < best_cost:
                    best_index = new_index
                    best_cost = total_cost

        if best_index is None:
            raise ValueError("no collision-free path found for this drone")

        path = [self.goal]
        current = best_index
        while current >= 0:
            path.append(nodes[current])
            current = parents[current]
        return list(reversed(path))


def prune_path(path, obstacles=()):
    if len(path) <= 2:
        return list(path)
    pruned = [path[0]]
    anchor = 0
    for index in range(2, len(path)):
        if not segment_is_clear(path[anchor], path[index], obstacles):
            pruned.append(path[index - 1])
            anchor = index - 1
    pruned.append(path[-1])
    return pruned


class DWA:
    def __init__(self, max_speed=1.0, heading_samples=9):
        self.max_speed = max_speed
        self.heading_samples = heading_samples

    def avoid_obstacle(self, current_pos, obstacles, goal):
        heading = math.atan2(goal[1] - current_pos[1], goal[0] - current_pos[0])
        candidates = []
        for index in range(self.heading_samples):
            offset = (index - self.heading_samples // 2) * math.pi / 8
            velocity = (math.cos(heading + offset) * self.max_speed, math.sin(heading + offset) * self.max_speed)
            next_pos = (current_pos[0] + velocity[0], current_pos[1] + velocity[1])
            if not any(point_in_obstacle(next_pos, obstacle, margin=0.002) for obstacle in obstacles):
                score = distance(next_pos, goal) + abs(offset) * 0.2
                candidates.append((score, velocity))
        return min(candidates, key=lambda item: item[0])[1] if candidates else (0.0, 0.0)

    def adjust_path(self, path, obstacles):
        adjusted = [path[0]]
        for current, goal in zip(path[:-1], path[1:]):
            if any(point_in_obstacle(goal, obstacle, margin=0.002) for obstacle in obstacles):
                velocity = self.avoid_obstacle(current, obstacles, goal)
                goal = (current[0] + velocity[0], current[1] + velocity[1])
            adjusted.append(goal)
        return adjusted


def bezier_smoothing(path, samples_per_segment=4):
    if len(path) < 3:
        return list(path)
    smoothed = [path[0]]
    for index in range(len(path) - 1):
        start = path[index]
        end = path[index + 1]
        previous = path[index - 1] if index else start
        following = path[index + 2] if index + 2 < len(path) else end
        control = (start[0] + (following[0] - previous[0]) / 6, start[1] + (following[1] - previous[1]) / 6)
        for sample in range(1, samples_per_segment + 1):
            t = sample / samples_per_segment
            inverse = 1 - t
            smoothed.append((inverse * inverse * start[0] + 2 * inverse * t * control[0] + t * t * end[0], inverse * inverse * start[1] + 2 * inverse * t * control[1] + t * t * end[1]))
    return smoothed


def cost_function(path, w1=1, w2=1, w3=1):
    distance_cost = sum(distance(first, second) for first, second in zip(path, path[1:]))
    return w1 * distance_cost + w2 * max(0, len(path) - 2) + w3 * distance_cost * 0.05


def plan_drone_route(start, goal, obstacles=()):
    margin = max(distance(start, goal) * 0.15, 0.01)
    obstacle_x = [value for obstacle in obstacles for value in (obstacle[0], obstacle[0] + obstacle[2])]
    obstacle_y = [value for obstacle in obstacles for value in (obstacle[1], obstacle[1] + obstacle[3])]
    bounds = (
        min([start[0], goal[0], *obstacle_x]) - margin,
        max([start[0], goal[0], *obstacle_x]) + margin,
        min([start[1], goal[1], *obstacle_y]) - margin,
        max([start[1], goal[1], *obstacle_y]) + margin,
    )
    global_path = ImprovedInformedRRTStar(start, goal, bounds, obstacles=obstacles).plan()
    pruned_path = prune_path(global_path, obstacles=obstacles)
    local_path = DWA(max_speed=max(distance(start, goal) / 10, 0.01)).adjust_path(pruned_path, obstacles)
    smooth_path = bezier_smoothing(local_path)
    return smooth_path, cost_function(smooth_path)


def create_browser_view(path_points, start, goal, obstacles=None, map_size=(30, 30)):
    width = 900
    height = 700
    padding = 60

    if obstacles is None:
        obstacles = []

    map_w, map_h = map_size
    min_x = 0
    max_x = map_w
    min_y = 0
    max_y = map_h

    def transform_x(value):
        return padding + (value - min_x) / (max_x - min_x + 1e-9) * (width - 2 * padding)

    def transform_y(value):
        return height - padding - (value - min_y) / (max_y - min_y + 1e-9) * (height - 2 * padding)

    points = " ".join(f"{transform_x(x):.2f},{transform_y(y):.2f}" for x, y in path_points)
    start_x = transform_x(start[0])
    start_y = transform_y(start[1])
    goal_x = transform_x(goal[0])
    goal_y = transform_y(goal[1])

    obstacle_svg = "".join(
        f'<rect x="{transform_x(x):.2f}" y="{transform_y(y + h):.2f}" width="{(transform_x(x + w) - transform_x(x)):.2f}" height="{(transform_y(y) - transform_y(y + h)):.2f}" fill="#475569" stroke="#1e293b" stroke-width="2" rx="4" />'
        for x, y, w, h in obstacles
    )

    grid_lines = "".join(
        f'<line x1="{transform_x(i):.2f}" y1="{padding:.2f}" x2="{transform_x(i):.2f}" y2="{height - padding:.2f}" stroke="#e2e8f0" stroke-width="1" />'
        + f'<line x1="{padding:.2f}" y1="{transform_y(i):.2f}" x2="{width - padding:.2f}" y2="{transform_y(i):.2f}" stroke="#e2e8f0" stroke-width="1" />'
        for i in range(int(map_w) + 1)
    )

    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>Drone Path Planning</title>
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <style>
        body {{
          margin: 0;
          font-family: Arial, sans-serif;
          background: linear-gradient(135deg, #020817, #0f172a 60%, #111827);
          color: #e2e8f0;
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
        }}
        .card {{
          width: min(95vw, 1100px);
          background: rgba(15, 23, 42, 0.96);
          border: 1px solid #334155;
          border-radius: 18px;
          box-shadow: 0 20px 50px rgba(0,0,0,0.4);
          padding: 20px;
        }}
        h1 {{ font-size: 28px; margin: 0 0 16px; text-align: center; }}
        #map {{ height: 700px; width: 100%; border-radius: 12px; overflow: hidden; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h1>Drone Path Planning Map</h1>
        <div id="map"></div>
      </div>

      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <script>
        const startLatLng = [{start[1]:.6f}, {start[0]:.6f}];
        const endLatLng = [{goal[1]:.6f}, {goal[0]:.6f}];
        const map = L.map('map').setView([(startLatLng[0] + endLatLng[0]) / 2, (startLatLng[1] + endLatLng[1]) / 2], 6);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {{
          attribution: '&copy; OpenStreetMap contributors'
        }}).addTo(map);

        const route = [
          {"lat": {start[1]:.6f}, "lng": {start[0]:.6f}},
          {"lat": {goal[1]:.6f}, "lng": {goal[0]:.6f}}
        ];

        L.polyline(route, {{ color: '#2563eb', weight: 5, opacity: 0.9 }}).addTo(map);
        L.marker(startLatLng).addTo(map).bindPopup('Start');
        L.marker(endLatLng).addTo(map).bindPopup('End');
      </script>
    </body>
    </html>
    """

    return html


# -------------------------------
# Main Workflow
# -------------------------------
if __name__ == "__main__":
    print("Drone Path Planning Demo")
    print("Enter start and end points manually. You can use place names or coordinates.")

    default_start = (0, 0)
    default_goal = (20, 20)
    default_map_size = (30, 30)
    locations = load_locations()
    obstacles = []

    try:
        start_input = input(f"Start point [{default_start[0]},{default_start[1]}]: ").strip()
        start = parse_point(start_input, locations) if start_input else default_start

        goal_input = input(f"End point [{default_goal[0]},{default_goal[1]}]: ").strip()
        goal = parse_point(goal_input, locations) if goal_input else default_goal

        map_input = input(f"Map size as width,height [{default_map_size[0]},{default_map_size[1]}]: ").strip()
        if map_input:
            map_w, map_h = parse_point(map_input, locations)
            map_size = (float(map_w), float(map_h))
        else:
            map_size = default_map_size

        obstacle_choice = input("Add obstacles? [n]: ").strip().lower()
        if obstacle_choice in {"y", "yes", "true"}:
            obstacles_file = input("Obstacle dataset file [obstacles.json]: ").strip() or "obstacles.json"
            obstacles = load_obstacles(obstacles_file)
            if not obstacles:
                print(f"No obstacles loaded from {obstacles_file}. Showing empty map.")

    except ValueError as exc:
        print(f"Input error: {exc}")
        print("Using default values instead.")
        start = default_start
        goal = default_goal
        map_size = default_map_size
        locations = load_locations()
        obstacles = []

    planner = ImprovedInformedRRTStar(start, goal, map_size)
    global_path = planner.plan()

    pruned_path = prune_path(global_path)

    dwa = DWA(max_speed=1.0)
    safe_velocity = dwa.avoid_obstacle(pruned_path[0], obstacles=obstacles, goal=goal)
    smooth_path = bezier_smoothing(pruned_path)
    total_cost = cost_function(smooth_path)
    print("Final Path:", smooth_path)
    print("Safe Velocity:", safe_velocity)
    print("Total Cost:", total_cost)
    print(f"Loaded obstacles: {obstacles}")

    html_path = Path(__file__).with_name("drone_path.html")
    html_path.write_text(create_browser_view(smooth_path, start, goal, obstacles=obstacles, map_size=map_size), encoding="utf-8")
    print(f"Browser view saved to: {html_path.resolve()}")
    webbrowser.open_new_tab(f"file://{html_path.resolve()}")
    print("Opened in your default browser.")

