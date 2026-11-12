#!/usr/bin/env python3
"""
Anemometer-Test
===============
Simple bench test for the wind sensor (anemometer) connected to the
PiLogger One "Imp"/"GND" pulse input.  Answers two questions live on the
console:

  1. Kommt ein Signal an?        – pulses per second / per measurement window
  2. Ist es stark genug / sauber? – (GPIO mode) pulse widths, contact bounce,
                                    idle level.  Voltage levels are checked
                                    with a multimeter, see docs/anemometer_test.md

Three signal sources – pick the one that matches your setup:

  --source rawdata   (default, safe)
      Polls the running PiLogger WebMonitor (http://localhost:8080/rawdata/)
      and converts its wind value back into pulses.  Nothing has to be
      stopped; SailMon keeps working.

  --source i2c
      Reads the PiLogger pulse counter (register 0x40) directly over I2C,
      triggered by the PiLogger interrupt on GPIO 4 – exactly like
      PiLogger-bottle.py does.  Gives exact pulse counts but the WebMonitor
      must be stopped first:   sudo systemctl stop pilo-webmon
      (restart afterwards:     sudo systemctl start pilo-webmon)

  --source gpio
      The anemometer is wired directly to a free Raspberry Pi GPIO
      (default GPIO 17) and GND, internal pull-up enabled.  PiLogger is not
      involved.  Measures raw edges, debounced pulses, pulse (low) duration
      and contact bounce.  Works on any Pi, e.g. on the workbench.

Examples:
  python3 scripts/test_anemometer.py
  python3 scripts/test_anemometer.py --source i2c
  python3 scripts/test_anemometer.py --source gpio --pin 17 --duration 60
  python3 scripts/test_anemometer.py --csv /tmp/anemo.csv

Exit code: 0 = pulses were detected, 1 = no pulses detected, 2 = setup error.
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# ── Defaults (overridable from the SailMon config.py if present) ──────────────
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_DIR)
try:
    import config as _cfg                     # SailMon config.py
    DEFAULT_URL = _cfg.PILOGGER_URL
except Exception:                             # pragma: no cover – dev box
    DEFAULT_URL = "http://localhost:8080"

DEFAULT_I2C_ADDR   = 0x48    # PiLogger One slave address (72)
PILOGGER_IRQ_GPIO  = 4       # PiLogger "measurement done" interrupt line
DEFAULT_GPIO_PIN   = 17      # free GPIO for --source gpio
DEFAULT_FACTOR     = 1.44    # PiLogger default sensor constant (km/h per pulse/s)
DEFAULT_UNIT       = "km/h"

BAR_WIDTH = 20


# ── Small helpers ─────────────────────────────────────────────────────────────

def fetch_json(url, timeout=3.0):
    """GET a JSON document; raises on network/HTTP error."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def parse_float(s, default=None):
    """PiLogger returns numbers as padded strings, sometimes with a comma."""
    try:
        return float(str(s).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def bar(value, full_scale):
    """ASCII bar graph, `full_scale` = value that fills the whole bar."""
    if full_scale <= 0:
        full_scale = 1.0
    n = int(round(min(1.0, value / full_scale) * BAR_WIDTH))
    return "█" * n + "░" * (BAR_WIDTH - n)


def now_str():
    return time.strftime("%H:%M:%S")


class Stats:
    """Running statistics shared by all modes."""

    def __init__(self):
        self.t_start        = time.monotonic()
        self.factor         = DEFAULT_FACTOR   # set by the runner
        self.unit           = DEFAULT_UNIT
        self.windows        = 0
        self.windows_signal = 0
        self.pulses_total   = 0.0
        self.max_pps        = 0.0
        self.max_speed      = 0.0
        self.t_last_signal  = None

    def add_window(self, pulses, pps, speed=0.0):
        self.windows += 1
        self.pulses_total += pulses
        if pulses >= 0.5:                      # at least one pulse in window
            self.windows_signal += 1
            self.t_last_signal = time.monotonic()
        self.max_pps   = max(self.max_pps, pps)
        self.max_speed = max(self.max_speed, speed)

    @property
    def seen_signal(self):
        return self.windows_signal > 0

    def since_signal(self):
        if self.t_last_signal is None:
            return time.monotonic() - self.t_start
        return time.monotonic() - self.t_last_signal


class CsvLog:
    """Optional CSV recorder (one line per printed window)."""

    def __init__(self, path, header):
        self._f = open(path, "w", encoding="utf-8") if path else None
        if self._f:
            self._f.write(";".join(header) + "\n")

    def row(self, *cols):
        if self._f:
            self._f.write(";".join(str(c) for c in cols) + "\n")
            self._f.flush()

    def close(self):
        if self._f:
            self._f.close()


def print_summary(stats, extra=None):
    factor, unit = stats.factor, stats.unit
    dur = time.monotonic() - stats.t_start
    print()
    print("─" * 64)
    print(f"Zusammenfassung  (Testdauer {dur:.0f} s)")
    print(f"  Messfenster gesamt : {stats.windows}")
    print(f"  Fenster mit Signal : {stats.windows_signal}")
    print(f"  Pulse gesamt       : {stats.pulses_total:.0f}")
    print(f"  Maximum            : {stats.max_pps:.2f} Pulse/s"
          f"  ≙ {stats.max_pps * factor:.1f} {unit}")
    if extra:
        for line in extra:
            print("  " + line)
    print()
    if stats.seen_signal:
        print("  ERGEBNIS: ✔  SIGNAL ERKANNT – das Anemometer liefert Pulse.")
    else:
        print("  ERGEBNIS: ✘  KEIN SIGNAL – es wurden keine Pulse gezählt.")
        print("            → Verdrahtung Imp/GND, Kontakt (Multimeter-Test)"
              " und Sensor prüfen, siehe docs/anemometer_test.md")
    print("─" * 64)


# ── Mode 1: PiLogger WebMonitor /rawdata/ ─────────────────────────────────────

def run_rawdata(args, stats, csv):
    base = args.url.rstrip("/")

    # Read the PiLogger configuration once so we can convert the wind value
    # back into pulses.   WindAkt1 = count * FactPulse1 / MeasInter / TimPuFact
    try:
        raspi = fetch_json(base + "/getraspiconf/")
        pilo  = fetch_json(base + "/getpiloconf/")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"FEHLER: PiLogger WebMonitor unter {base} nicht erreichbar ({exc}).")
        print("        Läuft der Dienst?   sudo systemctl status pilo-webmon")
        return 2

    meas_inter = parse_float(raspi.get("MeasInter"), 2.0)
    tpf        = parse_float(pilo.get("TimPuFac"), 5.0) or 1.0
    factor     = parse_float(raspi.get("FactPulse1"), DEFAULT_FACTOR) or DEFAULT_FACTOR
    unit       = str(raspi.get("UnitPulse1", DEFAULT_UNIT)).strip() or DEFAULT_UNIT
    window     = meas_inter * tpf
    resolution = 0.1 / factor                 # pulses/s hidden by 0.1 rounding
    stats.factor, stats.unit = factor, unit

    print(f"Anemometer-Test – Quelle: PiLogger WebMonitor ({base})")
    print(f"  Messintervall {meas_inter:g} s × Pulszähl-Zeitfaktor {tpf:g}"
          f"  → Windwert alle {window:g} s neu")
    print(f"  Sensorkonstante {factor:g} {unit} pro Puls/s")
    if resolution > 0.3:
        print(f"  Hinweis: Anzeige in 0,1 {unit} → unter {resolution:.2f} Pulse/s"
              f" nicht auflösbar (für exakte Zählung: --source i2c)")
    if pilo.get("Fehler"):
        print(f"  WARNUNG vom PiLogger: {pilo['Fehler']}")
    print("  Jetzt die Schalen drehen / Wind machen.  Strg+C beendet.\n")
    print(f" {'Zeit':8} {'Wind':>12}  {'Pulse/s':>8} {'Pulse/Fenster':>13}"
          f"  {'Signal':{BAR_WIDTH}}")

    full_scale = max(10.0 * factor, 1.0)      # bar full at 10 pulses/s
    last_speed  = None
    t_last_line = 0.0
    errors      = 0

    try:
      while True:
        try:
            data = fetch_json(base + "/rawdata/", timeout=max(1.0, args.interval))
            errors = 0
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors += 1
            print(f" {now_str()}  !! WebMonitor nicht erreichbar: {exc}")
            if errors >= 5:
                print("FEHLER: 5× keine Antwort – Abbruch.")
                return 2
            time.sleep(args.interval)
            continue

        if data.get("Error"):
            print(f" {now_str()}  !! PiLogger meldet: {data['Error']}")

        speed = parse_float(data.get("PiLoWind1"), 0.0) or 0.0
        pps   = speed / factor
        per_w = pps * window
        t     = time.monotonic()

        # Print when the value changes, or at least once per window
        if speed != last_speed or (t - t_last_line) >= window:
            stats.add_window(per_w, pps, speed)
            if per_w >= 0.5:
                status = f"{bar(speed, full_scale)} OK"
            else:
                status = f"{bar(0, 1)} kein Signal (seit {stats.since_signal():.0f} s)"
            print(f" {now_str():8} {speed:8.1f} {unit:<4}  {pps:8.2f}"
                  f" {per_w:13.1f}  {status}")
            csv.row(now_str(), f"{speed:.1f}", unit, f"{pps:.3f}", f"{per_w:.1f}")
            last_speed  = speed
            t_last_line = t

        if args.duration and (t - stats.t_start) >= args.duration:
            break
        time.sleep(args.interval)
    except KeyboardInterrupt:
        pass

    print_summary(stats)
    return 0 if stats.seen_signal else 1


