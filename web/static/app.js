/**
 * SailMon – Frontend Application
 * ================================
 * Map-first single page app.
 *
 * Layout:  Header (wind/speed + trend) | Full-screen map | Right nav panel
 * Data:    WebSocket /ws  (JSON, ~1 Hz)
 * Map:     Leaflet + OSM base + OpenSeaMap overlay
 * Sessions: Accessible via hamburger menu (≡)
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  wind:      { kn: null, avg10: null, avg1h: null, ok: false },
  gps:       { lat: null, lon: null, sog: null, hdg: 0, fix: 0, sats: 0, ok: false },
  trip_id:   null,
  connected: false,
};

// ── Trend tracking (30-second rolling window) ─────────────────────────────────
const TREND_WINDOW    = 30;    // seconds
const TREND_THRESHOLD = 0.5;  // knots

const trendBuf = { wind: [], speed: [] };

function pushTrend(buf, value) {
  const now = Date.now() / 1000;
  if (value != null) buf.push({ t: now, v: value });
  const cutoff = now - TREND_WINDOW;
  while (buf.length > 0 && buf[0].t < cutoff) buf.shift();
}

function calcTrend(buf, current) {
  if (buf.length < 3 || current == null) return 0;
  const oldest = buf[0].v;
  const delta  = current - oldest;
  if (delta >  TREND_THRESHOLD) return  1;
  if (delta < -TREND_THRESHOLD) return -1;
  return 0;
}

function trendArrow(t) {
  return t > 0 ? '↑' : t < 0 ? '↓' : '→';
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let ws, wsReconnectTimer;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    state.connected = true;
  };

  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    Object.assign(state.wind, d.wind);
    Object.assign(state.gps,  d.gps);

    // Track trip transitions
    if (d.trip_id && d.trip_id !== state.trip_id) {
      // New trip started – reset track and load initial positions
      liveTrackCoords = [];
      if (livePolyline) livePolyline.setLatLngs([]);
      loadInitialTrack(d.trip_id);
    }
    state.trip_id = d.trip_id;

    updateHeader();
    updateMapLive();
  };

  ws.onclose = ws.onerror = () => {
    state.connected = false;
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = setTimeout(connectWS, 3000);
  };
}

connectWS();

// ── Header ────────────────────────────────────────────────────────────────────
const elWindSpeed  = document.getElementById('wind-speed');
const elBoatSpeed  = document.getElementById('boat-speed');
const elWindTrend  = document.getElementById('wind-trend');
const elSpeedTrend = document.getElementById('speed-trend');

function updateHeader() {
  const w = state.wind;
  const g = state.gps;

  pushTrend(trendBuf.wind,  w.kn);
  pushTrend(trendBuf.speed, g.sog);

  const wt = calcTrend(trendBuf.wind,  w.kn);
  const st = calcTrend(trendBuf.speed, g.sog);

  elWindSpeed.textContent  = w.ok && w.kn  != null ? w.kn.toFixed(1)  : '-.-';
  elBoatSpeed.textContent  = g.ok && g.sog != null ? g.sog.toFixed(1) : '-.-';
  elWindTrend.textContent  = trendArrow(wt);
  elSpeedTrend.textContent = trendArrow(st);
}

// ── Live Map ──────────────────────────────────────────────────────────────────
let liveMap, livePolyline, liveMarker;
let liveTrackCoords = [];
let mapFollowing    = true;

const MAP_DEFAULT_ZOOM = 17;
const PAN_STEP_PX      = 100;   // pixels per pan-button press

function initMap() {
  liveMap = L.map('map', {
    center:         [52.52, 13.40],
    zoom:           MAP_DEFAULT_ZOOM,
    zoomControl:    false,   // we provide our own zoom buttons
    attributionControl: true,
  });

  // OSM base layer via local tile proxy (offline-capable)
  L.tileLayer('/tiles/osm/{z}/{x}/{y}.png', {
    maxZoom:     19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(liveMap);

  // OpenSeaMap nautical overlay (seamark layer)
  L.tileLayer('/tiles/opensea/{z}/{x}/{y}.png', {
    maxZoom:     18,
    opacity:     1.0,
    attribution: '© <a href="https://www.openseamap.org">OpenSeaMap</a>',
  }).addTo(liveMap);

  // Track polyline – red dashed line
  livePolyline = L.polyline([], {
    color:       '#e00000',
    weight:      2,
    opacity:     0.85,
    dashArray:   '6, 8',
    lineJoin:    'round',
  }).addTo(liveMap);

  // Boat marker – red filled arrow (SVG icon, rotates to heading)
  liveMarker = L.marker([52.52, 13.40], {
    icon: L.divIcon({
      html:       '<svg class="boat-svg" viewBox="0 0 20 30" xmlns="http://www.w3.org/2000/svg"><polygon points="10,0 20,30 10,22 0,30" fill="#e00000"/></svg>',
      className:  'boat-icon',
      iconSize:   [20, 30],
      iconAnchor: [10, 22],  // anchor at the back of the arrow
    }),
  }).addTo(liveMap);

  // Stop auto-follow when user manually pans
  liveMap.on('dragstart', () => { mapFollowing = false; updateFollowBtn(); });

  // Update coordinate display on map move
  liveMap.on('mousemove', (e) => {
    document.getElementById('coords').textContent =
      e.latlng.lat.toFixed(5) + ', ' + e.latlng.lng.toFixed(5);
  });
}

function updateMapLive() {
  if (!liveMap) return;

  const g = state.gps;
  if (!g.ok || g.lat == null) return;

  const ll = [g.lat, g.lon];

  // Update coordinate display with GPS position
  document.getElementById('coords').textContent =
    g.lat.toFixed(5) + ', ' + g.lon.toFixed(5);

  // Rotate boat marker to heading
  const el = liveMarker.getElement();
  if (el) {
    const svg = el.querySelector('.boat-svg');
    if (svg) svg.style.transform = `rotate(${g.hdg || 0}deg)`;
  }

  liveMarker.setLatLng(ll);
  liveTrackCoords.push(ll);
  livePolyline.setLatLngs(liveTrackCoords);

  if (mapFollowing) {
    liveMap.panTo(ll, { animate: true, duration: 0.5 });
  }
}

async function loadInitialTrack(tripId) {
  // When a trip is already active and the browser connects mid-trip,
  // load the stored track points so the full path is shown.
  try {
    const res  = await fetch(`/api/trips/${tripId}`);
    const data = await res.json();
    if (data.track && data.track.length > 0) {
      liveTrackCoords = data.track.map(p => [p.latitude, p.longitude]);
      if (livePolyline) livePolyline.setLatLngs(liveTrackCoords);
    }
  } catch (_) { /* no-op if offline */ }
}

