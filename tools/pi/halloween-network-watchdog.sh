#!/usr/bin/env bash
set -euo pipefail

IFACE="${HALLOWEEN_NET_IFACE:-wlan0}"
TARGETS="${HALLOWEEN_NET_TARGETS:-1.1.1.1 8.8.8.8}"
FAILURE_THRESHOLD="${HALLOWEEN_NET_FAILURE_THRESHOLD:-3}"
FAILURE_FILE="${HALLOWEEN_NET_FAILURE_FILE:-/run/halloween-network-watchdog.failures}"
APP_SERVICE="${HALLOWEEN_APP_SERVICE:-halloween.service}"
APP_HEALTH_URL="${HALLOWEEN_APP_HEALTH_URL:-http://127.0.0.1:5000/healthz}"
RESTART_APP_ON_HEALTH_FAILURE="${HALLOWEEN_RESTART_APP_ON_HEALTH_FAILURE:-0}"

log() {
  printf 'halloween-network-watchdog: %s\n' "$*"
}

ping_target() {
  ping -I "$IFACE" -c 1 -W 2 "$1" >/dev/null 2>&1
}

route_gateway() {
  ip route show default 2>/dev/null | awk -v iface="$IFACE" '$0 ~ "dev " iface {print $3; exit}'
}

record_network_success() {
  rm -f "$FAILURE_FILE"
}

record_network_failure() {
  local failures=0
  if [ -f "$FAILURE_FILE" ]; then
    failures="$(cat "$FAILURE_FILE" 2>/dev/null || printf '0')"
  fi
  failures=$((failures + 1))
  printf '%s\n' "$failures" > "$FAILURE_FILE"
  printf '%s\n' "$failures"
}

check_app() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "$APP_HEALTH_URL" >/dev/null
    return
  fi

  python3 - "$APP_HEALTH_URL" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=3) as response:
    if response.status >= 400:
        raise SystemExit(1)
PY
}

recover_app_if_needed() {
  if check_app; then
    return
  fi

  if [ "$RESTART_APP_ON_HEALTH_FAILURE" = "1" ]; then
    log "local app health check failed; restarting ${APP_SERVICE}"
    systemctl restart "$APP_SERVICE"
  else
    log "local app health check failed; leaving ${APP_SERVICE} running"
  fi
}

recover_network() {
  log "network failed ${FAILURE_THRESHOLD} consecutive checks; restarting network stack for ${IFACE}"

  if command -v nmcli >/dev/null 2>&1; then
    nmcli device disconnect "$IFACE" >/dev/null 2>&1 || true
    sleep 3
    nmcli device connect "$IFACE" >/dev/null 2>&1 || true
    nmcli networking off >/dev/null 2>&1 || true
    sleep 2
    nmcli networking on >/dev/null 2>&1 || true
    return
  fi

  if systemctl list-unit-files NetworkManager.service >/dev/null 2>&1; then
    systemctl restart NetworkManager.service
    return
  fi

  if systemctl list-unit-files dhcpcd.service >/dev/null 2>&1; then
    systemctl restart dhcpcd.service
    return
  fi

  if systemctl list-unit-files wpa_supplicant.service >/dev/null 2>&1; then
    systemctl restart wpa_supplicant.service
    return
  fi

  ip link set "$IFACE" down || true
  sleep 3
  ip link set "$IFACE" up || true
}

if command -v iw >/dev/null 2>&1; then
  iw dev "$IFACE" set power_save off >/dev/null 2>&1 || true
fi

recover_app_if_needed

gateway="$(route_gateway || true)"
if [ -n "$gateway" ] && ping_target "$gateway"; then
  record_network_success
  log "network ok via gateway ${gateway}"
  exit 0
fi

for target in $TARGETS; do
  if ping_target "$target"; then
    record_network_success
    log "network ok via ${target}"
    exit 0
  fi
done

failures="$(record_network_failure)"
log "network check failed on ${IFACE}; consecutive failures=${failures}"

if [ "$failures" -ge "$FAILURE_THRESHOLD" ]; then
  recover_network
  record_network_success
fi
