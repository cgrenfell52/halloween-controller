from flask import Flask, request, jsonify, render_template_string
import os
import random
import threading
import time
import pygame

pygame.mixer.init()

AUDIO_FOLDER = os.path.join(os.path.dirname(__file__), "audio")

TRACKS = {
    "WELCOME": os.path.join(AUDIO_FOLDER, "welcome.mp3"),
    "HAG": os.path.join(AUDIO_FOLDER, "hag.mp3"),
    "SKINNY": os.path.join(AUDIO_FOLDER, "skinny.mp3"),
    "TREAT": os.path.join(AUDIO_FOLDER, "treat.mp3"),
    "TRICK": os.path.join(AUDIO_FOLDER, "trick.mp3"),
}
# Optional serial support for later
try:
    import serial  # pyserial
except ImportError:
    serial = None

app = Flask(__name__)

pygame.mixer.init()
pygame.mixer.set_num_channels(8)

AUDIO_FOLDER = os.path.join(os.path.dirname(__file__), "audio")

TRACK_FILES = {
    "WELCOME": os.path.join(AUDIO_FOLDER, "welcome.mp3"),
    "DOOR": os.path.join(AUDIO_FOLDER, "door.mp3"),
    "HAG": os.path.join(AUDIO_FOLDER, "hag.mp3"),
    "SKINNY": os.path.join(AUDIO_FOLDER, "skinny.mp3"),
    "TREAT": os.path.join(AUDIO_FOLDER, "treat.mp3"),
    "TRICK": os.path.join(AUDIO_FOLDER, "trick.mp3"),
}

TRACKS = {}

# -----------------------------
# CONFIG
# -----------------------------
USE_MOCK_ARDUINO = False
SERIAL_PORT = "COM5"
BAUD_RATE = 115200
HOST = "0.0.0.0"
PORT = 5000

PROTOCOL_VERSION = "PROP_CTRL_V2"

# -----------------------------
# OUTPUTS / HARDWARE NAMES
# -----------------------------
OUTPUT_NAMES = [
    "HEAD_1",
    "HEAD_2",
    "HORN",
    "AIR_CANNON",
    "DOOR",
    "AIR_TICKLER",
    "CRACKLER",
    "FOG",
    "STROBE",
]

SERVICE_BUTTONS = [
    ("HEAD 1", "TOGGLE:HEAD_1"),
    ("HEAD 2", "TOGGLE:HEAD_2"),
    ("HORN", "TOGGLE:HORN"),
    ("AIR CANNON", "TOGGLE:AIR_CANNON"),
    ("DOOR", "TOGGLE:DOOR"),
    ("AIR TICKLER", "TOGGLE:AIR_TICKLER"),
    ("CRACKLER", "TOGGLE:CRACKLER"),
    ("FOG", "TOGGLE:FOG"),
]

FUN_BUTTONS = [
    ("HEAD 1", "RUN:TRICK_HEAD_1"),
    ("HEAD 2", "RUN:TRICK_HEAD_2"),
    ("HORN", "RUN:TRICK_HORN"),
    ("AIR CANNON", "RUN:TRICK_AIR_CANNON"),
    ("DOOR", "RUN:DOOR_SEQUENCE"),
]

# -----------------------------
# SCENES
# -----------------------------
SCENES = {
    "TRICK_HEAD_1": {"label": "Head 1 Trick", "duration_ms": 1200},
    "TRICK_HEAD_2": {"label": "Head 2 Trick", "duration_ms": 1200},
    "TRICK_HORN": {"label": "Horn Trick", "duration_ms": 900},
    "TRICK_AIR_CANNON": {"label": "Air Cannon Trick", "duration_ms": 500},
    "TRICK_BOTH_HEADS": {"label": "Both Heads Trick", "duration_ms": 2000},
    "DOOR_SEQUENCE": {"label": "Door Sequence", "duration_ms": 3700},
    "FOG_BURST": {"label": "Fog Burst", "duration_ms": 2000},
}

TRICK_SCENES = [
    "TRICK_HEAD_1",
    "TRICK_HEAD_2",
    "TRICK_HORN",
    "TRICK_AIR_CANNON",
    "TRICK_BOTH_HEADS",
]

SCENE_TEST_BUTTONS = [
    ("RUN HEAD 1", "RUN:TRICK_HEAD_1"),
    ("RUN HEAD 2", "RUN:TRICK_HEAD_2"),
    ("RUN HORN", "RUN:TRICK_HORN"),
    ("RUN AIR CANNON", "RUN:TRICK_AIR_CANNON"),
    ("RUN BOTH HEADS", "RUN:TRICK_BOTH_HEADS"),
    ("RUN DOOR", "RUN:DOOR_SEQUENCE"),
    ("RUN FOG", "RUN:FOG_BURST"),
]

ALLOWED_SYS_COMMANDS = {
    "SYS:PING",
    "SYS:STATUS",
    "SYS:STOP",
    "SYS:RESET",
    "SYS:ALL_OFF",
}

