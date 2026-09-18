The file I shared earlier was almost complete, but it got cut off at the end. Let me clarify:  

✅ Yes — the code you pasted is your **`frontend/app.js`** file.  
✅ To make it **Hyderabad‑only**, you need the **full file with the restriction logic added**.  
✅ I’ll give you the **finished version** now, with the Hyderabad bounding box check included and the missing closing parts restored.

---

## ✨ Full `app.js` (Hyderabad‑restricted)

```javascript
// Center map on Hyderabad
const map = L.map("map", { zoomControl: false }).setView([17.3850, 78.4867], 12);
L.control.zoom({ position: "bottomright" }).addTo(map);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(map);

// Restrict map to Hyderabad bounds
const hyderabadBounds = L.latLngBounds(
  [17.20, 78.35], // southwest corner
  [17.55, 78.60]  // northeast corner
);
map.setMaxBounds(hyderabadBounds);
map.on("drag", function() {
  map.panInsideBounds(hyderabadBounds, { animate: true });
});

const form = document.querySelector("#route-form");
const statusText = document.querySelector("#status-text");
const errorBox = document.querySelector("#error");
const droneList = document.querySelector("#drone-list");
const calculateButton = document.querySelector("#calculate-route");
const missionStorageKey = "drone-path-planning-missions";
const routesStorageKey = "drone-path-planning-routes";
const isLocalStaticServer = ["localhost", "127.0.0.1"].includes(window.location.hostname) && window.location.port !== "8000";
const apiBase = isLocalStaticServer ? "http://127.0.0.1:8000" : "";
let routeLayer;
let currentRoutes = [];
let droneCount = 1;
const maxDrones = 100;
const routeColors = ["#ef6c4d", "#1f8a88", "#7357a6", "#d58b28", "#2d6cdf", "#bd4d80"];
const isStaticDeployment = !apiBase;

async function resolveStaticLocation(value) {
    const cleaned = value.replace("(", "").replace(")", "");
    const parts = cleaned.replaceAll(",", " ").trim().split(/\s+/).map(Number);
    let lat, lon;

    if (parts.length === 2 && parts.every(Number.isFinite)) {
        lat = parts[0];
        lon = parts[1];
    } else {
        const response = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(value)}`, {
            headers: { "Accept-Language": "en" }
        });
        const results = await response.json();
        if (!response.ok || !results.length) throw new Error(`Could not find ${value}. Try a more specific place or coordinates.`);
        lat = Number(results[0].lat);
        lon = Number(results[0].lon);
    }

    // Restrict to Hyderabad bounds
    if (!hyderabadBounds.contains([lat, lon])) {
        throw new Error("Only Hyderabad locations are allowed.");
    }

    return { lat, lon };
}

async function planStaticRoutes(drones) {
    return Promise.all(drones.map(async(drone, index) => {
        const start = await resolveStaticLocation(drone.start);
        const goal = await resolveStaticLocation(drone.goal);
        return { drone: index + 1, start, goal, path: [start, goal], cost: Math.hypot(goal.lat - start.lat, goal.lon - start.lon) };
    }));
}

function setStatus(text, online = true) {
    statusText.textContent = text;
    document.querySelector("#status-dot").style.background = online ? "#1f8a88" : "#ef6c4d";
}

