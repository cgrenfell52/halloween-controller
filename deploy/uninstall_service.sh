#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hauntos.service"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl was not found. This uninstaller is intended for Raspberry Pi/systemd deployments."
  exit 1
fi

echo "Stopping ${SERVICE_NAME}..."
sudo systemctl stop "${SERVICE_NAME}" 2>/dev/null || true

echo "Disabling ${SERVICE_NAME}..."
sudo systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

if [[ -f "${SERVICE_TARGET}" ]]; then
  echo "Removing ${SERVICE_TARGET}..."
  sudo rm -f "${SERVICE_TARGET}"
fi

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "HauntOS service uninstalled."
