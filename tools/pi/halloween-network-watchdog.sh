#!/usr/bin/env bash
set -euo pipefail

IFACE="${HALLOWEEN_NET_IFACE:-wlan0}"
TARGETS="${HALLOWEEN_NET_TARGETS:-1.1.1.1 8.8.8.8}"
FAILURE_THRESHOLD="${HALLOWEEN_NET_FAILURE_THRESHOLD:-3}"
FAILURE_FILE="${HALLOWEEN_NET_FAILURE_FILE:-/run/halloween-network-watchdog.failures}"
APP_SERVICE="${HALLOWEEN_APP_SERVICE:-halloween.service}"
APP_HEALTH_URL="${HALLOWEEN_APP_HEALTH_URL:-http://127.0.0.1:5000/healthz}"
RESTART_APP_ON_HEALTH_FAILURE="${HALLOWEEN_RESTART_APP_ON_HEALTH_FAILURE:-0}"
TAILSCALE_RECOVERY_ENABLED="${HALLOWEEN_TAILSCALE_RECOVERY_ENABLED:-1}"
TAILSCALE_FAILURE_THRESHOLD="${HALLOWEEN_TAILSCALE_FAILURE_THRESHOLD:-3}"
TAILSCALE_FAILURE_FILE="${HALLOWEEN_TAILSCALE_FAILURE_FILE:-/run/halloween-tailscale-watchdog.failures}"

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

record_tailscale_success() {
  rm -f "$TAILSCALE_FAILURE_FILE"
}

record_tailscale_failure() {
  local failures=0
  if [ -f "$TAILSCALE_FAILURE_FILE" ]; then
    failures="$(cat "$TAILSCALE_FAILURE_FILE" 2>/dev/null || printf '0')"
  fi
  failures=$((failures + 1))
  printf '%s\n' "$failures" > "$TAILSCALE_FAILURE_FILE"
  printf '%s\n' "$failures"
}

disable_wifi_power_save() {
  if ! command -v iw >/dev/null 2>&1; then
    log "iw not installed; cannot verify WiFi power save"
    return
  fi

  local before=""
  before="$(iw dev "$IFACE" get power_save 2>/dev/null || true)"
  iw dev "$IFACE" set power_save off >/dev/null 2>&1 || true
  local after=""
  after="$(iw dev "$IFACE" get power_save 2>/dev/null || true)"

  if [ "$after" = "Power save: off" ]; then
    if [ "$before" != "$after" ]; then
      log "disabled WiFi power save on ${IFACE}"
    fi
    return
  fi

  log "could not disable WiFi power save on ${IFACE}: ${after:-unknown status}"
}

check_tailscale_health() {
  if [ "$TAILSCALE_RECOVERY_ENABLED" != "1" ] || ! command -v tailscale >/dev/null 2>&1; then
    return 0
  fi

  tailscale status --json 2>/dev/null | python3 -c 'import json, sys
try:
    status = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)

health = status.get("Health") or []
backend = status.get("BackendState")
if backend == "Running" and not health:
    raise SystemExit(0)
print("; ".join(str(item) for item in health) or f"BackendState={backend}")
raise SystemExit(1)
'
}

recover_tailscale_if_needed() {
  if [ "$TAILSCALE_RECOVERY_ENABLED" != "1" ] || ! command -v tailscale >/dev/null 2>&1; then
    return
  fi

  local health_output=""
  if health_output="$(check_tailscale_health 2>&1)"; then
    record_tailscale_success
    return
  fi

  local failures=""
  failures="$(record_tailscale_failure)"
  log "tailscale health check failed; consecutive failures=${failures}; ${health_output:-no status}"

  if [ "$failures" -ge "$TAILSCALE_FAILURE_THRESHOLD" ]; then
    log "restarting tailscaled after ${TAILSCALE_FAILURE_THRESHOLD} consecutive health failures"
    systemctl restart tailscaled.service || true
    record_tailscale_success
  fi
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

disable_wifi_power_save

recover_app_if_needed
recover_tailscale_if_needed

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
