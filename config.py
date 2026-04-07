"""
SailMon – Configuration
========================
Central configuration file.  Edit values here to match your hardware setup.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── PiLogger WebMonitor ──────────────────────────────────────────────────────
# PiLogger-bottle.py runs on port 8080 by default.
# We read from its /rawdata/ endpoint so we never conflict with its I2C usage.
PILOGGER_URL         = "http://localhost:8080"
PILOGGER_POLL_SEC    = 2.0        # seconds between wind polls
PILOGGER_WIND_UNIT   = "km/h"     # unit reported by PiLogger (set in its config)

# ─── GPS (gpsd) ───────────────────────────────────────────────────────────────
# GPS dongle connects via USB; gpsd abstracts the physical interface.
# The existing gpsd setup (see scripts/setup_system.sh) already handles USB GPS.
GPS_HOST             = "localhost"
GPS_PORT             = 2947
GPS_POLL_SEC         = 1.0        # seconds between GPS reads

# ─── PICO Display (MAX7219 4-in-1 LED dot-matrix) ────────────────────────────
# Two MAX7219 4-in-1 modules driven by a Raspberry Pi PICO over SPI.
# The PICO connects to the RPi 4B via USB and appears as a serial port.
#
# If both the PICO and the GPS dongle enumerate as ttyACM devices, add a udev
# rule to give the PICO a stable name (see services/display_service.py header).
PICO_SERIAL_PORT     = "/dev/ttyACM0"   # adjust if GPS takes ttyACM0
PICO_BAUD_RATE       = 115200
DISPLAY_ENABLED      = True             # set False for dev without hardware

# Trend indicator threshold: change > this value in 30 s = trending up/down
TREND_THRESHOLD_KN   = 0.5

# ─── Web Server ───────────────────────────────────────────────────────────────
WEB_HOST             = "0.0.0.0"
WEB_PORT             = 8000

# ─── Data Storage ─────────────────────────────────────────────────────────────
DB_PATH              = os.path.join(BASE_DIR, "data", "sailmon.db")
GPX_DIR              = os.path.join(BASE_DIR, "data", "gpx")

# ─── Map Tiles ────────────────────────────────────────────────────────────────
# OSM base layer + OpenSeaMap nautical overlay (seamark layer).
# Tiles are cached locally on first fetch for offline use.
TILE_CACHE_DIR       = os.path.join(BASE_DIR, "data", "tiles", "osm")
OPENSEA_CACHE_DIR    = os.path.join(BASE_DIR, "data", "tiles", "opensea")
OSM_TILE_URL         = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OPENSEA_TILE_URL     = "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"
TILE_USER_AGENT      = "SailMon/1.0 (personal sailing instrument)"

# Default map zoom level (17 = good street/harbour detail for OpenSeaMap)
MAP_DEFAULT_ZOOM     = 17

# ─── Trip Detection ───────────────────────────────────────────────────────────
TRIP_START_KNOTS     = 0.5        # start a new trip once speed exceeds this
TRIP_END_KNOTS       = 0.3        # end trip when speed falls below this …
TRIP_END_TIMEOUT_S   = 120        # … for this many seconds continuously
LOG_INTERVAL_S       = 5          # how often to write a measurement to the DB

# ─── Unit Conversions ─────────────────────────────────────────────────────────
KMH_TO_KNOTS         = 0.539957
MS_TO_KNOTS          = 1.943844
MPS_TO_KNOTS         = 1.943844   # alias
