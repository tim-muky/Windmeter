"""
WindmeterV3 – Pico W Standalone Sailing Logger
==============================================
MicroPython firmware for the Raspberry Pi Pico W (SC0918).

One board replaces the old Raspberry Pi + Pico + PiLogger head.  It:
  • counts the cup anemometer directly on a GPIO (no I²C pulse-counter board),
  • reads a u-blox NEO-M9N GPS over UART (position + speed-over-ground + UTC),
  • shows live wind speed and boat speed on two MAX7219 4-in-1 displays,
  • logs one CSV row per second to a microSD card,
  • sounds a buzzer when a gust exceeds a threshold.

Trip distance and max wind/speed are NOT shown on the boat – they are derived
from the CSV log by the macOS viewer at home.

All wiring / calibration / thresholds live in config.py.
See README.md for the pin-out and flashing instructions.
"""

import machine
import time
import os

from machine import Pin, SPI, UART, PWM

import config
import sdcard


# ══════════════════════════════════════════════════════════════════════════════
#  MAX7219 display driver  (font + renderer carried over from the proven
#  pico_firmware, unchanged so it keeps working)
# ══════════════════════════════════════════════════════════════════════════════

_REG_DECODE = 0x09
_REG_INTENS = 0x0A
_REG_SCAN = 0x0B
_REG_SHUT = 0x0C
_REG_TEST = 0x0F

