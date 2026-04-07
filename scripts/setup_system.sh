#!/bin/bash
# =============================================================================
# SailMon System Setup Script
# Run ONCE on a fresh Raspberry Pi 4B with Raspberry Pi OS (Bookworm / Bullseye)
#
# What this script does:
#   1. Updates system packages
#   2. Installs gpsd + Python GPS library
#   3. Creates Python virtual environment and installs pip dependencies
#   4. Configures gpsd for USB GPS auto-detect
#   5. Creates a udev rule so the PICO display controller gets a stable
#      device name (/dev/ttyPICO) even when the GPS dongle is also attached
#   6. Installs and enables the sailmon systemd service
#   7. Creates required data directories
#
# Usage (run as root from the project directory):
#   sudo bash scripts/setup_system.sh
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "╔══════════════════════════════════════════════════╗"
echo "║         SailMon System Setup                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ─────────────────────────────────────────────────────
echo "▶ [1/7] Updating package lists …"
apt-get update -qq

echo "▶ [1/7] Installing system packages …"
apt-get install -y --no-install-recommends \
    gpsd \
    gpsd-clients \
    python3-gps \
    python3-pip \
    python3-venv \
    libgps-dev

# ── 2. Python virtual environment ──────────────────────────────────────────
echo ""
echo "▶ [2/7] Creating Python virtual environment …"
VENV="$PROJECT_DIR/.venv"
python3 -m venv "$VENV" --system-site-packages
"$VENV/bin/pip" install --quiet --upgrade pip

echo "▶ [2/7] Installing Python dependencies (incl. pyserial for PICO) …"
"$VENV/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"

# ── 3. Configure gpsd ──────────────────────────────────────────────────────
echo ""
echo "▶ [3/7] Configuring gpsd …"
cat > /etc/default/gpsd << 'EOF'
# gpsd configuration
# USB GPS dongle (u-blox) – auto-detected by udev
START_DAEMON="true"
GPSD_OPTIONS="-n"
DEVICES=""
USBAUTO="true"
GPSD_SOCKET="/var/run/gpsd.sock"
EOF

systemctl enable gpsd
systemctl restart gpsd
echo "  gpsd configured – USB auto-detect enabled"

# ── 4. PICO udev rule ──────────────────────────────────────────────────────
# The Raspberry Pi PICO running MicroPython exposes a USB CDC serial device.
# Both the PICO and the u-blox GPS may appear as /dev/ttyACM* and compete for
# the same name.  This rule gives the PICO a permanent symlink: /dev/ttyPICO
#
# Raspberry Pi PICO USB IDs:
#   idVendor  = 2e8a  (Raspberry Pi)
#   idProduct = 0005  (MicroPython CDC)
echo ""
echo "▶ [4/7] Adding udev rule for PICO display controller …"
cat > /etc/udev/rules.d/99-sailmon-pico.rules << 'EOF'
# Raspberry Pi PICO running MicroPython → stable symlink /dev/ttyPICO
SUBSYSTEM=="tty", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0005", \
    SYMLINK+="ttyPICO", MODE="0666", GROUP="dialout"
EOF
udevadm control --reload-rules
udevadm trigger
echo "  udev rule installed → PICO will appear as /dev/ttyPICO"

# ── 5. Data directories ────────────────────────────────────────────────────
echo ""
echo "▶ [5/7] Creating data directories …"
mkdir -p "$PROJECT_DIR/data/tiles/osm"
mkdir -p "$PROJECT_DIR/data/tiles/opensea"
mkdir -p "$PROJECT_DIR/data/gpx"
chown -R pi:pi "$PROJECT_DIR/data"

# ── 6. Install systemd service ────────────────────────────────────────────
echo ""
echo "▶ [6/7] Installing sailmon.service …"
cp "$PROJECT_DIR/sailmon.service" /etc/systemd/system/sailmon.service
# Patch path to the actual project directory
sed -i "s|/home/pi/sailmon|$PROJECT_DIR|g" /etc/systemd/system/sailmon.service
systemctl daemon-reload
systemctl enable sailmon.service
echo "  sailmon.service enabled (auto-starts on boot)"

# ── 7. Update config.py with correct PICO port ────────────────────────────
echo ""
echo "▶ [7/7] Setting PICO serial port to /dev/ttyPICO in config.py …"
sed -i 's|PICO_SERIAL_PORT.*=.*|PICO_SERIAL_PORT     = "/dev/ttyPICO"|' \
    "$PROJECT_DIR/config.py"
echo "  config.py updated"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  System setup complete!                                      ║"
echo "║                                                              ║"
echo "║  Next steps:                                                 ║"
echo "║  1. Flash MicroPython + firmware onto the PICO               ║"
echo "║     (see README or ask Claude for the PICO setup guide)      ║"
echo "║  2. Plug in: PICO via USB, GPS dongle via USB                ║"
echo "║     Verify: ls /dev/ttyPICO /dev/ttyACM*                    ║"
echo "║  3. Set up WiFi hotspot (optional):                          ║"
echo "║     sudo bash scripts/setup_hotspot.sh                       ║"
echo "║  4. Pre-download map tiles (needs internet):                 ║"
echo "║     .venv/bin/python3 scripts/download_tiles.py             ║"
echo "║  5. Start SailMon:                                           ║"
echo "║     sudo systemctl start sailmon                            ║"
echo "║     Open http://<pi-ip>:8000 in a browser                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
