"""
Anemometer-Test auf dem Raspberry Pi PICO
=========================================
MicroPython-Pulszähler für einen Reedkontakt-Windgeber (2 Adern) auf dem
Werkstatttisch, ohne Raspberry Pi und ohne PiLogger.

Verdrahtung (PICO-Pinnummern = physische Pins):
  Ader 1  → GP15 (Pin 20)
  Ader 2  → GND  (Pin 18)
  optional: 10 kΩ von GP15 nach 3V3 (Pin 36), um einen „härteren“ Pull-up
            ähnlich dem PiLogger-Eingang nachzubilden.  Ohne Widerstand
            arbeitet der interne Pull-up des PICO (ca. 50 kΩ), das reicht
            zum Zählen.

Starten:
  Thonny: Datei öffnen → Ausführen (F5), Ausgabe erscheint in der Shell.
  Oder:   mpremote run pico_firmware/anemo_test.py
  Stop:   Strg+C (zeigt die Zusammenfassung).

Die Onboard-LED leuchtet, solange der Kontakt geschlossen ist.

Ausgabe pro Sekunde:
  Flanken  alle fallenden Flanken (roh)
  Pulse    nach Entprellung (DEBOUNCE_MS)
  Low ms   Schließdauer pro Puls min/avg/max – unter 1 ms = Prellen
  Prell    verworfene Flanken
  ≙ Wind   Pulse/s × FACTOR (nur Orientierung)
"""

import machine
import micropython
import time

micropython.alloc_emergency_exception_buf(100)

# ─── Einstellungen ────────────────────────────────────────────────────────────
PIN         = 15        # GP15
DEBOUNCE_MS = 5         # Flanken kürzer als das nach einem Puls gelten als Prellen
FACTOR      = 1.44      # Einheit pro Puls/s (PiLogger-Standard: 1.44 km/h)
UNIT        = "km/h"
BAR_WIDTH   = 20
BAR_FULL    = 10.0      # Pulse/s, bei denen der Balken voll ist

_DEBOUNCE_US = DEBOUNCE_MS * 1000

# ─── Zähler (nur Integer, werden im Hard-IRQ verändert) ───────────────────────
n_fall   = 0            # fallende Flanken im laufenden Intervall
n_pulse  = 0            # entprellte Pulse im laufenden Intervall
n_glitch = 0            # verworfene Flanken im laufenden Intervall
low_sum  = 0            # Summe Schließdauern (µs) im Intervall
low_n    = 0
low_min  = 0
low_max  = 0
t_fall   = 0            # Zeitstempel letzte fallende Flanke (µs)
t_accept = -10000000    # Zeitstempel letzter akzeptierter Puls (µs)

pin = machine.Pin(PIN, machine.Pin.IN, machine.Pin.PULL_UP)
try:
    led = machine.Pin("LED", machine.Pin.OUT)     # PICO und PICO W
except Exception:
    led = machine.Pin(25, machine.Pin.OUT)


def _irq(p):
    global n_fall, n_pulse, n_glitch, low_sum, low_n, low_min, low_max
    global t_fall, t_accept
    t = time.ticks_us()
    v = p.value()
    led.value(1 - v)                       # LED an, solange Kontakt geschlossen
    if v == 0:                             # fallende Flanke = Kontakt schließt
        n_fall += 1
        t_fall = t
        if time.ticks_diff(t, t_accept) >= _DEBOUNCE_US:
            n_pulse += 1
            t_accept = t
        else:
            n_glitch += 1
    else:                                  # steigende Flanke = Kontakt öffnet
        if t_fall:
            d = time.ticks_diff(t, t_fall)
            if d >= 0:
                low_sum += d
                low_n += 1
                if low_min == 0 or d < low_min:
                    low_min = d
                if d > low_max:
                    low_max = d


def _bar(pps):
    n = int(min(1.0, pps / BAR_FULL) * BAR_WIDTH + 0.5)
    return "#" * n + "." * (BAR_WIDTH - n)