_FONT = {
    '0': [0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    '1': [0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110],
    '2': [0b01110, 0b10001, 0b00001, 0b00110, 0b01000, 0b10000, 0b11111],
    '3': [0b11110, 0b00001, 0b00001, 0b01110, 0b00001, 0b00001, 0b11110],
    '4': [0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010],
    '5': [0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110],
    '6': [0b00110, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110],
    '7': [0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000],
    '8': [0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110],
    '9': [0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b01110],
    '-': [0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000],
    ' ': [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
    '.': [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00011, 0b00011],
    '^': [0b00100, 0b01110, 0b11111, 0b00100, 0b00100, 0b00100, 0b00100],
    'v': [0b00100, 0b00100, 0b00100, 0b00100, 0b11111, 0b01110, 0b00100],
    '>': [0b00100, 0b00010, 0b11111, 0b00010, 0b00100, 0b00000, 0b00000],
}
_CHAR_W = {'.': 2}
_DEF_W = 5


def _render(value, trend):
    """Build a 32-column framebuffer: [trend arrow] [right-aligned value]."""
    if value is None or value < 0:
        val_str = '----'
    elif value < 10.0:
        val_str = ' ' + '{:.1f}'.format(value)
    elif value < 100.0:
        val_str = '{:.1f}'.format(value)
    else:
        val_str = '{:.0f}'.format(int(value))

    fb = [0] * 32

    def draw_char(ch, x_start):
        rows = _FONT.get(ch, _FONT[' '])
        w = _CHAR_W.get(ch, _DEF_W)
        for col in range(w):
            if not (0 <= x_start + col < 32):
                continue
            col_byte = 0
            for row in range(7):
                if w == 2:
                    bit = (rows[row] >> (1 - col)) & 1
                else:
                    bit = (rows[row] >> (4 - col)) & 1
                if bit:
                    col_byte |= (1 << (7 - (row + 1)))
            fb[x_start + col] = col_byte

    arrow = '^' if trend == 1 else ('v' if trend == -1 else '>')
    draw_char(arrow, 0)

    total_w = 0
    for i, ch in enumerate(val_str):
        total_w += _CHAR_W.get(ch, _DEF_W)
        if i < len(val_str) - 1:
            total_w += 1
    x = 7 + max(0, 25 - total_w)
    for ch in val_str:
        draw_char(ch, x)
        x += _CHAR_W.get(ch, _DEF_W) + 1
    return fb


class Display:
    """One MAX7219 4-in-1 module (4 cascaded 8×8 matrices)."""

    def __init__(self, spi, cs_pin, n, intensity):
        self._spi = spi
        self._cs = Pin(cs_pin, Pin.OUT, value=1)
        self._n = n
        self._init(intensity)

    def _tx(self, data):
        self._cs.value(0)
        self._spi.write(bytes(data))
        self._cs.value(1)

    def _all(self, reg, val):
        self._tx([reg, val] * self._n)

    def _init(self, intensity):
        self._all(_REG_TEST, 0)
        self._all(_REG_SCAN, 7)
        self._all(_REG_DECODE, 0)
        self._all(_REG_INTENS, intensity)
        self._all(_REG_SHUT, 1)
        self.clear()

    def clear(self):
        for row in range(1, 9):
            self._all(row, 0)

    def show(self, fb):
        for row in range(8):
            data = []
            for chip in range(self._n - 1, -1, -1):
                col_byte = 0
                for bit in range(8):
                    col = chip * 8 + bit
                    if col < 32 and (fb[col] >> (7 - row)) & 1:
                        col_byte |= (0x80 >> bit)
                data += [row + 1, col_byte]
            self._tx(data)

    def set_intensity(self, level):
        self._all(_REG_INTENS, max(0, min(15, level)))


# ══════════════════════════════════════════════════════════════════════════════
#  Anemometer – pulse counting via GPIO interrupt
# ══════════════════════════════════════════════════════════════════════════════

class Anemometer:
    """
    Counts falling edges from a reed/hall cup anemometer on PIN_ANEMO.
    Internal pull-up holds the line high; each cup pass yanks it to 0 V.
    A short debounce rejects reed-switch contact bounce.
    """

    def __init__(self, pin_num, debounce_ms):
        self._count = 0
        self._last_us = 0
        self._debounce_us = debounce_ms * 1000
        self.pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self.pin.irq(trigger=Pin.IRQ_FALLING, handler=self._tick)

    def _tick(self, pin):
        now = time.ticks_us()
        if time.ticks_diff(now, self._last_us) < self._debounce_us:
            return
        self._last_us = now
        self._count += 1

    def take(self):
        """Atomically read and reset the pulse count since the last call."""
        state = machine.disable_irq()
        c = self._count
        self._count = 0
        machine.enable_irq(state)
        return c


# ══════════════════════════════════════════════════════════════════════════════
#  GPS – minimal NMEA parser (RMC for fix/pos/speed/time, GGA for sats)
# ══════════════════════════════════════════════════════════════════════════════

class GPS:
    def __init__(self, uart):
        self.uart = uart
        self._buf = b''
        self.lat = None
        self.lon = None
        self.sog_kn = None
        self.cog = None
        self.sats = 0
        self.fix = 0
        self.utc = None          # (Y, M, D, h, m, s)
        self.has_fix = False

    def update(self):
        data = self.uart.read()
        if data:
            self._buf += data
            while b'\n' in self._buf:
                line, self._buf = self._buf.split(b'\n', 1)
                self._parse(line.strip())
            if len(self._buf) > 1024:          # guard against a stuck line
                self._buf = self._buf[-256:]

    def _parse(self, line):
        try:
            s = line.decode('ascii')
        except Exception:
            return
        if not s.startswith('$') or '*' not in s:
            return
        body = s[1:s.index('*')]
        p = body.split(',')
        if len(p[0]) < 5:
            return
        typ = p[0][2:]             # strip talker id (GP/GN/GA/...)
        if typ == 'RMC':
            self._parse_rmc(p)
        elif typ == 'GGA':
            self._parse_gga(p)

    def _parse_rmc(self, p):
        if len(p) < 10:
            return
        if p[2] != 'A':            # 'A' = valid fix, 'V' = void
            self.has_fix = False
            return
        lat = self._coord(p[3], p[4])
        lon = self._coord(p[5], p[6])
        if lat is None or lon is None:
            return
        self.lat = lat
        self.lon = lon
        try:
            self.sog_kn = float(p[7]) if p[7] else 0.0
        except ValueError:
            pass
        try:
            self.cog = float(p[8]) if p[8] else None
        except ValueError:
            pass
        self.utc = self._datetime(p[1], p[9])
        self.has_fix = True

    def _parse_gga(self, p):
        if len(p) < 8:
            return
        try:
            self.fix = int(p[6]) if p[6] else 0
        except ValueError:
            pass
        try:
            self.sats = int(p[7]) if p[7] else 0
        except ValueError:
            pass

    @staticmethod
    def _coord(val, hemi):
        # NMEA ddmm.mmmm / dddmm.mmmm → signed decimal degrees
        if not val or not hemi:
            return None
        try:
            dot = val.index('.')
            deg = int(val[:dot - 2])
            minutes = float(val[dot - 2:])
            d = deg + minutes / 60.0
            return -d if hemi in ('S', 'W') else d
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _datetime(t, d):
        try:
            return (2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]),
                    int(t[0:2]), int(t[2:4]), int(t[4:6]))
        except (ValueError, IndexError):
            return None

    def iso(self):
        if not self.utc:
            return ''
        return '%04d-%02d-%02dT%02d:%02d:%02dZ' % self.utc