ALLOWED_TOGGLE_COMMANDS = {f"TOGGLE:{name}" for name in OUTPUT_NAMES}
ALLOWED_RUN_COMMANDS = {f"RUN:{scene_name}" for scene_name in SCENES.keys()}
ALLOWED_COMMANDS = ALLOWED_SYS_COMMANDS | ALLOWED_TOGGLE_COMMANDS | ALLOWED_RUN_COMMANDS

# -----------------------------
# GLOBAL STATE
# -----------------------------
state = {
    "arduino_connected": False,
    "arduino_mode": "MOCK" if USE_MOCK_ARDUINO else "SERIAL",
    "protocol_version": PROTOCOL_VERSION,
    "arduino_protocol_version": "UNKNOWN",
    "system_status": "STARTING",
    "current_action": "NONE",
    "last_command": "None",
    "last_result": None,
    "last_received_status": "BOOT",
    "scene_active": False,
    "pending_fog": False,
    "next_fog_due_epoch": 0,
    "busy_until_epoch": 0,
    "outputs": {name: False for name in OUTPUT_NAMES},
    "recent_scenes": [],
    "log": [],
    "show_cancelled": False,
    "active_show_token": 0,
}

scene_bag = []
arduino = None
command_lock = threading.Lock()
system_command_lock = threading.Lock()
serial_io_lock = threading.Lock()
show_control_lock = threading.Lock()
show_token_counter = 0
audio_lock = threading.Lock()

AUDIO_CHANNELS = {
    "BACKGROUND": pygame.mixer.Channel(0),
    "MAIN": pygame.mixer.Channel(1),
    "HEAD_1": pygame.mixer.Channel(2),
    "HEAD_2": pygame.mixer.Channel(3),
    "DOOR": pygame.mixer.Channel(4),
}


# -----------------------------
# HTML
# -----------------------------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <title>Halloween Prop Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #111;
      color: #eee;
      margin: 0;
      padding: 20px;
    }
    h1, h2 {
      margin-top: 0;
    }
    .card {
      background: #1a1a1a;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
      box-shadow: 0 0 10px rgba(0,0,0,0.25);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    button, .navbtn {
      font-size: 18px;
      padding: 16px;
      border: none;
      border-radius: 10px;
      background: #2b2b2b;
      color: white;
      cursor: pointer;
      transition: background 0.2s ease, transform 0.05s ease, opacity 0.2s ease;
      text-decoration: none;
      display: inline-block;
      text-align: center;
      box-sizing: border-box;
    }
    button:hover, .navbtn:hover {
      background: #3a3a3a;
    }
    button:active {
      transform: scale(0.98);
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .good {
      background: #1f5e2d;
    }
    .danger {
      background: #7a1f1f;
    }
    .navrow {
      display: flex;
      gap: 12px;
      margin-bottom: 18px;
      flex-wrap: wrap;
    }
    .status-row {
      margin-bottom: 6px;
    }
  </style>
</head>
<body>
  <h1>Halloween Prop Control</h1>

  <div class="navrow">
    <a class="navbtn" href="/">Main</a>
    <a class="navbtn" href="/service">Service</a>
  </div>

  <div class="card">
    <div class="status-row"><strong>Arduino Connected:</strong> <span id="arduino_connected"></span></div>
    <div class="status-row"><strong>System Status:</strong> <span id="system_status"></span></div>
    <div class="status-row"><strong>Current Action:</strong> <span id="current_action"></span></div>
    <div class="status-row"><strong>Last Result:</strong> <span id="last_result"></span></div>
  </div>

  <div class="card">
    <h2>Main Show Controls</h2>
    <div class="grid">
      <button class="good" onclick="runMain('TRICK')">TRICK</button>
      <button class="good" onclick="runMain('TREAT')">TREAT</button>
      <button class="danger" onclick="runCommand('SYS:STOP')">STOP</button>
    </div>
  </div>

  <div class="card">
    <h2>Fun Buttons</h2>
    <div class="grid">
      {% for label, command in fun_buttons %}
      <button onclick="runCommand('{{ command }}')">{{ label }}</button>
      {% endfor %}
    </div>
  </div>

  <script>
    let requestInFlight = false;

    function setButtonsDisabled(disabled) {
      const buttons = document.querySelectorAll("button");
      buttons.forEach(btn => {
        btn.disabled = disabled;
      });
    }

    async function refreshStatus() {
      try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("Status request failed: " + res.status);
        const data = await res.json();

        document.getElementById("arduino_connected").textContent = data.arduino_connected;
        document.getElementById("system_status").textContent = data.system_status;
        document.getElementById("current_action").textContent = data.current_action;
        document.getElementById("last_result").textContent = data.last_result ?? "None";
      } catch (err) {
        console.error("refreshStatus error:", err);
      }
    }

    window.runMain = async function(mode) {
      if (requestInFlight) return;
      requestInFlight = true;
      setButtonsDisabled(true);

      try {
        const res = await fetch("/api/run_main", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: mode })
        });

        const data = await res.json();
        console.log("runMain:", data);
      } catch (err) {
        console.error("runMain error:", err);
      } finally {
        requestInFlight = false;
        setButtonsDisabled(false);
        refreshStatus();
      }
    };

    window.runCommand = async function(command) {
      if (requestInFlight) return;
      requestInFlight = true;
      setButtonsDisabled(true);

      try {
        const res = await fetch("/api/run_command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: command })
        });

        const data = await res.json();
        console.log("runCommand:", data);
      } catch (err) {
        console.error("runCommand error:", err);
      } finally {
        requestInFlight = false;
        setButtonsDisabled(false);
        refreshStatus();
      }
    };

    setInterval(refreshStatus, 1000);
    refreshStatus();
  </script>
