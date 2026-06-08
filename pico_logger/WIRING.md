# WindmeterV3 — Wiring Plan

Single Raspberry Pi Pico W, powered from one USB power bank. Everything shares
that 5 V source and a common ground. Pin numbers below are **physical pins** on
the Pico (1–40) with the GP name in brackets, so you can count pads on the board.

```
 USB power bank ──micro-USB──► Pico W
                                 │
                                 ├─ VBUS (pin 40, 5 V) ──► 5 V rail ──► MAX7219 ×2 VCC, GPS VIN
                                 ├─ 3V3  (pin 36, 3.3 V) ─► microSD VCC
                                 └─ GND  (many pins) ─────► common GND rail
```

The Pico's **VBUS is the bank's 5 V passed straight through** — that's your 5 V
rail, not a second supply. The Pico's own 3.3 V regulator (pin 36) only feeds
the SD card's logic; never hang the displays off it.

## Power rails

| Rail | From Pico | Feeds |
|---|---|---|
| **5 V** | VBUS — **pin 40** | both MAX7219 `VCC`, GPS `VIN`, the bulk capacitor + |
| **3.3 V** | 3V3 OUT — **pin 36** | microSD `VCC` |
| **GND** | any GND — pins 3, 8, 13, 18, 23, 28, 38 | every module GND, anemometer, buzzer −, capacitor − |

Run a short 5 V wire and a GND wire to a small distribution point (a 2-rail
strip on the perfboard), then branch to each module from there.

## Connections

### Displays — 2× MAX7219 4-in-1 (SPI0, shared bus, separate CS)
CLK and DIN are **bused to both** modules; each module gets its own CS.

| Pico pin | → | Display 1 (wind) | Display 2 (boat) |
|---|---|---|---|
| pin 9  (GP6)  | → | CLK | CLK |
| pin 10 (GP7)  | → | DIN | DIN |
| pin 7  (GP5)  | → | CS  | — |
| pin 11 (GP8)  | → | —   | CS |
| 5 V rail (VBUS) | → | VCC | VCC |
| GND rail | → | GND | GND |

### GPS — u-blox NEO-M9N (UART0)
TX/RX cross over: GPS **TX → Pico RX**, GPS **RX → Pico TX**.

| Pico pin | → | GPS module |
|---|---|---|
| pin 1 (GP0, TX) | → | RX |
| pin 2 (GP1, RX) | ← | TX |
| 5 V rail (VBUS) | → | VIN *(if the board has a regulator; use 3V3 if it's a bare 3.3 V module)* |
| GND rail | → | GND |

### microSD — SPI breakout (3.3 V-native)
| Pico pin | → | SD module |
|---|---|---|
| pin 14 (GP10) | → | SCK / CLK |
| pin 15 (GP11) | → | MOSI / DI / CMD |
| pin 16 (GP12) | ← | MISO / DO / DAT0 |
| pin 17 (GP13) | → | CS |
| 3.3 V (pin 36) | → | VCC |
| GND rail | → | GND |

### Anemometer (the survivor)
No external pull-up — the firmware enables the Pico's internal one.

| Pico pin | → | Anemometer |
|---|---|---|
| pin 20 (GP15) | → | signal (one leg) |
| GND rail | → | other leg |

### Gust buzzer (active or passive)
| Pico pin | → | Buzzer |
|---|---|---|
| pin 19 (GP14) | → | + |
| GND rail | → | − |

## Bulk capacitor (do not skip)

Solder one **470–1000 µF / ≥10 V electrolytic across the 5 V rail and GND**,
physically close to the two displays. The LED current jumps as digits change;
this cap keeps VBUS from sagging and rebooting the Pico.

```
   5 V rail ───┬───────────► MAX7219 VCC (both)
              ─┴─  +
          470–1000 µF
              ─┬─  −
    GND rail ──┴───────────► MAX7219 GND (both)
```

Watch polarity: the capacitor's **−** stripe goes to GND.

## Pico W pin map (pins used)

```
                ┌─────── USB ───────┐
   GPS RX ◄ GP0 │ 1               40│ VBUS  ──► 5 V rail
   GPS TX ► GP1 │ 2               39│ VSYS
        GND ────│ 3               38│ GND ──────► GND rail
            GP2 │ 4               37│ 3V3_EN
            GP3 │ 5               36│ 3V3 OUT ──► SD VCC (3.3 V)
            GP4 │ 6               35│ ADC_VREF
  DISP1 CS  GP5 │ 7               34│ GP28
        GND ────│ 8               33│ GND
  DISP CLK  GP6 │ 9               32│ GP27
  DISP DIN  GP7 │10               31│ GP26
  DISP2 CS  GP8 │11               30│ RUN
            GP9 │12               29│ GP22
        GND ────│13               28│ GND
  SD SCK   GP10 │14               27│ GP21
  SD MOSI  GP11 │15               26│ GP20
  SD MISO  GP12 │16               25│ GP19
  SD CS    GP13 │17               24│ GP18
        GND ────│18               23│ GND
  BUZZER + GP14 │19               22│ GP17
  ANEMO    GP15 │20               21│ GP16
                └───────────────────┘
```

## Build & test order

1. **Pico alone** on the power bank — confirm it boots and runs `main.py`
   (displays do a brightness sweep). Add the bulk cap now.
2. **Displays** — wire both; you should see dashes `----`, then `0.0` on wind.
3. **Anemometer** — spin it; the wind display should climb.
4. **GPS** — wire UART; once it gets a fix outdoors, the boat-speed display
   leaves `----` and a `WIND_*.csv` appears on the SD card. (No fix? try
   `GPS_BAUD = 9600` in `config.py`.)
5. **SD card** — check the CSV grows ~1 row/second, then open it in the viewer.
6. **Buzzer** — temporarily lower `GUST_THRESHOLD_KN` to test the alarm.

Solder everything to perfboard (not loose Dupont) and use a connector on the
anemometer lead — vibration and a single cut conductor are what started all this.
