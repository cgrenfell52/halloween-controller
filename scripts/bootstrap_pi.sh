#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/cgrenfell52/halloween-controller.git"
REPO_DIR="$HOME/halloween-controller"
SERVICE_FILE="/etc/systemd/system/halloween.service"
ARDUINO_FQBN="arduino:avr:mega"
ARDUINO_PORT="/dev/ttyACM0"
CODEX_PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKhD6Z+AqnaqJrRHZZHBK9h/n19cYoK+dY8RBSS1p8Oz halloween-controller-codex-windows"

echo "== Halloween controller Pi bootstrap =="

echo "== Trusting Windows/Codex SSH key =="
mkdir -p "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
if ! grep -qxF "$CODEX_PUBLIC_KEY" "$HOME/.ssh/authorized_keys"; then
  printf '%s\n' "$CODEX_PUBLIC_KEY" >> "$HOME/.ssh/authorized_keys"
fi
chmod 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/authorized_keys"

echo "== Installing system packages =="
sudo apt update
sudo apt install -y git curl python3-venv python3-pip

echo "== Fetching project repo =="
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

echo "== Setting up Python venv =="
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m py_compile app.py

echo "== Installing Arduino CLI =="
if [ ! -x "$HOME/bin/arduino-cli" ]; then
  mkdir -p "$HOME/bin"
  (
    cd "$HOME"
    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
  )
fi
export PATH="$HOME/bin:$PATH"

arduino-cli version
arduino-cli core update-index
arduino-cli core install arduino:avr

echo "== Compiling Arduino firmware =="
arduino-cli compile --fqbn "$ARDUINO_FQBN" arduino/firmware

if [ -e "$ARDUINO_PORT" ]; then
  echo "== Uploading Arduino firmware to $ARDUINO_PORT =="
  sudo systemctl stop halloween.service 2>/dev/null || true
  arduino-cli upload -p "$ARDUINO_PORT" --fqbn "$ARDUINO_FQBN" arduino/firmware
else
  echo "WARNING: $ARDUINO_PORT was not found. Skipping firmware upload."
fi

echo "== Installing halloween.service =="
sudo tee "$SERVICE_FILE" >/dev/null <<SERVICE
[Unit]
Description=Halloween Prop Controller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=candydisp
WorkingDirectory=/home/candydisp/halloween-controller
Environment=PYTHONUNBUFFERED=1
Environment=HALLOWEEN_SERIAL_PORT=/dev/ttyACM0
ExecStart=/home/candydisp/halloween-controller/venv/bin/python /home/candydisp/halloween-controller/app.py

Restart=on-failure
RestartSec=2

KillSignal=SIGINT
TimeoutStopSec=5
FinalKillSignal=SIGKILL
KillMode=control-group

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable halloween.service
sudo systemctl restart halloween.service

echo "== Service status =="
sudo systemctl status halloween.service --no-pager

echo "== Done =="
