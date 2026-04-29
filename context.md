# HauntOS Codex Handoff Context

Last updated: 2026-04-28

## Project

HauntOS is a Raspberry Pi haunt/show controller built as a local Flask app. The UI is served from the Pi and controls routines made of output, wait, sound, video, and all-off tiles.

Workspace path:

```text
C:\Users\Zorro\Documents\New project\hauntos
```

Local dev URL:

```text
http://127.0.0.1:5000/
```

Run locally:

```powershell
python -m app.main
```

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

## Current Git State

This folder is now its own Git repo. Runtime artifacts are ignored.

Ignored intentionally:

- `config/*.json`: live device/routine/settings data; app recreates defaults.
- `audio/*` and `video/*`: uploaded media; `.gitkeep` placeholders are tracked.
- `logs/`
- Python `__pycache__/` and `*.pyc`

Alpha tag:

```text
v0.1.0-alpha
```

## Implemented Features

- Config system with default JSON creation, validation, and safe writes.
- GPIO controller with mock mode and Raspberry Pi GPIO support.
- Audio controller with pygame fallback/mock mode.
- Video controller with mpv/vlc support, mock mode, and video tile modes:
  - `play_and_continue`
  - `wait_until_done`
- Threaded routine engine with hard stop support.
- Live routine status reporting from `/api/status`.
- Physical input monitor service with cooldown, enabled flag, active-low support, and show-armed gate.
- Scheduler service with active hours, fixed/random intervals, chosen/random routine, and show-armed gate.
- Flask API for devices, routines, outputs, run/test, stop, media, config backup/import/reset, scheduler, setup, system info.
- Web UI with fixed sidebar, dashboard, outputs, inputs/routine editor, audio, video, scheduler, setup, and system pages.
- Tile routine editor supports add/edit/delete/move/save/test.
- Active tile highlight while a routine is running.
- Start Show / Stop Show behavior:
  - Start Show arms physical inputs and scheduler.
  - Stop Show gracefully disarms future triggers and lets the current routine finish.
  - STOP EVERYTHING hard-cancels routines/media/outputs and disarms the show.
- Audio/video upload/list/delete UI.
- Config export/import/factory reset.
- Raspberry Pi deployment service files.
- Hotspot/captive portal deployment scripts and docs.
- First-run setup wizard for controller/input/output naming and test output.

## Product Decisions

- Hotspot controls should stay out of the V1 app UI. Hotspot is a deployment/network mode and can disconnect the user if toggled casually. Keep it as scripts/docs for V1.
- A later version can add a guided "connect this Pi to house WiFi" flow.
- Runtime config JSON is not committed. The app should create defaults and users can export/import backups through the UI.
- Uploaded media is not committed. Users upload files through the UI.

## Known Gaps / Next Good Work

- Add a UI/API mock input trigger for testing physical input behavior while in mock mode.
- Improve Pi readiness/status panel so it clearly says what is real hardware vs mock.
- Confirm real GPIO behavior on a Raspberry Pi with `mock_mode: false`.
- Confirm real audio playback on Pi with pygame/audio device.
- Confirm real video playback on Pi with `mpv` or `vlc`.
- Hotspot scripts should be tested on a fresh Raspberry Pi OS install before relying on them in the field.
- The scheduler topbar badge shows enabled/disabled, but the UI could also show "waiting for armed/active hours" more clearly.

## Important Files

- `app/main.py`: Flask app factory/startup/shutdown.
- `app/routes.py`: API and page routes.
- `app/config_store.py`: config defaults, load/save/validation.
- `app/gpio_controller.py`: outputs/inputs/mock GPIO.
- `app/routine_engine.py`: threaded routine execution and runtime status.
- `app/input_monitor.py`: physical input polling.
- `app/scheduler.py`: background scheduler.
- `app/audio_controller.py`: audio file list/play/stop.
- `app/video_controller.py`: video file list/play/stop.
- `static/js/main.js`: all frontend behavior.
- `static/css/style.css`: app styling.
- `templates/*.html`: Flask templates.
- `deploy/`: Pi service and hotspot/captive portal deployment files.

## Verification Commands

```powershell
node --check static\js\main.js
python -m compileall app
```

## Current User Preferences

- Dark professional Halloween/show-control look.
- Keep UI practical and control-panel-like, not a marketing page.
- Large readable buttons.
- STOP EVERYTHING must always be obvious and accessible.
- Avoid unnecessary technical text like GPIO numbers in everyday UI.
- Input/routine page should stay clean and tile-based.
- Save should be explicit; routine edits are local until Save.
- Toasts should use user-given input/output names where possible.

