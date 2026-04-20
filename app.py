from datetime import timedelta
import glob
import hmac
import json
from flask import Flask, request, jsonify, render_template, redirect, session, url_for
import os
import random
import shutil
import subprocess
import threading
import time


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


AUDIO_DISABLED = env_flag("HALLOWEEN_AUDIO_DISABLED")
SET_SYSTEM_VOLUME = env_flag("HALLOWEEN_SET_SYSTEM_VOLUME", default=True)
SYSTEM_VOLUME_PERCENT = int(os.environ.get("HALLOWEEN_SYSTEM_VOLUME", "100"))
SERIAL_RECONNECT_INTERVAL_SECONDS = float(os.environ.get("HALLOWEEN_SERIAL_RECONNECT_INTERVAL", "5"))
VIDEO_DISABLED = env_flag("HALLOWEEN_VIDEO_DISABLED", default=(os.name == "nt"))

try:
    import pygame
except ImportError:
    pygame = None


def set_startup_system_volume():
    if AUDIO_DISABLED or not SET_SYSTEM_VOLUME:
        return

    volume = max(0, min(100, SYSTEM_VOLUME_PERCENT))
    commands = []

    if shutil.which("pactl"):
        commands.extend(
            [
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
            ]
        )

    if shutil.which("amixer"):
        for control in ("Master", "PCM", "Speaker", "Headphone"):
            commands.append(["amixer", "-q", "sset", control, f"{volume}%", "unmute"])

    success = False
    for command in commands:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            success = success or result.returncode == 0
        except Exception:
            continue

    if success:
        print(f"AUDIO VOLUME -> requested system output volume {volume}%", flush=True)
    else:
        print("AUDIO VOLUME WARNING -> no system mixer command succeeded.", flush=True)


def init_audio_mixer():
    if AUDIO_DISABLED:
        return False

    if pygame is None:
        print("AUDIO WARNING -> pygame is not installed; audio disabled.", flush=True)
        return False

    set_startup_system_volume()

    try:
        pygame.mixer.init()
        pygame.mixer.set_num_channels(8)
        return True
    except Exception as e:
        print(f"AUDIO WARNING -> mixer init failed; audio disabled: {e}", flush=True)
        return False


class NullAudioChannel:
    def play(self, sound):
        return None

    def stop(self):
        return None


AUDIO_MIXER_READY = init_audio_mixer()


def make_audio_channels():
    if AUDIO_MIXER_READY:
        return {
            "BACKGROUND": pygame.mixer.Channel(0),
            "MAIN": pygame.mixer.Channel(1),
            "HEAD_1": pygame.mixer.Channel(2),
            "HEAD_2": pygame.mixer.Channel(3),
            "DOOR": pygame.mixer.Channel(4),
        }

    return {
        "BACKGROUND": NullAudioChannel(),
        "MAIN": NullAudioChannel(),
        "HEAD_1": NullAudioChannel(),
        "HEAD_2": NullAudioChannel(),
        "DOOR": NullAudioChannel(),
    }


AUDIO_FOLDER = os.path.join(os.path.dirname(__file__), "audio")

# Optional serial support for later
try:
    import serial  # pyserial
except ImportError:
    serial = None

try:
    from gpiozero import Button
except ImportError:
    Button = None

app = Flask(__name__)

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
USE_MOCK_ARDUINO = env_flag("HALLOWEEN_USE_MOCK_ARDUINO")
MOCK_SCENE_DELAY_SCALE = float(os.environ.get("HALLOWEEN_MOCK_SCENE_DELAY_SCALE", "1"))
GPIO_DISABLED = env_flag("HALLOWEEN_GPIO_DISABLED")
TRICK_GPIO_PIN = int(os.environ.get("HALLOWEEN_TRICK_GPIO", "17"))
TREAT_GPIO_PIN = int(os.environ.get("HALLOWEEN_TREAT_GPIO", "27"))
GPIO_BOUNCE_TIME = float(os.environ.get("HALLOWEEN_GPIO_BOUNCE_TIME", "0.1"))
SERIAL_PORT = os.environ.get("HALLOWEEN_SERIAL_PORT", "/dev/ttyACM0")
BAUD_RATE = 115200
HOST = "0.0.0.0"
PORT = 5000
ACCESS_PASSWORD = os.environ.get("HALLOWEEN_ACCESS_PASSWORD", "")
SESSION_SECRET = os.environ.get("HALLOWEEN_SECRET_KEY", ACCESS_PASSWORD or "halloween-dev-secret")
SESSION_DAYS = int(os.environ.get("HALLOWEEN_SESSION_DAYS", "180"))
SETTINGS_FILE = os.environ.get(
    "HALLOWEEN_SETTINGS_FILE",
    os.path.join(os.path.dirname(__file__), "settings.local.json"),
)
VIDEO_FOLDER = os.path.join(os.path.dirname(__file__), "video")
VIDEO_PLAYER = os.environ.get("HALLOWEEN_VIDEO_PLAYER", "mpv")
VIDEO_DISPLAY = os.environ.get("HALLOWEEN_VIDEO_DISPLAY", ":0")
VIDEO_XAUTHORITY = os.environ.get("HALLOWEEN_VIDEO_XAUTHORITY", "/home/candydisp/.Xauthority")
VIDEO_AMBIENT_FILE = os.environ.get(
    "HALLOWEEN_VIDEO_AMBIENT_FILE",
    os.path.join(VIDEO_FOLDER, "ambient.mp4"),
)
VIDEO_TRIGGERED_FILE = os.environ.get(
    "HALLOWEEN_VIDEO_TRIGGERED_FILE",
    os.path.join(VIDEO_FOLDER, "triggered.mp4"),
)

