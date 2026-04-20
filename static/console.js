const stateFields = [
  "arduino_mode",
  "arduino_serial_port",
  "arduino_connected",
  "protocol_version",
  "arduino_protocol_version",
  "system_status",
  "current_action",
  "last_command",
  "last_result",
  "last_received_status",
  "serial_reconnect_state",
  "serial_reconnect_attempts",
  "serial_last_error",
  "scene_active",
  "pending_fog",
  "show_cancelled",
  "active_show_token",
  "gpio_enabled",
  "gpio_trick_pin",
  "gpio_treat_pin",
  "quiet_mode_enabled",
  "quiet_mode_active",
  "quiet_start_time",
  "quiet_end_time"
];

let requestInFlight = false;

function setText(id, value, fallback = "None") {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = value === null || value === undefined || value === "" ? fallback : String(value);
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll("button").forEach((button) => {
    if (button.dataset.emergency === "true") return;
    button.disabled = disabled;
  });
}

function statusClass(status) {
  const value = String(status || "").toUpperCase();
  if (value === "IDLE") return "badge badge-idle";
  if (value.includes("STOP") || value.includes("RESET")) return "badge badge-stop";
  if (value.includes("ERROR") || value.includes("FAILED")) return "badge badge-error";
  if (value.includes("RUNNING")) return "badge badge-running";
  return "badge badge-muted";
}

function updateBadges(data) {
  const statusBadge = document.getElementById("status_badge");
  if (statusBadge) {
    statusBadge.textContent = data.system_status || "UNKNOWN";
    statusBadge.className = statusClass(data.system_status);
  }

  const modeBadge = document.getElementById("mode_badge");
  if (modeBadge) {
    modeBadge.textContent = data.arduino_mode || "UNKNOWN";
    modeBadge.className = data.arduino_mode === "SERIAL" ? "badge badge-idle" : "badge badge-running";
  }
}

function formatBusyUntil(epochValue) {
  if (!epochValue || epochValue <= 0) return "None";
  const remaining = Math.max(0, epochValue - Date.now() / 1000);
  return `${remaining.toFixed(1)}s remaining`;
}

function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return "Never";
  return `${Number(seconds).toFixed(1)}s ago`;
}

function renderOutputTiles(outputs) {
  const container = document.getElementById("output_tiles");
  if (!container || !outputs) return;

  container.replaceChildren();
  Object.entries(outputs).forEach(([name, enabled]) => {
    const tile = document.createElement("div");
    tile.className = `output-tile${enabled ? " on" : ""}`;

    const label = document.createElement("div");
    label.className = "output-name";
    label.textContent = name.replace(/_/g, " ");

    const state = document.createElement("div");
    state.className = "output-state";
    state.textContent = enabled ? "ON" : "OFF";

    tile.append(label, state);
    container.appendChild(tile);
  });
}

function applyToggleButtonStates(outputs) {
  const serviceButtons = window.SERVICE_BUTTONS || [];

  serviceButtons.forEach((item) => {
    const command = item[1];
    const outputName = command.split(":")[1];
    const button = document.getElementById(`btn-${command.replace(/:/g, "-")}`);
    if (!button || !outputName) return;

    button.classList.toggle("toggle-on", Boolean(outputs && outputs[outputName]));
  });
}

function renderRecentScenes(items) {
  const container = document.getElementById("recent_scenes");
  if (!container) return;

  container.replaceChildren();
  if (!items || items.length === 0) {
    container.textContent = "No scenes yet.";
    return;
  }

  [...items].reverse().forEach((item) => {
    const row = document.createElement("div");
    row.className = "history-item";

    const title = document.createElement("strong");
    title.textContent = item.scene || "Unknown";

    const meta = document.createElement("div");
    meta.className = "history-meta";
    meta.textContent = `${item.mode || "Unknown"} | ${item.duration_ms || 0} ms | ${item.started_at_text || "Unknown"}`;

    row.append(title, meta);
    container.appendChild(row);
  });
}