# ── Mode 2: direct I2C read of the PiLogger pulse counter ─────────────────────

def _pilogger_timing(bus, addr):
    """Read MeasInter and TimPuFact from the PiLogger (same regs as WebMonitor)."""
    time_base = bus.read_byte_data(addr, 0x12)
    lo        = bus.read_byte_data(addr, 0x13)
    hi        = bus.read_byte_data(addr, 0x14)
    tpf       = bus.read_byte_data(addr, 0x16)
    c_base    = {0: 1.0, 1: 1 / 4, 2: 1 / 64, 3: 1 / 512}.get(time_base, 1.0)
    meas_inter = (256 * hi + lo) * c_base
    return meas_inter, max(1, tpf)


def run_i2c(args, stats, csv):
    # Refuse to fight with the WebMonitor for the bus / interrupt line
    if not args.force:
        try:
            urllib.request.urlopen(args.url.rstrip("/") + "/", timeout=1.0)
            print("FEHLER: Der PiLogger WebMonitor läuft noch (antwortet auf "
                  f"{args.url}).")
            print("        Erst stoppen:  sudo systemctl stop pilo-webmon")
            print("        Danach wieder: sudo systemctl start pilo-webmon")
            print("        (oder --force, auf eigenes Risiko)")
            return 2
        except Exception:
            pass                                  # not running → good

    try:
        import smbus
    except ImportError:
        print("FEHLER: python3-smbus fehlt:  sudo apt install python3-smbus")
        return 2

    addr = args.i2c_addr
    try:
        bus = smbus.SMBus(1)
        meas_inter, tpf = _pilogger_timing(bus, addr)
        bus.read_word_data(addr, 0x40)            # dummy read
    except OSError as exc:
        print(f"FEHLER: I2C-Zugriff auf PiLogger (Adresse 0x{addr:02X}) "
              f"fehlgeschlagen: {exc}")
        print("        Prüfen:  i2cdetect -y 1   (PiLogger sollte bei 48 erscheinen)")
        return 2

    factor = args.factor if args.factor else DEFAULT_FACTOR
    unit   = args.unit   if args.unit   else DEFAULT_UNIT
    window = meas_inter * tpf
    stats.factor, stats.unit = factor, unit

    print(f"Anemometer-Test – Quelle: PiLogger I2C (0x{addr:02X}, Register 0x40)")
    print(f"  Messintervall {meas_inter:g} s × Pulszähl-Zeitfaktor {tpf}"
          f"  → Zählerstand alle {window:g} s")
    print(f"  Umrechnung: {factor:g} {unit} pro Puls/s  (--factor/--unit)")

    # Interrupt from the PiLogger on GPIO 4 fires once per measurement
    # interval; every `tpf`-th interrupt the counter register is valid.
    counts = []                                   # filled by callback
    lock   = threading.Lock()
    irq    = {"n": 0}
    button = None

    def on_irq():
        with lock:
            irq["n"] += 1
            if irq["n"] % tpf == 0:
                try:
                    counts.append(bus.read_word_data(addr, 0x40))
                except OSError:
                    counts.append(None)

    try:
        from gpiozero import Button
        button = Button(PILOGGER_IRQ_GPIO)        # pull-up, falling edge
        button.when_pressed = on_irq
        print(f"  Trigger: PiLogger-Interrupt auf GPIO {PILOGGER_IRQ_GPIO}")
    except Exception as exc:
        print(f"  Hinweis: kein GPIO-Interrupt ({exc}) → zeitgesteuertes Polling")
        button = None

    print("  Jetzt die Schalen drehen / Wind machen.  Strg+C beendet.\n")
    print(f" {'Zeit':8} {'Pulse':>6} {'Pulse/s':>8} {'≙ Wind':>12}"
          f"  {'Signal':{BAR_WIDTH}}")

    full_scale   = 10.0                            # bar full at 10 pulses/s
    t_next_poll  = time.monotonic() + window
    t_last_count = time.monotonic()

    try:
        while True:
            time.sleep(0.1)
            t = time.monotonic()
            with lock:
                pending, counts[:] = counts[:], []
            if button is None and t >= t_next_poll:
                t_next_poll += window
                try:
                    pending.append(bus.read_word_data(addr, 0x40))
                except OSError:
                    pending.append(None)

            for cnt in pending:
                t_last_count = t
                if cnt is None:
                    print(f" {now_str()}  !! I2C-Lesefehler")
                    continue
                pps   = cnt / window
                speed = pps * factor
                stats.add_window(cnt, pps, speed)
                if cnt > 0:
                    status = f"{bar(pps, full_scale)} OK"
                else:
                    status = f"{bar(0, 1)} kein Signal (seit {stats.since_signal():.0f} s)"
                print(f" {now_str():8} {cnt:6d} {pps:8.2f} {speed:8.1f} {unit:<4}"
                      f"  {status}")
                csv.row(now_str(), cnt, f"{pps:.3f}", f"{speed:.1f}", unit)

            if button is not None and (t - t_last_count) > 3 * window + 2:
                print(f" {now_str()}  !! Kein Interrupt vom PiLogger auf GPIO "
                      f"{PILOGGER_IRQ_GPIO} seit {t - t_last_count:.0f} s – "
                      "läuft pilo-webmon noch? HAT richtig gesteckt?")
                t_last_count = t

            if args.duration and (t - stats.t_start) >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if button is not None:
            button.close()

    print_summary(stats, extra=[f"Interrupts vom PiLogger : {irq['n']}"])
    return 0 if stats.seen_signal else 1


