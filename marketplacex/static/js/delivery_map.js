(function () {
  var box = document.getElementById("track");
  if (!box || !window.L) return;
  var d = box.dataset;
  var mode = d.mode, status = d.status, stepMs = Number(d.step) * 1000;
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var line = document.getElementById("track-line");
  var note = document.getElementById("track-note");
  var FALLBACK = [21.0285, 105.8542]; // Hoan Kiem, Hanoi (the demo customer's ward)

  // Naive UTC timestamps from the server, compared against the server's own clock.
  function ms(iso) { return iso ? Date.parse(iso.slice(0, 23) + "Z") : null; }
  var skew = ms(d.now) - Date.now();
  var shippedAt = ms(d.shipped);

  // Trip shape per courier, in km east (x) / north (y) of the start, ending at home (0, 0).
  var KM = { vinbot: 1.2, vinno: 2.5, vinfast: 4, vindrone: 3, vinsubmarine: 6, vinair: 12 };
  function shape(sx, sy) {
    var pts = [], i, t;
    if (mode === "vindrone") return [[sx, sy], [0, 0]];
    if (mode === "vinair") {
      for (i = 0; i <= 24; i++) { t = i / 24; pts.push([sx * (1 - t) - sy * .35 * t * (1 - t) * 4, sy * (1 - t) + sx * .35 * t * (1 - t) * 4]); }
      return pts;
    }
    if (mode === "vinsubmarine") {
      for (i = 0; i <= 40; i++) { t = i / 40; var w = Math.sin(t * Math.PI * 5) * .45 * (1 - t); pts.push([sx * (1 - t) - sy / KM[mode] * w, sy * (1 - t) + sx / KM[mode] * w]); }
      return pts;
    }
    return [[sx, sy], [sx, sy * .45], [sx * .3, sy * .45], [sx * .3, 0], [0, 0]];
  }

  var map = L.map("track-map", { zoomControl: false, scrollWheelZoom: false, attributionControl: true });
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  function pin(cls, icon, size) {
    return L.divIcon({ className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      html: '<span class="pin ' + cls + '"><i class="bi bi-' + icon + '"></i></span>' });
  }
  var route = [], lengths = [], total = 0;
  var full = L.polyline([], { color: "#1f4d3a", opacity: .55, weight: 4, dashArray: "1 9", lineCap: "round" }).addTo(map);
  var done = L.polyline([], { color: "#1f4d3a", weight: 5, lineCap: "round" }).addTo(map);
  var depot = L.marker(FALLBACK, { icon: pin("pin-depot", "shop", 30), keyboard: false, title: "MarketplaceX warehouse" }).addTo(map);
  var home = L.marker(FALLBACK, { icon: pin("pin-home", "house-heart-fill", 40), keyboard: false, title: "Your address", zIndexOffset: 500 }).addTo(map);
  var courier = L.marker(FALLBACK, { icon: pin("pin-courier pin-" + mode, d.icon, 44), keyboard: false, title: d.name, zIndexOffset: 1000 }).addTo(map);

  function place(at) {
    var lat = at[0], kmLng = 111.32 * Math.cos(lat * Math.PI / 180);
    var bearing = (Number(d.order) * 137.5) % 360 * Math.PI / 180, r = KM[mode] || 4;
    route = shape(Math.sin(bearing) * r, Math.cos(bearing) * r).map(function (p) {
      return [lat + p[1] / 110.57, at[1] + p[0] / kmLng];
    });
    lengths = [0]; total = 0;
    for (var i = 1; i < route.length; i++) { total += map.distance(route[i - 1], route[i]); lengths.push(total); }
    full.setLatLngs(route);
    home.setLatLng(at);
    depot.setLatLng(route[0]);
    map.fitBounds(L.latLngBounds(route), { padding: [48, 48], animate: false });
  }

  function along(f) {
    var target = f * total, i = 1;
    while (i < lengths.length - 1 && lengths[i] < target) i++;
    var a = route[i - 1], b = route[i], seg = (lengths[i] - lengths[i - 1]) || 1, t = (target - lengths[i - 1]) / seg;
    t = Math.max(0, Math.min(1, t));
    return { at: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], i: i, heading: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }

  var shown = 0;
  function goal() {
    if (status === "delivered") return 1;
    if (status !== "shipped" || !shippedAt) return 0;
    return Math.max(0, Math.min(.97, (Date.now() + skew - shippedAt) / stepMs));
  }
  function words(f) {
    if (status === "cancelled") return "Order cancelled. The courier stayed at the warehouse.";
    if (status === "delivered") return "Delivered to your door.";
    if (status !== "shipped") return "Packing your order at the MarketplaceX warehouse.";
    var left = (1 - f) * total / 1000;
    var secs = Math.max(1, Math.round((1 - f) * stepMs / 1000));
    return d.name + " is " + left.toFixed(1) + " km away · arriving in about " + secs + " s";
  }
  var wrote = 0;
  function frame(now) {
    var g = goal();
    shown = still ? g : shown + (g - shown) * .12;
    if (Math.abs(g - shown) < .0005) shown = g;
    if (route.length) {
      var p = along(shown);
      courier.setLatLng(p.at);
      done.setLatLngs(route.slice(0, p.i).concat([p.at]));
      var el = courier.getElement();
      // The plane glyph's nose points north and heading is a compass bearing.
      if (el && mode === "vinair") el.firstChild.firstChild.style.transform = "rotate(" + p.heading * 180 / Math.PI + "deg)";
      box.classList.toggle("is-moving", status === "shipped");
      if (now - wrote > 500) { line.textContent = words(shown); wrote = now; }
    }
    requestAnimationFrame(frame);
  }

  place(FALLBACK);
  requestAnimationFrame(frame);
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(function (pos) {
      place([pos.coords.latitude, pos.coords.longitude]);
      note.textContent = "Courier position is simulated. Pinned to your current location.";
    }, function () {
      note.textContent = "Courier position is simulated. Showing Hoan Kiem, Hanoi because location access is off.";
    }, { timeout: 8000, maximumAge: 600000 });
  }

  document.addEventListener("order:progress", function (e) {
    var p = e.detail, s = p.steps.filter(function (x) { return x.name === "shipped"; })[0];
    status = p.status;
    if (s && s.at) shippedAt = ms(s.at);
  });
})();
