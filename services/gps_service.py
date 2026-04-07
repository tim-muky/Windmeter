"""
GPS Service
===========
Reads position, speed, heading and fix quality from gpsd via the
gpsd Python socket protocol (no extra library needed – uses raw socket).

Recommended hardware
--------------------
u-blox NEO-M8N or NEO-M9N USB dongle (e.g. "AZDelivery GPS NEO-M8N" on
Amazon.de, ~€20-25).  Simply plug into any USB port; gpsd will detect it
automatically once udev rules are in place (handled by setup_system.sh).

Why u-blox?
  • Multi-constellation (GPS + GLONASS + Galileo + BeiDou)
  • 1-10 Hz update rate configurable
  • Excellent cold-start time (~26 s)
  • Class-1 device: works straight away with gpsd on Raspberry Pi OS

gpsd integration
----------------
The standard Python `gps` package (gpsd-clients) is used.
Install: sudo apt install gpsd gpsd-clients python3-gps
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import config

log = logging.getLogger(__name__)


@dataclass
class GpsReading:
    timestamp:  float  = field(default_factory=time.time)
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    speed_knots: float = 0.0          # Speed Over Ground
    heading:    float  = 0.0          # Track Made Good (degrees true)
    altitude_m: float  = 0.0
    satellites: int    = 0
    fix:        int    = 0            # 0=no fix, 2=2D, 3=3D
    hdop:       float  = 99.9         # Horizontal Dilution of Precision
    ok: bool           = False        # True once we have a usable fix


# Module-level shared state
latest: GpsReading = GpsReading()


async def run(stop_event: asyncio.Event) -> None:
    """
    Async task: connects to gpsd, reads TPV (Time-Position-Velocity)
    reports in a loop.  Reconnects automatically on connection loss.
    """
    global latest
    log.info(
        "GPS service starting – connecting to gpsd at %s:%d",
        config.GPS_HOST, config.GPS_PORT
    )

    while not stop_event.is_set():
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(config.GPS_HOST, config.GPS_PORT),
                timeout=5.0
            )
            log.info("Connected to gpsd")

            # Send WATCH command to start streaming JSON reports
            watch_cmd = b'?WATCH={"enable":true,"json":true}\n'
            writer.write(watch_cmd)
            await writer.drain()

            buf = b""
            while not stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(
                        reader.read(4096), timeout=config.GPS_POLL_SEC * 3
                    )
                    if not chunk:
                        log.warning("gpsd connection closed")
                        break
                    buf += chunk
                    # gpsd sends newline-delimited JSON
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        _process_line(line)
                except asyncio.TimeoutError:
                    pass  # no data, loop again

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
            log.debug("gpsd not available (%s) – retrying in 5 s", e)
            latest = GpsReading(ok=False)
            await asyncio.sleep(5)
        except Exception as exc:
            log.error("GPS service error: %s", exc)
            await asyncio.sleep(5)

    log.info("GPS service stopped.")


def _process_line(raw: bytes) -> None:
    """Parse a single gpsd JSON line and update `latest`."""
    global latest
    import json
    try:
        data = json.loads(raw.decode("utf-8", errors="replace").strip())
    except json.JSONDecodeError:
        return

    if data.get("class") != "TPV":
        return

    mode = data.get("mode", 0)      # 0=unknown, 1=no fix, 2=2D, 3=3D
    if mode < 2:
        latest = GpsReading(ok=False, fix=mode)
        return

    # Speed from gpsd is in m/s → convert to knots
    speed_ms = data.get("speed", 0.0) or 0.0
    speed_kn = round(speed_ms * config.MPS_TO_KNOTS, 1)

    latest = GpsReading(
        timestamp   = time.time(),
        latitude    = data.get("lat"),
        longitude   = data.get("lon"),
        speed_knots = speed_kn,
        heading     = data.get("track", 0.0) or 0.0,
        altitude_m  = data.get("alt", 0.0) or 0.0,
        fix         = mode,
        ok          = mode >= 2 and data.get("lat") is not None,
    )