# ══════════════════════════════════════════════════════════════════════════════
#  Gust alarm buzzer
# ══════════════════════════════════════════════════════════════════════════════

class Buzzer:
    def __init__(self, pin_num, freq):
        self._pwm = PWM(Pin(pin_num))
        self._pwm.freq(freq)
        self._pwm.duty_u16(0)

    def beep(self, ms=120):
        self._pwm.duty_u16(32768)
        time.sleep_ms(ms)
        self._pwm.duty_u16(0)

    def double_beep(self):
        self.beep(120)
        time.sleep_ms(80)
        self.beep(120)


# ══════════════════════════════════════════════════════════════════════════════
#  Trend tracker (rising / falling arrow for the displays)
# ══════════════════════════════════════════════════════════════════════════════

class Trend:
    """1 = rising, -1 = falling, 0 = stable over the last `window_s` seconds."""

    def __init__(self, window_s=10, threshold=0.5):
        self._window = window_s
        self._thr = threshold
        self._hist = []          # (ticks_ms, value)

    def update(self, value):
        if value is None:
            return 0
        now = time.ticks_ms()
        self._hist.append((now, value))
        cutoff = time.ticks_diff(now, self._window * 1000)
        while self._hist and time.ticks_diff(self._hist[0][0], cutoff) < 0:
            self._hist.pop(0)
        oldest = self._hist[0][1]
        delta = value - oldest
        if delta > self._thr:
            return 1
        if delta < -self._thr:
            return -1
        return 0


# ══════════════════════════════════════════════════════════════════════════════
#  SD-card CSV logger
# ══════════════════════════════════════════════════════════════════════════════

_CSV_HEADER = "utc,lat,lon,sog_kn,wind_kn,wind_avg_kn,cog,sats,fix\n"


