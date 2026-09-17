# Drone Path Planning

This project is a browser-based drone route planner. A Python backend serves a frontend map, accepts place names or coordinates entered at runtime, and draws the calculated route on live OpenStreetMap tiles.

## Project files

- [main.py](main.py) — entry point and logic
- [server.py](server.py) — backend HTTP server and route API
- [frontend/index.html](frontend/index.html) — browser interface
- [frontend/app.js](frontend/app.js) — map interaction and API client
- [frontend/styles.css](frontend/styles.css) — responsive visual styling
- [obstacles.json](obstacles.json) — sample obstacle dataset
- [locations.json](locations.json) — optional empty dataset placeholder
- [test_main.py](test_main.py) and [test_server.py](test_server.py) — validation tests
- [requirements.txt](requirements.txt) — dependency list

## How to run

From the project folder, start the backend:

```powershell
py server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Keep the terminal running while using the map. Stop the server with `Ctrl+C`.

### Publish it publicly with Render

1. Push this project to a GitHub repository.
2. Create an account at [Render](https://render.com).
3. Choose **New > Blueprint** and connect the GitHub repository.
4. Render will read [render.yaml](render.yaml), build the app, and give you a public HTTPS URL.
5. Open that Render URL. Do not use Go Live for the public deployment; Go Live only serves static frontend files.

The deployed owner page is available at your public URL followed by `/owner.html`.

### Free GitHub Pages demo

The frontend is also published without a payment card at:

<https://srija0731.github.io/drone-path-planning/>

The GitHub Pages version runs route drawing and geocoding in the browser. Its owner page reads planned routes from the same browser, but it does not provide shared live telemetry or the backend obstacle-avoidance planner. Use the Python backend deployment for those features.

The owner monitoring page is available at [http://127.0.0.1:8000/owner.html](http://127.0.0.1:8000/owner.html). It polls the latest drone positions and shows `Planned`, `In transit`, `Reached safely`, or `Attention required`.

If `python` is not recognized on your system, use:

```powershell
py main.py
```

## Inputs

In the browser, add one or more drones. For each drone, enter any place in real time, such as `Hyderabad, Telangana`, `Warangal, Telangana`, or `Rajiv Gandhi International Airport`. You can also enter GPS coordinates such as `17.3850, 78.4867`. The backend sends place names to Nominatim/OpenStreetMap, so internet access is required for live lookup. No place names are hardcoded.

Use **Add another drone** to plan multiple routes in one operation. The API and browser support up to 100 drones per calculation and display each route in a different color.

An external drone or GPS device can report progress with:

```json
POST /api/drones/status
{"drone": 1, "status": "reached_safely", "lat": 17.9689, "lon": 79.5941}
```

For a real drone gateway, set a shared token before starting the server:

```powershell
$env:DRONE_API_TOKEN = "replace-with-a-long-random-token"
py server.py
```

Send live telemetry to `POST /api/telemetry` using the `Authorization: Bearer <token>` header. The request can include `drone`, `status`, `lat`, `lon`, `battery`, `flight_mode`, and `device`. A drone is shown as connected while it sends telemetry at least once every 15 seconds. The reusable standard-library client is [telemetry_client.py](telemetry_client.py).

Accepted formats:

- `x,y`
- `x y`

## Dataset format

The obstacle file is JSON. Example:

```json
[
  {"x": 6, "y": 8, "w": 3, "h": 3},
  {"x": 11, "y": 4, "w": 2, "h": 7}
]
```

This file is optional. If it is missing, the program still runs with no obstacles.

### Optional location file

[locations.json](locations.json) is intentionally empty. The app does not require a dataset because places are entered and resolved at runtime. If you later add static shortcuts, use this format:

```json
[
  {"name": "home", "lat": 12.9716, "lon": 77.5946},
  {"name": "airport", "lat": 13.1999, "lon": 77.7063}
]
```

You can add your own named GPS points. The backend also uses Nominatim to geocode unknown place names when internet access is available.

## Output

Run all tests with:

```powershell
py -m unittest -q
```

The older `py main.py` command remains available for the original terminal-generated HTML demo; `py server.py` is the full frontend/backend application.
