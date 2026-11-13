# anemotest – Anemometer-Tester auf dem Raspberry Pi Zero W

Eigenständiges Prüfgerät für einen Reedkontakt-Windgeber (zwei Adern).
Der Pi analysiert den Sensorausgang direkt am GPIO und zeigt im lokalen Netz
eine Web-Oberfläche mit:

| Frage | Anzeige |
|-------|---------|
| Kommt ein Signal? | **JA / NEIN**, Alter des letzten Pulses, Eingangspegel |
| Wie schnell? | Frequenz in Hz, Pulse/min, Umdrehungen/min, daraus Windwert |
| Wie stark ist das Signal? | Ruhepegel, Tiefpegel bei geschlossenem Kontakt, Kontaktwiderstand, Bewertung (nur mit ADC) |
| Wie sauber? | Schließdauer, Tastverhältnis, Prellen, Bewertung |
| Verlauf | Frequenz und Tiefpegel der letzten 5 Minuten als Diagramm und Tabelle |

Unabhängig von SailMon und PiLogger. Nichts aus dem Hauptprojekt wird benötigt.

## Hardware

- Raspberry Pi Zero W (oder jeder andere Pi bis Pi 4; pigpio läuft nicht auf dem Pi 5)
- Reedkontakt-Anemometer, zwei Adern
- **optional** für die Signalstärke: ein ADC und ein 10 kΩ Widerstand. Unterstützt:
  - **ADS1115-Modul** (auch ADS1015): fertiges Breakout-Board, I2C, 16 Bit, 860 Messungen/s.
    Die übliche Wahl, wenn man ein Modul mit Stiftleiste kaufen will.
  - **MCP3008**: nackter DIP-Chip für das Steckbrett, SPI, 10 Bit, mehrere tausend Messungen/s.

Der Pi kann selbst keine Spannung messen, er sieht nur HIGH oder LOW. Ohne ADC
sagt die Oberfläche deshalb nur: „Pulse werden erkannt, der Pegel reicht für den
Logikeingang.“ Mit ADC misst sie den Tiefpegel in Volt und rechnet den
Kontaktwiderstand aus. Beide ADCs reichen dafür: bei Handdrehung ist der Kontakt
einige zehn Millisekunden geschlossen, mit Fön noch etwa 5 ms, das sind beim
ADS1115 immer noch mehrere Messungen pro Schließung.

### Verdrahtung Sensor (immer)

| Anemometer | Pi Zero W (Pin) |
|------------|-----------------|
| Ader 1 | GPIO 17 (Pin 11) |
| Ader 2 | GND (Pin 9) |

Der interne Pull-up des Pi (ca. 50 kΩ) wird eingeschaltet. Polung egal.

### Verdrahtung ADS1115-Modul (optional, für die Signalstärke)

| ADS1115 | Pi Zero W (Pin) |
|---------|-----------------|
| VDD | 3,3 V (Pin 1) |
| GND | GND (Pin 6) |
| SCL | GPIO 3 / SCL (Pin 5) |
| SDA | GPIO 2 / SDA (Pin 3) |
| ADDR | GND (ergibt Adresse 0x48) |
| ALRT | frei lassen |
| A0 | Sensorknoten (die Ader an GPIO 17) |
| A1 bis A3 | frei lassen |

Das Modul **nur mit 3,3 V** versorgen, nicht mit 5 V: die I2C-Leitungen und
der Messbereich bleiben dann im Rahmen des Pi. Zusätzlich **10 kΩ von GPIO 17
nach 3,3 V** legen, siehe unten. I2C muss eingeschaltet sein (`install.sh`
erledigt das). Prüfen: `i2cdetect -y 1` zeigt `48`.

### Verdrahtung MCP3008 (Alternative, nackter Chip)

```
                 ┌─────────────┐
   Sensorknoten ─┤ CH0     VDD ├─ 3,3 V (Pin 1)
                 │        VREF ├─ 3,3 V (Pin 1)
                 │        AGND ├─ GND
                 │         CLK ├─ GPIO 11 / SCLK (Pin 23)
                 │        DOUT ├─ GPIO 9  / MISO (Pin 21)
                 │         DIN ├─ GPIO 10 / MOSI (Pin 19)
                 │          CS ├─ GPIO 8  / CE0  (Pin 24)
                 │        DGND ├─ GND
                 └─────────────┘
```

Der MCP3008 ist ein einfacher DIP-Chip mit 16 Beinen (kein Modul nötig), er
passt direkt auf ein Steckbrett. Pinbelegung, Kerbe oben:

| Pin | Name | Pin | Name |
|-----|------|-----|------|
| 1 | CH0 | 16 | VDD |
| 2 | CH1 | 15 | VREF |
| 3 | CH2 | 14 | AGND |
| 4 | CH3 | 13 | CLK |
| 5 | CH4 | 12 | DOUT |
| 6 | CH5 | 11 | DIN |
| 7 | CH6 | 10 | CS |
| 8 | CH7 | 9 | DGND |

### Pull-up am Sensorknoten (für beide ADCs)

„Sensorknoten“ ist die Ader, die an GPIO 17 hängt. Zusätzlich **10 kΩ von
GPIO 17 nach 3,3 V** legen: damit ist der Pull-up bekannt (Standard
`--pullup 10000`) und der Tiefpegel entspricht dem, was auch ein PiLogger-Eingang
sehen würde. Ohne den Widerstand liefert der ADC trotzdem Werte, aber der
errechnete Kontaktwiderstand stimmt dann nicht.

## Installation