app.secret_key = SESSION_SECRET
app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)

PROTOCOL_VERSION = "PROP_CTRL_V2"

# -----------------------------
# OUTPUTS / HARDWARE NAMES
# -----------------------------
OUTPUT_NAMES = [
    "HEAD_1",
    "HEAD_2",
    "AIR_CANNON",
    "AIR_TICKLER",
    "DOOR",
    "HORN",
    "CRACKLER",
    "STROBE",
    "FOG",
]

SERVICE_BUTTONS = [
    ("HEAD 1 / SKINNY", "TOGGLE:HEAD_1"),
    ("HEAD 2 / HAG", "TOGGLE:HEAD_2"),
    ("AIR CANNON", "TOGGLE:AIR_CANNON"),
    ("AIR TICKLER", "TOGGLE:AIR_TICKLER"),
    ("DOOR OPEN/CLOSE", "TOGGLE:DOOR"),
    ("OOGA HORN", "TOGGLE:HORN"),
    ("CRACKLER", "TOGGLE:CRACKLER"),
    ("STROBE", "TOGGLE:STROBE"),
    ("FOG", "TOGGLE:FOG"),
]

FUN_BUTTONS = [
    ("HEAD 1", "RUN:TRICK_HEAD_1"),
    ("HEAD 2", "RUN:TRICK_HEAD_2"),
    ("HORN", "RUN:TRICK_HORN"),
    ("CRACKLER", "RUN:TRICK_CRACKLER"),
    ("AIR CANNON", "RUN:TRICK_AIR_CANNON"),
    ("DOOR", "RUN:DOOR_SEQUENCE"),
]

# -----------------------------
# SCENES
# -----------------------------
SCENES = {
    "TRICK_HEAD_1": {"label": "Head 1 / Skinny Trick", "duration_ms": 1200},
    "TRICK_HEAD_2": {"label": "Head 2 / Hag Trick", "duration_ms": 1200},
    "TRICK_HORN": {"label": "Ooga Horn Trick", "duration_ms": 900},
    "TRICK_CRACKLER": {"label": "Crackler Trick", "duration_ms": 900},
    "TRICK_AIR_CANNON": {"label": "Air Cannon Trick", "duration_ms": 300},
    "TRICK_BOTH_HEADS": {"label": "Both Heads Trick", "duration_ms": 2000},
    "DOOR_SEQUENCE": {"label": "Door Sequence", "duration_ms": 22000},
    "FOG_BURST": {"label": "Fog Burst", "duration_ms": 10000},
}

TRICK_SCENES = [
    "TRICK_HEAD_1",
    "TRICK_HEAD_2",
    "TRICK_HORN",
    "TRICK_CRACKLER",
    "TRICK_AIR_CANNON",
    "TRICK_BOTH_HEADS",
]

QUIET_EXCLUDED_TRICK_SCENES = {
    "TRICK_HORN",
    "TRICK_CRACKLER",
    "TRICK_AIR_CANNON",
}

DEFAULT_SETTINGS = {
    "quiet_mode_enabled": True,
    "quiet_start_time": "21:00",
    "quiet_end_time": "08:00",
}