// ── Map navigation buttons ────────────────────────────────────────────────────

function updateFollowBtn() {
  const btn = document.getElementById('btn-follow');
  btn.classList.toggle('active', mapFollowing);
}

document.getElementById('btn-zoom-in').addEventListener('click', () => {
  liveMap.zoomIn();
});

document.getElementById('btn-zoom-out').addEventListener('click', () => {
  liveMap.zoomOut();
});

document.getElementById('btn-pan-up').addEventListener('click', () => {
  liveMap.panBy([0, -PAN_STEP_PX]);
  mapFollowing = false; updateFollowBtn();
});

document.getElementById('btn-pan-down').addEventListener('click', () => {
  liveMap.panBy([0, PAN_STEP_PX]);
  mapFollowing = false; updateFollowBtn();
});

document.getElementById('btn-pan-left').addEventListener('click', () => {
  liveMap.panBy([-PAN_STEP_PX, 0]);
  mapFollowing = false; updateFollowBtn();
});

document.getElementById('btn-pan-right').addEventListener('click', () => {
  liveMap.panBy([PAN_STEP_PX, 0]);
  mapFollowing = false; updateFollowBtn();
});

document.getElementById('btn-pan-reset').addEventListener('click', () => {
  mapFollowing = true;
  updateFollowBtn();
  if (state.gps.lat != null) {
    liveMap.setView([state.gps.lat, state.gps.lon], MAP_DEFAULT_ZOOM);
  }
});

document.getElementById('btn-follow').addEventListener('click', () => {
  mapFollowing = true;
  updateFollowBtn();
  if (state.gps.lat != null) {
    liveMap.panTo([state.gps.lat, state.gps.lon], { animate: true });
  }
});

document.getElementById('btn-north').addEventListener('click', () => {
  // Reset bearing to north (Leaflet doesn't support bearing natively,
  // but this re-centres the view cleanly when using the default projection)
  liveMap.setBearing ? liveMap.setBearing(0) : null;
});

// ── Sessions overlay ──────────────────────────────────────────────────────────
const sessionsOverlay = document.getElementById('sessions-overlay');

document.getElementById('menu-btn').addEventListener('click', () => {
  sessionsOverlay.classList.remove('hidden');
  loadSessions();
});

document.getElementById('sessions-close').addEventListener('click', () => {
  sessionsOverlay.classList.add('hidden');
});

sessionsOverlay.addEventListener('click', (e) => {
  if (e.target === sessionsOverlay) sessionsOverlay.classList.add('hidden');
});

