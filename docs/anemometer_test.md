# Anemometer testen – kommt ein Signal, und ist es stark genug?

Einfaches Test-Setup für den Windgeber (Anemometer) am **PiLogger One**.
Drei Stufen, jede für sich aussagekräftig:

| Stufe | Werkzeug | Beantwortet |
|-------|----------|-------------|
| 1. Sensor allein | Multimeter (Ω) | Schaltet der Kontakt überhaupt? |
| 2. Am PiLogger-Eingang | Multimeter (V DC) | Ist der Pegel stark genug für den Eingang? |
| 3. Live-Zählung | `scripts/test_anemometer.py` oder `pico_firmware/anemo_test.py` | Kommen die Pulse im System an, wie viele, wie sauber? |

## So ist der Windgeber angebunden

```
Anemometer ──► Klemmen „Imp“ / „GND“ am PiLogger One
               │  16‑Bit‑Pulszähler, Ruhepegel ≈ 3,1 V (interner Pull‑up)
               ▼
           PiLogger WebMonitor (PiLogger-bottle.py, Port 8080)
               │  Wind = Pulse × Sensorkonstante / Messintervall / Zeitfaktor
               ▼
           SailMon wind_service  (liest /rawdata/ alle 2 s)  ──► Web‑UI + LED‑Anzeige
```

Der Imp‑Eingang ist laut PiLogger‑Handbuch für **mechanische Schalter (Reedkontakt)
und Open‑Collector‑Ausgänge** ausgelegt. Ein Puls heißt: der Sensor zieht „Imp“
kurz auf GND. Bei Reedkontakten ist die Polung egal, bei Open‑Collector muss der
Ausgang an „Imp“ und die Sensormasse an „GND“.

> Die genaue Schaltschwelle des Imp‑Eingangs ist in den erreichbaren Quellen
> nicht veröffentlicht. Für 3,3‑V‑Logik gilt als sicher: **LOW < 0,8 V, HIGH > 2,3 V**.
> Alle Grenzwerte unten sind darauf ausgelegt.

## Was du brauchst

- Multimeter (Gleichspannung, Widerstand)
- ein Stück Draht oder eine Pinzette (für den Kurzschluss‑Referenztest)
- für Stufe 3: SSH‑Zugang zum Pi mit laufendem PiLogger WebMonitor

---

## Stufe 1 – Sensor allein (ohne Pi)

### Reed‑Anemometer (2 Adern, passiv, der häufigste Typ)

1. Sensor abklemmen, Multimeter auf **Ω** (oder Durchgangspiepser) an beide Adern.
2. Schalenstern **langsam von Hand** drehen, eine volle Umdrehung.
3. Erwartung: der Wert springt zwischen **OL / ∞** (offen) und **< 10 Ω**
   (geschlossen), typischerweise 1× oder 2× pro Umdrehung.
   **Notiere die Pulse pro Umdrehung**, das brauchst du später für die Sensorkonstante.

| Messung | Bedeutung |
|---------|-----------|
| OL ↔ < 10 Ω | Kontakt in Ordnung |
| OL ↔ 50 … 500 Ω | Kontakt/Kabel mit hohem Übergangswiderstand, Pegel am PiLogger prüfen (Stufe 2) |
| immer OL | Reedkontakt defekt, Magnet fehlt/zu weit weg, Kabelbruch |
| immer < 10 Ω | Kurzschluss im Kabel oder Reed verklebt |
| schließt nur bei bestimmten Stellungen nicht | Magnet‑/Reed‑Abstand, Sensor mechanisch prüfen |

### Hall‑ oder Open‑Collector‑Sensor (3 Adern: VCC, GND, OUT)

Der Ω‑Test funktioniert hier nicht, der Sensor braucht Versorgung.

1. VCC laut Datenblatt anlegen (meist 3,3 V oder 5 V; am Pi liegt 3,3 V an Pin 1, 5 V an Pin 2).
2. Bei Open‑Collector: **10 kΩ von OUT nach VCC** als Pull‑up.
3. Multimeter **V DC** zwischen OUT und GND, Schalen langsam drehen.
4. Erwartung: Pegel wechselt zwischen ≈ VCC und **< 0,5 V**.

---

## Stufe 2 – Am PiLogger: Signal vorhanden und stark genug?

1. Sensor an **Imp** und **GND** anschließen (Open‑Collector: OUT → Imp, Sensormasse → GND,
   Sensor‑VCC separat versorgen, z. B. 3,3 V vom Pi).
   **Niemals** einen Push‑Pull‑Ausgang mit 5 V direkt auf Imp legen.
2. Multimeter **V DC**: rote Spitze auf **Imp**, schwarze auf **GND**.
3. Ruhe (Kontakt offen) ablesen, dann Schalen langsam drehen, bis der Kontakt
   schließt, und den Wert bei geschlossenem Kontakt ablesen.