SCENE_TEST_BUTTONS = [
    ("RUN HEAD 1", "RUN:TRICK_HEAD_1"),
    ("RUN HEAD 2", "RUN:TRICK_HEAD_2"),
    ("RUN HORN", "RUN:TRICK_HORN"),
    ("RUN CRACKLER", "RUN:TRICK_CRACKLER"),
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


def valid_time_string(value: str):
    try:
        hours_text, minutes_text = value.split(":", 1)
        hours = int(hours_text)
        minutes = int(minutes_text)
    except (AttributeError, ValueError):
        return False

    return 0 <= hours <= 23 and 0 <= minutes <= 59


def time_string_to_minutes(value: str):
    hours_text, minutes_text = value.split(":", 1)
    return (int(hours_text) * 60) + int(minutes_text)


def is_quiet_window_active(now_minutes: int, start_time: str, end_time: str, enabled: bool = True):
    if not enabled:
        return False

    start_minutes = time_string_to_minutes(start_time)
    end_minutes = time_string_to_minutes(end_time)

    if start_minutes == end_minutes:
        return True

    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes

    return now_minutes >= start_minutes or now_minutes < end_minutes


def load_settings():
    settings = DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as settings_handle:
            saved_settings = json.load(settings_handle)
    except FileNotFoundError:
        saved_settings = {}
    except Exception as e:
        print(f"SETTINGS WARNING -> failed to read settings: {e}", flush=True)
        saved_settings = {}

    if isinstance(saved_settings, dict):
        settings.update(
            {
                key: saved_settings[key]
                for key in DEFAULT_SETTINGS.keys()
                if key in saved_settings
            }
        )

    if not valid_time_string(settings["quiet_start_time"]):
        settings["quiet_start_time"] = DEFAULT_SETTINGS["quiet_start_time"]
    if not valid_time_string(settings["quiet_end_time"]):
        settings["quiet_end_time"] = DEFAULT_SETTINGS["quiet_end_time"]
    settings["quiet_mode_enabled"] = bool(settings["quiet_mode_enabled"])

    return settings


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as settings_handle:
        json.dump(settings, settings_handle, indent=2)
        settings_handle.write("\n")


settings = load_settings()

# -----------------------------
# GLOBAL STATE
# -----------------------------
state = {
    "arduino_connected": False,
    "arduino_mode": "MOCK" if USE_MOCK_ARDUINO else "SERIAL",
    "arduino_serial_port": None,
    "protocol_version": PROTOCOL_VERSION,
    "arduino_protocol_version": "UNKNOWN",
    "system_status": "STARTING",
    "current_action": "NONE",
    "last_command": "None",
    "last_result": None,
    "last_received_status": "BOOT",
    "serial_reconnect_state": "IDLE",
    "serial_reconnect_attempts": 0,
    "serial_last_connected_epoch": 0,
    "serial_last_heard_epoch": 0,
    "serial_last_error": None,
    "serial_last_error_epoch": 0,
    "scene_active": False,
    "pending_fog": False,
    "next_fog_due_epoch": 0,
    "busy_until_epoch": 0,
    "outputs": {name: False for name in OUTPUT_NAMES},
    "recent_scenes": [],
    "log": [],
    "show_cancelled": False,
    "active_show_token": 0,
    "gpio_enabled": False,
    "gpio_trick_pin": TRICK_GPIO_PIN,
    "gpio_treat_pin": TREAT_GPIO_PIN,
    "quiet_mode_enabled": settings["quiet_mode_enabled"],
    "quiet_mode_active": False,
    "quiet_start_time": settings["quiet_start_time"],
    "quiet_end_time": settings["quiet_end_time"],
    "quiet_excluded_scenes": sorted(QUIET_EXCLUDED_TRICK_SCENES),
    "trick_bag_available_scenes": TRICK_SCENES[:],
    "last_trick_scene": None,
    "video_enabled": not VIDEO_DISABLED,
    "video_mode": "DISABLED" if VIDEO_DISABLED else "IDLE",
    "video_current_file": None,
    "video_last_event": "DISABLED" if VIDEO_DISABLED else "IDLE",
    "video_last_error": None,
    "video_player": VIDEO_PLAYER,
}


def reset_runtime_state():
    state.update(
        {
            "arduino_connected": False,
            "arduino_mode": "MOCK" if USE_MOCK_ARDUINO else "SERIAL",
            "arduino_serial_port": None,
            "protocol_version": PROTOCOL_VERSION,
            "arduino_protocol_version": "UNKNOWN",
            "system_status": "STARTING",
            "current_action": "NONE",
            "last_command": "None",
            "last_result": None,
            "last_received_status": "BOOT",
            "serial_reconnect_state": "IDLE",
            "serial_reconnect_attempts": 0,
            "serial_last_connected_epoch": 0,
            "serial_last_heard_epoch": 0,
            "serial_last_error": None,
            "serial_last_error_epoch": 0,
            "scene_active": False,
            "pending_fog": False,
            "next_fog_due_epoch": 0,
            "busy_until_epoch": 0,
            "outputs": {name: False for name in OUTPUT_NAMES},
            "recent_scenes": [],
            "log": [],
            "show_cancelled": False,
            "active_show_token": 0,
            "gpio_enabled": False,
            "gpio_trick_pin": TRICK_GPIO_PIN,
            "gpio_treat_pin": TREAT_GPIO_PIN,
            "quiet_mode_enabled": settings["quiet_mode_enabled"],
            "quiet_mode_active": False,
            "quiet_start_time": settings["quiet_start_time"],
            "quiet_end_time": settings["quiet_end_time"],
            "quiet_excluded_scenes": sorted(QUIET_EXCLUDED_TRICK_SCENES),
            "trick_bag_available_scenes": TRICK_SCENES[:],
            "last_trick_scene": None,
            "video_enabled": not VIDEO_DISABLED,
            "video_mode": "DISABLED" if VIDEO_DISABLED else "IDLE",
            "video_current_file": None,
            "video_last_event": "DISABLED" if VIDEO_DISABLED else "IDLE",
            "video_last_error": None,
            "video_player": VIDEO_PLAYER,
        }
    )


scene_bag = []
arduino = None
command_lock = threading.Lock()
system_command_lock = threading.Lock()
serial_io_lock = threading.Lock()
arduino_connect_lock = threading.Lock()
show_control_lock = threading.Lock()
show_token_counter = 0
audio_lock = threading.Lock()
gpio_buttons = []
video_lock = threading.Lock()
ambient_video_process = None
triggered_video_process = None

AUDIO_CHANNELS = make_audio_channels()


# -----------------------------
# HELPERS
# -----------------------------
def log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    state["log"].append(entry)
    state["log"] = state["log"][-200:]
    print(entry, flush=True)


def set_video_state(mode: str, current_file=None, last_event=None, last_error=None):
    state["video_mode"] = mode
    state["video_current_file"] = current_file
    if last_event is not None:
        state["video_last_event"] = last_event
    state["video_last_error"] = last_error


def video_player_available():
    return shutil.which(VIDEO_PLAYER) is not None


def video_runtime_enabled():
    return not VIDEO_DISABLED and video_player_available()


def video_environment():
    env = os.environ.copy()
    env["DISPLAY"] = VIDEO_DISPLAY
    if VIDEO_XAUTHORITY:
        env["XAUTHORITY"] = VIDEO_XAUTHORITY
    return env


def build_video_command(file_path: str, loop: bool):
    command = [
        VIDEO_PLAYER,
        "--no-audio",
        "--x11-netwm=no",
        "--geometry=3840x1080+0+0",
        "--keepaspect-window=no",
        "--no-border",
        "--really-quiet",
    ]
    if loop:
        command.append("--loop-file=inf")
    command.append(file_path)
    return command


def stop_video_process(process, label: str):
    if process is None:
        return None

    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            log(f"VIDEO STOP -> {label}")
    except Exception as e:
        log(f"VIDEO WARNING -> Failed to stop {label}: {e}")

    return None


def launch_video_process(file_path: str, loop: bool, label: str):
    if not os.path.exists(file_path):
        set_video_state("ERROR", last_event=f"MISSING:{label}", last_error=f"Missing file: {file_path}")
        log(f"VIDEO ERROR -> Missing {label.lower()} file: {file_path}")
        return None

    if not video_runtime_enabled():
        reason = "disabled" if VIDEO_DISABLED else f"player not found: {VIDEO_PLAYER}"
        set_video_state("DISABLED" if VIDEO_DISABLED else "ERROR", last_event=f"SKIPPED:{label}", last_error=reason)
        log(f"VIDEO DISABLED -> skipped {label.lower()} playback ({reason})")
        return None

    try:
        process = subprocess.Popen(
            build_video_command(file_path, loop),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=video_environment(),
        )
        set_video_state(
            "AMBIENT" if loop else "TRIGGERED",
            current_file=os.path.basename(file_path),
            last_event=f"STARTED:{label}",
            last_error=None,
        )
        log(f"VIDEO START -> {label} ({os.path.basename(file_path)})")
        return process
    except Exception as e:
        set_video_state("ERROR", last_event=f"FAILED:{label}", last_error=str(e))
        log(f"VIDEO ERROR -> Failed to start {label.lower()} video: {e}")
        return None


def ensure_ambient_video():
    global ambient_video_process

    with video_lock:
        if triggered_video_process is not None and triggered_video_process.poll() is None:
            return False

        if ambient_video_process is not None and ambient_video_process.poll() is None:
            return True

        ambient_video_process = launch_video_process(VIDEO_AMBIENT_FILE, loop=True, label="AMBIENT")
        return ambient_video_process is not None


def play_triggered_video_once():
    global ambient_video_process, triggered_video_process

    with video_lock:
        ambient_video_process = stop_video_process(ambient_video_process, "AMBIENT")
        triggered_video_process = stop_video_process(triggered_video_process, "TRIGGERED")
        triggered_video_process = launch_video_process(VIDEO_TRIGGERED_FILE, loop=False, label="TRIGGERED")
        if triggered_video_process is None:
            ambient_video_process = launch_video_process(VIDEO_AMBIENT_FILE, loop=True, label="AMBIENT")
            return False
        return True


def resume_ambient_video():
    global ambient_video_process, triggered_video_process

    with video_lock:
        triggered_video_process = stop_video_process(triggered_video_process, "TRIGGERED")
        if ambient_video_process is not None and ambient_video_process.poll() is None:
            set_video_state(
                "AMBIENT",
                current_file=os.path.basename(VIDEO_AMBIENT_FILE),
                last_event="RESUMED:AMBIENT",
                last_error=None,
            )
            return True

        ambient_video_process = launch_video_process(VIDEO_AMBIENT_FILE, loop=True, label="AMBIENT")
        return ambient_video_process is not None


def video_worker():
    global ambient_video_process, triggered_video_process

    while True:
        time.sleep(1)

        with video_lock:
            if triggered_video_process is not None and triggered_video_process.poll() is not None:
                exit_code = triggered_video_process.returncode
                triggered_video_process = None
                log(f"VIDEO COMPLETE -> TRIGGERED (exit={exit_code})")
                ambient_video_process = launch_video_process(VIDEO_AMBIENT_FILE, loop=True, label="AMBIENT")
                continue

            if ambient_video_process is not None and ambient_video_process.poll() is not None:
                exit_code = ambient_video_process.returncode
                ambient_video_process = None
                log(f"VIDEO WARNING -> Ambient loop exited (exit={exit_code})")

        ensure_ambient_video()


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def current_minutes():
    now = time.localtime()
    return (now.tm_hour * 60) + now.tm_min


def quiet_mode_active():
    return is_quiet_window_active(
        current_minutes(),
        settings["quiet_start_time"],
        settings["quiet_end_time"],
        settings["quiet_mode_enabled"],
    )


def available_trick_scenes():
    if quiet_mode_active():
        return [scene for scene in TRICK_SCENES if scene not in QUIET_EXCLUDED_TRICK_SCENES]
    return TRICK_SCENES[:]


def refresh_quiet_mode_state():
    active = quiet_mode_active()
    available_scenes = available_trick_scenes()
    state.update(
        {
            "quiet_mode_enabled": settings["quiet_mode_enabled"],
            "quiet_mode_active": active,
            "quiet_start_time": settings["quiet_start_time"],
            "quiet_end_time": settings["quiet_end_time"],
            "quiet_excluded_scenes": sorted(QUIET_EXCLUDED_TRICK_SCENES),
            "trick_bag_available_scenes": available_scenes,
        }
    )
    return active, available_scenes


def reset_fog_timer():
    state["next_fog_due_epoch"] = time.time() + (5 * 60)


def avoid_repeat_at_bag_start():
    last_scene = state.get("last_trick_scene")
    if len(scene_bag) <= 1 or scene_bag[0] != last_scene:
        return

    for index, scene in enumerate(scene_bag[1:], start=1):
        if scene != last_scene:
            scene_bag[0], scene_bag[index] = scene_bag[index], scene_bag[0]
            return


def choose_trick_scene():
    global scene_bag

    quiet_active, available_scenes = refresh_quiet_mode_state()
    scene_bag = [scene for scene in scene_bag if scene in available_scenes]

    if not scene_bag:
        scene_bag = available_scenes[:]
        random.shuffle(scene_bag)
        avoid_repeat_at_bag_start()
        mode_text = "quiet" if quiet_active else "regular"
        log(f"Refilled {mode_text} trick bag: {scene_bag}")

    scene = scene_bag.pop(0)
    state["last_trick_scene"] = scene
    log(f"Selected trick scene: {scene}")
    return scene


audio_lock = threading.Lock()

def load_audio():
    TRACKS.clear()

    if not AUDIO_MIXER_READY:
        log("AUDIO DISABLED -> skipping audio load")
        return

    for track_name, file_path in TRACK_FILES.items():
        if not os.path.exists(file_path):
            log(f"AUDIO WARNING -> Missing file for {track_name}: {file_path}")
            continue

        try:
            TRACKS[track_name] = pygame.mixer.Sound(file_path)
            log(f"AUDIO LOADED -> {track_name}")
        except Exception as e:
            log(f"AUDIO ERROR -> Failed to load {track_name}: {e}")

AUDIO_CHANNELS = make_audio_channels()

def play_audio(name: str, channel_name: str = "MAIN", stop_same_channel: bool = True):
    track_name = name.strip().upper()
    channel_name = channel_name.strip().upper()

    if not AUDIO_MIXER_READY:
        log(f"AUDIO DISABLED -> skipped {track_name} on {channel_name}")
        return True

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
    if not line.startswith("ERROR:SERIAL_IO"):
        state["serial_last_heard_epoch"] = time.time()

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
            state["system_status"] = "IDLE"
            state["current_action"] = "NONE"
        elif line.startswith("ERROR:SERIAL_IO"):
            state["arduino_connected"] = False
            state["serial_reconnect_state"] = "WAITING"
            state["serial_last_error"] = line
            state["serial_last_error_epoch"] = time.time()
            state["system_status"] = "ERROR"
            state["current_action"] = "SERIAL_IO"
            state["scene_active"] = False
            clear_busy_marker()
            for output_name in state["outputs"]:
                state["outputs"][output_name] = False
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
            for key, enabled in self.outputs.items():
                lines.append(f"STATE:{key}:{'ON' if enabled else 'OFF'}")
            lines.append("DONE:SYS:STATUS")
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
            delay_seconds = (duration_ms / 1000.0) * MOCK_SCENE_DELAY_SCALE
            if delay_seconds > 0:
                time.sleep(delay_seconds)

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
            try:
                self.ser.reset_input_buffer()
                self.ser.write((command + "\n").encode("utf-8"))
                self.ser.flush()
                log(f"SERIAL SEND -> {command}")
            except Exception as e:
                mark_arduino_disconnected(f"ERROR:SERIAL_IO:{repr(e)}")
                return [state["last_result"]]

            lines = []
            deadline = time.time() + command_timeout_seconds(command)
            expected_terminal = expected_terminal_line(command)

            while time.time() < deadline:
                try:
                    raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
                    if raw:
                        lines.append(raw)
                        log(f"SERIAL RECV <- {raw}")
                        if raw.startswith("ERROR:") or (expected_terminal and raw == expected_terminal):
                            break
                    else:
                        time.sleep(0.05)
                except Exception as e:
                    mark_arduino_disconnected(f"ERROR:SERIAL_IO:{repr(e)}")
                    lines.append(state["last_result"])
                    break

            return lines


# -----------------------------
# COMMAND PIPELINE
# -----------------------------
def serial_port_candidates():
    candidates = []
    for port in [SERIAL_PORT, *sorted(glob.glob("/dev/ttyACM*")), *sorted(glob.glob("/dev/ttyUSB*"))]:
        if port and port not in candidates:
            candidates.append(port)
    return candidates


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


def connect_arduino(run_handshake: bool = True):
    global arduino

    with arduino_connect_lock:
        try:
            state["serial_reconnect_state"] = "CONNECTING"

            if USE_MOCK_ARDUINO:
                arduino = MockArduino()
                state["arduino_connected"] = True
                state["arduino_serial_port"] = "MOCK"
                state["system_status"] = "IDLE"
                state["current_action"] = "NONE"
                state["last_received_status"] = "STATUS:IDLE"
                log("Connected to mock Arduino.")
            else:
                errors = []
                for port in serial_port_candidates():
                    try:
                        arduino = SerialArduino(port, BAUD_RATE)
                        state["arduino_serial_port"] = port
                        break
                    except Exception as e:
                        errors.append(f"{port}: {repr(e)}")
                else:
                    raise RuntimeError("No Arduino serial port connected. Tried " + "; ".join(errors))

                state["arduino_connected"] = True
                state["system_status"] = "IDLE"
                state["current_action"] = "NONE"
                state["last_received_status"] = "STATUS:IDLE"
                log(f"Connected to Arduino on {state['arduino_serial_port']} @ {BAUD_RATE}.")

            now = time.time()
            state["serial_reconnect_state"] = "CONNECTED"
            state["serial_last_connected_epoch"] = now
            state["serial_last_heard_epoch"] = now

            if run_handshake:
                handshake_with_arduino()

        except Exception as e:
            state["arduino_connected"] = False
            state["serial_reconnect_state"] = "FAILED"
            state["serial_last_error"] = f"ERROR:CONNECT_FAILED:{repr(e)}"
            state["serial_last_error_epoch"] = time.time()
            state["system_status"] = "ERROR"
            state["current_action"] = "CONNECT_FAILED"
            state["last_result"] = f"ERROR:CONNECT_FAILED:{e}"
            log(f"Arduino connection failed: {repr(e)}")


def mark_arduino_disconnected(error: str):
    global arduino

    try:
        if arduino is not None and hasattr(arduino, "ser"):
            arduino.ser.close()
    except Exception:
        pass

    arduino = None
    state["arduino_connected"] = False
    state["serial_reconnect_state"] = "WAITING"
    state["serial_last_error"] = error
    state["serial_last_error_epoch"] = time.time()
    state["system_status"] = "ERROR"
    state["current_action"] = "SERIAL_IO"
    state["last_result"] = error
    clear_busy_marker()
    log(error)


def serial_reconnect_worker():
    if USE_MOCK_ARDUINO:
        return

    while True:
        time.sleep(SERIAL_RECONNECT_INTERVAL_SECONDS)

        if state["arduino_connected"]:
            continue

        state["serial_reconnect_attempts"] += 1
        state["serial_reconnect_state"] = "ATTEMPTING"
        log(f"Arduino reconnect attempt {state['serial_reconnect_attempts']}.")
        connect_arduino(run_handshake=True)


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

    has_error = any(line.startswith("ERROR:") for line in lines)
    if expected_done and not success and not has_error and not command.startswith("SYS:"):
        state["last_result"] = "ERROR:UNEXPECTED_REPLY"

    return success


def expected_terminal_line(command: str):
    if command == "SYS:PING":
        return "PONG"
    if command.startswith("RUN:"):
        return f"DONE:{command[4:]}"
    if command.startswith("TOGGLE:") or command.startswith("SYS:"):
        return f"DONE:{command}"
    return None


def command_timeout_seconds(command: str):
    if command.startswith("RUN:"):
        scene_name = command[4:]
        duration_ms = SCENES.get(scene_name, {}).get("duration_ms", 0)
        return max(3.0, (duration_ms / 1000.0) + 12.0)

    return 3.0


def transact_command(command: str):
    valid, validation_error = validate_command(command)
    if not valid:
        state["last_result"] = validation_error
        log(f"Rejected invalid command: {command}")
        return False

    with command_lock:
        if arduino is None or not state["arduino_connected"]:
            connect_arduino(run_handshake=False)

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
        if arduino is None or not state["arduino_connected"]:
            connect_arduino(run_handshake=False)

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
        
def play_trick_scene_audio(scene_name: str, include_trick_track: bool = True):
    if include_trick_track:
        play_audio("TRICK", channel_name="MAIN")

    if scene_name in {"TRICK_HEAD_1", "TRICK_BOTH_HEADS"}:
        play_audio("SKINNY", channel_name="HEAD_1")

    if scene_name in {"TRICK_HEAD_2", "TRICK_BOTH_HEADS"}:
        play_audio("HAG", channel_name="HEAD_2")

    return True


def play_scene_test_audio(scene_name: str):
    if scene_name.startswith("TRICK_"):
        play_trick_scene_audio(scene_name, include_trick_track=False)
    elif scene_name == "DOOR_SEQUENCE":
        play_audio("DOOR", channel_name="DOOR")
    elif scene_name == "FOG_BURST":
        play_audio("WELCOME", channel_name="BACKGROUND")

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
            if AUDIO_MIXER_READY:
                pygame.mixer.stop()
            else:
                for channel in AUDIO_CHANNELS.values():
                    channel.stop()
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
    play_triggered_video = False

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

            play_triggered_video = True

        elif mode == "TREAT":
            trick_scene = choose_trick_scene()
            state["last_command"] = f"SHOW:{mode}:DOOR_SEQUENCE:{trick_scene}"

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled before door sequence.")
                stop_all_audio()
                return

            play_audio("DOOR", channel_name="DOOR")
            play_audio("TREAT", channel_name="MAIN")

            if not run_scene("DOOR_SEQUENCE", "TREAT", show_token=show_token):
                return

            if is_show_cancelled(show_token):
                state["last_result"] = "ERROR:SHOW_CANCELLED"
                log("Show cancelled after door sequence, before treat trick.")
                stop_all_audio()
                return

            play_trick_scene_audio(trick_scene, include_trick_track=False)

            if not run_scene(trick_scene, "TREAT_TRICK", show_token=show_token):
                return

            play_triggered_video = True

        else:
            state["last_result"] = "ERROR:UNKNOWN_MODE"
            log(f"Unknown mode: {mode}")
            return

        if play_triggered_video and not is_show_cancelled(show_token):
            play_triggered_video_once()

    finally:
        state["scene_active"] = False
        clear_busy_marker()
        maybe_run_pending_fog_after_scene()


def start_show_request(mode: str, source: str):
    mode = mode.strip().upper()

    if mode not in {"TRICK", "TREAT"}:
        state["last_result"] = f"ERROR:UNKNOWN_MODE:{mode}"
        log(f"Ignoring unknown {source} show request: {mode}")
        return None

    if state["scene_active"] or state["system_status"] != "IDLE":
        state["last_result"] = "ERROR:BUSY"
        log(f"Busy, ignoring {source} {mode} request.")
        return None

    show_token = begin_new_show()
    log(f"{source} trigger accepted: {mode} (token={show_token})")
    threading.Thread(target=run_show, args=(mode, show_token), daemon=True).start()
    return show_token


def handle_gpio_trigger(mode: str):
    start_show_request(mode, "GPIO")


def setup_gpio_triggers():
    global gpio_buttons

    state["gpio_enabled"] = False
    gpio_buttons = []

    if GPIO_DISABLED:
        log("GPIO triggers disabled by HALLOWEEN_GPIO_DISABLED.")
        return False

    if Button is None:
        log("GPIO triggers unavailable: gpiozero is not installed.")
        return False

    try:
        trick_button = Button(TRICK_GPIO_PIN, pull_up=True, bounce_time=GPIO_BOUNCE_TIME)
        treat_button = Button(TREAT_GPIO_PIN, pull_up=True, bounce_time=GPIO_BOUNCE_TIME)

        trick_button.when_pressed = lambda: handle_gpio_trigger("TRICK")
        treat_button.when_pressed = lambda: handle_gpio_trigger("TREAT")

        gpio_buttons = [trick_button, treat_button]
        state["gpio_enabled"] = True
        state["gpio_trick_pin"] = TRICK_GPIO_PIN
        state["gpio_treat_pin"] = TREAT_GPIO_PIN
        log(f"GPIO triggers enabled: TRICK=GPIO{TRICK_GPIO_PIN}, TREAT=GPIO{TREAT_GPIO_PIN}")
        return True
    except Exception as e:
        gpio_buttons = []
        state["gpio_enabled"] = False
        log(f"GPIO triggers unavailable: {repr(e)}")
        return False


def run_manual_command(command: str):
    state["last_command"] = command

    if command in {"SYS:STOP", "SYS:RESET", "SYS:ALL_OFF"}:
        cancel_active_show(command)
        stop_all_audio()
        resume_ambient_video()
        ok = transact_system_command(command)
    elif command in {"SYS:PING", "SYS:STATUS"}:
        ok = transact_system_command(command)
    elif command.startswith("RUN:"):
        scene_name = command[4:]
        play_scene_test_audio(scene_name)
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
def auth_enabled():
    return bool(ACCESS_PASSWORD)


def is_authenticated():
    return not auth_enabled() or session.get("authenticated") is True


@app.before_request
def require_authentication():
    if not auth_enabled() or is_authenticated():
        return None

    if request.endpoint in {"login", "static"}:
        return None

    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "AUTH_REQUIRED"}), 401

    return redirect(url_for("login", next=request.full_path))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if hmac.compare_digest(password, ACCESS_PASSWORD):
            session.clear()
            session.permanent = True
            session["authenticated"] = True
            next_url = request.args.get("next") or url_for("index")
            if not next_url.startswith("/"):
                next_url = url_for("index")
            return redirect(next_url)
        error = "Wrong password"

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return render_template(
        "index.html",
        fun_buttons=FUN_BUTTONS,
    )

