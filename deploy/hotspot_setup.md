# HauntOS Hotspot Mode

Hotspot mode lets a Raspberry Pi create its own WiFi network for show control.
It is optional and is not required for local development.

## Target Behavior

- WiFi SSID: `HauntOS`
- WiFi password: `hauntcontroller`
- Pi hotspot address: `192.168.4.1`
- Connected phones/tablets receive DHCP addresses from the Pi
- HauntOS UI opens at `http://192.168.4.1:5000`

HauntOS already runs Flask on `0.0.0.0:5000`, which allows browsers connected
to the hotspot to reach the web interface.

## Recommended Raspberry Pi OS Method

Recent Raspberry Pi OS releases use NetworkManager by default. See the
Raspberry Pi networking documentation:
`https://www.raspberrypi.com/documentation/computers/configuration.html#networking`

The installer in this folder uses `nmcli` to create an access point connection
named `HauntOS-Hotspot` with IPv4 shared mode. NetworkManager shared mode
provides the static Pi address and DHCP service for connected devices.

## Install

Run this from the Pi console or over a connection you can afford to lose:

```bash
cd /home/pi/hauntos
chmod +x deploy/install_hotspot.sh
./deploy/install_hotspot.sh
```

The script will warn before changing networking. Type `YES` to continue.

After install:

1. Connect your phone or tablet to WiFi network `HauntOS`.
2. Use password `hauntcontroller`.
3. Open `http://192.168.4.1:5000` in the browser.

## Optional Captive Portal Auto-Open

Phones and tablets usually auto-open a page only when the hotspot behaves like a
captive portal. HauntOS includes an optional helper for that.

Install hotspot mode first, then run:

```bash
cd /home/pi/hauntos
chmod +x deploy/install_captive_portal.sh
./deploy/install_captive_portal.sh
```

The captive portal helper:

- Runs a tiny port 80 redirect service
- Redirects plain HTTP requests to `http://192.168.4.1:5000`
- Adds a NetworkManager `dnsmasq-shared` catch-all DNS rule

This improves auto-open behavior, but mobile operating systems vary. The manual
URL remains:

```text
http://192.168.4.1:5000
```

Disable captive portal helper:

```bash
cd /home/pi/hauntos
./deploy/install_captive_portal.sh --disable
```

## Custom Values

You can override defaults with environment variables:

```bash
HAUNTOS_HOTSPOT_SSID="HauntOS" \
HAUNTOS_HOTSPOT_PASSWORD="hauntcontroller" \
HAUNTOS_WIFI_IFACE="wlan0" \
./deploy/install_hotspot.sh
```

The password must be at least 8 characters for WPA-PSK.

## Disable Hotspot

Use the script rollback mode:

```bash
cd /home/pi/hauntos
./deploy/install_hotspot.sh --disable
```

This brings down and deletes only the `HauntOS-Hotspot` NetworkManager
connection. It does not remove NetworkManager or change saved home WiFi
connections.

Manual rollback commands:

```bash
sudo nmcli connection down HauntOS-Hotspot
sudo nmcli connection delete HauntOS-Hotspot
sudo nmcli radio wifi on
```

Then reconnect the Pi to your normal WiFi network.

## Notes

- Installing hotspot mode may disconnect an active WiFi SSH session.
- Prefer doing first setup with a keyboard/monitor or Ethernet attached.
- If your Pi uses an older non-NetworkManager network stack, review the script
  before running it. The script installs/enables NetworkManager if `nmcli` is
  missing.
- The HauntOS systemd service is separate. Install it with
  `deploy/install_service.sh` so the web UI starts at boot.
- The captive portal helper is separate. Install it only after hotspot mode is
  working.