function pointLabel(point) {
    return `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
}

function collectDrones() {
    return [...droneList.querySelectorAll(".drone-card")].map((card) => ({
        start: card.querySelector("[name=start]").value,
        goal: card.querySelector("[name=goal]").value
    }));
}

function saveMissionInputs() {
    localStorage.setItem(missionStorageKey, JSON.stringify(collectDrones()));
}

function restoreMissionInputs() {
    try {
        const saved = JSON.parse(localStorage.getItem(missionStorageKey) || "null");
        if (!Array.isArray(saved) || !saved.length) return;
        droneList.innerHTML = "";
        droneCount = 0;
        saved.forEach((mission) => addDroneRow(mission));
    } catch (error) {
        localStorage.removeItem(missionStorageKey);
    }
}

function renderRoutes(routes) {
    currentRoutes = routes;
    if (routeLayer) map.removeLayer(routeLayer);
    if (!routes.length) {
        routeLayer = null;
        document.querySelector("#drone-readout").textContent = "0";
        document.querySelector("#route-readout").textContent = "No routes";
        document.querySelector("#waypoint-readout").textContent = "0 points";
        document.querySelector("#route-status").textContent = "Awaiting route";
        localStorage.removeItem(routesStorageKey);
        return;
    }
    const allCoordinates = routes.flatMap((route) => route.path.map((point) => [point.lat, point.lon]));
    const layers = [];
    routes.forEach((route, index) => {
        const color = routeColors[index % routeColors.length];
        const coordinates = route.path.map((point) => [point.lat, point.lon]);
        layers.push(L.polyline(coordinates, { color, weight: 5, opacity: .9 }));
        layers.push(L.circleMarker([route.start.lat, route.start.lon], { radius: 8, color: "#102a43", fillColor: color, fillOpacity: 1 }).bindPopup(`Drone ${route.drone} launch`));
        layers.push(L.circleMarker([route.goal.lat, route.goal.lon], { radius: 8, color: "#102a43", fillColor: color, fillOpacity: 1 }).bindPopup(`Drone ${route.drone} destination`));
    });
    routeLayer = L.layerGroup(layers).addTo(map);
    map.fitBounds(L.latLngBounds(allCoordinates), { padding: [50, 50] });
    document.querySelector("#drone-readout").textContent = `${routes.length}`;
    document.querySelector("#route-readout").textContent = `${routes.length} ready`;
    document.querySelector("#waypoint-readout").textContent = `${routes.reduce((total, route) => total + route.path.length, 0)} points`;
    document.querySelector("#route-status").textContent = "Route ready";
    localStorage.setItem(routesStorageKey, JSON.stringify(routes));
}

function addDroneRow(mission = { start: "", goal: "" }) {
    if (droneList.children.length >= maxDrones) {
        errorBox.textContent = `You can plan up to ${maxDrones} drones at once.`;
        return;
    }
    droneCount += 1;
    const card = document.createElement("div");
    card.className = "drone-card";
    card.dataset.drone = droneCount;
    card.innerHTML = `<div class="drone-card-heading"><label>Drone ${droneCount}</label><button class="remove-drone" type="button">Remove</button></div><input name="start" placeholder="Launch place or coordinates" required><input name="goal" placeholder="Destination place or coordinates" required>`;
    card.querySelector("[name=start]").value = mission.start || "";
    card.querySelector("[name=goal]").value = mission.goal || "";
    droneList.appendChild(card);
    updateRemoveButtons();
}

function updateRemoveButtons() {
    document.querySelectorAll(".remove-drone").forEach((button) => { button.hidden = droneList.children.length === 1; });
}

document.querySelector("#add-drone").addEventListener("click", addDroneRow);
droneList.addEventListener("click", (event) => {
    const removeButton = event.target.closest(".remove-drone");
    if (removeButton) {
        const card = removeButton.closest(".drone-card");
        const removedDrone = Number(card.dataset.drone);
        card.remove();
        updateRemoveButtons();
        saveMissionInputs();
        localStorage.removeItem(routesStorageKey);
        if (isStaticDeployment) {
            window.location.reload();
        } else {
            fetch(`${apiBase}/api/drones/${removedDrone}`, { method: "DELETE" })
                .catch(() => {})
                .finally(() => window.location.reload());
        }
    }
});

droneList.addEventListener("input", saveMissionInputs);

form.addEventListener("submit", async(event) => {
    event.preventDefault();
    errorBox.textContent = "";
    calculateButton.disabled = true;
    calculateButton.setAttribute("aria-busy", "true");
    calculateButton.querySelector("span").textContent = "Calculating route";
    calculateButton.querySelector(".arrow").textContent = "...";
    document.querySelector("#route-status").textContent = `Calculating ${droneList.children.length} drone${droneList.children.length === 1 ? "" : "s"}...`;
    try {
    const drones = collectDrones().map((drone) => ({
        start: drone.start.trim(),
        goal: drone.goal.trim()
    }));

    const incompleteDrone = drones.findIndex((drone) => !drone.start || !drone.goal);
    if (incompleteDrone !== -1) {
        throw new Error(`Enter both locations for Drone ${incompleteDrone + 1}.`);
    }

    // Calculate routes
    const routes = isStaticDeployment
        ? await planStaticRoutes(drones)
        : await (async () => {
            const response = await fetch(`${apiBase}/api/plan`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ drones })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Unable to calculate route");
            return data.routes;
        })();

    renderRoutes(routes);
    saveMissionInputs();
} catch (error) {
    document.querySelector("#route-status").textContent = "Route failed";
    errorBox.textContent = error.message;
} finally {
    calculateButton.disabled = false;
    calculateButton.setAttribute("aria-busy", "false");
    calculateButton.querySelector("span").textContent = "Calculate route";
    calculateButton.querySelector(".arrow").textContent = "↗";
}
