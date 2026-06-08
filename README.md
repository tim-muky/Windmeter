# Windmeter

A DIY sailing instrument: live **wind speed** and **boat speed** on LED
displays, with the track, positions and speeds recorded for review at home.

## V3 — Pico W (current)

After the original Raspberry Pi rig went overboard, V3 rebuilds the instrument
around a single **Raspberry Pi Pico W** and keeps only the surviving cup
anemometer. The Pico counts the anemometer directly (no more PiLogger pulse
head), reads a **u-blox NEO-M9N** GPS, drives the two **MAX7219** displays,
logs to a **microSD card**, and sounds a **gust buzzer** — all on USB
power-bank power. No on-boat web interface; trips are reviewed at home.

| Path | What it is |
|---|---|
| [`pico_logger/`](pico_logger/) | MicroPython firmware for the Pico W (+ wiring & flashing in its README) |
| [`viewer/`](viewer/) | macOS map viewer — drag a `WIND_*.csv` from the SD card onto `index.html` to see the track, wind/boat speed ribbon and trip stats |

Start at [`pico_logger/README.md`](pico_logger/README.md) for the build.

## V2 — Raspberry Pi "SailMon" (legacy)

The previous Raspberry Pi 4B implementation (polled a PiLogger WebMonitor for
wind, gpsd for GPS, SQLite + a live Leaflet web UI) lives in `main.py`,
`config.py`, `services/`, and `web/`. It's superseded by V3 but kept for
reference — the web map and GPX logic were reused in the V3 viewer.
