#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hauntos.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SOURCE="${SCRIPT_DIR}/${SERVICE_NAME}"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl was not found. This installer is intended for Raspberry Pi/systemd deployments."
  exit 1
fi

if [[ ! -f "${SERVICE_SOURCE}" ]]; then
  echo "Missing service file: ${SERVICE_SOURCE}"
  exit 1
fi

echo "Installing ${SERVICE_NAME}..."
sudo install -m 0644 "${SERVICE_SOURCE}" "${SERVICE_TARGET}"

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling ${SERVICE_NAME}..."
sudo systemctl enable "${SERVICE_NAME}"

echo "Starting ${SERVICE_NAME}..."
sudo systemctl start "${SERVICE_NAME}"

echo "HauntOS service installed and started."
sudo systemctl --no-pager --full status "${SERVICE_NAME}"
