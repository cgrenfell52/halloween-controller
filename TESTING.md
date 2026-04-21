# Testing

This project can be tested without the Raspberry Pi or Arduino connected.

## Python, Flask, and Mock Arduino Tests

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

The test script sets:

```text
HALLOWEEN_AUDIO_DISABLED=1
HALLOWEEN_USE_MOCK_ARDUINO=1
HALLOWEEN_MOCK_SCENE_DELAY_SCALE=0
```

This lets the Flask API, controller state, protocol parser, STOP behavior, and
mock Arduino transactions run without audio hardware, serial hardware, or scene
delays.

## Arduino Firmware Compile

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\compile_arduino.ps1
```

The default board target is:

```text
arduino:avr:mega
```

That default is based on the current firmware pin map using pin 22. Override it
if the real board is different:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\compile_arduino.ps1 -Fqbn "arduino:avr:mega"
```

The compile script uses repo-local Arduino CLI data/download/build folders, all
ignored by git.

## Pi Display Session

The live dual-TV Pi setup now uses a repo-managed LXDE session override for a
black fallback desktop with no wallpaper or panel chrome.

Relevant files:

```text
tools/pi/lxsession/LXDE-pi/autostart
tools/pi/apply_display_session.sh
```

To re-apply that session config on the Pi:

```bash
bash tools/pi/apply_display_session.sh
```

After applying it, the idle fallback desktop should be plain black and the
cursor should remain hidden.
