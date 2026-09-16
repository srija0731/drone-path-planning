"""Small dependency-free client for a drone or flight-controller gateway."""

import argparse
import json
import os
from urllib.request import Request, urlopen


def send_telemetry(server_url, drone, latitude, longitude, status="in_transit", battery=None, flight_mode=None, device=None, token=None):
    payload = {
        "drone": drone,
        "status": status,
        "lat": latitude,
        "lon": longitude,
    }
    if battery is not None:
        payload["battery"] = battery
    if flight_mode:
        payload["flight_mode"] = flight_mode
    if device:
        payload["device"] = device

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"{server_url.rstrip('/')}/api/telemetry",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Send one drone telemetry heartbeat")
    parser.add_argument("--server", default=os.environ.get("DRONE_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--drone", type=int, required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--status", default="in_transit", choices=("planned", "in_transit", "reached_safely", "failed"))
    parser.add_argument("--battery", type=float)
    parser.add_argument("--flight-mode")
    parser.add_argument("--device")
    parser.add_argument("--token", default=os.environ.get("DRONE_API_TOKEN"))
    arguments = parser.parse_args()
    result = send_telemetry(
        arguments.server,
        arguments.drone,
        arguments.lat,
        arguments.lon,
        arguments.status,
        arguments.battery,
        arguments.flight_mode,
        arguments.device,
        arguments.token,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
