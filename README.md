# Halloween Prop Controller

This project runs a Halloween TRICK/TREAT prop controller built around a Raspberry Pi 5 and an Arduino Mega.

The Pi handles:

- the Flask web UI
- password-protected remote access
- GPIO TRICK/TREAT triggers
- audio playback
- dual-TV video playback
- show orchestration
- serial communication and reconnect logic

The Arduino handles:

- relay/output switching
- timing-critical prop scenes
- safe output shutdown
- protocol state reporting back to the Pi

## Current Hardware Layout

### Arduino Mega Outputs

- `HEAD_1 / Skinny`: pin `4`
- `HEAD_2 / Hag`: pin `5`
- `AIR_CANNON`: pin `6`
- `AIR_TICKLER`: pin `7`
- `DOOR`: pin `8`
- `HORN / Ooga horn`: pin `9`
- `CRACKLER`: pin `10`
- `STROBE`: pin `13`
- `FOG`: pin `22`

### Raspberry Pi Trigger Inputs

The physical TRICK and TREAT buttons are dry-contact inputs to the Pi.

- `TRICK`: `GPIO17`, physical pin `11`
- `TREAT`: `GPIO27`, physical pin `13`
- ground: any Pi ground pin, commonly physical pin `9` or `14`

Internal pull-ups are enabled in software. Do not apply external voltage to these trigger lines.

## Show Flow

### TRICK

1. Choose a trick scene from the trick bag.
2. Play trick trigger audio and any matching head voice audio.
3. Run the chosen trick scene on the Arduino.
4. Play door audio.
5. Run the door sequence on the Arduino.
6. After the door sequence completes, play the triggered TV video.
7. Return to looping ambient TV video.

### TREAT

1. Play door audio and treat trigger audio together.
2. Run the door sequence on the Arduino.
3. Choose a trick scene from the same trick bag.
4. Play only the matching head voice audio for that trick scene.
5. Run the trick scene on the Arduino.
6. After that final trick completes, play the triggered TV video.
7. Return to looping ambient TV video.

`STOP`, `RESET`, and `ALL_OFF` cancel the active show, stop audio, force outputs off, and restore ambient TV playback.

## Quiet Time

Quiet time is supported in the app and configurable from the UI/settings API.

Default quiet window in the repo:

- start: `21:00`
- end: `08:00`

During quiet time, the trick bag excludes:

- `TRICK_HORN`
- `TRICK_CRACKLER`
- `TRICK_AIR_CANNON`

## Audio Layout

Audio files in `audio/` are stereo files with a split channel design:

- left channel: non-voice show audio / speaker feed
- right channel: voice feed for ServoDMX AutoTalk

Do not mono-sum the channels together. That would send non-voice effects into AutoTalk and voice cues into the general speaker feed.

On startup, the app requests `100%` system output volume by default so final loudness can be adjusted downstream on the speakers/amp.

## TV Video System

The Pi 5 drives two identical `1920x1080` TVs from its dual HDMI outputs.

The app uses one combined side-by-side video for each state:

- `video/ambient.mp4`: looping idle video
- `video/triggered.mp4`: one-shot triggered video

Each video is formatted as a single `3840x1080` file:

- left half = left TV
- right half = right TV

The app launches `mpv` on the Pi in the active X11 desktop session and manages the transition between ambient and triggered playback.

Current deployed display approach:

- Raspberry Pi OS 64-bit with desktop packages installed
- LightDM autologin into `LXDE-pi-x`
- X11 desktop extended across both displays
- `/home/candydisp/dual-tv-layout.sh` applies the `3840x1080` layout on login

## Serial Protocol

Protocol version: `PROP_CTRL_V2`

Pi to Arduino:

- `RUN:<scene>`
- `TOGGLE:<output>`
- `SYS:<command>`

Arduino to Pi:

- `READY:PROP_CTRL_V2`
- `STATUS:<state>`
- `STATUS:RUNNING_SCENE:<scene>`
- `STATUS:RUNNING_SERVICE:<output>`
- `STATE:<output>:ON`
- `STATE:<output>:OFF`
- `DONE:<command>`
- `ERROR:<reason>`

`SYS:STATUS` reports the current system state, every output state, and ends with `DONE:SYS:STATUS`.

## Reliability Features

The controller currently includes:

- serial port fallback across `/dev/ttyACM*` and `/dev/ttyUSB*`
- startup handshake with `SYS:PING` and `SYS:STATUS`
- serial reconnect worker after disconnect/error
- serial health state exposed through `/api/status`
- password-protected UI/API access
- GPIO trigger debounce control
- app-managed ambient video recovery

## Important Files

- `app.py`: main controller app
- `arduino/firmware/firmware.ino`: Arduino Mega firmware
- `audio/`: audio assets
- `video/`: combined dual-screen video assets
- `tests/test_controller_logic.py`: controller behavior tests
- `tests/test_flask_routes.py`: route/auth tests
- `tests/test_protocol_contract.py`: Python/firmware protocol contract tests
- `handoff.txt`: condensed technical handoff

## Pi Setup Notes

### Python Dependencies

On the Pi:

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

For Pi GPIO support, prefer apt packages over building `lgpio` from pip:

```bash
sudo apt install -y python3-gpiozero python3-lgpio
```

### Service

The controller is intended to run through:

```text
/etc/systemd/system/halloween.service
```

Typical service behavior:

- starts the Flask app
- connects to the Arduino
- enables GPIO triggers
- starts ambient video playback

### Video/Desktop Requirements

The current dual-TV playback depends on:

- LightDM enabled
- autologin user session set to `LXDE-pi-x`
- both TVs configured as `1920x1080`
- extended X11 desktop spanning both outputs
- `mpv` available on the Pi

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Syntax check:

```bash
python -m py_compile app.py
```

Run locally:

```bash
python app.py
```

On Windows and other non-Pi environments, video playback is disabled by default so local development does not try to launch the Pi TV stack.

## Environment Variables

Common runtime overrides:

- `HALLOWEEN_SERIAL_PORT`
- `HALLOWEEN_USE_MOCK_ARDUINO`
- `HALLOWEEN_MOCK_SCENE_DELAY_SCALE`
- `HALLOWEEN_GPIO_DISABLED`
- `HALLOWEEN_TRICK_GPIO`
- `HALLOWEEN_TREAT_GPIO`
- `HALLOWEEN_GPIO_BOUNCE_TIME`
- `HALLOWEEN_SET_SYSTEM_VOLUME`
- `HALLOWEEN_SYSTEM_VOLUME`
- `HALLOWEEN_ACCESS_PASSWORD`
- `HALLOWEEN_SECRET_KEY`
- `HALLOWEEN_SESSION_DAYS`
- `HALLOWEEN_VIDEO_DISABLED`
- `HALLOWEEN_VIDEO_PLAYER`
- `HALLOWEEN_VIDEO_DISPLAY`
- `HALLOWEEN_VIDEO_XAUTHORITY`
- `HALLOWEEN_VIDEO_AMBIENT_FILE`
- `HALLOWEEN_VIDEO_TRIGGERED_FILE`

## Design Rules

- keep timing-critical relay logic on the Arduino
- keep Flask responsive
- preserve STOP responsiveness
- keep Python and firmware protocol compatibility aligned
- treat the Pi as the show orchestrator and the Arduino as the hardware executor
