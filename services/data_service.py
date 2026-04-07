"""
Data Service
============
Handles:
  • SQLite database (trips + measurements)
  • Automatic trip detection (start / stop based on speed threshold)
  • GPX file export per trip
  • Cleanup helpers used by the web API

Database schema
---------------
  trips        – one row per sailing trip
  measurements – one row per log interval (default 5 s) during a trip

Trip lifecycle
--------------
  IDLE  →  speed > TRIP_START_KNOTS  →  ACTIVE  (new trip created)
  ACTIVE → speed < TRIP_END_KNOTS for TRIP_END_TIMEOUT_S  →  IDLE  (trip closed)
"""

import asyncio
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from xml.etree import ElementTree as ET

import config

log = logging.getLogger(__name__)

# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    os.makedirs(config.GPX_DIR, exist_ok=True)
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trips (
                id          TEXT PRIMARY KEY,
                name        TEXT,
                start_time  TEXT NOT NULL,
                end_time    TEXT,
                distance_nm REAL DEFAULT 0,
                max_wind_kn REAL DEFAULT 0,
                max_speed_kn REAL DEFAULT 0,
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS measurements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id     TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                latitude    REAL,
                longitude   REAL,
                speed_kn    REAL,
                heading     REAL,
                wind_kn     REAL,
                wind_avg10_kn REAL,
                altitude_m  REAL,
                satellites  INTEGER,
                FOREIGN KEY (trip_id) REFERENCES trips(id)
            );

            CREATE INDEX IF NOT EXISTS idx_meas_trip
                ON measurements(trip_id, timestamp);
        """)
    log.info("Database ready at %s", config.DB_PATH)


# ─── Trip state machine ───────────────────────────────────────────────────────

@dataclass
class ActiveTrip:
    id: str
    name: str
    start_time: float
    last_point_lat: Optional[float] = None
    last_point_lon: Optional[float] = None
    distance_nm: float = 0.0
    max_wind_kn: float = 0.0
    max_speed_kn: float = 0.0
    below_threshold_since: Optional[float] = None


_active_trip: Optional[ActiveTrip] = None


def _haversine_nm(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in nautical miles."""
    from math import radians, sin, cos, sqrt, atan2
    R = 3440.065  # Earth radius in NM
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)
    a = sin(Δφ/2)**2 + cos(φ1)*cos(φ2)*sin(Δλ/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _start_trip() -> ActiveTrip:
    trip_id = str(uuid.uuid4())
    name    = datetime.now().strftime("Trip %Y-%m-%d %H:%M")
    now_s   = time.time()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO trips (id, name, start_time) VALUES (?, ?, ?)",
            (trip_id, name, _ts_now())
        )
    log.info("Trip started: %s (%s)", name, trip_id)
    return ActiveTrip(id=trip_id, name=name, start_time=now_s)


def _close_trip(trip: ActiveTrip) -> None:
    with _get_conn() as conn:
        conn.execute(
            """UPDATE trips SET end_time=?, distance_nm=?,
               max_wind_kn=?, max_speed_kn=? WHERE id=?""",
            (_ts_now(), round(trip.distance_nm, 2),
             trip.max_wind_kn, trip.max_speed_kn, trip.id)
        )
    log.info("Trip closed: %s  dist=%.2f NM  max_wind=%.1f kn",
             trip.name, trip.distance_nm, trip.max_wind_kn)
    # Export GPX asynchronously
    asyncio.get_event_loop().create_task(_export_gpx(trip.id))


def _record_measurement(trip: ActiveTrip, gps, wind) -> None:
    """Write one row to measurements and update trip running totals."""
    # Distance
    if (gps.latitude is not None and gps.longitude is not None
            and trip.last_point_lat is not None):
        d = _haversine_nm(
            trip.last_point_lat, trip.last_point_lon,
            gps.latitude, gps.longitude
        )
        trip.distance_nm += d

    trip.last_point_lat = gps.latitude
    trip.last_point_lon = gps.longitude
    trip.max_wind_kn    = max(trip.max_wind_kn,  wind.speed_knots)
    trip.max_speed_kn   = max(trip.max_speed_kn, gps.speed_knots)

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO measurements
               (trip_id, timestamp, latitude, longitude, speed_kn,
                heading, wind_kn, wind_avg10_kn, altitude_m, satellites)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (trip.id, _ts_now(),
             gps.latitude, gps.longitude, gps.speed_knots,
             gps.heading, wind.speed_knots, wind.avg_10m_knots,
             gps.altitude_m, gps.satellites)
        )