class Logger:
    """
    Opens one CSV file per power-on, named from the first GPS fix time.
    Appends + flushes every row so a sudden power cut loses at most one line.
    Logging only starts once GPS gives us a UTC timestamp (needed for the name
    and the row).  Wind still shows on the display before that.
    """

    def __init__(self, mount):
        self._mount = mount
        self._f = None
        self.path = None
        self.ok = False
        self._mount_ok = self._mount_card()

    def _mount_card(self):
        try:
            spi = SPI(config.SPI_SD_ID, baudrate=1_000_000,
                      sck=Pin(config.PIN_SD_SCK),
                      mosi=Pin(config.PIN_SD_MOSI),
                      miso=Pin(config.PIN_SD_MISO))
            sd = sdcard.SDCard(spi, Pin(config.PIN_SD_CS))
            os.mount(sd, self._mount)
            return True
        except Exception as exc:
            print("SD mount failed:", exc)
            return False

    def _open(self, utc):
        name = "%s/WIND_%04d%02d%02d_%02d%02d%02d.csv" % (
            self._mount, utc[0], utc[1], utc[2], utc[3], utc[4], utc[5])
        try:
            self._f = open(name, "w")
            self._f.write(_CSV_HEADER)
            self._f.flush()
            self.path = name
            self.ok = True
            print("Logging to", name)
        except Exception as exc:
            print("Cannot open log file:", exc)

    def log(self, gps, wind_kn, wind_avg_kn):
        if not self._mount_ok or not gps.has_fix or not gps.utc:
            return
        if self._f is None:
            self._open(gps.utc)
            if self._f is None:
                return
        cog = "%.1f" % gps.cog if gps.cog is not None else ""
        try:
            self._f.write("%s,%.6f,%.6f,%.2f,%.2f,%.2f,%s,%d,%d\n" % (
                gps.iso(), gps.lat, gps.lon,
                gps.sog_kn or 0.0, wind_kn, wind_avg_kn,
                cog, gps.sats, gps.fix))
            self._f.flush()
        except Exception as exc:
            print("Log write error:", exc)
            self.ok = False


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Displays ──────────────────────────────────────────────────────────────
    disp_spi = SPI(config.SPI_DISP_ID, baudrate=10_000_000, polarity=0, phase=0,
                   sck=Pin(config.PIN_DISP_SCK), mosi=Pin(config.PIN_DISP_MOSI))
    wind_disp = Display(disp_spi, config.PIN_CS_WIND, config.DISP_MODULES,
                        config.DISP_INTENSITY)
    speed_disp = Display(disp_spi, config.PIN_CS_SPEED, config.DISP_MODULES,
                         config.DISP_INTENSITY)

    # Startup brightness sweep, then dashes while we wait for data
    for d in (wind_disp, speed_disp):
        for i in list(range(0, 12, 2)) + list(range(11, -1, -2)):
            d.set_intensity(i)
            time.sleep_ms(25)
        d.set_intensity(config.DISP_INTENSITY)
    wind_disp.show(_render(None, 0))
    speed_disp.show(_render(None, 0))

    # ── Peripherals ───────────────────────────────────────────────────────────
    anemo = Anemometer(config.PIN_ANEMO, config.ANEMO_DEBOUNCE_MS)

    gps_uart = UART(config.UART_GPS_ID, baudrate=config.GPS_BAUD,
                    tx=Pin(config.PIN_GPS_TX), rx=Pin(config.PIN_GPS_RX),
                    rxbuf=1024)
    gps = GPS(gps_uart)

    buzzer = Buzzer(config.PIN_BUZZER, config.BUZZER_FREQ)
    logger = Logger(config.SD_MOUNT)

    wind_trend = Trend()
    speed_trend = Trend()

    counts = []                  # rolling per-second pulse counts
    gust_armed = True
    secs = 0

    while True:
        # Pump the GPS UART continuously for ~1 second
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < int(config.LOG_INTERVAL_S * 1000):
            gps.update()
            time.sleep_ms(40)

        # ── Wind speed from pulse count, smoothed over WIND_WINDOW_S ──────────
        counts.append(anemo.take())
        if len(counts) > config.WIND_WINDOW_S:
            counts.pop(0)
        hz = sum(counts) / len(counts)                 # avg pulses/sec
        wind_kn = hz * config.KMH_PER_HZ * config.KMH_TO_KNOTS

        # ── Boat speed from GPS ──────────────────────────────────────────────
        sog = gps.sog_kn if gps.has_fix else None

        # ── Displays ─────────────────────────────────────────────────────────
        wind_disp.show(_render(wind_kn, wind_trend.update(wind_kn)))
        speed_disp.show(_render(sog, speed_trend.update(sog)))

        # ── Gust alarm (with hysteresis so it doesn't chatter) ───────────────
        if gust_armed and wind_kn >= config.GUST_THRESHOLD_KN:
            buzzer.double_beep()
            gust_armed = False
        elif wind_kn < config.GUST_THRESHOLD_KN - config.GUST_HYSTERESIS_KN:
            gust_armed = True

        # ── Log to SD ────────────────────────────────────────────────────────
        # wind_avg_kn here is the smoothed value; the viewer derives trip max/avg.
        logger.log(gps, wind_kn, wind_kn)

        secs += 1


main()
