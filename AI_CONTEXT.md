# AI Context Notes

This file preserves the important operating context for future AI sessions.

## Project

- Repo: `C:\Users\Mike\Documents\halloween-controller`
- GitHub: `https://github.com/cgrenfell52/halloween-controller.git`
- Pi user: `candydisp`
- Pi hostname: `CandyDisp`
- Pi Tailscale IP: `100.112.189.79`
- Public URL: `https://candydisp.tail9037f9.ts.net`
- Public password: `griswold`
- Pi app path: `/home/candydisp/halloween-controller`
- Service: `halloween.service`
- Service command: `/home/candydisp/halloween-controller/venv/bin/python /home/candydisp/halloween-controller/app.py`

## Access

- Prefer Tailscale over local `192.168.x.x` addresses.
- SSH from Windows:

```powershell
ssh -i "$env:USERPROFILE\.ssh\halloween_pi_ed25519" candydisp@100.112.189.79
```

- Login password is stored on the Pi outside the repo:

```text
/etc/systemd/system/halloween.service.d/access.conf
```

- Git pulls do not overwrite the password.
- To disable public Funnel:

```bash
sudo tailscale funnel --https=443 off
```

## Hardware Pins

Arduino Mega outputs:

```text
HEAD_1 / Skinny     = D4
HEAD_2 / Hag        = D5
AIR_CANNON          = D6
AIR_TICKLER         = D7
DOOR                = D8
HORN / Ooga horn    = D9
CRACKLER            = D10
STROBE              = D13
FOG                 = D22
```

Pi GPIO triggers:

```text
TRICK = GPIO17 = physical pin 11
TREAT = GPIO27 = physical pin 13
GND   = physical pin 9 or 14, or any Pi ground
```

Dry contact only. Do not put voltage on Pi GPIO trigger inputs.

## Architecture Rules

- Pi runs Flask UI, audio, GPIO triggers, and serial orchestration.
- Arduino executes physical and timing-critical relay behavior.
- Do not move physical timing from Arduino to Python.
- STOP must remain responsive and safe.
- Do not block the Flask main thread.
- Serial protocol is `PROP_CTRL_V2`.
- Arduino may appear as `/dev/ttyACM0` or `/dev/ttyACM1`; app auto-detects `/dev/ttyACM*` and `/dev/ttyUSB*`.

## Audio Rules

Current stereo split:

```text
LEFT channel  = non-voice show audio / speaker feed
RIGHT channel = voice / ServoDMX AutoTalk feed
```

Do not mono-sum left and right.

Audio filenames must stay lowercase:

```text
audio/welcome.mp3
audio/door.mp3
audio/hag.mp3
audio/skinny.mp3
audio/treat.mp3
audio/trick.mp3
audio/closing.mp3
```

Head audio:

- `skinny.mp3` and `hag.mp3` had leading silence trimmed.
- Do not add fade-in to `skinny.mp3` or `hag.mp3`; they are fast scares and need instant attack.
- `door.mp3` was reduced and softened to help popping.

Generic trick audio:

- Real TRICK show should play `trick.mp3`.
- Service/manual scene tests should not play generic `trick.mp3`.
- Manual `RUN HEAD 1` should play `SKINNY` only.
- Manual `RUN HEAD 2` should play `HAG` only.
- Manual `RUN BOTH HEADS` should play `SKINNY + HAG` only.
- Manual `RUN CRACKLER` should run the crackler physical scene only.
- TREAT show plays `door.mp3` and `treat.mp3` at the same time.

## Current Physical Timings

Air Cannon trick:

```text
AIR_CANNON ON 0.3s
AIR_CANNON OFF
```

Door sequence:

```text
DOOR ON immediately
Wait 10s
AIR_TICKLER fires 5 total times
Each tickle pulse random 0.35s-0.7s
Gaps between tickles random 0.5s-4.0s
DOOR stays ON for 22s total
DOOR OFF at end
```

Fog:

```text
FOG ON 10s
FOG OFF
```

Other timings:

```text
HEAD_1 / Skinny = 1.2s
HEAD_2 / Hag    = 1.2s
HORN            = 0.9s
CRACKLER        = 0.9s
BOTH_HEADS      = 2.0s
```

Python `SCENES` durations must match firmware timings:

```text
TRICK_AIR_CANNON = 300 ms
DOOR_SEQUENCE    = 22000 ms
FOG_BURST        = 10000 ms
```

## Deploy Workflow

Local tests:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Pi pull/restart:

```bash
cd ~/halloween-controller
git pull --ff-only
sudo systemctl restart halloween.service
```

Firmware compile/upload on Pi:

```bash
export PATH="$HOME/bin:$PATH"
cd ~/halloween-controller
arduino-cli compile --fqbn arduino:avr:mega arduino/firmware
sudo systemctl stop halloween.service
PORT=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
arduino-cli upload -p "$PORT" --fqbn arduino:avr:mega arduino/firmware
sudo systemctl restart halloween.service
```

## Sanity Checks

Service:

```bash
systemctl is-active halloween.service
sudo journalctl -u halloween.service -n 80 --no-pager
```

Authenticated local Pi API check:

```bash
curl -s -c /tmp/hc.cookies -b /tmp/hc.cookies -X POST -d 'password=griswold' http://127.0.0.1:5000/login >/dev/null
curl -s -b /tmp/hc.cookies http://127.0.0.1:5000/api/status
```

Healthy status:

```text
arduino_connected: true
arduino_protocol_version: PROP_CTRL_V2
system_status: IDLE
gpio_enabled: true
gpio_trick_pin: 17
gpio_treat_pin: 27
gpio_bounce_time: 0.15
```

## Last Known Good

- Latest pushed/deployed commit after tickler variation: `334bc04 Increase door tickler variation`
- Tests passed at that point: `35/35`
- Firmware compiled and uploaded successfully.
- Pi service active.
- Arduino connected on `/dev/ttyACM1`.
- System `IDLE`.

## Troubleshooting

- If Service Toggles seem broken, first check Arduino serial port. The app should auto-detect, but confirm with:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
dmesg | tail -60
```

- Service toggle clicks log:

```text
WEB command requested: TOGGLE:...
```

If this log appears, the browser reached Flask.

- If GPIO trigger fails, confirm physical pin vs GPIO number. TREAT is physical pin 13, not GPIO13.
- ALSA underrun warnings have appeared but have not blocked startup.

## Working Style

- User wants hand-holding and plain explanations.
- Discuss risky changes before implementation when possible.
- Once a change is agreed, implement and verify end-to-end.
- Avoid remotely firing physical props unless explicitly asked. Safe commands like `SYS:PING` are okay.
- Hardware tests should be done carefully; STOP must always be available.
