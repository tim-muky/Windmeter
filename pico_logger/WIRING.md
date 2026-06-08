# WindmeterV3 — Detailed Wiring Plan

Complete build wiring for the Pico W instrument. Everything runs from **one USB
power bank**; all 5 V loads share the Pico's VBUS rail and there is one common
ground.

Pin references are **physical Pico pins (1–40)** with the GP name in brackets,
so you can count pads on the board rather than guess.

**Contents**
1. [Block diagram](#1-block-diagram)
2. [Wiring bill of materials](#2-wiring-bill-of-materials)
3. [Conventions (wire colours & gauge)](#3-conventions)
4. [Power distribution & current budget](#4-power-distribution--current-budget)
5. [Grounding strategy](#5-grounding-strategy)
6. [Complete netlist (every wire)](#6-complete-netlist)
7. [Module-by-module detail](#7-module-by-module-detail)
8. [Full Pico W pin map (all 40 pins)](#8-full-pico-w-pin-map)
9. [Enclosure & masthead cabling](#9-enclosure--masthead-cabling)
10. [Assembly sequence + continuity checks](#10-assembly-sequence)
11. [Power-on bring-up](#11-power-on-bring-up)
12. [Troubleshooting](#12-troubleshooting)
13. [Quick reference](#13-quick-reference)

---

## 1. Block diagram

```
                         ┌──────────────────────────────┐
   USB power bank ──USB──►│ Raspberry Pi Pico W          │
   (always-on mode)       │                              │
                          │  VBUS(40) ─► 5 V rail ────────┼──► MAX7219 #1 VCC (wind)
                          │                               ├──► MAX7219 #2 VCC (boat)
                          │                               ├──► GPS VIN
                          │                               └──► bulk cap 470–1000 µF
                          │                               │
                          │  3V3(36)  ─► 3.3 V rail ───────┼──► microSD VCC
                          │                               │
                          │  GND      ─► GND rail ─────────┼──► every module GND, buzzer −,
                          │                               │    anemometer, cap −
                          │  SPI0  (GP5/6/7/8) ───────────┼──► MAX7219 #1 + #2 (shared CLK/DIN)
                          │  SPI1  (GP10/11/12/13) ───────┼──► microSD
                          │  UART0 (GP0/1) ───────────────┼──► GPS
                          │  GP15 ────────────────────────┼──► anemometer (internal pull-up)
                          │  GP14 ────────────────────────┼──► buzzer +
                          └──────────────────────────────┘
```

---

## 2. Wiring bill of materials

Parts needed for the *wiring itself* (the modules are in the main hardware list):

| Item | Qty | Spec |
|---|---|---|
| Hook-up wire | ~2 m | 24 AWG stranded for signals; **22 AWG for the 5 V & GND rails** (display current) |
| Bulk capacitor | 1 | **470–1000 µF, ≥10 V** electrolytic (16 V gives margin) |
| Ceramic decoupling cap | 1–2 | 100 nF, only if a module lacks its own (most MAX7219 boards have it) |
| 2-row screw-terminal / perfboard rail | 1 | to make the 5 V and GND distribution nodes |
| JST or marine plug for the anemometer lead | 1 | so the masthead cable is unpluggable |
| Heatshrink assortment | — | insulate splices/joints |
| **Optional** anemometer line protection: 1 kΩ resistor + 10 nF cap | 1 ea | RC filter / GPIO protection on a long masthead lead (see §7.5) |
| **Optional** TVS / 3.3 V zener on anemometer line | 1 | surge clamp for a long exposed cable |

---

## 3. Conventions

**Wire colours** (used throughout this doc — adapt to what you have, but stay
consistent):

| Colour | Use |
|---|---|
| 🔴 Red | 5 V (VBUS rail) |
| 🟠 Orange | 3.3 V rail |
| ⚫ Black | GND |
| 🟡 Yellow | SPI clock (CLK/SCK) |
| 🟢 Green | SPI data out (DIN/MOSI) |
| 🔵 Blue | SPI data in / chip-select (MISO/CS) |
| ⚪ White / grey | UART, anemometer, buzzer |

**Gauge:** 22 AWG for the 5 V and GND rails (they carry the combined display
current); 24–26 AWG is fine for everything else. Keep SPI and UART runs short
(< 15 cm inside the box).

---

## 4. Power distribution & current budget

Everything is fed from the bank through the Pico's micro-USB. **VBUS (pin 40) is
that same 5 V passed straight through the connector** — use it as your 5 V rail.
Do **not** power the displays from 3V3 (pin 36); the Pico's regulator can't
supply that current and will brown out.

Estimated current draw:

| Load | Typical | Peak |
|---|---|---|
| Pico W (WiFi off) | 35 mA | 100 mA |
| GPS NEO-M9N | 25 mA | 35 mA (acquiring) |
| MAX7219 ×2 @ intensity 8, a few digits | 80–160 mA | — |
| MAX7219 ×2 worst case (all LEDs, full bright) | — | ~600 mA–1 A |
| microSD (writes) | 30 mA | 100 mA |
| Buzzer (sounding) | 30 mA | — |
| **Total** | **~250–400 mA** | **~0.8 A** |

→ A **2 A** power bank and a decent cable have ample margin. The firmware runs
the displays at intensity 8, so you'll sit at the "typical" figures.

**Build the rails first:** run one stout red wire from VBUS(40) and one black
from GND(38) to a 2-row terminal strip; branch every 5 V and GND connection from
there (star distribution — see §5). Put the bulk cap across these two rails.

---

## 5. Grounding strategy

Use a **star ground**: every module's GND returns to the common GND rail node,
not daisy-chained module-to-module. This matters because the displays' switching
current shouldn't share a ground path with the GPS or the anemometer signal
return (it adds noise / false counts).

```
                       ┌─► MAX7219 #1 GND
                       ├─► MAX7219 #2 GND
   Pico GND(38) ──────►●  (GND rail node)  ─┬─► GPS GND
        Pico GND(3) ───┘                     ├─► microSD GND
   (a 2nd ground wire                        ├─► buzzer −
    for display return                       ├─► anemometer leg B
    is good practice)                        └─► bulk cap −
```

Give the two displays their own GND wires straight to the rail. Adding a second
ground wire from Pico **pin 3** to the rail (alongside pin 38) gives the display
return current a low-impedance path.

---

## 6. Complete netlist

Every wire in the build. "Bus" wires (CLK/DIN go to both displays) can be run as
two wires from the Pico pad, or one wire to display #1 and a short jumper from
display #1 to display #2 — both are noted.

### Power rails

| # | From | To | Colour |
|---|---|---|---|
| W1 | Pico VBUS — pin 40 | 5 V rail node | 🔴 22 AWG |
| W2 | Pico 3V3 OUT — pin 36 | 3.3 V rail node | 🟠 |
| W3 | Pico GND — pin 38 | GND rail node | ⚫ 22 AWG |
| W4 | Pico GND — pin 3 | GND rail node (2nd return) | ⚫ 22 AWG |

### 5 V rail → loads

| # | From | To | Colour |
|---|---|---|---|
| W5 | 5 V rail | MAX7219 #1 VCC | 🔴 |
| W6 | 5 V rail | MAX7219 #2 VCC | 🔴 |
| W7 | 5 V rail | GPS VIN/VCC | 🔴 |
| W8 | 5 V rail | bulk cap **+** | 🔴 |

### 3.3 V rail → loads

| # | From | To | Colour |
|---|---|---|---|
| W9 | 3.3 V rail | microSD VCC | 🟠 |

### GND rail → returns

| # | From | To | Colour |
|---|---|---|---|
| W10 | GND rail | MAX7219 #1 GND | ⚫ |
| W11 | GND rail | MAX7219 #2 GND | ⚫ |
| W12 | GND rail | GPS GND | ⚫ |
| W13 | GND rail | microSD GND | ⚫ |
| W14 | GND rail | buzzer **−** | ⚫ |
| W15 | GND rail | anemometer leg B | ⚫ |
| W16 | GND rail | bulk cap **−** | ⚫ |

### Signals — displays (SPI0)

| # | From | To | Colour |
|---|---|---|---|
| W17 | Pico GP6 — pin 9 | MAX7219 #1 CLK | 🟡 |
| W18 | Pico GP6 — pin 9 (or #1 CLK) | MAX7219 #2 CLK | 🟡 |
| W19 | Pico GP7 — pin 10 | MAX7219 #1 DIN | 🟢 |
| W20 | Pico GP7 — pin 10 (or #1 DIN) | MAX7219 #2 DIN | 🟢 |
| W21 | Pico GP5 — pin 7 | MAX7219 #1 CS | 🔵 |
| W22 | Pico GP8 — pin 11 | MAX7219 #2 CS | 🔵 |

### Signals — GPS (UART0, TX/RX cross over)

| # | From | To | Colour |
|---|---|---|---|
| W23 | Pico GP0 (TX) — pin 1 | GPS **RX** | ⚪ |
| W24 | Pico GP1 (RX) — pin 2 | GPS **TX** | 🩶 |

### Signals — microSD (SPI1)

| # | From | To | Colour |
|---|---|---|---|
| W25 | Pico GP10 — pin 14 | SD SCK/CLK | 🟡 |
| W26 | Pico GP11 — pin 15 | SD MOSI/DI | 🟢 |
| W27 | Pico GP12 — pin 16 | SD MISO/DO | 🔵 |
| W28 | Pico GP13 — pin 17 | SD CS | 🟣 |

### Signals — anemometer & buzzer

| # | From | To | Colour |
|---|---|---|---|
| W29 | Pico GP15 — pin 20 | anemometer leg A (signal) | ⚪ |
| W30 | Pico GP14 — pin 19 | buzzer **+** | ⚪ |

**30 wires total.** (Fewer if you jumper the display CLK/DIN bus between the two
modules instead of running W18/W20 back to the Pico.)

---

## 7. Module-by-module detail

Breakout boards vary in silkscreen labels; common variants are listed.

### 7.1 Power rails + bulk capacitor (build this first)

```
   Pico pin40 VBUS ──🔴W1──►●═══════════════════ 5 V rail ═══════════════►
                            │           │            │           │
                          [+]│         to #1        to #2       to GPS
                       470–1000µF      VCC          VCC         VIN
                          [−]│
   Pico pin38 GND ───⚫W3──►●═══════════════════ GND rail ═══════════════►
   Pico pin3  GND ───⚫W4──►┘ (same node)
```

- Capacitor polarity: the striped leg is **−** → GND rail. Reversed electrolytics
  can burst.
- Place the cap physically next to the two displays.

### 7.2 Displays — 2× MAX7219 "FC-16" 4-in-1

Each module has a **5-pin INPUT header** (use this one) and a 5-pin OUTPUT header
(for daisy-chaining — leave unused). Input labels: **VCC, GND, DIN, CS, CLK**.

```
   Pico                         MAX7219 #1 (WIND)        MAX7219 #2 (BOAT)
   pin 9  GP6  ─🟡─┬──────────► CLK                      
                  └────────────────────────────────────► CLK
   pin 10 GP7  ─🟢─┬──────────► DIN
                  └────────────────────────────────────► DIN
   pin 7  GP5  ─🔵────────────► CS
   pin 11 GP8  ─🔵────────────────────────────────────► CS
   5 V rail    ─🔴────────────► VCC ───────────────────► VCC
   GND rail    ─⚫────────────► GND ───────────────────► GND
```

- CLK and DIN are a **shared bus**; CS is **separate** per module (that's how the
  firmware addresses them: GP5 = wind, GP8 = boat).
- Confirm you're on the **arrow-IN** side of each module. If a display is blank
  but its neighbour works, you're likely on the OUT header.
- 5 V VCC with 3.3 V logic from the Pico works on virtually all FC-16 modules. If
  one is unreliable, power that module from 3V3 instead, or add a 74HCT245/125
  buffer on CLK/DIN/CS.

### 7.3 GPS — u-blox NEO-M9N

Pins used: **VCC/VIN, GND, TX, RX**. (Ignore PPS/SDA/SCL/SAFEBOOT/RESET.)

```
   pin 1  GP0 (Pico TX) ─⚪──► GPS RX
   pin 2  GP1 (Pico RX) ◄─🩶── GPS TX
   5 V rail             ─🔴──► VIN   (most M9N boards have a regulator: 3.3–5 V OK)
   GND rail             ─⚫──► GND
```

- **TX↔RX cross over.** TX-to-TX gives no data.
- If your specific board is **3.3 V-only** (no regulator on the silkscreen), feed
  VCC from the **3.3 V rail** instead of 5 V.
- Mount the antenna with a clear view of the sky; keep it away from the GPS being
  right under a big metal mast fitting if possible.
- Default baud 38400 (`GPS_BAUD` in `config.py`); drop to 9600 if no data.

### 7.4 microSD — SPI breakout

Pin labels differ by board: **VCC** may be `3V3`/`5V`/`VCC`; data pins may be
`MISO/MOSI/SCK/CS` or `DO/DI/CLK/CS`.

```
   pin 14 GP10 ─🟡──► SCK / CLK
   pin 15 GP11 ─🟢──► MOSI / DI / CMD
   pin 16 GP12 ◄─🔵── MISO / DO / DAT0
   pin 17 GP13 ─🟣──► CS
   3.3 V rail  ─🟠──► VCC      (use the 3V3 input on a 3.3 V-native board)
   GND rail    ─⚫──► GND
```

- Prefer a **3.3 V-native** breakout. On cheap "5 V" Catalex-type modules with an
  onboard regulator + level shifter, feed their **5 V** pin from the 5 V rail
  instead — but then keep the SPI wires short, as those level shifters can be
  marginal.
- Format the card **FAT32** before first use.

### 7.5 Anemometer (the survivor)

Two wires from a reed/hall switch. The firmware enables the Pico's **internal
pull-up**, so no external resistor is required for basic operation.

```
   pin 20 GP15 ─⚪W29──► anemometer leg A (signal)
   GND rail    ─⚫W15──► anemometer leg B
```

**Optional, recommended for a long masthead cable** (adds noise immunity and
protects the GPIO):

```
   pin 20 GP15 ──┬── 1 kΩ ──► anemometer leg A
                 │
               10 nF
                 │
   GND rail ─────┴──────────► anemometer leg B
```

- The 1 kΩ series resistor limits current into the pin if the line ever sees a
  surge; the 10 nF cap to GND forms an RC low-pass (~µs with the resistor, ~ms
  with the internal pull-up) that smooths reed bounce. Harmless at the
  anemometer's few-Hz rate.
- For an exposed run you can add a small **TVS or 3.3 V zener** from GP15 to GND
  as a surge clamp.
- `ANEMO_DEBOUNCE_MS` in firmware (default 4 ms) handles bounce in software too.

### 7.6 Gust buzzer

**2-pin active buzzer** (most common): longer leg is **+**.

```
   pin 19 GP14 ─⚪W30──► buzzer +
   GND rail    ─⚫W14──► buzzer −
```

**3-pin buzzer module** (VCC / GND / I-O or SIG):

```
   pin 19 GP14 ────────► SIG / I-O
   3.3 V rail  ────────► VCC
   GND rail    ────────► GND
```

The firmware drives GP14 with PWM, so a **passive** piezo also works (it'll tone
at `BUZZER_FREQ`). An active buzzer is loudest for an alarm.

---

## 8. Full Pico W pin map

Used pins marked ◄ / ►; everything else is free for future expansion.

```
                      ┌──────── USB ────────┐
   ► GPS RX    GP0  ──┤ 1                 40 ├──  VBUS    ► 5 V rail
   ◄ GPS TX    GP1  ──┤ 2                 39 ├──  VSYS
     GND ─────────────┤ 3 ────────────────38 ├──  GND     ► GND rail
                GP2  ──┤ 4                 37 ├──  3V3_EN
                GP3  ──┤ 5                 36 ├──  3V3(OUT) ► 3.3 V rail
                GP4  ──┤ 6                 35 ├──  ADC_VREF
   ► DISP1 CS  GP5  ──┤ 7                 34 ├──  GP28
     GND ─────────────┤ 8                 33 ├──  GND/AGND
   ► DISP CLK  GP6  ──┤ 9                 32 ├──  GP27
   ► DISP DIN  GP7  ──┤10                 31 ├──  GP26
   ► DISP2 CS  GP8  ──┤11                 30 ├──  RUN
                GP9  ──┤12                 29 ├──  GP22
     GND ─────────────┤13                 28 ├──  GND
   ► SD SCK    GP10 ──┤14                 27 ├──  GP21
   ► SD MOSI   GP11 ──┤15                 26 ├──  GP20
   ◄ SD MISO   GP12 ──┤16                 25 ├──  GP19
   ► SD CS     GP13 ──┤17                 24 ├──  GP18
     GND ─────────────┤18                 23 ├──  GND
   ► BUZZER +  GP14 ──┤19                 22 ├──  GP17
   ◄ ANEMO     GP15 ──┤20                 21 ├──  GP16
                      └─────────────────────┘

   Power pins used:  40 (VBUS→5 V),  36 (3V3→3.3 V),  3 & 38 (GND)
   Free for later:   GP2–4, GP9, GP16–22, GP26–28 (3× ADC), plus spare GNDs
```

---

## 9. Enclosure & masthead cabling

- **Box:** IP65+ enclosure; either a clear-lid box or cut windows for the two
  matrices behind a clear acrylic/polycarbonate panel. Bed the panel in sealant.
- **Glands:** sealed cable glands for (a) the anemometer lead and (b) the GPS
  antenna lead. Don't run cables through unsealed holes.
- **Anemometer connector:** fit a **JST/marine 2-pin plug** at the box so the
  masthead lead unplugs — and so a future break is found at a connector, not by
  re-cutting wire. Strain-relieve both sides.
- **Power:** the USB cable to the bank is the one non-sealed entry — keep the
  bank inside the cabin/dry bag and run a short cable, or use a gland-friendly
  panel-mount USB.
- **Mounting:** solder to perfboard and standoff-mount it; do **not** leave the
  Pico/modules on loose Dupont jumpers — vibration works them loose. Add a dab of
  hot glue / conformal coat on connectors in the marine environment.

---

## 10. Assembly sequence

Build and verify in stages. Multimeter in **continuity** and **DC volts**.

1. **Rails, unpowered.** Wire W1–W4 and the bulk cap. With a meter, check
   **5 V rail ↔ GND rail is NOT shorted** (continuity should *not* beep). Verify
   cap polarity.
2. **Power check.** Plug the bank in (nothing else connected yet). Measure
   **5 V rail → GND = ~5 V**, and **Pico 3V3(36) → GND = ~3.3 V**. Pico on-board
   LED behaviour per your MicroPython.
3. **Displays.** Wire W5/W6, W10/W11, W17–W22. Power up: brightness sweep, then
   `----`, then wind `0.0`. If a module is blank, recheck IN-side header and CS.
4. **Anemometer.** Wire W15, W29 (+ optional RC). Spin it — wind display climbs.
5. **GPS.** Wire W7, W12, W23/W24. Outdoors, wait for fix (can take minutes
   cold). Boat-speed display leaves `----`; a `WIND_*.csv` appears on the card.
6. **microSD.** Wire W9, W13, W25–W28. Confirm the CSV grows ~1 row/second.
7. **Buzzer.** Wire W14, W30. Temporarily set `GUST_THRESHOLD_KN` low to hear it.

After each stage, re-check the **5 V↔GND not-shorted** test before powering.

---

## 11. Power-on bring-up

| Stage | Expected on the displays | Where to look if not |
|---|---|---|
| Power applied | both displays sweep brightness, then show `----` | rails (§10.2), display IN header |
| ~1 s after boot | wind shows `0.0` | anemometer/display wiring |
| Spin anemometer | wind value rises with speed | W29/W15, debounce, `KMH_PER_HZ` |
| GPS fix (outdoors) | boat speed leaves `----`; SD file created | `GPS_BAUD`, TX/RX swap, antenna sky view |
| Moving | boat speed tracks SOG; CSV grows | SD wiring, card format |
| Gust > threshold | buzzer sounds | W30, threshold value, buzzer polarity |

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Pico keeps resetting when displays update | VBUS sag on LED current | add/upsize the **bulk cap**; better bank/cable; lower `DISP_INTENSITY` |
| One display blank | wired to OUT header, or CS swapped | move to IN side; check W21/W22 |
| Both displays garbled | CLK/DIN swapped or loose | verify W17–W20; shorten wires |
| Wind stuck at 0.0 | anemometer not pulling GP15 low | check W29/W15; confirm internal pull-up (don't also wire an external pull-up to 5 V) |
| Wind reads wildly high | electrical noise counted as pulses | add the RC filter (§7.5); star-ground; raise `ANEMO_DEBOUNCE_MS` |
| Boat speed always `----` | no GPS data | swap TX/RX (W23/W24); set `GPS_BAUD=9600`; sky view |
| No CSV on card | SD not mounting | reseat card; FAT32; check W25–W28, W9/W13; try lower SD SPI baud |
| Buzzer silent | polarity / wrong pin | swap buzzer leads; confirm W30 on GP14 |
| Wind value off by a constant factor | calibration | trim `KMH_PER_HZ` |

---

## 13. Quick reference

| Function | Pico pin | GP | Module pin |
|---|---|---|---|
| 5 V rail (from bank) | 40 | VBUS | displays VCC, GPS VIN, cap + |
| 3.3 V rail | 36 | 3V3 | SD VCC |
| GND rail | 38 (+3) | GND | all GND, cap −, buzzer − |
| Display CLK (bus) | 9 | GP6 | both CLK |
| Display DIN (bus) | 10 | GP7 | both DIN |
| Display 1 CS (wind) | 7 | GP5 | #1 CS |
| Display 2 CS (boat) | 11 | GP8 | #2 CS |
| GPS (Pico TX→) | 1 | GP0 | GPS RX |
| GPS (Pico RX←) | 2 | GP1 | GPS TX |
| SD SCK | 14 | GP10 | SCK |
| SD MOSI | 15 | GP11 | MOSI |
| SD MISO | 16 | GP12 | MISO |
| SD CS | 17 | GP13 | CS |
| Buzzer + | 19 | GP14 | + |
| Anemometer | 20 | GP15 | signal (other leg → GND) |

Bulk cap **470–1000 µF** across the 5 V/GND rails, by the displays. Star-ground
everything. Connector on the anemometer lead.