@app.route("/service")
def service():
    return render_template(
        "service.html",
        service_buttons=SERVICE_BUTTONS,
        scene_test_buttons=SCENE_TEST_BUTTONS,
    )

@app.route("/api/status")
def api_status():
    refresh_quiet_mode_state()
    payload = dict(state)
    now = time.time()
    payload["serial_last_heard_seconds_ago"] = (
        round(now - state["serial_last_heard_epoch"], 1) if state["serial_last_heard_epoch"] else None
    )
    payload["serial_last_connected_seconds_ago"] = (
        round(now - state["serial_last_connected_epoch"], 1) if state["serial_last_connected_epoch"] else None
    )
    payload["serial_last_error_seconds_ago"] = (
        round(now - state["serial_last_error_epoch"], 1) if state["serial_last_error_epoch"] else None
    )
    return jsonify(payload)


@app.route("/api/settings", methods=["POST"])
def api_settings():
    global scene_bag

    data = request.get_json(force=True)
    quiet_enabled = bool(data.get("quiet_mode_enabled", False))
    quiet_start_time = str(data.get("quiet_start_time", "")).strip()
    quiet_end_time = str(data.get("quiet_end_time", "")).strip()

    if not valid_time_string(quiet_start_time):
        return jsonify({"ok": False, "error": "Invalid quiet start time"}), 400
    if not valid_time_string(quiet_end_time):
        return jsonify({"ok": False, "error": "Invalid quiet end time"}), 400

    settings.update(
        {
            "quiet_mode_enabled": quiet_enabled,
            "quiet_start_time": quiet_start_time,
            "quiet_end_time": quiet_end_time,
        }
    )
    save_settings(settings)
    scene_bag = []
    refresh_quiet_mode_state()
    log(
        "Quiet time settings updated: "
        f"enabled={quiet_enabled}, start={quiet_start_time}, end={quiet_end_time}"
    )
    return jsonify({"ok": True, "settings": settings, "quiet_mode_active": state["quiet_mode_active"]})