| Ruhe | Kontakt geschlossen | Bewertung |
|------|---------------------|-----------|
| ≈ 3,1 V | **< 0,5 V** | ✔ Signal stark genug |
| ≈ 3,1 V | 0,8 … 2,5 V | ✘ zu schwach: Übergangswiderstand zu hoch (Klemme nachziehen, Kabel/Kontakt tauschen) |
| ≈ 3,1 V | ≈ 3,1 V (ändert sich nie) | ✘ kein Signal: Unterbrechung, Sensor schaltet nicht |
| ≈ 0 V | ≈ 0 V | ✘ Kurzschluss, oder Sensor zieht dauerhaft |
| ≈ 0 V **auch ohne Sensor** | – | PiLogger‑Eingang/Pull‑up prüfen, HAT‑Sitz prüfen |

**Referenztest ohne Sensor:** Sensor abklemmen, Multimeter zeigt ≈ 3,1 V, dann
mit dem Draht **Imp–GND** ein paar Mal kurz brücken. Bei laufendem Testskript
(Stufe 3) müssen dabei Pulse erscheinen. Damit ist die Kette
PiLogger → WebMonitor → SailMon unabhängig vom Sensor geprüft.

---

## Stufe 3 – Live‑Zählung mit dem Testskript

Das Skript liegt in `scripts/test_anemometer.py`, läuft mit dem System‑Python
des Pi und braucht keine zusätzlichen Pakete.

### Variante A – Standard, nichts stoppen (empfohlen)

```bash
cd ~/sailmon          # bzw. dein Projektverzeichnis
python3 scripts/test_anemometer.py
```

Das Skript holt sich Messintervall, Zeitfaktor und Sensorkonstante vom
WebMonitor und rechnet den Windwert zurück in Pulse:

```
Anemometer-Test – Quelle: PiLogger WebMonitor (http://localhost:8080)
  Messintervall 2 s × Pulszähl-Zeitfaktor 5  → Windwert alle 10 s neu
  Sensorkonstante 1.44 km/h pro Puls/s
  Jetzt die Schalen drehen / Wind machen.  Strg+C beendet.

 Zeit             Wind   Pulse/s Pulse/Fenster  Signal
 10:21:03      0.0 km/h      0.00           0.0  ░░░░░░░░░░░░░░░░░░░░ kein Signal (seit 12 s)
 10:21:13      7.2 km/h      5.00          50.0  ██████████░░░░░░░░░░ OK
```

- **Pulse/s** sollte beim Drehen von Hand bei etwa 1 … 5 liegen, mit Fön/Ventilator deutlich höher.
- **Windwert alle X s neu**: der PiLogger liefert nur alle *Messintervall × Zeitfaktor*
  Sekunden einen Wert. Für einen flotteren Test im WebMonitor
  (`http://<pi>:8080` → Einstellungen → „Pulszähl Zeitfaktor“) vorübergehend **1** eintragen.
- Strg+C beendet und zeigt eine Zusammenfassung mit Ergebnis **SIGNAL ERKANNT** oder **KEIN SIGNAL**.

### Variante B – exakte Pulszahl direkt vom PiLogger (I2C)

Liest das Zählerregister des PiLogger selbst, getriggert vom PiLogger‑Interrupt
auf GPIO 4, genau wie der WebMonitor. Der WebMonitor muss dafür kurz gestoppt werden
(SailMon zeigt so lange keinen Wind):

```bash
sudo systemctl stop pilo-webmon
python3 scripts/test_anemometer.py --source i2c --factor 1.44 --unit km/h
sudo systemctl start pilo-webmon
```

Ausgabe pro Messfenster: Rohzählerstand, Pulse/s und daraus errechneter Wind.
Nützlich, wenn die Anzeige im WebMonitor wegen Rundung auf 0,1 einzelne Pulse verschluckt.

### Variante C – Sensor direkt an einem Pi‑GPIO (ohne PiLogger)

Für den Werkstatttisch oder wenn der Verdacht auf den PiLogger fällt.
Der Pi‑Eingang hat eine ähnliche Schaltschwelle wie der PiLogger: zählt der Pi
sauber, ist der LOW‑Pegel auch für den PiLogger tief genug.

Verdrahtung (Pi‑Header, BCM‑Nummern):

| Sensor | Pi |
|--------|----|
| Reed Ader 1 | GPIO 17 (Pin 11) |
| Reed Ader 2 | GND (Pin 9) |
| Hall/OC: OUT | GPIO 17 |
| Hall/OC: GND | GND |
| Hall/OC: VCC | 3,3 V (Pin 1) – **kein 5 V**, der GPIO verträgt max. 3,3 V |

```bash
python3 scripts/test_anemometer.py --source gpio --pin 17
```

```
 Zeit     Flanken Pulse  Pulse/s   Low min/avg/max ms Prell  Signal
 09:07:32       6     6     6.00   30.2/  30.3/  30.4     0  ████████████░░░░░░░░ OK
 09:07:33      24     9     9.00    0.6/   6.6/  30.3    15  ██████████████████░░ OK
```

- **Flanken** = alle fallenden Flanken, **Pulse** = nach Entprellung (5 ms, `--debounce-ms`).
- **Low min/avg/max** = wie lange der Kontakt pro Puls geschlossen war. Werte unter
  1 ms sind Prellen, kein echter Puls.
