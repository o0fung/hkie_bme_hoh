import json
import os
from typing import Optional

DEFAULT_CONFIG = {
    "simulation": False,
    "settings": {
        "emg_max_range_flexor": 100,
        "emg_max_range_extensor": 100,
        "training_muscle_mode": "auto",
        "training_trigger_mode": "auto",
        "hand_start_percent": 70,
        "threshold_percent": 20,
        "trigger_threshold_percent": 50,
        "trigger_wait_seconds": 1.0,
        "relax_flexion_percent": 12,
        "relax_extension_percent": 12,
        "countdown_seconds": 5,
        "stars_to_collect": 3,
        "training_duration_minutes": 20,
        "target_flexion_percent": 80,
        "target_extension_percent": 30,
        "grip_step_percent": 1,
        "command_rate_hz": 10,
        "activation_hysteresis_percent": 2,
        "deactivation_hysteresis_percent": 5,
        "forward_deadband_percent": 0,
        "reversal_deadband_percent": 0,
        "background_blur_percent": 100,
        "sound_enabled": True,
        "music_enabled": True,
        "sound_effect_volume_percent": 60,
        "music_volume_percent": 18,
        "theme_mode": "system",
        "dynamic_mvc_alpha_up": 0.2,
        "dynamic_mvc_alpha_down": 0.01,
        "dynamic_mvc_up_margin_ratio": 0.03,
        "dynamic_mvc_hold_activity_ratio": 0.85,
        "dynamic_mvc_decay_trigger_ratio": 0.2,
        "dynamic_mvc_decay_grace_seconds": 2.0,
    },
    "emg_flexor": {
        "name": "EMGS",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    },
    "emg_extensor": {
        "name": "EMGS",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    },
    "exo_hand": {
        "name": "Exo-Hand",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "",
        "feedback_characteristic_uuid": "",
    },
}


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[WARNING] Failed to load config file at {path}: {exc}")
        return None


def _read_packaged_json(filename: str) -> Optional[dict]:
    try:
        import importlib.resources as pkg_resources

        config_pkg = pkg_resources.files("config")
        cfg_file = config_pkg.joinpath(filename)
        if cfg_file.is_file():
            return json.loads(cfg_file.read_text(encoding="utf-8"))
    except (
        ImportError,
        ModuleNotFoundError,
        FileNotFoundError,
        AttributeError,
        TypeError,
        OSError,
        json.JSONDecodeError,
    ):
        pass

    # Python < 3.9 fallback
    try:
        import importlib_resources as pkg_resources  # type: ignore

        config_pkg = pkg_resources.files("config")
        cfg_file = config_pkg.joinpath(filename)
        with cfg_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (
        ImportError,
        ModuleNotFoundError,
        FileNotFoundError,
        AttributeError,
        TypeError,
        OSError,
        json.JSONDecodeError,
    ):
        return None


def load_config(candidate_paths: list[str]) -> dict:
    """
    Load config from explicit candidate paths, then packaged defaults, then built-ins.
    """
    configured_path = os.environ.get("HOH_CONFIG_PATH", "").strip()
    all_candidates = [configured_path] if configured_path else []
    all_candidates.extend(candidate_paths)

    for path in all_candidates:
        if os.path.exists(path):
            cfg = _read_json(path)
            if cfg is not None:
                print(f"[INFO] Loaded config: {path}")
                return cfg

    packaged_config = _read_packaged_json("devices.json")
    if packaged_config is not None:
        print("[INFO] Loaded packaged config: config/devices.json")
        return packaged_config

    print("[WARNING] No config file found. Using built-in defaults.")
    return DEFAULT_CONFIG