```bash
# auf dem Pi, z. B. per scp oder git das Verzeichnis anemotest/ kopieren
cd ~/anemotest
sudo bash install.sh
```

Das Skript installiert `pigpio`, `python3-pigpio`, `python3-smbus` und
`python3-spidev`, startet den `pigpiod`-Dienst, schaltet I2C und SPI ein und
richtet `anemotest.service` ein, der beim Booten automatisch startet.

Web-Oberfläche: `http://<hostname>.local:8080` oder `http://<IP>:8080`
(IP mit `hostname -I` nachsehen).

Manueller Start zum Ausprobieren:

```bash
python3 anemotest.py                    # GPIO 17, ADC automatisch, Port 8080
python3 anemotest.py --gpio 27 --adc none
python3 anemotest.py --simulate         # ohne Hardware, zeigt die Oberfläche mit Testdaten
python3 anemotest.py --help
```

Parameter dauerhaft ändern: Zeile `ExecStart=` in
`/etc/systemd/system/anemotest.service`, dann `sudo systemctl daemon-reload &&
sudo systemctl restart anemotest`.

| Option | Bedeutung | Standard |
|--------|-----------|----------|
| `--gpio` | BCM-GPIO des Sensors | 17 |
| `--debounce-ms` | Flanken kürzer als das nach einem Puls gelten als Prellen | 5 |
| `--timeout` | Sekunden ohne Puls bis „NEIN“ | 3 |
| `--factor` / `--unit` | Sensorkonstante, Einheit pro Puls/s | 1.44 km/h (PiLogger-Standard) |
| `--pulses-per-rev` | Pulse pro Umdrehung für U/min | 1 |
| `--adc` | `auto`, `none`, `ads1115`, `mcp3008` (auto: erst ADS1115 auf I2C, dann MCP3008) | auto |
| `--adc-address` | I2C-Adresse des ADS1115 | 0x48 |
| `--pullup` | Pull-up am Sensorknoten in Ohm | 10000 |
| `--port` | Port der Web-Oberfläche | 8080 |

## Die Werte lesen

**Signal.** JA, solange der letzte Puls jünger als der Timeout ist. „Eingangspegel
LOW“ bei stehendem Sensor heißt: Kontakt dauerhaft geschlossen oder Kurzschluss.

**Frequenz.** Aus den Pulsabständen der letzten 5 Sekunden. Von Hand gedreht
etwa 1 bis 5 Hz, mit Fön oder Ventilator deutlich mehr. Der Windwert ist nur
eine Umrechnung mit der eingestellten Konstante.

**Signalstärke (mit ADC).** Maßgeblich ist der schlechteste Tiefpegel der letzten
50 Schließungen:

| Tiefpegel | Bewertung |
|-----------|-----------|
| ≤ 0,4 V | stark, viel Reserve |
| ≤ 0,8 V | ausreichend für 3,3-V-Logik, wenig Reserve |
| ≤ 1,5 V | schwach, Übergangswiderstand zu hoch |
| > 1,5 V | zu schwach, wird nicht sicher als Puls erkannt |

Ruhepegel unter 2,5 V deutet auf Leckstrom oder Teil-Kurzschluss im Kabel hin.
Der Kontaktwiderstand folgt aus Tiefpegel und Pull-up; gesunde Reedkontakte
liegen unter 1 Ω, Werte über 100 Ω kommen von Steckern, Klemmen oder Korrosion.

**Signalqualität.** Die Schließdauer ist die Zeit, die der Kontakt pro Puls
geschlossen bleibt, bei Handdrehung einige zehn Millisekunden. Werte unter 1 ms
sind Prellen. Liegt der Prellanteil über 10 %, zählt ein nachgeschalteter Logger
zu viele Pulse. Abhilfe: 100 nF parallel zum Kontakt oder Sensor prüfen.

## Fehlersuche

| Meldung / Symptom | Ursache | Abhilfe |
|-------------------|---------|---------|
| `pigpiod läuft nicht` | Dienst aus | `sudo systemctl enable --now pigpiod` |
| `python3-pigpio fehlt` | Paket fehlt | `sudo apt install pigpio python3-pigpio` |
| `ADS1115 nicht gefunden` | I2C aus, Modul nicht an 0x48 oder falsch verdrahtet | `sudo raspi-config nonint do_i2c 0`, `i2cdetect -y 1`, ADDR an GND |
| ADC deaktiviert, kein `/dev/spidev0.0` | SPI aus | `sudo raspi-config nonint do_spi 0` und neu starten |
| Ruhepegel ≈ 0 V trotz offenem Kontakt | ADC-Eingang (A0 bzw. CH0) nicht am Sensorknoten | Verdrahtung oben prüfen |
| Seite nicht erreichbar | Dienst läuft nicht oder falscher Port | `systemctl status anemotest`, `journalctl -u anemotest -f` |
| `.local` wird nicht aufgelöst | mDNS fehlt auf dem Client | IP-Adresse verwenden |

## Dateien

| Datei | Inhalt |
|-------|--------|
| `anemotest.py` | Start, Kommandozeile, Threads |
| `pulse.py` | Pulsanalyse (Frequenz, Schließdauer, Prellen), pigpio-Anbindung, Simulation |
| `adc.py` | ADS1115/ADS1015- und MCP3008-Abfrage, Pegelauswertung |
| `web.py` | HTTP-Server mit `/api/status`, `/api/history`, `/api/reset` |
| `static/index.html` | Oberfläche, ohne externe Bibliotheken |
| `anemotest.service`, `install.sh` | Autostart |
