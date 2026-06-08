# WindmeterV3 — Pico W Logger

Standalone MicroPython firmware for a **Raspberry Pi Pico W (SC0918)**. It
replaces the old Raspberry Pi + Pico + PiLogger head with a single board that
counts the anemometer itself, reads the GPS, drives the two MAX7219 displays,
logs to microSD, and sounds a gust buzzer.

Trip distance and max wind/speed are **not** shown on the boat — they're
computed from the SD log by the macOS viewer (`../viewer/index.html`).

## Wiring (Pico W GP numbers)

> Full pin-by-pin plan with physical pin numbers, power rails, the bulk
> capacitor and a build/test order: **[WIRING.md](WIRING.md)**.

| Pico pin | Connects to | Function |
|---|---|---|
| **GP1** ← | GPS **TX** | UART0 RX (NMEA in) |
| GP0 → | GPS **RX** | UART0 TX (config, optional) |
| **GP5** → | Display 1 **CS** | wind display |
| **GP6** → | both displays **CLK** | SPI0 SCK |
| **GP7** → | both displays **DIN** | SPI0 MOSI |
| **GP8** → | Display 2 **CS** | boat-speed display |
| **GP10 / GP11 / GP12** | SD **CLK / MOSI / MISO** | SPI1 |
| **GP13** → | SD **CS** | |
| **GP14** → | buzzer **+** | gust alarm (PWM) |
| **GP15** ← | **anemometer** (other leg → GND) | pulse input, internal pull-up |
| **VBUS (pin 40)** → | MAX7219 **VCC (5 V)**, GPS VIN | 5 V from the USB power bank |
| **3V3 (pin 36)** → | SD VCC | 3.3 V |
| **GND** | everything | common ground |

Power the whole thing from a **USB power bank** into the Pico's micro-USB.
Pick a bank with an **always-on / low-current mode** — many banks auto-switch
off under the Pico's small load.

MAX7219 modules run on 5 V (VBUS) with 3.3 V SPI logic — this works on the vast
majority of modules; if one is flaky, power it from 3V3 instead, or add a
74HCT buffer.

## Flashing

1. Install **MicroPython** for the Pico W (hold BOOTSEL, plug in USB, drop the
   `.uf2` onto the `RPI-RP2` drive). Get it from micropython.org.
2. Copy these three files to the Pico's filesystem (Thonny, `mpremote`, or
   `rshell`):
   - `main.py`
   - `config.py`
   - `sdcard.py`
3. Reset. The displays do a brightness sweep, then show dashes until data
   arrives.

```
mpremote connect auto cp config.py sdcard.py main.py :
mpremote connect auto reset
```

## Calibration

`KMH_PER_HZ` in `config.py` is seeded to **1.44** — derived from your scope
reading (5.24 Hz ≈ 7.5 km/h). To trim it: drive/tow the anemometer at a known
speed (GPS SOG in still air, or a handheld meter) and scale the constant so the
display matches.

`GPS_BAUD` defaults to **38400** (NEO-M9N default). If you get no GPS fix, try
**9600** — some modules ship at that rate.

## Log format

One CSV file per power-on on the SD card, named from the first GPS fix, e.g.
`WIND_20260608_143201.csv`:

```
utc,lat,lon,sog_kn,wind_kn,wind_avg_kn,cog,sats,fix
2026-06-08T14:32:01Z,54.321100,10.143200,4.10,3.90,3.70,212.4,9,1
```

Rows are written once per second **after** the first GPS fix (position logging
needs GPS anyway); wind still shows on the display before a fix. Each row is
flushed immediately, so a sudden power cut loses at most the last line.

Open any of these files in the macOS viewer to see the track, the wind/boat
speed ribbon, and the trip stats.