</body>
</html>
"""

SERVICE_HTML = """
<!doctype html>
<html>
<head>
  <title>Halloween Prop Control - Service</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #111;
      color: #eee;
      margin: 0;
      padding: 20px;
    }
    h1, h2 {
      margin-top: 0;
    }
    .card {
      background: #1a1a1a;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
      box-shadow: 0 0 10px rgba(0,0,0,0.25);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    button, .navbtn {
      font-size: 18px;
      padding: 16px;
      border: none;
      border-radius: 10px;
      background: #2b2b2b;
      color: white;
      cursor: pointer;
      transition: background 0.2s ease, transform 0.05s ease, opacity 0.2s ease;
      text-decoration: none;
      display: inline-block;
      text-align: center;
      box-sizing: border-box;
    }
    button:hover, .navbtn:hover {
      background: #3a3a3a;
    }
    button:active {
      transform: scale(0.98);
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .danger {
      background: #7a1f1f;
    }
    .toggle-on {
      background: #1f5e2d !important;
    }
    pre {
      background: #0d0d0d;
      padding: 12px;
      border-radius: 8px;
      max-height: 320px;
      overflow: auto;
      white-space: pre-wrap;
    }
    .pill {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: #2b2b2b;
      margin: 4px;
      font-size: 14px;
    }
    .status-row {
      margin-bottom: 6px;
    }
    .mini {
      font-size: 13px;
      color: #bbb;
    }
    .history-item {
      background: #0d0d0d;
      padding: 10px;
      border-radius: 8px;
      margin-bottom: 8px;
      font-size: 14px;
    }
    .navrow {
      display: flex;
      gap: 12px;
      margin-bottom: 18px;
      flex-wrap: wrap;
    }
  </style>
</head>
<body>
  <h1>Halloween Prop Control - Service</h1>

  <div class="navrow">
    <a class="navbtn" href="/">Main</a>
    <a class="navbtn" href="/service">Service</a>
  </div>

  <div class="card">
    <div class="status-row"><strong>Arduino Mode:</strong> <span id="arduino_mode"></span></div>
    <div class="status-row"><strong>Arduino Connected:</strong> <span id="arduino_connected"></span></div>
    <div class="status-row"><strong>Controller Protocol:</strong> <span id="protocol_version"></span></div>
    <div class="status-row"><strong>Arduino Protocol:</strong> <span id="arduino_protocol_version"></span></div>
    <div class="status-row"><strong>System Status:</strong> <span id="system_status"></span></div>
    <div class="status-row"><strong>Current Action:</strong> <span id="current_action"></span></div>
    <div class="status-row"><strong>Last Command:</strong> <span id="last_command"></span></div>
    <div class="status-row"><strong>Last Result:</strong> <span id="last_result"></span></div>
    <div class="status-row"><strong>Last Received Status:</strong> <span id="last_received_status"></span></div>
    <div class="status-row"><strong>Scene Active:</strong> <span id="scene_active"></span></div>
    <div class="status-row"><strong>Pending Fog:</strong> <span id="pending_fog"></span></div>
    <div class="status-row"><strong>Busy Until:</strong> <span id="busy_until_text"></span></div>
    <div class="status-row"><strong>Show Cancelled:</strong> <span id="show_cancelled"></span></div>
    <div class="status-row"><strong>Active Show Token:</strong> <span id="active_show_token"></span></div>
  </div>

  <div class="card">
    <h2>System Controls</h2>
    <div class="grid">
      <button class="danger" onclick="runCommand('SYS:STOP')">STOP</button>
      <button class="danger" onclick="runCommand('SYS:RESET')">RESET</button>
      <button onclick="runCommand('SYS:ALL_OFF')">ALL OFF</button>
      <button onclick="runCommand('SYS:STATUS')">STATUS</button>
      <button onclick="runCommand('SYS:PING')">PING</button>
    </div>
  </div>

  <div class="card">
    <h2>Scene Test Controls</h2>
    <div class="grid">
      {% for label, command in scene_test_buttons %}
      <button onclick="runCommand('{{ command }}')">{{ label }}</button>
      {% endfor %}
    </div>
    <div class="mini" style="margin-top: 10px;">
      These directly test scene timing and output behavior.
    </div>
  </div>

  <div class="card">
    <h2>Service Toggles</h2>
    <div class="grid">
      {% for label, command in service_buttons %}
      <button id="btn-{{ command|replace(':', '-') }}" onclick="runCommand('{{ command }}')">{{ label }}</button>
      {% endfor %}
    </div>
    <div class="mini" style="margin-top: 10px;">
      STROBE is not shown here because it follows the DOOR relay on the Arduino.
    </div>
  </div>

  <div class="card">
    <h2>Output States</h2>
    <div id="output_states"></div>
  </div>

  <div class="card">
    <h2>Recent Scenes</h2>
    <div id="recent_scenes"></div>
  </div>

  <div class="card">
    <h2>Log</h2>
    <pre id="log_box"></pre>
  </div>

  <script>
    const serviceButtons = {{ service_buttons|tojson }};
    let requestInFlight = false;

    function setButtonsDisabled(disabled) {
      const buttons = document.querySelectorAll("button");
      buttons.forEach(btn => {
        btn.disabled = disabled;
      });
    }

    function formatEpoch(epochValue) {
      if (!epochValue || epochValue <= 0) return "None";
      const now = Date.now() / 1000;
      const remaining = Math.max(0, epochValue - now);
      return remaining.toFixed(1) + "s remaining";
    }

    function renderOutputPills(outputs) {
      const container = document.getElementById("output_states");
      container.innerHTML = "";
      for (const [name, enabled] of Object.entries(outputs)) {
        const span = document.createElement("span");
        span.className = "pill";
        span.textContent = name + ": " + (enabled ? "ON" : "OFF");
        if (enabled) span.style.background = "#1f5e2d";
        container.appendChild(span);
      }
    }

    function applyToggleButtonStates(outputs) {
      for (const item of serviceButtons) {
        const command = item[1];
        const parts = command.split(":");
        if (parts.length < 2) continue;

        const outputName = parts[1];
        const buttonId = "btn-" + command.replace(/:/g, "-");
        const button = document.getElementById(buttonId);
        if (!button) continue;

        if (outputs[outputName]) {
          button.classList.add("toggle-on");
        } else {
          button.classList.remove("toggle-on");
        }
      }
    }

    function renderRecentScenes(items) {
      const container = document.getElementById("recent_scenes");
      container.innerHTML = "";

      if (!items || items.length === 0) {
        container.textContent = "No scenes yet.";
        return;
      }

      const newestFirst = [...items].reverse();

      for (const item of newestFirst) {
        const div = document.createElement("div");
        div.className = "history-item";

        const started = item.started_at_text || "Unknown";
        const mode = item.mode || "Unknown";
        const scene = item.scene || "Unknown";
        const duration = item.duration_ms ?? "Unknown";

        div.innerHTML = `
          <div><strong>${scene}</strong></div>
          <div>Mode: ${mode}</div>
          <div>Duration: ${duration} ms</div>
          <div>Started: ${started}</div>
        `;
        container.appendChild(div);
      }
    }

    async function refreshStatus() {
      try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("Status request failed: " + res.status);
        const data = await res.json();

        document.getElementById("arduino_mode").textContent = data.arduino_mode;
        document.getElementById("arduino_connected").textContent = data.arduino_connected;
        document.getElementById("protocol_version").textContent = data.protocol_version;
        document.getElementById("arduino_protocol_version").textContent = data.arduino_protocol_version;
        document.getElementById("system_status").textContent = data.system_status;
        document.getElementById("current_action").textContent = data.current_action;
        document.getElementById("last_command").textContent = data.last_command;
        document.getElementById("last_result").textContent = data.last_result ?? "None";
        document.getElementById("last_received_status").textContent = data.last_received_status;
        document.getElementById("scene_active").textContent = String(data.scene_active);
        document.getElementById("pending_fog").textContent = String(data.pending_fog);
        document.getElementById("busy_until_text").textContent = formatEpoch(data.busy_until_epoch);
        document.getElementById("show_cancelled").textContent = String(data.show_cancelled);
        document.getElementById("active_show_token").textContent = String(data.active_show_token);
        document.getElementById("log_box").textContent = data.log.join("\\n");

        renderOutputPills(data.outputs);
        applyToggleButtonStates(data.outputs);
        renderRecentScenes(data.recent_scenes);
      } catch (err) {
        console.error("refreshStatus error:", err);
      }
    }

    window.runCommand = async function(command) {
      if (requestInFlight) return;
      requestInFlight = true;
      setButtonsDisabled(true);

      try {
        const res = await fetch("/api/run_command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: command })
        });

        const data = await res.json();
        console.log("runCommand:", data);
      } catch (err) {
        console.error("runCommand error:", err);
      } finally {
        requestInFlight = false;
        setButtonsDisabled(false);
        refreshStatus();
      }
    };

    setInterval(refreshStatus, 1000);
    refreshStatus();
  </script>
