import json
import os
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from main import load_locations, load_obstacles, plan_drone_route, resolve_location


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MAX_DRONES = 100
MAX_REQUEST_BYTES = 1_000_000
TELEMETRY_TIMEOUT_SECONDS = 15
DRONE_API_TOKEN = os.environ.get("DRONE_API_TOKEN", "").strip()
DRONE_STATUS = {}
DRONE_STATUS_LOCK = Lock()


def current_time():
    return datetime.now(timezone.utc).isoformat()


def is_connected(record):
    if not record.get("connected", False):
        return False
    last_seen = record.get("last_seen")
    if not last_seen:
        return False
    try:
        timestamp = datetime.fromisoformat(last_seen)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - timestamp <= timedelta(seconds=TELEMETRY_TIMEOUT_SECONDS)


def authorize_telemetry(handler):
    if not DRONE_API_TOKEN:
        return True
    authorization = handler.headers.get("Authorization", "")
    return authorization == f"Bearer {DRONE_API_TOKEN}" or handler.headers.get("X-Drone-Token") == DRONE_API_TOKEN


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
            with DRONE_STATUS_LOCK:
                fleet = []
                for record in DRONE_STATUS.values():
                    item = record.copy()
                    item["connected"] = is_connected(record) if record.get("last_seen") else False
                    fleet.append(item)
            self.send_json(fleet)
            return

        if parsed.path == "/api/obstacles":
            obstacles = load_obstacles(ROOT / "obstacles.json")
            self.send_json(
                [
                    {"x": x, "y": y, "w": width, "h": height}
                    for x, y, width, height in obstacles
                ]
            )
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/plan", "/api/drones/status", "/api/telemetry"}:
            self.send_json({"error": "Endpoint not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body is too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")

            if parsed.path in {"/api/drones/status", "/api/telemetry"}:
                if parsed.path == "/api/telemetry" and not authorize_telemetry(self):
                    self.send_json({"error": "invalid telemetry credentials"}, status=401)
                    return
                drone_id = int(payload.get("drone"))
                status = str(payload.get("status", "in_transit"))
                allowed = {"planned", "in_transit", "reached_safely", "failed", "disconnected"}
                if status not in allowed:
                    raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
                with DRONE_STATUS_LOCK:
                    if drone_id not in DRONE_STATUS:
                        raise ValueError(f"drone {drone_id} is not in the current mission")
                    record = DRONE_STATUS[drone_id]
                    record["status"] = status
                    record["reached"] = status == "reached_safely"
                    record["safe"] = status == "reached_safely"
                    record["last_seen"] = current_time()
                    record["connected"] = True
                    if "battery" in payload:
                        battery = float(payload["battery"])
                        if not 0 <= battery <= 100:
                            raise ValueError("battery must be between 0 and 100")
                        record["battery"] = battery
                    if "flight_mode" in payload:
                        record["flight_mode"] = str(payload["flight_mode"])[:40]
                    if "device" in payload:
                        record["device"] = str(payload["device"])[:80]
                    if "lat" in payload and "lon" in payload:
                        latitude = float(payload["lat"])
                        longitude = float(payload["lon"])
                        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                            raise ValueError("latitude or longitude is out of range")
                        record["position"] = {"lat": latitude, "lon": longitude}
                    record = record.copy()
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
            planned_status = {}
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
                planned_status[index] = {
                    "drone": index,
                    "status": "planned",
                    "reached": False,
                    "safe": True,
                    "connected": False,
                    "battery": None,
                    "flight_mode": "grounded",
                    "device": None,
                    "position": {"lat": start[0], "lon": start[1]},
                    "last_seen": current_time(),
                }
            with DRONE_STATUS_LOCK:
                DRONE_STATUS.clear()
                DRONE_STATUS.update(planned_status)
            self.send_json({"routes": routes})
        except (ValueError, json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
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
            with DRONE_STATUS_LOCK:
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
