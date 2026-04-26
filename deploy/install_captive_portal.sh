#!/usr/bin/env bash
set -euo pipefail

# Optional captive portal helper for HauntOS hotspot mode.
# It makes most connected phones/tablets discover the controller by resolving
# DNS names to 192.168.4.1 and redirecting plain HTTP traffic to the Flask UI.

SERVICE_NAME="hauntos-portal.service"
PROJECT_DIR="${HAUNTOS_PROJECT_DIR:-/home/pi/hauntos}"
HOTSPOT_IP="${HAUNTOS_HOTSPOT_IP:-192.168.4.1}"
DNSMASQ_SHARED_DIR="/etc/NetworkManager/dnsmasq-shared.d"
DNSMASQ_CONF="${DNSMASQ_SHARED_DIR}/hauntos-captive.conf"
MODE="${1:-install}"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

usage() {
  cat <<EOF
Usage:
  ./deploy/install_captive_portal.sh
  ./deploy/install_captive_portal.sh --disable

Environment overrides:
  HAUNTOS_PROJECT_DIR    Default: /home/pi/hauntos
  HAUNTOS_HOTSPOT_IP     Default: 192.168.4.1
EOF
}

confirm_install() {
  cat <<EOF

WARNING: This enables captive portal behavior for HauntOS hotspot mode.

It will:
  - Copy ${SERVICE_NAME} to /etc/systemd/system/
  - Start a port 80 redirector to http://${HOTSPOT_IP}:5000
  - Add a NetworkManager dnsmasq-shared rule resolving DNS to ${HOTSPOT_IP}
  - Restart NetworkManager, which may briefly interrupt networking

Install hotspot mode first with:
  ./deploy/install_hotspot.sh

Rollback:
  ./deploy/install_captive_portal.sh --disable

Type YES to continue:
EOF

  read -r reply
  if [[ "${reply}" != "YES" ]]; then
    echo "Cancelled. No captive portal changes were made."
    exit 0
  fi
}

install_portal() {
  confirm_install

  if [[ ! -f "${PROJECT_DIR}/deploy/${SERVICE_NAME}" ]]; then
    echo "Missing ${PROJECT_DIR}/deploy/${SERVICE_NAME}"
    exit 1
  fi

  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl was not found. Captive portal service requires systemd."
    exit 1
  fi

  echo "Installing redirect service..."
  ${SUDO} cp "${PROJECT_DIR}/deploy/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
  ${SUDO} systemctl daemon-reload
  ${SUDO} systemctl enable --now "${SERVICE_NAME}"

  if command -v nmcli >/dev/null 2>&1; then
    echo "Installing NetworkManager captive DNS rule..."
    ${SUDO} mkdir -p "${DNSMASQ_SHARED_DIR}"
    echo "address=/#/${HOTSPOT_IP}" | ${SUDO} tee "${DNSMASQ_CONF}" >/dev/null
    ${SUDO} systemctl restart NetworkManager
  else
    echo "nmcli was not found. Skipping DNS catch-all rule."
    echo "The port 80 redirector is installed, but auto-open behavior may be limited."
  fi

  cat <<EOF

Captive portal helper installed.

Connect to the HauntOS WiFi network. Most phones/tablets should offer to open
the controller automatically. Manual URL:
  http://${HOTSPOT_IP}:5000

EOF
}

disable_portal() {
  echo "Disabling captive portal helper..."
  ${SUDO} systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
  ${SUDO} rm -f "/etc/systemd/system/${SERVICE_NAME}"
  ${SUDO} systemctl daemon-reload 2>/dev/null || true

  if [[ -f "${DNSMASQ_CONF}" ]]; then
    ${SUDO} rm -f "${DNSMASQ_CONF}"
    ${SUDO} systemctl restart NetworkManager 2>/dev/null || true
  fi

  echo "Captive portal helper disabled."
}

case "${MODE}" in
  install)
    install_portal
    ;;
  --disable|disable|uninstall|remove)
    disable_portal
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
