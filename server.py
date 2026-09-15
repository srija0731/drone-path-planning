import json
import os
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from main import load_locations, load_obstacles, plan_drone_route, resolve_location


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MAX_DRONES = 100
DRONE_STATUS = {}


def current_time():
    return datetime.now(timezone.utc).isoformat()


class DroneRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/locations":
            locations = load_locations(ROOT / "locations.json")
            self.send_json(
                [
                    {"name": name, "lat": coordinates[0], "lon": coordinates[1]}
                    for name, coordinates in sorted(locations.items())
                ]
            )
            return

        if parsed.path == "/api/health":
            self.send_json({"status": "ok"})
            return

        if parsed.path == "/api/drones":
            self.send_json(list(DRONE_STATUS.values()))
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/plan", "/api/drones/status"}:
            self.send_json({"error": "Endpoint not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            if parsed.path == "/api/drones/status":
                drone_id = int(payload.get("drone"))
                if drone_id not in DRONE_STATUS:
                    raise ValueError(f"drone {drone_id} is not in the current mission")
                status = str(payload.get("status", "in_transit"))
                allowed = {"planned", "in_transit", "reached_safely", "failed"}
                if status not in allowed:
                    raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
                record = DRONE_STATUS[drone_id]
                record["status"] = status
                record["reached"] = status == "reached_safely"
                record["safe"] = status == "reached_safely"
                record["last_seen"] = current_time()
                if "lat" in payload and "lon" in payload:
                    record["position"] = {"lat": float(payload["lat"]), "lon": float(payload["lon"])}
                self.send_json(record)
                return

            locations = load_locations(ROOT / "locations.json")
            obstacles = load_obstacles(ROOT / "obstacles.json")
            missions = payload.get("drones")
            if missions is None:
                missions = [{"start": payload.get("start"), "goal": payload.get("goal")}]
            if not isinstance(missions, list) or not missions:
                raise ValueError("at least one drone mission is required")
            if len(missions) > MAX_DRONES:
                raise ValueError(f"a maximum of {MAX_DRONES} drones can be planned at once")

            routes = []
            DRONE_STATUS.clear()
            for index, mission in enumerate(missions, start=1):
                if not isinstance(mission, dict):
                    raise ValueError(f"drone {index} must contain start and goal")
                start_input = str(mission.get("start") or "").strip()
                goal_input = str(mission.get("goal") or "").strip()
                if not start_input or not goal_input:
                    raise ValueError(f"drone {index}: enter both launch point and destination")
                start = resolve_location(start_input, locations)
                goal = resolve_location(goal_input, locations)
                path, cost = plan_drone_route(start, goal, obstacles=obstacles)
                routes.append(
                    {
                        "drone": index,
                        "start": {"lat": start[0], "lon": start[1]},
                        "goal": {"lat": goal[0], "lon": goal[1]},
                        "path": [{"lat": point[0], "lon": point[1]} for point in path],
                        "cost": cost,
                    }
                )
                DRONE_STATUS[index] = {
                    "drone": index,
                    "status": "planned",
                    "reached": False,
                    "safe": True,
                    "position": {"lat": start[0], "lon": start[1]},
                    "last_seen": current_time(),
                }
            self.send_json({"routes": routes})
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            self.send_json({"error": str(exc)}, status=400)
        except ConnectionAbortedError:
            pass

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = "/api/drones/"
        if not parsed.path.startswith(prefix):
            self.send_json({"error": "Endpoint not found"}, status=404)
            return
        try:
            drone_id = int(parsed.path.removeprefix(prefix))
            removed = DRONE_STATUS.pop(drone_id, None)
            if removed is None:
                self.send_json({"error": f"drone {drone_id} is not in the current mission"}, status=404)
                return
            self.send_json({"removed": drone_id})
        except ValueError:
            self.send_json({"error": "invalid drone id"}, status=400)


def run_server(host=None, port=None):
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = int(port or os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DroneRequestHandler)
    public_url = f"http://{host}:{port}"
    print(f"Drone Path Planning: {public_url}")
    print("Press Ctrl+C to stop the server.")
    if os.environ.get("OPEN_BROWSER", "true").lower() in {"1", "true", "yes"}:
        webbrowser.open_new_tab(public_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


def plan_gps_route(start, goal):
    midpoint = ((start[0] + goal[0]) / 2, (start[1] + goal[1]) / 2)
    return [start, midpoint, goal]


if __name__ == "__main__":
    run_server()
