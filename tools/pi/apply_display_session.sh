#!/bin/bash
set -euo pipefail

TARGET_DIR="$HOME/.config/lxsession/LXDE-pi"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$TARGET_DIR"
install -m 644 "$SCRIPT_DIR/lxsession/LXDE-pi/autostart" "$TARGET_DIR/autostart"

pkill lxpanel || true
pkill pcmanfm || true

if [[ -n "${DISPLAY:-}" ]]; then
  xsetroot -solid black || true
fi

echo "Installed LXDE autostart from repo."
