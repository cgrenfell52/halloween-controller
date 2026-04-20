# Halloween Prop Controller

See README.md for the GitHub-facing primary documentation.

This file is the short local summary.

## What The System Does

- Raspberry Pi 5 runs the Flask controller UI, GPIO triggers, audio, serial, and TV video playback.
- Arduino Mega runs the timing-critical prop outputs and scenes.
- Ambient dual-screen video loops continuously.
- Triggered dual-screen video plays after the end of a TRICK or TREAT show flow.

## Hardware Pins

- HEAD_1 / Skinny: pin 4
- HEAD_2 / Hag: pin 5
- AIR_CANNON: pin 6
- AIR_TICKLER: pin 7
- DOOR: pin 8
- HORN: pin 9
- CRACKLER: pin 10
- STROBE: pin 13
- FOG: pin 22

Pi dry-contact triggers:

- TRICK: GPIO17 / physical pin 11
- TREAT: GPIO27 / physical pin 13
- ground: any Pi GND pin

## Important Runtime Facts

- Protocol version: PROP_CTRL_V2
- Arduino baud rate: 115200
- Default serial port: /dev/ttyACM0 with fallback scanning for /dev/ttyACM* and /dev/ttyUSB*
- Startup system volume request: 100 percent by default
- Quiet time defaults: 21:00 to 08:00, configurable in app settings

## TV Video

- video/ambient.mp4 = looping idle video
- video/triggered.mp4 = one-shot triggered video
- both are combined 3840x1080 files
- left half = left TV
- right half = right TV

The deployed Pi uses an X11 extended desktop and app-managed mpv playback.

## Core Rules

- Keep timing-critical relay logic on the Arduino.
- Keep Flask responsive.
- Preserve STOP responsiveness.
- Keep Python and firmware protocol behavior aligned.
- Update README.md and handoff.txt when architecture changes materially.