def main():
    global n_fall, n_pulse, n_glitch, low_sum, low_n, low_min, low_max

    print("Anemometer-Test auf dem PICO  –  Reed zwischen GP%d und GND" % PIN)
    print("  Entprellzeit %d ms, Umrechnung %g %s pro Puls/s" % (DEBOUNCE_MS, FACTOR, UNIT))
    if pin.value() == 0:
        print("  Ruhepegel: LOW  → Kontakt dauerhaft geschlossen oder Kurzschluss?")
    else:
        print("  Ruhepegel: HIGH → Eingang offen, ok")
    print("  Jetzt die Schalen drehen.  Strg+C beendet.\n")
    print(" %7s %5s %8s %20s %5s  %s" %
          ("Flanken", "Pulse", "Pulse/s", "Low min/avg/max ms", "Prell", "Signal"))

    pin.irq(handler=_irq,
            trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
            hard=True)

    tot_pulse = tot_glitch = tot_fall = 0
    max_pps = 0.0
    all_low_min = 0
    secs = 0
    last_signal = -1

    try:
        while True:
            time.sleep_ms(1000)
            secs += 1

            state = machine.disable_irq()      # Zähler atomar auslesen + nullen
            f, pu, g = n_fall, n_pulse, n_glitch
            ls, ln, lmin, lmax = low_sum, low_n, low_min, low_max
            n_fall = n_pulse = n_glitch = 0
            low_sum = low_n = low_min = low_max = 0
            machine.enable_irq(state)

            tot_fall += f
            tot_pulse += pu
            tot_glitch += g
            pps = float(pu)
            if pps > max_pps:
                max_pps = pps
            if lmin and (all_low_min == 0 or lmin < all_low_min):
                all_low_min = lmin

            if ln:
                low_txt = "%6.1f/%6.1f/%6.1f" % (lmin / 1000, ls / ln / 1000, lmax / 1000)
            else:
                low_txt = "%20s" % "-"

            if pu > 0:
                last_signal = secs
                status = "%s OK  = %.1f %s" % (_bar(pps), pps * FACTOR, UNIT)
            else:
                since = secs if last_signal < 0 else secs - last_signal
                lvl = "LOW" if pin.value() == 0 else "HIGH"
                status = "%s kein Signal (seit %d s, Pegel %s)" % (_bar(0), since, lvl)

            print(" %7d %5d %8.2f %20s %5d  %s" % (f, pu, pps, low_txt, g, status))

    except KeyboardInterrupt:
        pass
    finally:
        pin.irq(handler=None)
        led.value(0)

    print()
    print("-" * 60)
    print("Zusammenfassung (%d s)" % secs)
    print("  Pulse gesamt       : %d" % tot_pulse)
    print("  Maximum            : %.1f Pulse/s  = %.1f %s" % (max_pps, max_pps * FACTOR, UNIT))
    if tot_fall:
        ratio = 100.0 * tot_glitch / tot_fall
        print("  Prell-/Störflanken : %d von %d Flanken (%.0f %%)" % (tot_glitch, tot_fall, ratio))
        print("  Kürzeste Low-Phase : %.1f ms" % (all_low_min / 1000))
        if ratio > 10:
            print("  → Kontakt prellt stark: der PiLogger würde zu viele Pulse zählen.")
            print("    Abhilfe: 100 nF parallel zum Kontakt, oder Sensor prüfen.")
        elif ratio > 0:
            print("  → leichtes Prellen, für den PiLogger meist unkritisch.")
        else:
            print("  → Signal sauber, kein Prellen erkannt.")
    print()
    if tot_pulse:
        print("  ERGEBNIS: SIGNAL ERKANNT – der Reedkontakt liefert Pulse.")
    else:
        print("  ERGEBNIS: KEIN SIGNAL – keine Pulse gezählt.")
        print("            → Verdrahtung GP%d/GND, Kontakt mit Multimeter (Ohm) prüfen." % PIN)
    print("-" * 60)


main()
