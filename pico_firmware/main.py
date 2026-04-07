"""
WindMeter PICO Display Firmware
================================
MicroPython firmware for Raspberry Pi PICO.
Receives JSON commands via USB serial from the Raspberry Pi 4B and drives
two MAX7219 4-in-1 (32×8 px) LED dot-matrix display modules via SPI.

Hardware wiring (PICO BCM pin numbers):
  SPI0 SCK  (GP6)  → CLK on both display modules
  SPI0 MOSI (GP7)  → DIN on both display modules
  GP5               → CS  on Display 1 (Wind speed)
  GP8               → CS  on Display 2 (Boat speed)
  External 5 V      → VCC on both display modules
  PICO GND          → GND on both display modules (common ground)

Serial protocol:
  One JSON object per line, sent from the Raspberry Pi 4B, e.g.:
  {"wind": 14.0, "wind_trend": 1, "speed": 7.1, "speed_trend": 0}
  Fields:
    wind        – float | null   wind speed in knots
    wind_trend  – int            1=increasing, -1=decreasing, 0=stable
    speed       – float | null   boat speed in knots
    speed_trend – int            same encoding as wind_trend

Display layout (32 × 8 pixels per module):
  [trend arrow (5 px)] [gap (2 px)] [value right-aligned (25 px)]
  Value format: " 7.1" or "14.0" (4 chars using compact decimal point)
"""

import machine
import utime
import ujson
import sys
import select

# ─── Pin assignments ──────────────────────────────────────────────────────────

SPI_SCK   = 6
SPI_MOSI  = 7
CS_WIND   = 5    # Display 1 – wind speed
CS_SPEED  = 8    # Display 2 – boat speed
NUM_MOD   = 4    # Cascaded MAX7219 chips per display module

# ─── MAX7219 register addresses ───────────────────────────────────────────────

_REG_NOOP    = 0x00
_REG_DECODE  = 0x09
_REG_INTENS  = 0x0A
_REG_SCAN    = 0x0B
_REG_SHUT    = 0x0C
_REG_TEST    = 0x0F

# ─── 5 × 7 bitmap font ───────────────────────────────────────────────────────
# Each character: 7 row-bytes. Each byte = 5-bit row pattern, bit4=leftmost col.
# Row 0 = top row of glyph. The 7-tall glyph sits in rows 0–6; row 7 is blank.

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
    # Decimal point: stored 5-wide but only right-most 2 columns contain pixels.
    # Renderer special-cases this character to occupy only 2 columns.
    '.': [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00011, 0b00011],
    # Trend arrows
    '^': [0b00100, 0b01110, 0b11111, 0b00100, 0b00100, 0b00100, 0b00100],  # ↑
    'v': [0b00100, 0b00100, 0b00100, 0b00100, 0b11111, 0b01110, 0b00100],  # ↓
    '>': [0b00100, 0b00010, 0b11111, 0b00010, 0b00100, 0b00000, 0b00000],  # →
}

# Characters that are narrower than the default 5 columns
_CHAR_W = {'.': 2}
_DEF_W  = 5


def _render(value, trend):
    """
    Build a 32×8 framebuffer for the given value and trend.
    Returns a list of 32 ints (one per column), bit 7 = top row.

    Layout:
      cols  0– 5  trend arrow (5 cols + 1 gap)
      cols  7–31  value, right-aligned (25 cols)
    """
    # ── Format value string ──────────────────────────────────────────────────
    if value is None or value < 0:
        val_str = '----'
    elif value < 10.0:
        val_str = ' ' + '{:.1f}'.format(value)   # " 7.1"
    elif value < 100.0:
        val_str = '{:.1f}'.format(value)           # "14.0"
    else:
        val_str = '{:.0f}'.format(int(value))      # "123"

    # ── Framebuffer (column-major, 32 cols × 8 rows) ─────────────────────────
    fb = [0] * 32

    def draw_char(ch, x_start):
        rows = _FONT.get(ch, _FONT[' '])
        w    = _CHAR_W.get(ch, _DEF_W)
        for col in range(w):
            if not (0 <= x_start + col < 32):
                continue
            col_byte = 0
            for row in range(7):                         # rows 0-6 of glyph
                # Extract correct bit: for narrow chars use rightmost bits
                if w == 2:
                    bit = (rows[row] >> (1 - col)) & 1
                else:
                    bit = (rows[row] >> (4 - col)) & 1
                if bit:
                    col_byte |= (1 << (7 - (row + 1)))  # centre in 8 rows
            fb[x_start + col] = col_byte

    # ── Draw trend arrow in cols 0-4 ────────────────────────────────────────
    arrow = '^' if trend == 1 else ('v' if trend == -1 else '>')
    draw_char(arrow, 0)

    # ── Draw value right-aligned in cols 7-31 ───────────────────────────────
    # Calculate total pixel width of the value string
    total_w = 0
    for i, ch in enumerate(val_str):
        total_w += _CHAR_W.get(ch, _DEF_W)
        if i < len(val_str) - 1:
            total_w += 1   # inter-character gap

    x = 7 + max(0, 25 - total_w)   # right-align within the 25-column zone

    for i, ch in enumerate(val_str):
        draw_char(ch, x)
        x += _CHAR_W.get(ch, _DEF_W) + 1

    return fb


