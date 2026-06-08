"""
WindmeterV3 – Pico W Logger Configuration
=========================================
All wiring, calibration and threshold values live here so the firmware in
main.py stays generic.  Edit to match your build, then re-upload this file.

Target: Raspberry Pi Pico W (SC0918), MicroPython.

The Pico W is the whole instrument now – it counts the anemometer directly
(no PiLogger head), reads the GPS over UART, drives the two MAX7219 displays,
logs to the microSD card and sounds the gust buzzer.
"""

# ─── MAX7219 displays (SPI0, write-only) ──────────────────────────────────────
# Two 4-in-1 (32×8) modules: display 1 = wind speed, display 2 = boat speed.
# Same pin map and driver as the original pico_firmware, so it just works.
SPI_DISP_ID    = 0
PIN_DISP_SCK   = 6      # SPI0 SCK  → CLK on both modules
PIN_DISP_MOSI  = 7      # SPI0 MOSI → DIN on both modules
PIN_CS_WIND    = 5      # CS → display 1 (wind)
PIN_CS_SPEED   = 8      # CS → display 2 (boat speed)
DISP_MODULES   = 4      # cascaded 8×8 chips per module
DISP_INTENSITY = 8      # brightness 0-15

# ─── Anemometer (cup, reed/hall pulse output) ─────────────────────────────────
# One leg to PIN_ANEMO, the other to GND.  Internal pull-up holds the line high;
# each cup pass pulls it to 0 V → a falling edge we count.
PIN_ANEMO         = 15
ANEMO_DEBOUNCE_MS = 4       # ignore edges closer than this (reed-switch bounce)
KMH_PER_HZ        = 1.44    # calibration from your scope data (5.24 Hz ≈ 7.5 km/h).
                            # Field-trim: drive past a known speed / handheld meter.
WIND_WINDOW_S     = 3       # seconds of pulse history to average for a smooth read

# ─── GPS – u-blox NEO-M9N over UART0 (NMEA) ───────────────────────────────────
# Pico GP0 (TX) → GPS RX,  Pico GP1 (RX) ← GPS TX.
UART_GPS_ID = 0
PIN_GPS_TX  = 0
PIN_GPS_RX  = 1
GPS_BAUD    = 38400        # NEO-M9N default; many modules ship at 9600 – change
                           # this if you get no fix (try 9600).

# ─── microSD card (SPI1) ──────────────────────────────────────────────────────
SPI_SD_ID  = 1
PIN_SD_SCK = 10
PIN_SD_MOSI = 11
PIN_SD_MISO = 12
PIN_SD_CS  = 13
SD_MOUNT   = "/sd"

# ─── Gust alarm buzzer ────────────────────────────────────────────────────────
# Active or passive buzzer on PIN_BUZZER (driven with PWM so either works).
PIN_BUZZER         = 14
GUST_THRESHOLD_KN  = 22.0   # sound the alarm above this gust speed
GUST_HYSTERESIS_KN = 3.0    # must fall this far below threshold before re-arming
BUZZER_FREQ        = 2400   # tone for passive buzzers (ignored by active ones)

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_INTERVAL_S = 1.0        # one CSV row per second (after first GPS fix)

# ─── Unit conversion ──────────────────────────────────────────────────────────
KMH_TO_KNOTS = 0.539957