# ── Mode 3: anemometer directly on a Raspberry Pi GPIO ────────────────────────

def run_gpio(args, stats, csv):
    try:
        from gpiozero import Button
    except ImportError:
        print("FEHLER: python3-gpiozero fehlt:  sudo apt install python3-gpiozero")
        return 2

    factor = args.factor if args.factor else DEFAULT_FACTOR
    unit   = args.unit   if args.unit   else DEFAULT_UNIT
    debounce = args.debounce_ms / 1000.0
    stats.factor, stats.unit = factor, unit

    try:
        # bounce_time=None → we see every edge and do our own analysis
        button = Button(args.pin, pull_up=True, bounce_time=None)
    except Exception as exc:
        print(f"FEHLER: GPIO {args.pin} konnte nicht geöffnet werden: {exc}")
        return 2

    print(f"Anemometer-Test – Quelle: GPIO {args.pin} (Pull-up intern, "
          f"Puls = Pegel LOW)")
    print(f"  Verdrahtung: Sensor zwischen GPIO {args.pin} und GND; bei "
          "Open-Collector/Hall zusätzlich VCC an 3,3 V")
    print(f"  Entprellzeit {args.debounce_ms:g} ms, Umrechnung {factor:g} {unit}"
          " pro Puls/s")

    level = "LOW (Kontakt geschlossen?)" if button.is_pressed else "HIGH (offen, ok)"
    print(f"  Ruhepegel beim Start: {level}")
    if button.is_pressed:
        print("  → Dauer-LOW ohne Drehen deutet auf Kurzschluss oder einen"
              " Sensor mit Push-Pull-Ausgang (Ruhe = LOW) hin.")
    print("  Jetzt die Schalen drehen / Wind machen.  Strg+C beendet.\n")

    lock = threading.Lock()
    st = {
        "edges": 0,        # raw falling edges in current interval
        "pulses": 0,       # debounced pulses in current interval
        "glitches": 0,     # edges rejected as bounce
        "lows": [],        # low-phase durations (s) in current interval
        "t_fall": None,    # time of last falling edge
        "t_accept": -1.0,  # time of last accepted pulse
        "min_low": None,   # overall shortest low phase
        "tot_pulses": 0, "tot_glitches": 0,
    }

    def on_fall():
        t = time.monotonic()
        with lock:
            st["edges"] += 1
            st["t_fall"] = t
            if t - st["t_accept"] >= debounce:
                st["pulses"] += 1
                st["tot_pulses"] += 1
                st["t_accept"] = t
            else:
                st["glitches"] += 1
                st["tot_glitches"] += 1

    def on_rise():
        t = time.monotonic()
        with lock:
            if st["t_fall"] is not None:
                d = t - st["t_fall"]
                st["lows"].append(d)
                if st["min_low"] is None or d < st["min_low"]:
                    st["min_low"] = d

    button.when_pressed  = on_fall
    button.when_released = on_rise

    print(f" {'Zeit':8} {'Flanken':>7} {'Pulse':>5} {'Pulse/s':>8}"
          f" {'Low min/avg/max ms':>20} {'Prell':>5}  {'Signal':{BAR_WIDTH}}")

    full_scale = 10.0
    interval   = args.interval
    try:
        while True:
            time.sleep(interval)
            t = time.monotonic()
            with lock:
                edges, pulses, glitches, lows = (st["edges"], st["pulses"],
                                                 st["glitches"], st["lows"])
                st["edges"] = st["pulses"] = st["glitches"] = 0
                st["lows"] = []
            pps   = pulses / interval
            speed = pps * factor
            stats.add_window(pulses, pps, speed)

            if lows:
                lo_txt = (f"{min(lows)*1000:6.1f}/{sum(lows)/len(lows)*1000:6.1f}"
                          f"/{max(lows)*1000:6.1f}")
            else:
                lo_txt = f"{'–':>20}"
            if pulses > 0:
                status = f"{bar(pps, full_scale)} OK"
            else:
                lvl = "LOW" if button.is_pressed else "HIGH"
                status = (f"{bar(0, 1)} kein Signal (seit "
                          f"{stats.since_signal():.0f} s, Pegel {lvl})")
            print(f" {now_str():8} {edges:7d} {pulses:5d} {pps:8.2f}"
                  f" {lo_txt:>20} {glitches:5d}  {status}")
            csv.row(now_str(), edges, pulses, f"{pps:.3f}", f"{speed:.1f}", unit,
                    f"{min(lows)*1000:.2f}" if lows else "",
                    f"{max(lows)*1000:.2f}" if lows else "", glitches)

            if args.duration and (t - stats.t_start) >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        button.close()

    extra = []
    tot = st["tot_pulses"] + st["tot_glitches"]
    if tot:
        ratio = 100.0 * st["tot_glitches"] / tot
        extra.append(f"Prell-/Störflanken     : {st['tot_glitches']} von {tot}"
                     f" Flanken ({ratio:.0f} %)")
        if st["min_low"] is not None:
            extra.append(f"Kürzeste Low-Phase     : {st['min_low']*1000:.1f} ms")
        if ratio > 10:
            extra.append("→ Kontakt prellt stark: der PiLogger zählt dann zu viele"
                         " Pulse. Kondensator (z.B. 100 nF) parallel zum"
                         " Kontakt oder Sensor prüfen.")
        elif ratio > 0:
            extra.append("→ leichtes Prellen, für den PiLogger meist unkritisch.")
        else:
            extra.append("→ Signal sauber, kein Prellen erkannt.")
    print_summary(stats, extra=extra)
    return 0 if stats.seen_signal else 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Anemometer-Test: kommt ein Signal an, und wie sauber ist es?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Three signal sources")[0].strip())
    p.add_argument("--source", choices=("rawdata", "i2c", "gpio"), default="rawdata",
                   help="Signalquelle (Standard: rawdata = PiLogger WebMonitor)")
    p.add_argument("--url", default=DEFAULT_URL,
                   help=f"PiLogger WebMonitor URL (Standard: {DEFAULT_URL})")
    p.add_argument("--interval", type=float, default=1.0,
                   help="Abfrage-/Anzeigeintervall in Sekunden (Standard: 1.0)")
    p.add_argument("--duration", type=float, default=0,
                   help="Test nach N Sekunden automatisch beenden (0 = bis Strg+C)")
    p.add_argument("--i2c-addr", type=lambda s: int(s, 0), default=DEFAULT_I2C_ADDR,
                   help="PiLogger I2C-Adresse (Standard: 0x48)")
    p.add_argument("--force", action="store_true",
                   help="i2c: auch starten, wenn der WebMonitor noch läuft")
    p.add_argument("--pin", type=int, default=DEFAULT_GPIO_PIN,
                   help=f"gpio: BCM-GPIO des Sensors (Standard: {DEFAULT_GPIO_PIN})")
    p.add_argument("--debounce-ms", type=float, default=5.0,
                   help="gpio: Entprellzeit in ms (Standard: 5)")
    p.add_argument("--factor", type=float, default=None,
                   help="Sensorkonstante (Einheit pro Puls/s) für i2c/gpio-Anzeige")
    p.add_argument("--unit", default=None,
                   help="Einheit zur Sensorkonstante, z.B. km/h oder m/s")
    p.add_argument("--csv", default=None, help="Messwerte zusätzlich als CSV speichern")
    args = p.parse_args(argv)

    headers = {
        "rawdata": ["zeit", "wind", "einheit", "pulse_pro_s", "pulse_pro_fenster"],
        "i2c":     ["zeit", "pulse", "pulse_pro_s", "wind", "einheit"],
        "gpio":    ["zeit", "flanken", "pulse", "pulse_pro_s", "wind", "einheit",
                    "low_min_ms", "low_max_ms", "prellflanken"],
    }
    csv   = CsvLog(args.csv, headers[args.source])
    stats = Stats()
    runner = {"rawdata": run_rawdata, "i2c": run_i2c, "gpio": run_gpio}[args.source]

    try:
        rc = runner(args, stats, csv)
    except KeyboardInterrupt:                 # Ctrl+C during setup
        print("\nAbgebrochen.")
        rc = 1
    finally:
        csv.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
