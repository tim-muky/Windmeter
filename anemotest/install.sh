#!/bin/bash
# anemotest – Installation auf dem Raspberry Pi Zero W (Raspberry Pi OS)
# Aufruf aus dem anemotest-Verzeichnis:   sudo bash install.sh
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="${SUDO_USER:-pi}"

echo "▶ Pakete installieren (pigpio, spidev) …"
apt-get update -qq
apt-get install -y --no-install-recommends pigpio python3-pigpio python3-spidev python3-smbus i2c-tools

echo "▶ pigpiod aktivieren (liefert µs-genaue Flankenzeiten) …"
systemctl enable --now pigpiod

echo "▶ I2C (ADS1115) und SPI (MCP3008) einschalten – schadet nicht, wenn kein ADC dran ist …"
raspi-config nonint do_i2c 0 || echo "  raspi-config nicht verfügbar – I2C ggf. manuell aktivieren"
raspi-config nonint do_spi 0 || echo "  raspi-config nicht verfügbar – SPI ggf. manuell aktivieren"

echo "▶ systemd-Dienst einrichten …"
sed -e "s|__DIR__|$DIR|g" -e "s|__USER__|$USER_NAME|g" \
    "$DIR/anemotest.service" > /etc/systemd/system/anemotest.service
systemctl daemon-reload
systemctl enable --now anemotest.service

echo ""
echo "Fertig.  Web-UI:  http://$(hostname).local:8080   oder  http://$(hostname -I | awk '{print $1}'):8080"
echo "Status:  systemctl status anemotest      Log:  journalctl -u anemotest -f"
