"""
Display Service
===============
Sends wind-speed and boat-speed data (with 30-second trend) to the
Raspberry Pi PICO over USB serial.  The PICO drives two MAX7219 4-in-1
8×8 LED dot-matrix display modules via SPI.

Architecture:
  RPi 4B  ──(USB CDC)──►  RPi PICO  ──(SPI)──►  MAX7219 × 2  ──►  LED Matrices

Protocol: one JSON line per second, e.g.:
  {"wind": 14.0, "wind_trend": 1, "speed": 7.1, "speed_trend": 0}
  trend:  1 = increasing  |  -1 = decreasing  |  0 = stable

The PICO serial port is typically /dev/ttyACM0 or /dev/ttyACM1.
If both the PICO and the GPS dongle are USB CDC devices, they compete for
/dev/ttyACM0.  Use PICO_SERIAL_PORT in config.py to set the correct port,
or add a udev rule:
  /etc/udev/rules.d/99-pico.rules:
  SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0005", SYMLINK+="ttyPICO"
  (then set PICO_SERIAL_PORT = "/dev/ttyPICO" in config.py)
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Optional

import config

log = logging.getLogger(__name__)

# Rolling history buffers: (monotonic_time, value_knots)
_wind_hist:  deque = deque(maxlen=120)   # ≈ 2 min @ 1 Hz
_speed_hist: deque = deque(maxlen=120)


def _calc_trend(history: deque, current: Optional[float],
                window: float = 30.0) -> int:
    """
    Compare current value to the oldest reading within the last `window`
    seconds.  Returns 1 (rising), -1 (falling), or 0 (stable).
    Threshold is taken from config.TREND_THRESHOLD_KN.
    """
    now = time.monotonic()
    if current is not None:
        history.append((now, current))

    cutoff = now - window
    oldest_val = None
    for t, v in history:
        if t >= cutoff:
            oldest_val = v
            break

    if oldest_val is None or current is None:
        return 0

    delta = current - oldest_val
    thr   = config.TREND_THRESHOLD_KN
    if delta > thr:
        return 1
    if delta < -thr:
        return -1
    return 0


def _open_port():
    """Try to open the PICO serial port.  Returns a serial.Serial or None."""
    try:
        import serial
        ser = serial.Serial(
            config.PICO_SERIAL_PORT,
            baudrate=config.PICO_BAUD_RATE,
            timeout=1.0,
            write_timeout=1.0,
        )
        log.info("PICO display connected on %s", config.PICO_SERIAL_PORT)
        return ser
    except ImportError:
        log.warning("pyserial not installed – display service disabled")
        return None
    except Exception as exc:
        log.debug("Cannot open PICO port %s: %s", config.PICO_SERIAL_PORT, exc)
        return None


async def run(stop_event: asyncio.Event) -> None:
    """Async task: send wind/speed + trend to PICO display once per second."""
    if not config.DISPLAY_ENABLED:
        log.info("Display disabled in config – skipping PICO init")
        await stop_event.wait()
        return

    from services import wind_service, gps_service

    log.info("Display service starting (PICO port: %s)", config.PICO_SERIAL_PORT)

    ser: Optional[object] = None
    last_connect_attempt   = -999.0
    loop = asyncio.get_running_loop()

    while not stop_event.is_set():

        # ── Reconnect if needed (try every 10 s) ────────────────────────────
        if ser is None:
            now = time.monotonic()
            if now - last_connect_attempt >= 10.0:
                last_connect_attempt = now
                ser = await loop.run_in_executor(None, _open_port)

        # ── Read latest sensor values ────────────────────────────────────────
        wind_kn  = wind_service.latest.speed_knots if wind_service.latest.ok  else None
        speed_kn = gps_service.latest.speed_knots  if gps_service.latest.ok   else None

        wind_trend  = _calc_trend(_wind_hist,  wind_kn)
        speed_trend = _calc_trend(_speed_hist, speed_kn)

        # ── Send to PICO ─────────────────────────────────────────────────────
        if ser is not None:
            line = json.dumps({
                "wind":        wind_kn,
                "wind_trend":  wind_trend,
                "speed":       speed_kn,
                "speed_trend": speed_trend,
            }) + "\n"
            try:
                await loop.run_in_executor(None, ser.write, line.encode())
            except Exception as exc:
                log.warning("PICO write error (%s) – reconnecting", exc)
                try:
                    await loop.run_in_executor(None, ser.close)
                except Exception:
                    pass
                ser = None

        await asyncio.sleep(1.0)

    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
    log.info("Display service stopped.")
