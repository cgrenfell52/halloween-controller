# HauntOS V1

HauntOS is a Raspberry Pi-based Halloween show controller for outputs, inputs,
tile-based routines, audio playback, video playback, file uploads, and a mobile
web interface.

## Project Layout

```text
hauntos/
  app/
    main.py
    routes.py
    routine_engine.py
    input_monitor.py
    gpio_controller.py
    audio_controller.py
    video_controller.py
    config_store.py
  config/
    devices.json
    routines.json
    settings.json
  audio/
  video/
  deploy/
    hauntos.service
    hauntos-portal.service
    install_service.sh
    uninstall_service.sh
    hotspot_setup.md
    install_hotspot.sh
    install_captive_portal.sh
    captive_portal.py
  static/
    css/
    js/
  templates/
  requirements.txt
  README.md
```

## Development Setup

```powershell
cd hauntos
python -m venv venv
.\\venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

Open the web interface at:

```text
http://127.0.0.1:5000/
```

Local development does not require systemd. The service files under `deploy/`
are only for Raspberry Pi deployment.

## Raspberry Pi Service Deployment

The systemd unit expects the project to live at `/home/pi/hauntos` and the
virtual environment Python executable to exist at `/home/pi/hauntos/venv/bin/python`.

On the Pi:

```bash
cd /home/pi/hauntos
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
chmod +x deploy/install_service.sh deploy/uninstall_service.sh
./deploy/install_service.sh
```

The installer copies `deploy/hauntos.service` to `/etc/systemd/system/`, reloads
systemd, enables HauntOS at boot, and starts it immediately.

Useful service commands:

```bash
sudo systemctl status hauntos.service
sudo systemctl restart hauntos.service
sudo systemctl stop hauntos.service
journalctl -u hauntos.service -f
```

To remove the service:

```bash
cd /home/pi/hauntos
./deploy/uninstall_service.sh
```

The service uses `SIGINT` and `TimeoutStopSec=5` so HauntOS has a short clean
shutdown window before systemd forces termination.

## Raspberry Pi Hotspot Mode

Hotspot mode is optional. It lets the Pi create its own WiFi network named
`HauntOS` so a phone or tablet can connect directly at a show site.

Defaults:

- SSID: `HauntOS`
- Password: `hauntcontroller`
- Pi address: `192.168.4.1`
- UI URL: `http://192.168.4.1:5000`

Enable hotspot mode on the Pi:

```bash
cd /home/pi/hauntos
chmod +x deploy/install_hotspot.sh
./deploy/install_hotspot.sh
```

The script warns before changing network settings. Type `YES` to continue.
After it finishes, connect your phone to WiFi network `HauntOS` and open
`http://192.168.4.1:5000`.

Optional captive portal auto-open helper:

```bash
cd /home/pi/hauntos
chmod +x deploy/install_captive_portal.sh
./deploy/install_captive_portal.sh
```

This installs a small port 80 redirector and a NetworkManager DNS catch-all so
phones/tablets are more likely to offer the HauntOS UI automatically after
joining the hotspot. Mobile operating systems vary, so the manual URL remains
`http://192.168.4.1:5000`.

Disable hotspot mode:

```bash
cd /home/pi/hauntos
./deploy/install_hotspot.sh --disable
./deploy/install_captive_portal.sh --disable
```

Full hotspot notes and rollback commands are in `deploy/hotspot_setup.md`.

## Build Rule

Build forward one phase at a time. Do not implement later-phase behavior until
the current phase is accepted.
