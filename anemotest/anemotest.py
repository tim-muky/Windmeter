#!/usr/bin/env python3
"""
anemotest – Anemometer-Tester für den Raspberry Pi Zero W
==========================================================
Analysiert den Ausgang eines Reedkontakt-Windgebers direkt am GPIO und zeigt
das Ergebnis als Web-Oberfläche im lokalen Netz:

  • Signal vorhanden: ja / nein           (letzter Puls jünger als --timeout)
  • Frequenz in Hz, Pulse/min, U/min, daraus Windwert (--factor)
  • Signalstärke (nur mit MCP3008-ADC): Ruhepegel, Tiefpegel, Kontaktwiderstand
  • Signalqualität: Schließdauer, Tastverhältnis, Prellen

Verdrahtung: siehe README.md.  Start:

  python3 anemotest.py                      # GPIO 17, ADC automatisch, Port 8080
  python3 anemotest.py --gpio 27 --adc none
  python3 anemotest.py --simulate           # ohne Hardware (Entwicklung)

Web-UI anschließend unter http://<pi>:8080
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pulse import PulseAnalyzer, PigpioSource, SimSource          # noqa: E402
from adc import AdcMonitor, Mcp3008Reader, SimAdcReader           # noqa: E402
from web import App, make_server                                  # noqa: E402

log = logging.getLogger("anemotest")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_argument_group("Sensor")
    g.add_argument("--gpio", type=int, default=17, help="BCM-GPIO des Reedkontakts (Standard 17)")
    g.add_argument("--debounce-ms", type=float, default=5.0, help="Entprellzeit in ms (Standard 5)")
    g.add_argument("--timeout", type=float, default=3.0,
                   help="Sekunden ohne Puls, bis 'kein Signal' gemeldet wird (Standard 3)")
    g.add_argument("--window", type=float, default=5.0,
                   help="Fenster für die Frequenzberechnung in s (Standard 5)")
    g.add_argument("--factor", type=float, default=1.44,
                   help="Sensorkonstante: Einheit pro Puls/s (Standard 1.44 = PiLogger km/h)")
    g.add_argument("--unit", default="km/h", help="Einheit zur Sensorkonstante (Standard km/h)")
    g.add_argument("--pulses-per-rev", type=int, default=1,
                   help="Pulse pro Umdrehung für die U/min-Anzeige (Standard 1)")
    a = p.add_argument_group("ADC (Signalstärke)")
    a.add_argument("--adc", choices=("auto", "none", "mcp3008"), default="auto",
                   help="auto: MCP3008 verwenden, wenn /dev/spidev0.0 existiert")
    a.add_argument("--adc-channel", type=int, default=0, help="MCP3008-Kanal (Standard 0)")
    a.add_argument("--pullup", type=float, default=10_000.0,
                   help="Pull-up-Widerstand am Sensorknoten in Ohm (Standard 10000)")
    a.add_argument("--vref", type=float, default=3.3, help="ADC-Referenzspannung (Standard 3.3)")
    w = p.add_argument_group("Web")
    w.add_argument("--host", default="0.0.0.0")
    w.add_argument("--port", type=int, default=8080)
    w.add_argument("--verbose", action="store_true", help="HTTP-Zugriffe mitloggen")
    p.add_argument("--simulate", action="store_true",
                   help="Synthetische Pulse statt Hardware (Entwicklung/Demo)")
    return p.parse_args(argv)


def build_adc(args, source):
    if args.simulate:
        return AdcMonitor(SimAdcReader(source, vref=args.vref),
                          pullup_ohm=args.pullup, vref=args.vref)
    if args.adc == "none":
        return None
    if args.adc == "auto" and not os.path.exists("/dev/spidev0.0"):
        log.info("Kein /dev/spidev0.0 – ADC deaktiviert (SPI einschalten: "
                 "sudo raspi-config nonint do_spi 0)")
        return None
    try:
        reader = Mcp3008Reader(channel=args.adc_channel, vref=args.vref)
        reader.read()
    except Exception as exc:
        if args.adc == "mcp3008":
            raise SystemExit(f"ADC-Fehler: {exc}  (python3-spidev installiert? SPI aktiv?)")
        log.warning("ADC nicht nutzbar (%s) – Signalstärke wird nicht gemessen", exc)
        return None
    return AdcMonitor(reader, pullup_ohm=args.pullup, vref=args.vref)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")

    analyzer = PulseAnalyzer(debounce_ms=args.debounce_ms, timeout_s=args.timeout,
                             window_s=args.window, factor=args.factor, unit=args.unit,
                             pulses_per_rev=args.pulses_per_rev)
    if args.simulate:
        source = SimSource(analyzer)
    else:
        try:
            source = PigpioSource(analyzer, gpio=args.gpio)
        except ImportError:
            raise SystemExit("python3-pigpio fehlt:  sudo apt install pigpio python3-pigpio")
        except RuntimeError as exc:
            raise SystemExit(str(exc))
    adc = build_adc(args, source)

    meta = {"gpio": args.gpio, "adc": adc.reader.describe() if adc else None,
            "pullup_ohm": args.pullup, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    app = App(analyzer, source, adc, meta, verbose=args.verbose)
    server = make_server(app, args.host, args.port)

    stop = threading.Event()

    def worker():
        while not stop.wait(1.0):
            try:
                app.tick()
            except Exception:
                log.exception("Fehler im Messthread")
    threading.Thread(target=worker, daemon=True, name="history").start()
    threading.Thread(target=server.serve_forever, daemon=True, name="http").start()

    log.info("Quelle: %s", source.describe())
    log.info("ADC:    %s", adc.reader.describe() if adc else "keiner (Signalstärke nicht messbar)")
    log.info("Web-UI: http://%s:%d/", _display_host(args.host), args.port)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        while not stop.is_set():
            stop.wait(0.5)
    finally:
        log.info("Beende …")
        server.shutdown()
        if adc:
            adc.close()
            adc.reader.close()
        source.close()
    return 0


def _display_host(host):
    if host not in ("0.0.0.0", "::", ""):
        return host
    try:
        import socket
        return socket.gethostname() + ".local"
    except Exception:
        return "<pi>"


if __name__ == "__main__":
    sys.exit(main())