# ─── Main async task ──────────────────────────────────────────────────────────

async def run(stop_event: asyncio.Event) -> None:
    global _active_trip
    from services import wind_service, gps_service

    init_db()
    log.info("Data service started (log interval %d s)", config.LOG_INTERVAL_S)

    while not stop_event.is_set():
        await asyncio.sleep(config.LOG_INTERVAL_S)

        gps  = gps_service.latest
        wind = wind_service.latest

        speed = gps.speed_knots if gps.ok else 0.0

        # ── Trip start ────────────────────────────────────────────────────────
        if _active_trip is None:
            if speed >= config.TRIP_START_KNOTS and gps.ok:
                _active_trip = _start_trip()
            continue

        # ── Trip active ───────────────────────────────────────────────────────
        _record_measurement(_active_trip, gps, wind)

        # ── Trip end detection ────────────────────────────────────────────────
        if speed < config.TRIP_END_KNOTS:
            if _active_trip.below_threshold_since is None:
                _active_trip.below_threshold_since = time.time()
            elif time.time() - _active_trip.below_threshold_since >= config.TRIP_END_TIMEOUT_S:
                _close_trip(_active_trip)
                _active_trip = None
        else:
            _active_trip.below_threshold_since = None

    # Graceful shutdown: close any open trip
    if _active_trip:
        _close_trip(_active_trip)
        _active_trip = None

    log.info("Data service stopped.")


# ─── GPX export ───────────────────────────────────────────────────────────────

async def _export_gpx(trip_id: str) -> None:
    """Generate a .gpx file for the given trip (runs in thread executor)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_gpx, trip_id)


def _write_gpx(trip_id: str) -> None:
    with _get_conn() as conn:
        trip = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
        rows = conn.execute(
            """SELECT * FROM measurements WHERE trip_id=?
               AND latitude IS NOT NULL ORDER BY timestamp""",
            (trip_id,)
        ).fetchall()

    if not trip or not rows:
        return

    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "SailMon",
        "xmlns": "http://www.topografix.com/GPX/1/1",
    })
    meta = ET.SubElement(gpx, "metadata")
    ET.SubElement(meta, "name").text = trip["name"]
    ET.SubElement(meta, "time").text = trip["start_time"]

    trk  = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = trip["name"]
    trkseg = ET.SubElement(trk, "trkseg")

    for row in rows:
        trkpt = ET.SubElement(trkseg, "trkpt", {
            "lat": str(row["latitude"]),
            "lon": str(row["longitude"]),
        })
        ET.SubElement(trkpt, "ele").text  = str(row["altitude_m"] or 0)
        ET.SubElement(trkpt, "time").text = row["timestamp"]
        ext = ET.SubElement(trkpt, "extensions")
        ET.SubElement(ext, "speed").text    = str(row["speed_kn"] or 0)
        ET.SubElement(ext, "wind").text     = str(row["wind_kn"] or 0)
        ET.SubElement(ext, "heading").text  = str(row["heading"] or 0)

    safe_name = trip["name"].replace(" ", "_").replace(":", "-")
    path = os.path.join(config.GPX_DIR, f"{safe_name}.gpx")
    tree = ET.ElementTree(gpx)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    log.info("GPX exported: %s", path)


# ─── Read helpers (used by web API) ───────────────────────────────────────────

def get_trips() -> List[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trips ORDER BY start_time DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_trip(trip_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM trips WHERE id=?", (trip_id,)
        ).fetchone()
    return dict(row) if row else None


def get_track(trip_id: str) -> List[dict]:
    """Return lat/lon/speed/wind/timestamp rows for the map."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT timestamp, latitude, longitude, speed_kn, wind_kn, heading
               FROM measurements WHERE trip_id=? AND latitude IS NOT NULL
               ORDER BY timestamp""",
            (trip_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_active_trip_id() -> Optional[str]:
    return _active_trip.id if _active_trip else None