# ─── MAX7219 display driver ───────────────────────────────────────────────────

class Display:
    """Controls one 4-in-1 MAX7219 module (4 cascaded 8×8 matrices)."""

    def __init__(self, spi, cs_pin, intensity=8):
        self._spi = spi
        self._cs  = machine.Pin(cs_pin, machine.Pin.OUT, value=1)
        self._n   = NUM_MOD
        self._init(intensity)

    def _tx(self, data):
        self._cs.value(0)
        self._spi.write(bytes(data))
        self._cs.value(1)

    def _all(self, reg, val):
        """Write the same register/value to every cascaded chip."""
        self._tx([reg, val] * self._n)

    def _init(self, intensity):
        self._all(_REG_TEST,   0)             # display test off
        self._all(_REG_SCAN,   7)             # scan all 8 rows
        self._all(_REG_DECODE, 0)             # no BCD decode
        self._all(_REG_INTENS, intensity)     # brightness 0-15
        self._all(_REG_SHUT,   1)             # wake up
        self.clear()

    def clear(self):
        for row in range(1, 9):
            self._all(row, 0)

    def show(self, fb):
        """
        Write a 32-column framebuffer to the 4-chip cascade.

        Physical layout (left→right): chip0 | chip1 | chip2 | chip3
        SPI shift order (first sent ends up in last chip):
          → send chip3 data first, chip0 data last.

        For each of 8 rows we build one transaction of 8 bytes:
          [row, chip3_col_byte, row, chip2_col_byte, row, chip1_col_byte, row, chip0_col_byte]

        Each chip's col_byte: bit7 = leftmost column of that chip's 8-column block.
        """
        for row in range(8):
            data = []
            for chip in range(self._n - 1, -1, -1):   # chip3 → chip0
                col_byte = 0
                for bit in range(8):                    # bit7 = leftmost
                    col = chip * 8 + bit
                    if col < 32 and (fb[col] >> (7 - row)) & 1:
                        col_byte |= (0x80 >> bit)
                data += [row + 1, col_byte]
            self._tx(data)

    def set_intensity(self, level):
        self._all(_REG_INTENS, max(0, min(15, level)))


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    spi = machine.SPI(
        0,
        baudrate=10_000_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(SPI_SCK),
        mosi=machine.Pin(SPI_MOSI),
    )

    wind_disp  = Display(spi, CS_WIND,  intensity=8)
    speed_disp = Display(spi, CS_SPEED, intensity=8)

    # Startup: brief brightness sweep
    for d in (wind_disp, speed_disp):
        for i in list(range(0, 12, 2)) + list(range(11, -1, -2)):
            d.set_intensity(i)
            utime.sleep_ms(30)
        d.set_intensity(8)

    # Show dashes while waiting for first data
    wind_disp.show(_render(None, 0))
    speed_disp.show(_render(None, 0))

    # Set up non-blocking read on stdin (USB CDC)
    poll = select.poll()
    poll.register(sys.stdin, select.POLLIN)

    buf = b''
    while True:
        events = poll.poll(200)   # 200 ms timeout
        if events:
            try:
                chunk = sys.stdin.buffer.read(64)
                if chunk:
                    buf += chunk
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = ujson.loads(line)
                            wind_disp.show(_render(
                                msg.get('wind'),
                                msg.get('wind_trend', 0) or 0,
                            ))
                            speed_disp.show(_render(
                                msg.get('speed'),
                                msg.get('speed_trend', 0) or 0,
                            ))
                        except Exception:
                            pass
            except Exception:
                pass


main()
