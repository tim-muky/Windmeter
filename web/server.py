"""
Web Server
==========
FastAPI application serving:

  GET  /               → frontend SPA
  GET  /static/*       → JS, CSS, assets
  WS   /ws             → real-time data stream (JSON, ~1 Hz)
  GET  /api/trips      → list all trips
  GET  /api/trips/{id} → trip details + full track
  GET  /api/trips/{id}/gpx → download GPX file
  DELETE /api/trips/{id}  → delete trip
  GET  /tiles/osm/{z}/{x}/{y}.png      → cached OSM tile proxy
  GET  /tiles/opensea/{z}/{x}/{y}.png  → cached OpenSeaMap tile proxy

The tile proxy caches tiles on first request (when internet is available)
so the map works offline once tiles have been pre-fetched.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Set

import aiohttp
import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
from services import wind_service, gps_service, data_service

log = logging.getLogger(__name__)

app = FastAPI(title="SailMon", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─── WebSocket connection manager ────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
        log.debug("WS client connected – total %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
        log.debug("WS client disconnected – total %d", len(self.active))

    async def broadcast(self, data: dict):
        payload = json.dumps(data)
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self.active -= dead


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # keep connection alive / accept pings
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def broadcast_loop(stop_event: asyncio.Event):
    """Push live data to all connected WebSocket clients once per second."""
    while not stop_event.is_set():
        wind = wind_service.latest
        gps  = gps_service.latest

        payload = {
            "t": int(time.time()),
            "wind": {
                "kn":      wind.speed_knots    if wind.ok else None,
                "avg10":   wind.avg_10m_knots  if wind.ok else None,
                "avg1h":   wind.avg_1h_knots   if wind.ok else None,
                "ok":      wind.ok,
            },
            "gps": {
                "lat":     gps.latitude        if gps.ok else None,
                "lon":     gps.longitude       if gps.ok else None,
                "sog":     gps.speed_knots     if gps.ok else None,
                "hdg":     gps.heading         if gps.ok else None,
                "alt":     gps.altitude_m      if gps.ok else None,
                "fix":     gps.fix,
                "sats":    gps.satellites,
                "ok":      gps.ok,
            },
            "trip_id": data_service.get_active_trip_id(),
        }

        await manager.broadcast(payload)
        await asyncio.sleep(1.0)


# ─── REST API ────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/trips")
async def api_trips():
    return data_service.get_trips()


@app.get("/api/trips/{trip_id}")
async def api_trip_detail(trip_id: str):
    trip = data_service.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    track = data_service.get_track(trip_id)
    return {"trip": trip, "track": track}


@app.get("/api/trips/{trip_id}/gpx")
async def api_trip_gpx(trip_id: str):
    trip = data_service.get_trip(trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    safe = trip["name"].replace(" ", "_").replace(":", "-")
    path = os.path.join(config.GPX_DIR, f"{safe}.gpx")
    if not os.path.exists(path):
        raise HTTPException(404, "GPX not yet generated")
    return FileResponse(path, media_type="application/gpx+xml",
                        filename=f"{safe}.gpx")


@app.delete("/api/trips/{trip_id}")
async def api_trip_delete(trip_id: str):
    import sqlite3
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.execute("DELETE FROM measurements WHERE trip_id=?", (trip_id,))
            conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


# ─── Tile proxy ──────────────────────────────────────────────────────────────

_tile_session: Optional[aiohttp.ClientSession] = None


def _tile_path(cache_dir: str, z: int, x: int, y: int) -> str:
    return os.path.join(cache_dir, str(z), str(x), f"{y}.png")


async def _get_tile(cache_dir: str, remote_url_tpl: str,
                    z: int, x: int, y: int) -> Optional[bytes]:
    """Return tile bytes from cache or fetch from remote and cache."""
    path = _tile_path(cache_dir, z, x, y)

    # 1. Serve from cache if present
    if os.path.exists(path):
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    # 2. Try to fetch from remote
    global _tile_session
    if _tile_session is None or _tile_session.closed:
        _tile_session = aiohttp.ClientSession(
            headers={"User-Agent": config.TILE_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=10)
        )

    url = remote_url_tpl.format(z=z, x=x, y=y)
    try:
        async with _tile_session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                os.makedirs(os.path.dirname(path), exist_ok=True)
                async with aiofiles.open(path, "wb") as f:
                    await f.write(data)
                return data
    except Exception as e:
        log.debug("Tile fetch failed for %s: %s", url, e)

    return None


@app.get("/tiles/osm/{z}/{x}/{y}.png")
async def tile_osm(z: int, x: int, y: int):
    data = await _get_tile(config.TILE_CACHE_DIR, config.OSM_TILE_URL, z, x, y)
    if data is None:
        raise HTTPException(503, "Tile not available offline")
    return Response(content=data, media_type="image/png")


@app.get("/tiles/opensea/{z}/{x}/{y}.png")
async def tile_opensea(z: int, x: int, y: int):
    data = await _get_tile(config.OPENSEA_CACHE_DIR, config.OPENSEA_TILE_URL, z, x, y)
    if data is None:
        raise HTTPException(503, "Tile not available offline")
    return Response(content=data, media_type="image/png")