async function loadSessions() {
  const list = document.getElementById('session-list');
  list.innerHTML = '<li class="session-empty">Lade…</li>';

  let trips;
  try {
    trips = await (await fetch('/api/trips')).json();
  } catch (_) {
    list.innerHTML = '<li class="session-empty">Fehler beim Laden.</li>';
    return;
  }

  if (!trips.length) {
    list.innerHTML = '<li class="session-empty">Keine Sessions vorhanden.</li>';
    return;
  }

  // Group by date (YYYY-MM-DD)
  const byDate = {};
  trips.forEach(t => {
    const d = t.start_time ? t.start_time.slice(0, 10) : 'unbekannt';
    (byDate[d] = byDate[d] || []).push(t);
  });

  const datesSorted = Object.keys(byDate).sort((a, b) => b.localeCompare(a));

  list.innerHTML = datesSorted.map(date => {
    const label = new Date(date + 'T12:00:00').toLocaleDateString('de-DE', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
    const items = byDate[date].map(t => {
      const active = t.id === state.trip_id;
      const dur = t.end_time
        ? fmtDurFromISO(t.start_time, t.end_time)
        : active ? '● Aktiv' : '–';
      return `
        <li class="session-item ${active ? 'active-session' : ''}" data-id="${t.id}">
          <span class="si-name">${esc(t.name)}</span>
          ${active ? '<span class="si-badge">AKTIV</span>' : ''}
          <span class="si-stats">
            ${(t.distance_nm||0).toFixed(1)} NM &nbsp;·&nbsp;
            Max Wind ${(t.max_wind_kn||0).toFixed(1)} kn &nbsp;·&nbsp;
            ${dur}
          </span>
        </li>`;
    }).join('');
    return `<li class="session-date-header">${label}</li>${items}`;
  }).join('');

  list.querySelectorAll('.session-item').forEach(el => {
    el.addEventListener('click', () => {
      sessionsOverlay.classList.add('hidden');
      openTripModal(el.dataset.id);
    });
  });
}

// ── Trip detail modal ─────────────────────────────────────────────────────────
let modalMap = null;

async function openTripModal(tripId) {
  const data = await (await fetch(`/api/trips/${tripId}`)).json();
  const trip = data.trip;

  document.getElementById('modal-title').textContent = trip.name;
  document.getElementById('ms-dist').textContent  = (trip.distance_nm  || 0).toFixed(2);
  document.getElementById('ms-wind').textContent  = (trip.max_wind_kn  || 0).toFixed(1);
  document.getElementById('ms-speed').textContent = (trip.max_speed_kn || 0).toFixed(1);
  document.getElementById('ms-dur').textContent   =
    trip.end_time ? fmtDurFromISO(trip.start_time, trip.end_time) : '–';

  document.getElementById('modal-gpx').href = `/api/trips/${tripId}/gpx`;
  document.getElementById('trip-modal').classList.remove('hidden');

  setTimeout(() => {
    if (modalMap) { modalMap.remove(); modalMap = null; }
    modalMap = L.map('modal-map', { zoomControl: false, attributionControl: false });

    L.tileLayer('/tiles/osm/{z}/{x}/{y}.png',     { maxZoom: 19 }).addTo(modalMap);
    L.tileLayer('/tiles/opensea/{z}/{x}/{y}.png', { maxZoom: 18, opacity: 1.0 }).addTo(modalMap);

    const track = data.track;
    if (track && track.length > 0) {
      const coords = track.map(p => [p.latitude, p.longitude]);
      // Speed-coloured track
      for (let i = 0; i < coords.length - 1; i++) {
        L.polyline([coords[i], coords[i + 1]], {
          color:   speedColor(track[i].speed_kn || 0, 0, 8),
          weight:  3,
          opacity: 0.9,
        }).addTo(modalMap);
      }
      L.circleMarker(coords[0],               { radius: 6, color: '#00e5b0', fillColor: '#00e5b0', fillOpacity: 1 }).addTo(modalMap);
      L.circleMarker(coords[coords.length-1], { radius: 6, color: '#e00000', fillColor: '#e00000', fillOpacity: 1 }).addTo(modalMap);
      modalMap.fitBounds(L.latLngBounds(coords), { padding: [20, 20] });
    } else {
      modalMap.setView([52.52, 13.40], 12);
    }
  }, 100);
}

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('trip-modal').classList.add('hidden');
  if (modalMap) { modalMap.remove(); modalMap = null; }
});

document.getElementById('trip-modal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('trip-modal'))
    document.getElementById('modal-close').click();
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtDurFromISO(start, end) {
  const sec = Math.round((new Date(end) - new Date(start)) / 1000);
  if (sec < 0) return '–';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

function speedColor(spd, min, max) {
  const t = Math.min(1, Math.max(0, (spd - min) / (max - min)));
  const r = Math.round(255 * Math.min(1, t * 2));
  const g = Math.round(255 * Math.min(1, 2 - t * 2));
  return `rgb(${r},${g},40)`;
}

function esc(s) {
  return String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
initMap();
updateFollowBtn();
