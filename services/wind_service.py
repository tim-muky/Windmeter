"""
Wind Service
============
Polls the PiLogger WebMonitor's /rawdata/ JSON endpoint.

Why polling instead of reading I2C directly:
  PiLogger-bottle.py already owns the I2C bus and the interrupt GPIO.
  Competing with it would cause read errors.  The /rawdata/ endpoint
  gives us a clean, always-fresh value every MeasInter seconds (default 2 s).

JSON keys we care about:
  PiLoWind1   – momentary wind speed (string, e.g. "  12.3")
  UnitWind1   – unit string, e.g. "km/h"
  PiLoWind10m – 10-minute average (same unit)
  PiLoWind1h  – 1-hour average
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

import config

log = logging.getLogger(__name__)


@dataclass
class WindReading:
    timestamp: float        = field(default_factory=time.time)
    speed_knots: float      = 0.0   # momentary
    avg_10m_knots: float    = 0.0
    avg_1h_knots: float     = 0.0
    unit_raw: str           = "km/h"
    speed_raw: float        = 0.0   # original unit, for diagnostics
    ok: bool                = False  # False = no valid reading yet


# Module-level shared state (read by other services)
latest: WindReading = WindReading()


def _to_knots(value: float, unit: str) -> float:
    """Convert a wind speed value to knots based on its reported unit."""
    u = unit.strip().lower()
    if u in ("km/h", "kmh", "kph"):
        return round(value * config.KMH_TO_KNOTS, 1)
    if u in ("m/s", "ms"):
        return round(value * config.MS_TO_KNOTS, 1)
    if u in ("kn", "kt", "knots"):
        return round(value, 1)
    # Unknown unit – assume km/h as PiLogger default
    log.warning("Unknown wind unit '%s', assuming km/h", unit)
    return round(value * config.KMH_TO_KNOTS, 1)


def _parse_float(s) -> Optional[float]:
    """Safe float parse; PiLogger returns strings with commas as decimal sep."""
    try:
        return float(str(s).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


async def run(stop_event: asyncio.Event) -> None:
    """
    Async task: poll PiLogger /rawdata/ endpoint every PILOGGER_POLL_SEC.
    Updates the module-level `latest` WindReading in place.
    Runs until stop_event is set.
    """
    global latest
    url = f"{config.PILOGGER_URL}/rawdata/"
    interval = config.PILOGGER_POLL_SEC

    timeout = aiohttp.ClientTimeout(total=interval * 0.9)

    log.info("Wind service starting – polling %s every %.1f s", url, interval)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while not stop_event.is_set():
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)

                        unit = data.get("UnitWind1", config.PILOGGER_WIND_UNIT)
                        raw  = _parse_float(data.get("PiLoWind1", 0))
                        avg10 = _parse_float(data.get("PiLoWind10m", 0))
                        avg1h = _parse_float(data.get("PiLoWind1h", 0))

                        if raw is not None:
                            latest = WindReading(
                                timestamp     = time.time(),
                                speed_knots   = _to_knots(raw,   unit),
                                avg_10m_knots = _to_knots(avg10 or 0, unit),
                                avg_1h_knots  = _to_knots(avg1h or 0, unit),
                                unit_raw      = unit,
                                speed_raw     = raw,
                                ok            = True,
                            )
                    else:
                        log.warning("PiLogger returned HTTP %d", resp.status)

            except aiohttp.ClientConnectorError:
                log.debug("PiLogger not reachable – waiting")
                latest = WindReading(ok=False)
            except asyncio.TimeoutError:
                log.debug("PiLogger request timed out")
            except Exception as exc:
                log.error("Wind poll error: %s", exc)

            await asyncio.sleep(interval)

    log.info("Wind service stopped.")
