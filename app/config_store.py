"""JSON configuration storage for HauntOS.

Phase 2 implements safe loading, saving, default creation, and basic structure
validation for the shared config files.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"

DEFAULT_DEVICES = {
    "outputs": {
        "OUT1": {"name": "Output 1", "gpio": 17, "enabled": True},
        "OUT2": {"name": "Output 2", "gpio": 27, "enabled": True},
        "OUT3": {"name": "Output 3", "gpio": 22, "enabled": True},
        "OUT4": {"name": "Output 4", "gpio": 23, "enabled": True},
        "OUT5": {"name": "Output 5", "gpio": 24, "enabled": True},
        "OUT6": {"name": "Output 6", "gpio": 25, "enabled": True},
        "OUT7": {"name": "Output 7", "gpio": 5, "enabled": True},
        "OUT8": {"name": "Output 8", "gpio": 6, "enabled": True},
    },
    "inputs": {
        "IN1": {"name": "Input 1", "gpio": 12, "enabled": True, "cooldown": 5},
        "IN2": {"name": "Input 2", "gpio": 13, "enabled": True, "cooldown": 5},
        "IN3": {"name": "Input 3", "gpio": 16, "enabled": True, "cooldown": 5},
        "IN4": {"name": "Input 4", "gpio": 19, "enabled": True, "cooldown": 5},
    },
}

DEFAULT_ROUTINES = {
    "IN1": [],
    "IN2": [],
    "IN3": [],
    "IN4": [],
}

DEFAULT_SETTINGS = {
    "mock_mode": True,
    "active_low_outputs": False,
    "active_low_inputs": True,
    "controller_name": "HauntOS Controller",
    "setup_complete": False,
    "show_armed": False,
    "scheduler": {
        "enabled": False,
        "start_time": "19:00",
        "end_time": "22:00",
        "mode": "random",
        "interval_min": 120,
        "interval_max": 300,
        "routine": "IN1",
    },
}

DEFAULT_SCHEDULER = DEFAULT_SETTINGS["scheduler"]

DEFAULT_CONFIGS = {
    "devices": DEFAULT_DEVICES,
    "routines": DEFAULT_ROUTINES,
    "settings": DEFAULT_SETTINGS,
}


def load_config(name: str) -> dict[str, Any]:
    """Load a config dictionary, creating or repairing it when needed."""
    config_name = _normalize_name(name)
    path = _config_path(config_name)

    if not path.exists():
        LOGGER.warning("Config file missing, creating default: %s", path)
        default_data = _default_for(config_name)
        save_config(config_name, default_data)
        return default_data

    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Config file has invalid JSON, recreating default: %s (%s)", path, exc)
        default_data = _default_for(config_name)
        save_config(config_name, default_data)
        return default_data
    except OSError as exc:
        LOGGER.warning("Could not read config file, recreating default: %s (%s)", path, exc)
        default_data = _default_for(config_name)
        save_config(config_name, default_data)
        return default_data

    if not _is_valid_config(config_name, data):
        LOGGER.warning("Config file has invalid structure, recreating default: %s", path)
        default_data = _default_for(config_name)
        save_config(config_name, default_data)
        return default_data

    if config_name == "settings":
        merged = _merge_settings_defaults(data)
        if merged != data:
            save_config(config_name, merged)
        return merged

    return data


def save_config(name: str, data: dict[str, Any]) -> None:
    """Save a config dictionary using a temp file followed by atomic replace."""
    config_name = _normalize_name(name)

    if not _is_valid_config(config_name, data):
        raise ValueError(f"Invalid {config_name} config structure")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _config_path(config_name)
    temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=CONFIG_DIR,
            delete=False,
            prefix=f".{config_name}.",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(data, temp_file, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, path)
    except OSError:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def get_devices() -> dict[str, Any]:
    """Return devices.json as a dictionary."""
    return load_config("devices")


def get_routines() -> dict[str, Any]:
    """Return routines.json as a dictionary."""
    return load_config("routines")


def get_settings() -> dict[str, Any]:
    """Return settings.json as a dictionary."""
    return load_config("settings")


def save_devices(data: dict[str, Any]) -> None:
    """Save devices.json."""
    save_config("devices", data)


def save_routines(data: dict[str, Any]) -> None:
    """Save routines.json."""
    save_config("routines", data)


def save_settings(data: dict[str, Any]) -> None:
    """Save settings.json."""
    save_config("settings", data)


def reset_config(name: str) -> dict[str, Any]:
    """Restore one config file to its default value and return it."""
    config_name = _normalize_name(name)
    default_data = _default_for(config_name)
    save_config(config_name, default_data)
    return default_data


def reset_all_configs() -> dict[str, dict[str, Any]]:
    """Restore all config files to defaults."""
    return {name: reset_config(name) for name in DEFAULT_CONFIGS}


def validate_config(name: str, data: dict[str, Any]) -> None:
    """Raise ValueError if data is not valid for a config name."""
    config_name = _normalize_name(name)
    if not _is_valid_config(config_name, data):
        raise ValueError(f"Invalid {config_name} config structure")


def _normalize_name(name: str) -> str:
    config_name = name.removesuffix(".json")
    if config_name not in DEFAULT_CONFIGS:
        allowed = ", ".join(sorted(DEFAULT_CONFIGS))
        raise ValueError(f"Unknown config '{name}'. Expected one of: {allowed}")
    return config_name


def _config_path(name: str) -> Path:
    return CONFIG_DIR / f"{name}.json"


def _default_for(name: str) -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIGS[name])


def _is_valid_config(name: str, data: Any) -> bool:
    if not isinstance(data, dict):
        return False

    if name == "devices":
        return _valid_devices(data)

    if name == "routines":
        return all(
            input_id in data and isinstance(data[input_id], list)
            for input_id in _input_ids()
        )

    if name == "settings":
        return _has_keys(data, ("mock_mode", "active_low_outputs", "active_low_inputs"))

    return False


def _valid_devices(data: dict[str, Any]) -> bool:
    if not (
        _has_keys(data, ("outputs", "inputs"))
        and isinstance(data["outputs"], dict)
        and isinstance(data["inputs"], dict)
    ):
        return False

    outputs = data["outputs"]
    inputs = data["inputs"]

    outputs_valid = all(
        output_id in outputs
        and isinstance(outputs[output_id], dict)
        and _has_keys(outputs[output_id], ("name", "gpio", "enabled"))
        for output_id in _output_ids()
    )
    inputs_valid = all(
        input_id in inputs
        and isinstance(inputs[input_id], dict)
        and _has_keys(inputs[input_id], ("name", "gpio", "enabled", "cooldown"))
        for input_id in _input_ids()
    )

    return outputs_valid and inputs_valid


def _has_keys(data: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(key in data for key in keys)


def _merge_settings_defaults(settings: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    merged.update(settings)

    scheduler_settings = settings.get("scheduler", {})
    if isinstance(scheduler_settings, dict):
        merged["scheduler"] = copy.deepcopy(DEFAULT_SCHEDULER)
        merged["scheduler"].update(scheduler_settings)

    return merged


def _output_ids() -> tuple[str, ...]:
    return ("OUT1", "OUT2", "OUT3", "OUT4", "OUT5", "OUT6", "OUT7", "OUT8")


def _input_ids() -> tuple[str, ...]:
    return ("IN1", "IN2", "IN3", "IN4")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    print(get_devices())
    print(get_routines())
    print(get_settings())
