const map = L.map('map').setView([46.056946, 14.505751], 11);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19
}).addTo(map);

let currentLines = [];
let markers = [];
let pathLayers = [];

function clearMarkers() {
  markers.forEach(m => map.removeLayer(m));
  markers = [];
}

function clearLines() {
  currentLines.forEach(line => map.removeLayer(line));
  currentLines = [];
  pathLayers.forEach(p => map.removeLayer(p.layer));
  pathLayers = [];
}

function resetMap() {
  document.getElementById('start').value = '';
  document.getElementById('end').value = '';
  clearMarkers();
  clearLines();
  document.getElementById("route-info").style.display = 'none';
  document.getElementById("legend").style.display = 'none';
}

map.on('click', function (e) {
  const latlngStr = `${e.latlng.lat.toFixed(6)} ${e.latlng.lng.toFixed(6)}`;
  const startField = document.getElementById('start');
  const endField = document.getElementById('end');

  if (!startField.value) {
    startField.value = latlngStr;
    const marker = L.marker(e.latlng).addTo(map).bindPopup("Start").openPopup();
    markers.push(marker);
  } else if (!endField.value) {
    endField.value = latlngStr;
    const marker = L.marker(e.latlng).addTo(map).bindPopup("End").openPopup();
    markers.push(marker);
  } else {
    alert("Both points already selected. Press Reset to start over.");
  }
});

async function drawRoute(routingMode = "vegetation") {
  const startStr = document.getElementById('start').value.trim();
  const endStr = document.getElementById('end').value.trim();

  if (!startStr || !endStr) {
    alert("Please enter both start and end coordinates.");
    return;
  }

  const [startLat, startLon] = startStr.split(" ").map(parseFloat);
  const [endLat, endLon] = endStr.split(" ").map(parseFloat);

  if (isNaN(startLat) || isNaN(startLon) || isNaN(endLat) || isNaN(endLon)) {
    alert("Invalid coordinates. Use format: lat lon");
    return;
  }

  try {
    const res = await fetch("http://localhost:8000/api/get_paths/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin_coords: [startLat, startLon],
        destination_coords: [endLat, endLon],
        commute_mode: "walk",
        routing_mode: routingMode
      })
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    const colors = ['#c01ce6', '#1c51e6', '#e6511c'];
    const data = await res.json();
    const parsed = JSON.parse(data);

    clearMarkers();
    clearLines();

    const startMarker = L.marker([startLat, startLon]).addTo(map).bindPopup("Start").openPopup();
    const endMarker = L.marker([endLat, endLon]).addTo(map).bindPopup("End");
    markers.push(startMarker, endMarker);

    const legendList = document.getElementById("legend-list");
    legendList.innerHTML = "";
    pathLayers = [];

    parsed.features.forEach((feature, index) => {
      const color = colors[index % colors.length];
      const durationMin = (feature.properties.length_m / 1.4 / 60).toFixed(1);

      const layer = L.geoJSON(feature, {
        style: {
          color: color,
          weight: 4,
          opacity: 0.7
        }
      }).bindPopup(`Path #${feature.properties.path_num}<br>Length: ${feature.properties.length_m.toFixed(1)} m`)
        .addTo(map);

      pathLayers.push({ layer, color });

      const li = document.createElement("li");
      li.innerHTML = `Path #${feature.properties.path_num}<br>${feature.properties.length_m.toFixed(1)} m • ${durationMin} min`;
      li.style.borderLeftColor = color;
      li.onclick = () => highlightPath(index);
      legendList.appendChild(li);
    });

    document.getElementById("legend").style.display = 'block';

  } catch (err) {
    alert("Failed to fetch route: " + err.message);
    console.error(err);
  }
}

function highlightPath(index) {
  pathLayers.forEach((p, i) => {
    p.layer.setStyle({
      weight: i === index ? 8 : 4,
      opacity: i === index ? 1.0 : 0.7
    });
  });
}