- **Prell** = verworfene Flanken. Über ~10 % heißt: der PiLogger würde zu viele Pulse
  zählen, Abhilfe ist ein Kondensator (100 nF) parallel zu Imp/GND oder ein anderer Sensor.
- **Pegel** bei „kein Signal“: HIGH = Eingang offen (ok), LOW = Kurzschluss oder Sensor zieht dauerhaft.

### Variante D – Sensor an einem freien PICO (ohne Pi, ohne PiLogger)

Für einen Reedkontakt mit zwei Adern reicht ein PICO und Thonny.
Skript: `pico_firmware/anemo_test.py`.

| Sensor | PICO |
|--------|------|
| Ader 1 | GP15 (Pin 20) |
| Ader 2 | GND (Pin 18) |
| optional | 10 kΩ von GP15 nach 3V3 (Pin 36), bildet einen härteren Pull‑up wie am PiLogger nach |

1. PICO per USB anschließen, in Thonny `pico_firmware/anemo_test.py` öffnen.
2. Ausführen (F5). Die Ausgabe erscheint in der Thonny‑Shell, die Onboard‑LED
   leuchtet, solange der Kontakt geschlossen ist.
3. Schalen drehen, dann Strg+C für die Zusammenfassung.

Die Spalten sind dieselben wie bei Variante C (Flanken, Pulse, Low‑Zeit, Prell).
Die Zeitmessung läuft im Hardware‑Interrupt mit Mikrosekunden‑Auflösung und ist
damit genauer als auf dem Pi. Sensorkonstante und Entprellzeit stehen als
Konstanten am Anfang des Skripts (`FACTOR`, `UNIT`, `DEBOUNCE_MS`).

### Nützliche Optionen (Varianten A bis C)

| Option | Wirkung |
|--------|---------|
| `--duration 60` | nach 60 s automatisch beenden |
| `--csv /tmp/anemo.csv` | Messwerte mitschreiben (z. B. zum Vergleich vorher/nachher) |
| `--interval 0.5` | Abfrage‑/Anzeigeintervall |
| `--url http://192.168.4.1:8080` | WebMonitor auf einem anderen Pi |

Exit‑Code: **0** = Pulse erkannt, **1** = keine Pulse, **2** = Setup‑Fehler
(WebMonitor nicht erreichbar, I2C‑Fehler, GPIO belegt).

---

## Stufe 4 – Ende‑zu‑Ende in SailMon

Wenn Stufe 3 Pulse zeigt: SailMon‑Web‑UI (`http://<pi>:8000`) und die LED‑Anzeige
müssen den Windwert innerhalb von ~2 s nachziehen. Tun sie das nicht, liegt es nicht
mehr am Anemometer, sondern an `services/wind_service.py` bzw. der Verbindung zum
WebMonitor (`PILOGGER_URL` in `config.py`).

---

## Fehlersuche

| Symptom | Wahrscheinliche Ursache | Maßnahme |
|---------|-------------------------|----------|
| Draht‑Brücke Imp–GND erzeugt Pulse, Sensor nicht | Sensor oder Kabel | Stufe 1 und 2 wiederholen, Klemmen nachziehen |
| Auch die Draht‑Brücke erzeugt keine Pulse | PiLogger oder WebMonitor | `i2cdetect -y 1` muss `48` zeigen; `systemctl status pilo-webmon`; `PiLo-Error.log` im PiLogger‑Verzeichnis; HAT‑Sitz prüfen |
| Pulse kommen, Wind aber viel zu hoch | Prellen | 100 nF parallel zu Imp/GND, Kabel kürzen/schirmen, Zeitfaktor erhöhen |
| Pulse kommen, Wind konstant zu hoch/zu niedrig | Sensorkonstante | WebMonitor → Einstellungen → „Faktor Pulse 1“: Konstante = Wegstrecke pro Puls, Pulse pro Umdrehung aus Stufe 1 einrechnen |
| Wind fällt sporadisch auf 0 | Kontakt setzt bei bestimmten Stellungen aus, Kabelbruch bei Bewegung | Stufe 1 bei verschiedenen Winkeln, Kabel bewegen und beobachten |
| Pegel bei geschlossenem Kontakt nur 1 … 2,5 V | Übergangswiderstand | Reedkontakt/Stecker reinigen, Kabel tauschen |

## Quellen

- PiLogger: „Windgeschwindigkeit messen mit Raspberry und PiLogger“ –
  <https://www.pilogger.de/index.php/de/windgeschwindigkeit-messen>
- PiLogger: „Selbstbau Windgeber“ – <https://www.pilogger.de/index.php/de/selbstbau-windgeber>
- PiLogger One Handbuch (Impulseingang, 16‑Bit‑Zähler, Fühlerkonstante) –
  <https://docplayer.org/amp/106664305-Das-pilogger-one-handbuch.html>
- Umrechnung im WebMonitor: `pilogger_source/PiLogger-bottle.py`, Funktion `JetztAber()`
