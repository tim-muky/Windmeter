#!/bin/bash
# =============================================================================
# SailMon – Wi-Fi Hotspot Setup
# Creates a local Wi-Fi access point on the Raspberry Pi 4B.
#
# After running this script:
#   SSID     : SailMon
#   Password : sailmon123   ← change below before running!
#   Pi IP    : 10.42.0.1
#   Web UI   : http://10.42.0.1:8000
#
# The Pi uses NetworkManager's built-in hotspot feature (available on
# Raspberry Pi OS Bookworm).  The Pi can share the ethernet connection
# to the internet while simultaneously offering the hotspot (optional).
#
# Usage:
#   sudo bash scripts/setup_hotspot.sh
# =============================================================================

set -e

SSID="SailMon"
PASSWORD="sailmon123"     # ← CHANGE THIS before running!
IFACE="wlan0"
IP="10.42.0.1"

echo "╔══════════════════════════════╗"
echo "║   SailMon Hotspot Setup      ║"
echo "╚══════════════════════════════╝"

# Require NetworkManager
if ! command -v nmcli &> /dev/null; then
    echo "ERROR: nmcli not found. Install with: sudo apt install network-manager"
    exit 1
fi

echo ""
echo "▶ Creating hotspot connection …"

# Remove existing SailMon connection if it exists
nmcli connection delete "SailMon-AP" 2>/dev/null || true

# Create the access point
nmcli connection add \
    type        wifi \
    ifname      "$IFACE" \
    con-name    "SailMon-AP" \
    autoconnect yes \
    ssid        "$SSID" \
    -- \
    wifi.mode                  ap \
    wifi-sec.key-mgmt          wpa-psk \
    wifi-sec.psk               "$PASSWORD" \
    ipv4.method                shared \
    ipv4.addresses             "$IP/24" \
    ipv6.method                disabled

echo "▶ Activating hotspot …"
nmcli connection up "SailMon-AP"

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║  Hotspot active!                              ║"
echo "║                                               ║"
echo "║  SSID     : $SSID                         ║"
echo "║  Password : $PASSWORD         ← CHANGE THIS  ║"
echo "║  Pi IP    : $IP                      ║"
echo "║  Web UI   : http://$IP:8000    ║"
echo "║                                               ║"
echo "║  Connect your iPad/iPhone to '$SSID'       ║"
echo "║  and open http://$IP:8000 in Safari ║"
echo "╚═══════════════════════════════════════════════╝"
