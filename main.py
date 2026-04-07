#!/usr/bin/env python3
"""
SailMon – Main Entry Point
===========================
Starts all services concurrently:

  wind_service    – polls PiLogger WebMonitor every 2 s
  gps_service     – reads from gpsd (u-blox GPS receiver)
  display_service – sends wind/speed + trend to RPi PICO via USB serial
                    (PICO drives two MAX7219 4-in-1 8×8 LED matrix displays)
  data_service    – SQLite logging + trip lifecycle management
  web server      – FastAPI + WebSocket on port 8000

Graceful shutdown on SIGINT / SIGTERM:  all services stop cleanly,
the active trip (if any) is closed and written to disk.

Usage:
  python3 main.py

For production (auto-start on boot) use the sailmon.service systemd unit.
"""

import asyncio
import logging
import signal
import sys

import uvicorn

import config
from services import wind_service, gps_service, display_service, data_service
from web.server import app, broadcast_loop

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt  = "%H:%M:%S",
    handlers = [logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sailmon")


async def main() -> None:
    stop_event = asyncio.Event()

    # ── Signal handling ───────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: stop_event.set())

    log.info("╔══════════════════════════════╗")
    log.info("║        SailMon  v1.0         ║")
    log.info("╚══════════════════════════════╝")
    log.info("Web UI → http://%s:%d", config.WEB_HOST, config.WEB_PORT)

    # ── Uvicorn config (non-blocking) ─────────────────────────────────────────
    uv_config = uvicorn.Config(
        app         = app,
        host        = config.WEB_HOST,
        port        = config.WEB_PORT,
        log_level   = "warning",
        access_log  = False,
    )
    uv_server = uvicorn.Server(uv_config)

    # ── Launch all tasks ──────────────────────────────────────────────────────
    tasks = [
        asyncio.create_task(wind_service.run(stop_event),    name="wind"),
        asyncio.create_task(gps_service.run(stop_event),     name="gps"),
        asyncio.create_task(display_service.run(stop_event), name="display"),
        asyncio.create_task(data_service.run(stop_event),    name="data"),
        asyncio.create_task(broadcast_loop(stop_event),      name="ws-broadcast"),
        asyncio.create_task(_run_uvicorn(uv_server, stop_event), name="web"),
    ]

    log.info("All services started – waiting for shutdown signal")

    # Wait until stop_event is set (SIGINT / SIGTERM)
    await stop_event.wait()
    log.info("Shutdown signal received – stopping services …")

    uv_server.should_exit = True

    # Wait for all tasks with a timeout
    done, pending = await asyncio.wait(tasks, timeout=8)
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    log.info("SailMon stopped cleanly.")


async def _run_uvicorn(server: uvicorn.Server, stop_event: asyncio.Event) -> None:
    """Run uvicorn; when stop_event fires, signal it to exit."""
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
