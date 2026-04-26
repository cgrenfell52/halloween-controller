#!/usr/bin/env bash
set -euo pipefail

# HauntOS hotspot installer for Raspberry Pi OS.
# Uses NetworkManager because it is the default networking tool on current
# Raspberry Pi OS releases. This script is opt-in and is not needed for local
# development.

CONNECTION_NAME="HauntOS-Hotspot"
SSID="${HAUNTOS_HOTSPOT_SSID:-HauntOS}"
PASSWORD="${HAUNTOS_HOTSPOT_PASSWORD:-hauntcontroller}"
WIFI_IFACE="${HAUNTOS_WIFI_IFACE:-wlan0}"
STATIC_ADDRESS="${HAUNTOS_HOTSPOT_ADDRESS:-192.168.4.1/24}"
CHANNEL="${HAUNTOS_HOTSPOT_CHANNEL:-6}"
MODE="${1:-install}"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

usage() {
  cat <<EOF
Usage:
  ./deploy/install_hotspot.sh
  ./deploy/install_hotspot.sh --disable

Environment overrides:
  HAUNTOS_HOTSPOT_SSID        Default: HauntOS
  HAUNTOS_HOTSPOT_PASSWORD    Default: hauntcontroller
  HAUNTOS_WIFI_IFACE          Default: wlan0
  HAUNTOS_HOTSPOT_ADDRESS     Default: 192.168.4.1/24
  HAUNTOS_HOTSPOT_CHANNEL     Default: 6
EOF
}

require_networkmanager() {
  if command -v nmcli >/dev/null 2>&1; then
    return
  fi

  echo "nmcli was not found. Installing NetworkManager..."
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get was not found. Install NetworkManager manually, then rerun this script."
    exit 1
  fi

  ${SUDO} apt-get update
  ${SUDO} apt-get install -y network-manager
}

disable_hotspot() {
  require_networkmanager

  echo "Disabling ${CONNECTION_NAME}..."
  ${SUDO} nmcli connection down "${CONNECTION_NAME}" 2>/dev/null || true
  ${SUDO} nmcli connection delete "${CONNECTION_NAME}" 2>/dev/null || true
  ${SUDO} nmcli radio wifi on 2>/dev/null || true

  echo "Hotspot disabled."
  echo "Reconnect the Pi to your normal WiFi network if needed."
}

validate_settings() {
  if [[ "${#PASSWORD}" -lt 8 ]]; then
    echo "Hotspot password must be at least 8 characters."
    exit 1
  fi
}

confirm_install() {
  cat <<EOF

WARNING: This will change WiFi networking on this Raspberry Pi.

The Pi will create this hotspot:
  SSID:       ${SSID}
  Password:   ${PASSWORD}
  Interface:  ${WIFI_IFACE}
  Address:    ${STATIC_ADDRESS}

If you are connected over WiFi/SSH, this may disconnect you.
Use Ethernet or a keyboard/monitor for first setup when possible.

Rollback:
  ./deploy/install_hotspot.sh --disable

Type YES to continue:
EOF

  read -r reply
  if [[ "${reply}" != "YES" ]]; then
    echo "Cancelled. No hotspot changes were made."
    exit 0
  fi
}

install_hotspot() {
  validate_settings
  confirm_install
  require_networkmanager

  echo "Enabling NetworkManager..."
  ${SUDO} systemctl enable --now NetworkManager

  echo "Unblocking WiFi..."
  ${SUDO} rfkill unblock wifi 2>/dev/null || true

  if nmcli -t -f NAME connection show | grep -Fxq "${CONNECTION_NAME}"; then
    echo "Replacing existing ${CONNECTION_NAME} connection..."
    ${SUDO} nmcli connection down "${CONNECTION_NAME}" 2>/dev/null || true
    ${SUDO} nmcli connection delete "${CONNECTION_NAME}"
  fi

  echo "Creating hotspot connection..."
  ${SUDO} nmcli connection add \
    type wifi \
    ifname "${WIFI_IFACE}" \
    con-name "${CONNECTION_NAME}" \
    autoconnect yes \
    ssid "${SSID}"

  ${SUDO} nmcli connection modify "${CONNECTION_NAME}" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel "${CHANNEL}" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "${PASSWORD}" \
    ipv4.method shared \
    ipv4.addresses "${STATIC_ADDRESS}" \
    ipv6.method disabled

  echo "Starting hotspot..."
  ${SUDO} nmcli connection up "${CONNECTION_NAME}"

  cat <<EOF

HauntOS hotspot is configured.

Connect to WiFi:
  SSID:     ${SSID}
  Password: ${PASSWORD}

Open:
  http://192.168.4.1:5000

Rollback:
  ./deploy/install_hotspot.sh --disable
EOF
}

case "${MODE}" in
  install)
    install_hotspot
    ;;
  --disable|disable|uninstall|remove)
    disable_hotspot
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
