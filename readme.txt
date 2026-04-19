# Halloween Prop Controller

This project controls a Raspberry Pi 5 and Arduino-based Halloween prop setup.

The Raspberry Pi is the controller. It runs the Flask web interface, handles
TRICK/TREAT inputs, plays audio with pygame, and sends scene commands over
serial.

The Arduino is the hardware executor. It receives PROP_CTRL_V2 serial commands
from the Pi, switches physical outputs, runs timing-sensitive relay sequences,
and reports state back to the controller.

## Current Status

- Flask controller app exists in app.py.
- Arduino firmware exists in arduino/firmware/firmware.ino.
- Audio effects are stored in audio/.
- The deployed system is intended to run automatically with systemd on the Pi.
- The Arduino is expected at /dev/ttyACM0 on the Pi.
- Serial baud rate is 115200.

## Architecture

Pi responsibilities:

- Web UI
- Show orchestration
- GPIO trigger handling
- Audio playback
- Serial command dispatch
- STOP/audio cancellation behavior

Arduino responsibilities:

- Physical relay/output control
- Timing-critical scene execution
- Safe output shutdown
- Protocol state reporting

Timing-critical prop behavior should stay on the Arduino. The Flask app should
remain responsive and should not block the main web thread.

## Arduino Pin Layout

Current active output layout:

- HEAD_1 / Skinny: pin 4
- HEAD_2 / Hag: pin 5
- AIR_CANNON: pin 6
- AIR_TICKLER: pin 7
- DOOR: pin 8
- HORN / Ooga horn: pin 9
- CRACKLER: pin 10
- STROBE: pin 13
- FOG: pin 22

TV_1 and TV_2 are not active right now.

## Raspberry Pi Trigger Wiring

The TRICK and TREAT triggers are dry-contact switches wired to Pi GPIO inputs
with internal pull-up resistors enabled.

- TRICK trigger: GPIO17, physical pin 11
- TREAT trigger: GPIO27, physical pin 13
- Shared trigger ground: any Pi GND pin, for example physical pin 9 or 14

Wire each switch between its GPIO input and GND. Do not connect trigger wiring
to 3.3V or 5V.

Runtime overrides:

- HALLOWEEN_GPIO_DISABLED=1 disables physical trigger inputs.
- HALLOWEEN_TRICK_GPIO changes the TRICK GPIO number.
- HALLOWEEN_TREAT_GPIO changes the TREAT GPIO number.
- HALLOWEEN_GPIO_BOUNCE_TIME changes debounce time in seconds.

## Audio Volume

On startup, the controller asks the Pi system mixer to set output volume to
100 percent so final loudness can be adjusted on the external speakers.

Runtime overrides:

- HALLOWEEN_SYSTEM_VOLUME changes the requested system mixer volume percentage.
- HALLOWEEN_SET_SYSTEM_VOLUME=0 disables startup system volume changes.

## Important Files

- app.py: Main Flask controller, UI, serial communication, audio, and show logic.
- audio/: Sound effects used by the controller.
- arduino/firmware/firmware.ino: Arduino firmware for physical prop outputs.
- handoff.txt: Current project handoff and architecture notes for future work.
- readme.txt: This project overview.

## Serial Protocol

Protocol version: PROP_CTRL_V2

The Pi sends commands:

- RUN:<scene>
- TOGGLE:<output>
- SYS:<command>

The Arduino responds with lines such as:

- READY:PROP_CTRL_V2
- STATUS:<state>
- STATUS:RUNNING_SCENE:<scene>
- STATUS:RUNNING_SERVICE:<output>
- STATE:<output>:ON
- STATE:<output>:OFF
- DONE:<command>
- ERROR:<reason>

The controller expects commands to complete with either DONE or ERROR. Output
state changes should always be reported with STATE lines.

## System Commands

- SYS:PING
- SYS:STATUS
- SYS:STOP
- SYS:RESET
- SYS:ALL_OFF

STOP is safety-critical. It must stop audio, cancel the active show, and return
Arduino outputs to a safe OFF state.

## Scenes

Scene execution is split into two layers.

Python/Pi layer:

- Selects the scene.
- Plays audio.
- Sends RUN:<scene> to the Arduino.
- Sequences larger flows such as TRICK followed by DOOR.

Arduino layer:

- Executes output timing.
- Controls relays/effects.
- Reports completion with DONE:<scene>.

Known scenes include:

- TRICK_HEAD_1
- TRICK_HEAD_2
- TRICK_HORN
- TRICK_AIR_CANNON
- TRICK_BOTH_HEADS
- DOOR_SEQUENCE
- FOG_BURST

## Manual Run On Pi

The deployed app normally starts through systemd. For manual testing on the Pi:

```bash
source venv/bin/activate
python app.py
```

The web app listens on:

```text
http://<pi-address>:5000
```

## Deployment Notes

The Pi service is expected to be managed by:

```text
/etc/systemd/system/halloween.service
```

Important runtime configuration from the handoff:

- SERIAL_PORT = /dev/ttyACM0
- BAUD_RATE = 115200

On Raspberry Pi 5, GPIO support should use the system packages:

```bash
sudo apt install -y python3-gpiozero python3-lgpio
python3 -m venv --system-site-packages venv
```

Do not install lgpio through pip on the Pi. The apt package avoids local build
tool requirements and gives gpiozero the pin factory it needs for GPIO17 and
GPIO27.

## Development Notes

Before making changes, read handoff.txt.

Keep these constraints in mind:

- Do not move timing-critical relay logic from Arduino to Python.
- Do not block the Flask main thread.
- Keep serial communication compatible with PROP_CTRL_V2.
- Preserve STOP responsiveness.
- Keep Arduino outputs safe after STOP, RESET, and ALL_OFF.

## Next Goals

- Expand Arduino scene logic.
- Add smarter trigger logic.
- Improve reliability around STOP, serial state, and safe output handling.
- Keep Python orchestration and Arduino execution boundaries clear.