function renderLog(lines) {
  const box = document.getElementById("log_box");
  if (!box) return;
  box.textContent = (lines || []).slice(-80).join("\n");
  box.scrollTop = box.scrollHeight;
}

function applyState(data) {
  stateFields.forEach((field) => setText(field, data[field]));
  setText("busy_until_text", formatBusyUntil(data.busy_until_epoch));
  setText("serial_last_heard_text", formatAge(data.serial_last_heard_seconds_ago));
  setText("serial_last_connected_text", formatAge(data.serial_last_connected_seconds_ago));
  setText("serial_last_error_text", formatAge(data.serial_last_error_seconds_ago));
  setText("trick_bag_available_scenes", (data.trick_bag_available_scenes || []).join(", "), "None");
  updateBadges(data);
  renderOutputTiles(data.outputs);
  applyToggleButtonStates(data.outputs);
  renderRecentScenes(data.recent_scenes);
  renderLog(data.log);
  syncSettingsForm(data);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error(`Status request failed: ${response.status}`);
    applyState(await response.json());
  } catch (error) {
    console.error("refreshStatus error:", error);
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

async function runMain(mode) {
  if (requestInFlight) return;
  requestInFlight = true;
  setButtonsDisabled(true);

  try {
    await postJson("/api/run_main", { mode });
  } catch (error) {
    console.error("runMain error:", error);
  } finally {
    requestInFlight = false;
    setButtonsDisabled(false);
    refreshStatus();
  }
}

async function runCommand(command) {
  if (requestInFlight && command !== "SYS:STOP" && command !== "SYS:RESET") return;
  requestInFlight = true;
  setButtonsDisabled(true);

  try {
    await postJson("/api/run_command", { command });
  } catch (error) {
    console.error("runCommand error:", error);
  } finally {
    requestInFlight = false;
    setButtonsDisabled(false);
    refreshStatus();
  }
}

function syncSettingsForm(data) {
  const form = document.getElementById("settings_form");
  if (!form || form.dataset.dirty === "true") return;

  const quietEnabled = document.getElementById("quiet_mode_enabled_input");
  const quietStart = document.getElementById("quiet_start_time_input");
  const quietEnd = document.getElementById("quiet_end_time_input");

  if (quietEnabled) quietEnabled.checked = Boolean(data.quiet_mode_enabled);
  if (quietStart) quietStart.value = data.quiet_start_time || "21:00";
  if (quietEnd) quietEnd.value = data.quiet_end_time || "08:00";
}

async function saveSettings(form) {
  const quietEnabled = document.getElementById("quiet_mode_enabled_input");
  const quietStart = document.getElementById("quiet_start_time_input");
  const quietEnd = document.getElementById("quiet_end_time_input");
  const status = document.getElementById("settings_status");

  try {
    await postJson("/api/settings", {
      quiet_mode_enabled: Boolean(quietEnabled && quietEnabled.checked),
      quiet_start_time: quietStart ? quietStart.value : "21:00",
      quiet_end_time: quietEnd ? quietEnd.value : "08:00"
    });
    form.dataset.dirty = "false";
    if (status) status.textContent = "Saved";
    refreshStatus();
  } catch (error) {
    console.error("saveSettings error:", error);
    if (status) status.textContent = error.message || "Save failed";
  }
}

document.addEventListener("click", (event) => {
  const mainButton = event.target.closest("[data-main]");
  if (mainButton) {
    runMain(mainButton.dataset.main);
    return;
  }

  const commandButton = event.target.closest("[data-command]");
  if (commandButton) {
    runCommand(commandButton.dataset.command);
  }
});

document.addEventListener("input", (event) => {
  const form = event.target.closest("#settings_form");
  if (form) {
    form.dataset.dirty = "true";
    const status = document.getElementById("settings_status");
    if (status) status.textContent = "Unsaved";
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("#settings_form");
  if (!form) return;

  event.preventDefault();
  saveSettings(form);
});

refreshStatus();
setInterval(refreshStatus, 1000);
