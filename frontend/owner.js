const ownerMap = L.map("owner-map").setView([17.3850, 78.4867], 8);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(ownerMap);

const fleetList = document.querySelector("#owner-fleet-list");
const syncState = document.querySelector("#sync-state");
const isLocalStaticServer = ["localhost", "127.0.0.1"].includes(window.location.hostname) && window.location.port !== "8000";
const apiBase = isLocalStaticServer ? "http://127.0.0.1:8000" : "";
let markerLayer = L.layerGroup().addTo(ownerMap);
const statusLabels = { planned: "Planned", in_transit: "In transit", reached_safely: "Reached safely", failed: "Attention required" };

function formatPosition(position) {
    return `${position.lat.toFixed(5)}, ${position.lon.toFixed(5)}`;
}

function renderFleet(drones) {
    markerLayer.clearLayers();
    document.querySelector("#active-count").textContent = drones.filter((drone) => drone.status === "in_transit" || drone.status === "planned").length;
    document.querySelector("#safe-count").textContent = drones.filter((drone) => drone.status === "reached_safely").length;
    document.querySelector("#attention-count").textContent = drones.filter((drone) => drone.status === "failed").length;
    if (!drones.length) {
        fleetList.innerHTML = '<p class="empty">No mission has been planned yet.</p>';
        return;
    }
    const bounds = [];
    fleetList.innerHTML = drones.map((drone) => {
        const position = [drone.position.lat, drone.position.lon];
        bounds.push(position);
        L.circleMarker(position, { radius: 9, color: "#102a43", fillColor: drone.status === "reached_safely" ? "#1f8a88" : drone.status === "failed" ? "#c94f37" : "#ef6c4d", fillOpacity: 1 }).bindPopup(`Drone ${drone.drone}: ${statusLabels[drone.status] || drone.status}`).addTo(markerLayer);
        return `<article class="owner-drone-card"><div class="owner-drone-number">${drone.drone}</div><div><strong>Drone ${drone.drone}</strong><span>${formatPosition(drone.position)}</span><small>Last update: ${new Date(drone.last_seen).toLocaleTimeString()}</small></div><b class="status-${drone.status}">${statusLabels[drone.status] || drone.status}</b></article>`;
    }).join("");
    if (bounds.length) ownerMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 12 });
}

async function refreshOwnerView() {
    try {
        const response = await fetch(`${apiBase}/api/drones`, { cache: "no-store" });
        if (!response.ok) throw new Error("Status unavailable");
        renderFleet(await response.json());
        syncState.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        syncState.textContent = "Backend offline";
    }
}

refreshOwnerView();
setInterval(refreshOwnerView, 3000);