@app.route("/api/run_main", methods=["POST"])
def api_run_main():
    data = request.get_json(force=True)
    mode = data["mode"].strip().upper()

    if mode not in {"TRICK", "TREAT"}:
        return jsonify({"ok": False, "error": f"Invalid mode: {mode}"}), 400

    show_token = start_show_request(mode, "WEB")
    if show_token is None:
        return jsonify({"ok": False, "error": state["last_result"]}), 409

    return jsonify({"ok": True, "mode": mode, "show_token": show_token})


@app.route("/api/run_command", methods=["POST"])
def api_run_command():
    data = request.get_json(force=True)
    command = data["command"].strip().upper()

    valid, validation_error = validate_command(command)
    if not valid:
        return jsonify({"ok": False, "error": validation_error}), 400

    log(f"WEB command requested: {command}")
    threading.Thread(target=run_manual_command, args=(command,), daemon=True).start()
    return jsonify({"ok": True, "command": command})


if __name__ == "__main__":
    load_audio()
    connect_arduino()
    setup_gpio_triggers()
    reset_fog_timer()
    threading.Thread(target=serial_reconnect_worker, daemon=True).start()
    threading.Thread(target=idle_fog_worker, daemon=True).start()
    threading.Thread(target=video_worker, daemon=True).start()
    ensure_ambient_video()
    log(f"Web app starting on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