</body>
</html>
"""

# -----------------------------
# HELPERS
# -----------------------------
def log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    state["log"].append(entry)
    state["log"] = state["log"][-200:]
    print(entry, flush=True)


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def reset_fog_timer():
    state["next_fog_due_epoch"] = time.time() + (5 * 60)


def choose_trick_scene():
    global scene_bag

    if not scene_bag:
        scene_bag = TRICK_SCENES[:]
        random.shuffle(scene_bag)
        log(f"Refilled trick bag: {scene_bag}")

    scene = scene_bag.pop(0)
    log(f"Selected trick scene: {scene}")
    return scene


audio_lock = threading.Lock()

def load_audio():
    TRACKS.clear()

    for track_name, file_path in TRACK_FILES.items():
        if not os.path.exists(file_path):
            log(f"AUDIO WARNING -> Missing file for {track_name}: {file_path}")
            continue

        try:
            TRACKS[track_name] = pygame.mixer.Sound(file_path)
            log(f"AUDIO LOADED -> {track_name}")
        except Exception as e:
            log(f"AUDIO ERROR -> Failed to load {track_name}: {e}")

AUDIO_CHANNELS = {
    "BACKGROUND": pygame.mixer.Channel(0),
    "MAIN": pygame.mixer.Channel(1),
    "HEAD_1": pygame.mixer.Channel(2),
    "HEAD_2": pygame.mixer.Channel(3),
    "DOOR": pygame.mixer.Channel(4),
}

def play_audio(name: str, channel_name: str = "MAIN", stop_same_channel: bool = True):
    track_name = name.strip().upper()
    channel_name = channel_name.strip().upper()

    if track_name not in TRACKS:
        log(f"AUDIO ERROR -> Unknown or unloaded track: {track_name}")
        return False

    if channel_name not in AUDIO_CHANNELS:
        log(f"AUDIO ERROR -> Unknown channel: {channel_name}")
        return False

    sound = TRACKS[track_name]
    channel = AUDIO_CHANNELS[channel_name]

    with audio_lock:
        try:
            if stop_same_channel:
                channel.stop()

            channel.play(sound)
            log(f"AUDIO PLAY -> {track_name} on {channel_name}")
            return True
        except Exception as e:
            log(f"AUDIO ERROR -> Failed to play {track_name} on {channel_name}: {e}")
            return False


def set_busy_for_scene(scene_name: str):
    duration_ms = SCENES.get(scene_name, {}).get("duration_ms", 0)
    if duration_ms > 0:
        state["busy_until_epoch"] = time.time() + (duration_ms / 1000.0)
    else:
        state["busy_until_epoch"] = 0


def clear_busy_marker():
    state["busy_until_epoch"] = 0


def add_recent_scene(scene_name: str, mode: str):
    scene_info = SCENES.get(scene_name, {})
    entry = {
        "scene": scene_name,
        "mode": mode,
        "duration_ms": scene_info.get("duration_ms", 0),
        "started_at_epoch": time.time(),
        "started_at_text": now_text(),
    }
    state["recent_scenes"].append(entry)
    state["recent_scenes"] = state["recent_scenes"][-10:]


def validate_command(command: str):
    if command in ALLOWED_COMMANDS:
        return True, None
    return False, f"ERROR:INVALID_COMMAND:{command}"


def begin_new_show():
    global show_token_counter
    with show_control_lock:
        show_token_counter += 1
        state["active_show_token"] = show_token_counter
        state["show_cancelled"] = False
        return show_token_counter


def cancel_active_show(reason: str):
    with show_control_lock:
        state["show_cancelled"] = True
        token = state["active_show_token"]
    log(f"Show cancellation latched: {reason} (token={token})")


def is_show_cancelled(show_token: int):
    with show_control_lock:
        if state["show_cancelled"]:
            return True
        if state["active_show_token"] != show_token:
            return True
    return False


def apply_protocol_line(line: str):
    state["last_received_status"] = line

    if line.startswith("READY:"):
        state["arduino_protocol_version"] = line.split(":", 1)[1]
        return

    if line.startswith("STATUS:"):
        parts = line.split(":")
        if len(parts) == 2:
            state["system_status"] = parts[1]
            state["current_action"] = "NONE"
        else:
            state["system_status"] = parts[1]
            state["current_action"] = ":".join(parts[2:])

        state["scene_active"] = state["system_status"] == "RUNNING_SCENE"

        if state["system_status"] == "IDLE":
            clear_busy_marker()

        return

    if line.startswith("STATE:"):
        parts = line.split(":")
        if len(parts) == 3:
            name = parts[1]
            enabled = parts[2] == "ON"
            if name in state["outputs"]:
                state["outputs"][name] = enabled
        return

    if line == "PONG":
        state["last_result"] = "PONG"
        return

    if line.startswith("DONE:") or line.startswith("ERROR:"):
        state["last_result"] = line
        if line.startswith("DONE:"):
            clear_busy_marker()
            state["scene_active"] = False
        return


# -----------------------------
# MOCK ARDUINO
# -----------------------------
class MockArduino:
    def __init__(self):
        self.outputs = {name: False for name in OUTPUT_NAMES}
        self.system_state = "IDLE"
        self.current_action = "NONE"

    def transact(self, command: str):
        log(f"MOCK SEND -> {command}")
        lines = []

        if command == "SYS:PING":
            lines.append("READY:PROP_CTRL_V2")
            lines.append("PONG")
            return lines

        if command == "SYS:STATUS":
            if self.current_action == "NONE":
                lines.append(f"STATUS:{self.system_state}")
            else:
                lines.append(f"STATUS:{self.system_state}:{self.current_action}")
            return lines

        if command == "SYS:STOP":
            self.system_state = "STOPPING"
            self.current_action = "NONE"
            lines.append("STATUS:STOPPING")
            for key in self.outputs:
                self.outputs[key] = False
                lines.append(f"STATE:{key}:OFF")
            self.system_state = "IDLE"
            lines.append("DONE:SYS:STOP")
            lines.append("STATUS:IDLE")
            return lines

        if command == "SYS:RESET":
            self.system_state = "RESETTING"
            self.current_action = "NONE"
            lines.append("STATUS:RESETTING")
            for key in self.outputs:
                self.outputs[key] = False
                lines.append(f"STATE:{key}:OFF")
            self.system_state = "IDLE"
            lines.append("DONE:SYS:RESET")
            lines.append("STATUS:IDLE")
            return lines

        if command == "SYS:ALL_OFF":
            self.system_state = "STOPPING"
            self.current_action = "NONE"
            lines.append("STATUS:STOPPING")
            for key in self.outputs:
                self.outputs[key] = False
                lines.append(f"STATE:{key}:OFF")
            self.system_state = "IDLE"
            lines.append("DONE:SYS:ALL_OFF")
            lines.append("STATUS:IDLE")
            return lines

        if command.startswith("TOGGLE:"):
            output_name = command.split(":", 1)[1]
            if output_name not in self.outputs:
                lines.append("ERROR:UNKNOWN_COMMAND")
                return lines

            self.system_state = "RUNNING_SERVICE"
            self.current_action = output_name
            lines.append(f"STATUS:RUNNING_SERVICE:{output_name}")

            self.outputs[output_name] = not self.outputs[output_name]
            lines.append(f"STATE:{output_name}:{'ON' if self.outputs[output_name] else 'OFF'}")

            # Mirror Arduino behavior: STROBE follows DOOR when DOOR is addressed.
            if output_name == "DOOR" and "STROBE" in self.outputs:
                self.outputs["STROBE"] = self.outputs["DOOR"]
                lines.append(f"STATE:STROBE:{'ON' if self.outputs['STROBE'] else 'OFF'}")

            self.system_state = "IDLE"
            self.current_action = "NONE"
            lines.append(f"DONE:{command}")
            lines.append("STATUS:IDLE")
            return lines

        if command.startswith("RUN:"):
            action = command.split(":", 1)[1]

            if action not in SCENES:
                lines.append("ERROR:UNKNOWN_SCENE")
                return lines

            if self.system_state != "IDLE":
                lines.append("ERROR:BUSY")
                return lines

            self.system_state = "RUNNING_SCENE"
            self.current_action = action
            lines.append(f"STATUS:RUNNING_SCENE:{action}")

            duration_ms = SCENES[action]["duration_ms"]
            time.sleep(duration_ms / 1000.0)

            self.system_state = "IDLE"
            self.current_action = "NONE"
            lines.append(f"DONE:{action}")
            lines.append("STATUS:IDLE")
            return lines

        lines.append("ERROR:UNKNOWN_COMMAND")
        return lines


# -----------------------------
# SERIAL ARDUINO
# -----------------------------
class SerialArduino:
    def __init__(self, port: str, baud_rate: int):
        if serial is None:
            raise RuntimeError("pyserial is not installed. Install it with: pip install pyserial")
        self.ser = serial.Serial(port, baud_rate, timeout=0.2)
        time.sleep(4)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def transact(self, command: str):
        with serial_io_lock:
            self.ser.reset_input_buffer()
            self.ser.write((command + "\n").encode("utf-8"))
            self.ser.flush()
            log(f"SERIAL SEND -> {command}")

            lines = []
            quiet_loops = 0

            while quiet_loops < 12:
                raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if raw:
                    quiet_loops = 0
                    lines.append(raw)
                    log(f"SERIAL RECV <- {raw}")
                else:
                    quiet_loops += 1
                    time.sleep(0.05)

            return lines


# -----------------------------
# COMMAND PIPELINE
# -----------------------------
def handshake_with_arduino():
    if arduino is None:
        return False

    ok_ping = transact_system_command("SYS:PING")
    ok_status = transact_system_command("SYS:STATUS")

    if ok_ping or ok_status:
        log("Startup handshake completed.")
        return True

    log("Startup handshake incomplete.")
    return False


def connect_arduino():
    global arduino

    try:
        if USE_MOCK_ARDUINO:
            arduino = MockArduino()
            state["arduino_connected"] = True
            state["system_status"] = "IDLE"
            state["current_action"] = "NONE"
            state["last_received_status"] = "STATUS:IDLE"
            log("Connected to mock Arduino.")
        else:
            arduino = SerialArduino(SERIAL_PORT, BAUD_RATE)
            state["arduino_connected"] = True
            state["system_status"] = "IDLE"
            state["current_action"] = "NONE"
            state["last_received_status"] = "STATUS:IDLE"
            log(f"Connected to Arduino on {SERIAL_PORT} @ {BAUD_RATE}.")

        handshake_with_arduino()

    except Exception as e:
        state["arduino_connected"] = False
        state["system_status"] = "ERROR"
        state["current_action"] = "CONNECT_FAILED"
        state["last_result"] = f"ERROR:CONNECT_FAILED:{e}"
        log(f"Arduino connection failed: {repr(e)}")


def _process_command_lines(command: str, lines: list[str]):
    if not lines:
        state["last_result"] = "ERROR:NO_REPLY"
        return False

    expected_done = None
    if command.startswith("RUN:"):
        expected_done = f"DONE:{command[4:]}"
        scene_name = command[4:]
        set_busy_for_scene(scene_name)
    elif command.startswith("TOGGLE:") or command.startswith("SYS:"):
        expected_done = f"DONE:{command}"

    success = False
    state["last_result"] = None

    for line in lines:
        apply_protocol_line(line)

    for line in lines:
        if line == expected_done:
            success = True
        if line.startswith("ERROR:"):
            success = False

    if command == "SYS:PING":
        success = any(line == "PONG" for line in lines)

    if command == "SYS:STATUS":
        success = any(line.startswith("STATUS:") for line in lines)

    if expected_done and not success and state["last_result"] is None and not command.startswith("SYS:"):
        state["last_result"] = "ERROR:UNEXPECTED_REPLY"

    return success


def transact_command(command: str):
    valid, validation_error = validate_command(command)
    if not valid:
        state["last_result"] = validation_error
        log(f"Rejected invalid command: {command}")
        return False

    with command_lock:
        if arduino is None:
            state["last_result"] = "ERROR:NO_ARDUINO"
            return False

        lines = arduino.transact(command)
        return _process_command_lines(command, lines)


def transact_system_command(command: str):
    valid, validation_error = validate_command(command)
    if not valid:
        state["last_result"] = validation_error
        log(f"Rejected invalid system command: {command}")
        return False

    with system_command_lock:
        if arduino is None:
            state["last_result"] = "ERROR:NO_ARDUINO"
            return False

        lines = arduino.transact(command)
        return _process_command_lines(command, lines)


# -----------------------------
# SHOW LOGIC
# -----------------------------
def maybe_run_pending_fog_after_scene():
    if state["pending_fog"] and not state["scene_active"] and state["system_status"] == "IDLE":
        log("Running pending fog burst after scene.")
        state["pending_fog"] = False
        play_audio("WELCOME")
        add_recent_scene("FOG_BURST", "AUTO_FOG")
        if transact_command("RUN:FOG_BURST"):
            reset_fog_timer()


def run_scene(scene_name: str, mode: str, show_token=None):
    if scene_name not in SCENES:
        state["last_result"] = f"ERROR:UNKNOWN_SCENE:{scene_name}"
        log(f"Unknown scene: {scene_name}")
        return False

    if show_token is not None and is_show_cancelled(show_token):
        state["last_result"] = "ERROR:SHOW_CANCELLED"
        log(f"Refused to start scene because show is cancelled: {scene_name}")
        return False

    add_recent_scene(scene_name, mode)
    return transact_command(f"RUN:{scene_name}")
        
def play_trick_scene_audio(scene_name: str):
    play_audio("TRICK", channel_name="MAIN")

    if scene_name == "TRICK_HEAD_1":
        play_audio("HAG", channel_name="HEAD_1")
    elif scene_name == "TRICK_HEAD_2":
        play_audio("SKINNY", channel_name="HEAD_2")

    return True

def stop_audio_channel(channel_name: str):
    channel_name = channel_name.strip().upper()

    if channel_name not in AUDIO_CHANNELS:
        log(f"AUDIO ERROR -> Unknown channel for stop: {channel_name}")
        return False

    with audio_lock:
        try:
            AUDIO_CHANNELS[channel_name].stop()
            log(f"AUDIO STOP -> {channel_name}")
            return True
        except Exception as e:
            log(f"AUDIO ERROR -> Failed to stop channel {channel_name}: {e}")
            return False


def stop_all_audio():
    with audio_lock:
        try:
            pygame.mixer.stop()
            log("AUDIO STOP -> ALL")
            return True
        except Exception as e:
            log(f"AUDIO ERROR -> Failed to stop all audio: {e}")
            return False
        
def run_show(mode: str, show_token: int):
    if state["scene_active"] or state["system_status"] != "IDLE":
        state["last_result"] = "ERROR:BUSY"
        log("Busy, ignoring show request.")
        return

    state["scene_active"] = True

    try:
        if is_show_cancelled(show_token):
            state["last_result"] = "ERROR:SHOW_CANCELLED"
            log("Show cancelled before start.")
            stop_all_audio()
            return

        if mode == "TRICK":
            trick_scene = choose_trick_scene()
            state["last_command"] = f"SHOW:{mode}:{trick_scene}"

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled before trick scene.")
                stop_all_audio()
                return

            play_trick_scene_audio(trick_scene)

            if not run_scene(trick_scene, "TRICK", show_token=show_token):
                return

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled after trick scene, before door sequence.")
                stop_all_audio()
                return

            play_audio("DOOR", channel_name="DOOR")

            if not run_scene("DOOR_SEQUENCE", "TRICK", show_token=show_token):
                return

        elif mode == "TREAT":
            state["last_command"] = f"SHOW:{mode}:DOOR_SEQUENCE"

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled before door sequence.")
                stop_all_audio()
                return

            play_audio("DOOR", channel_name="DOOR")

            if not run_scene("DOOR_SEQUENCE", "TREAT", show_token=show_token):
                return

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled after door sequence, before treat audio.")
                stop_all_audio()
                return

            play_audio("TREAT", channel_name="MAIN")

        else:
            state["last_result"] = "ERROR:UNKNOWN_MODE"
            log(f"Unknown mode: {mode}")

    finally:
        state["scene_active"] = False
        clear_busy_marker()
        maybe_run_pending_fog_after_scene()


def run_manual_command(command: str):
    state["last_command"] = command

    if command in {"SYS:STOP", "SYS:RESET", "SYS:ALL_OFF"}:
        cancel_active_show(command)
        stop_all_audio()
        ok = transact_system_command(command)
    elif command in {"SYS:PING", "SYS:STATUS"}:
        ok = transact_system_command(command)
    elif command.startswith("RUN:"):
        scene_name = command[4:]
        ok = run_scene(scene_name, "MANUAL_TEST")
    else:
        ok = transact_command(command)

    if ok:
        log(f"Command complete: {command}")
    else:
        log(f"Command failed: {command} -> {state['last_result']}")


def idle_fog_worker():
    while True:
        time.sleep(1)

        if state["next_fog_due_epoch"] == 0:
            reset_fog_timer()
            continue

        now = time.time()
        if now >= state["next_fog_due_epoch"]:
            if state["scene_active"] or state["system_status"] != "IDLE":
                if not state["pending_fog"]:
                    state["pending_fog"] = True
                    log("Fog became due during active scene/state. Marked pending.")
                reset_fog_timer()
            else:
                log("Idle fog due. Running fog burst.")
                play_audio("WELCOME", channel_name="BACKGROUND")
                add_recent_scene("FOG_BURST", "AUTO_FOG")
                if transact_command("RUN:FOG_BURST"):
                    reset_fog_timer()


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    return render_template_string(
        INDEX_HTML,
        fun_buttons=FUN_BUTTONS,
    )

@app.route("/service")
def service():
    return render_template_string(
        SERVICE_HTML,
        service_buttons=SERVICE_BUTTONS,
        scene_test_buttons=SCENE_TEST_BUTTONS,
    )

@app.route("/api/status")
def api_status():
    return jsonify(state)


@app.route("/api/run_main", methods=["POST"])
def api_run_main():
    data = request.get_json(force=True)
    mode = data["mode"].strip().upper()

    if mode not in {"TRICK", "TREAT"}:
        return jsonify({"ok": False, "error": f"Invalid mode: {mode}"}), 400

    show_token = begin_new_show()
    threading.Thread(target=run_show, args=(mode, show_token), daemon=True).start()
    return jsonify({"ok": True, "mode": mode, "show_token": show_token})


@app.route("/api/run_command", methods=["POST"])
def api_run_command():
    data = request.get_json(force=True)
    command = data["command"].strip().upper()

    valid, validation_error = validate_command(command)
    if not valid:
        return jsonify({"ok": False, "error": validation_error}), 400

    threading.Thread(target=run_manual_command, args=(command,), daemon=True).start()
    return jsonify({"ok": True, "command": command})


if __name__ == "__main__":
    load_audio()
    connect_arduino()
    reset_fog_timer()
    threading.Thread(target=idle_fog_worker, daemon=True).start()
    log(f"Web app starting on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)