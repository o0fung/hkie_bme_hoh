"""
Entry point for running the HKIE BME HOH game.
This module allows the package to be run as: python -m app
or via the installed console script: run_hoh_game
"""
import sys
import os
import json
import math
import random
import time
import re
import platform
import subprocess
from typing import List, Optional, Dict, Tuple, Set
from importlib import metadata as importlib_metadata

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - runtime fallback for older Python
    tomllib = None  # type: ignore[assignment]

# If run as a script (e.g. python app/__main__.py), ensure package context is set
if __package__ is None or __package__ == "":
    package_root = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(package_root)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = "app"

import pygame

# Use relative imports since this file lives inside the app package
from .game.scene_manager import SceneManager
from .game.scenes import GameScene, SettingsScene
from .io.input_manager import EMGProcessor, EMGConfig
from .ble.ble_manager import BLEManager, BLEDeviceInfo
from .ble import emgs_client
from .ble.exo_client import ExoClient

# Config paths
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
_CWD_CONFIG_PATH = os.path.join(os.getcwd(), "config", "devices.json")
_PROJECT_CONFIG_PATH = os.path.join(_CONFIG_DIR, "devices.json")
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_CWD_LANGUAGE_PATH = os.path.join(os.getcwd(), "assets", "languages.json")
_PROJECT_LANGUAGE_PATH = os.path.join(_ASSETS_DIR, "languages.json")

_DEFAULT_LANGUAGE_PACKS: Dict[str, Dict[str, object]] = {
    "en": {
        "name": "English",
        "texts": {
            "btn_settings": "Settings",
            "btn_reset": "Reset",
            "btn_start": "Start",
            "btn_stop": "Stop",
            "btn_mirror_off": "Mirror: OFF",
            "btn_mirror_on": "Mirror: ON",
            "btn_exit": "Exit",
            "title_main": "Try Control the Exoskeleton Hand !!!",
            "label_flexor_emg": "Flexor EMG",
            "label_extensor_emg": "Extensor EMG",
            "status_lets_start": "Let's Start !!!",
            "status_great_job": "Great Job !!!",
            "status_hold_on_flexion": "Hold Flexion... {count}",
            "status_hold_on_extension": "Hold Extension... {count}",
            "status_games_on_flexion": "Grasp Hand !",
            "status_games_on_extension": "Open Hand !",
            "status_try_harder_flexion": "Try Harder (Flexion) !!!",
            "status_try_harder_extension": "Try Harder (Extension) !!!",
            "round_text": "Round {current}|{total}",
            "win_text": "You Win!",
            "settings_stepper_stars_to_collect": "Stars to Collect",
            "settings_training_muscle_button": "Training Muscle: {mode}",
            "settings_training_muscle_auto": "Auto",
            "settings_training_muscle_flexor_only": "Flexor Only",
            "settings_training_muscle_extensor_only": "Extensor Only",
            "settings_training_muscle_both": "Both Flexor and Extensor",
            "settings_stepper_relax_flexion_percent": "Relax Flexion %",
            "settings_stepper_relax_extension_percent": "Relax Extension %",
        },
    },
    "zh-Hant": {
        "name": "Traditional Chinese",
        "texts": {},
    },
    "zh-Hans": {
        "name": "Simplified Chinese",
        "texts": {},
    },
}

def _resolve_game_version() -> str:
    """
    Resolve app version from a single source of truth.

    Priority:
      1) pyproject.toml beside this source tree (reflect local program code)
      2) Installed package metadata (when run from built wheel/install only)
      3) Safe fallback
    """
    pyproject_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            if tomllib:
                with open(pyproject_path, "rb") as f:
                    pyproject = tomllib.load(f)
                version = str(pyproject.get("project", {}).get("version", "")).strip()
                if version:
                    return version
            else:
                # Python < 3.11 fallback: parse [project] version line safely.
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    in_project_section = False
                    for raw_line in f:
                        line = raw_line.strip()
                        if line.startswith("[") and line.endswith("]"):
                            in_project_section = (line == "[project]")
                            continue
                        if in_project_section:
                            m = re.match(r'version\s*=\s*"([^"]+)"', line)
                            if m:
                                return m.group(1).strip()
        except Exception:
            pass

    for package_name in ("hoh-game", "hkie-bme-hoh"):
        try:
            return importlib_metadata.version(package_name)
        except importlib_metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

    return "0.0.0"


GAME_VERSION = _resolve_game_version()

# Default config as fallback if sample file cannot be found
_DEFAULT_CONFIG = {
    "simulation": False,
    "settings": {
        "emg_max_range_flexor": 100,
        "emg_max_range_extensor": 100,
        "training_muscle_mode": "auto",
        "hand_start_percent": 70,
        "threshold_percent": 20,
        "relax_flexion_percent": 12,
        "relax_extension_percent": 12,
        "countdown_seconds": 5,
        "stars_to_collect": 3,
        "target_flexion_percent": 80,
        "target_extension_percent": 30,
        "grip_step_percent": 1,
        "command_rate_hz": 10,
        "activation_hysteresis_percent": 2,
        "deactivation_hysteresis_percent": 5,
        "forward_deadband_percent": 0,
        "reversal_deadband_percent": 0,
        "background_blur_percent": 100,
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
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    },
    "emg_extensor": {
        "name": "EMGS",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    },
    "exo_hand": {
        "name": "Exo-Hand",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "",
        "feedback_characteristic_uuid": ""
    }
}


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("HKIE BME Robot Hand Control")
        self.clock = pygame.time.Clock()

        # Fullscreen, but allow windowed fallback in dev by env var
        fullscreen = os.environ.get("GAME_FULLSCREEN", "1") == "1"
        display_info = pygame.display.Info()
        w = display_info.current_w
        h = display_info.current_h
        flags = pygame.FULLSCREEN if fullscreen else 0
        self.screen = pygame.display.set_mode((w, h), flags)
        self.screen_rect = self.screen.get_rect()
        # Keep 1920x1080 as baseline visual size across displays.
        self.ui_scale = max(0.85, min(2.5, min(w / 1920.0, h / 1080.0)))

        # Load config
        self.cfg = self._load_config()
        self.language_packs, self.current_language = self._load_language_packs()
        # Get simulation value - handle both bool and string values
        sim_value = self.cfg.get("simulation", False)
        if isinstance(sim_value, str):
            # Handle string values like "true", "false", "True", "False"
            simulation = sim_value.lower() in ("true", "1", "yes")
        else:
            # Already a boolean or other type - convert to bool
            simulation = bool(sim_value)
        
        # Set up disconnect handler to clear bound devices
        self._disconnect_notice: Optional[str] = None
        # During intentional rebind/swap, ignore transient disconnect callbacks
        # for those addresses so Settings bindings are not wiped accidentally.
        self._disconnect_ignore_addrs: Set[str] = set()
        def handle_disconnect(address: str):
            """Handle BLE device disconnection and keep role bindings reconnectable."""
            addr_upper = (address or "").upper()
            if addr_upper in self._disconnect_ignore_addrs:
                return
            disconnected_name = address
            # Keep role bindings when a device disconnects so it stays visible in
            # Settings and can be reconnected without restarting the app.
            if self.bound_flexor_emg and (self.bound_flexor_emg.address or "").upper() == addr_upper:
                disconnected_name = self.bound_flexor_emg.name or address
            if self.bound_extensor_emg and (self.bound_extensor_emg.address or "").upper() == addr_upper:
                disconnected_name = self.bound_extensor_emg.name or address
            if self.bound_exo_hand and (self.bound_exo_hand.address or "").upper() == addr_upper:
                disconnected_name = self.bound_exo_hand.name or address
                # ExoClient gets recreated on the next bind/rebind attempt.
                self.exo_hand_client = None
            self._disconnect_notice = (
                f"Device disconnected: {disconnected_name} [{address}]. Role kept in Settings for reconnect."
            )
        
        self.ble = BLEManager(simulation=simulation, on_disconnect=handle_disconnect)
        settings = self.cfg.get("settings", {})
        shared_emg_max_range = float(settings.get("emg_max_range", 100))
        # Persisted settings values (baseline for Reset behavior).
        self.settings_emg_max_range_flexor = float(settings.get("emg_max_range_flexor", shared_emg_max_range))
        self.settings_emg_max_range_extensor = float(settings.get("emg_max_range_extensor", shared_emg_max_range))
        # Runtime maxima can expand via dynamic MVC; reset returns them to settings_*.
        self.emg_max_range_flexor = float(self.settings_emg_max_range_flexor)
        self.emg_max_range_extensor = float(self.settings_emg_max_range_extensor)
        self.training_muscle_mode = str(settings.get("training_muscle_mode", "auto"))
        self.hand_start_percent = float(settings.get("hand_start_percent", 70))
        self.threshold_percent = float(settings.get("threshold_percent", 20))
        self.relax_flexion_percent = max(
            0.0,
            min(100.0, float(settings.get("relax_flexion_percent", 12))),
        )
        self.relax_extension_percent = max(
            0.0,
            min(100.0, float(settings.get("relax_extension_percent", 12))),
        )
        self.countdown_seconds = float(settings.get("countdown_seconds", 5))
        self.stars_to_collect = int(max(1, min(7, round(float(settings.get("stars_to_collect", 3))))))
        # Backward compatibility: legacy config used target_close_percent only.
        self.target_flexion_percent = float(settings.get("target_flexion_percent", settings.get("target_close_percent", 80)))
        self.target_extension_percent = float(settings.get("target_extension_percent", 30))
        self.grip_step_percent = float(settings.get("grip_step_percent", 1))
        self.command_rate_hz = float(settings.get("command_rate_hz", 10))
        self.activation_hysteresis_percent = float(settings.get("activation_hysteresis_percent", 2))
        self.deactivation_hysteresis_percent = float(settings.get("deactivation_hysteresis_percent", 5))
        self.forward_deadband_percent = max(0.0, min(100.0, float(settings.get("forward_deadband_percent", 0))))
        self.reversal_deadband_percent = max(0.0, min(100.0, float(settings.get("reversal_deadband_percent", 0))))
        self.background_blur_percent = max(0.0, min(100.0, float(settings.get("background_blur_percent", 100))))
        self.theme_mode = self._normalize_theme_mode(settings.get("theme_mode", "system"))
        self._system_theme_is_dark_cache = True
        self._system_theme_last_check = 0.0
        # Dynamic MVC tuning (configurable from settings section in devices.json).
        self.dynamic_mvc_alpha_up = max(0.0, min(1.0, float(settings.get("dynamic_mvc_alpha_up", 0.2))))
        self.dynamic_mvc_alpha_down = max(0.0, min(1.0, float(settings.get("dynamic_mvc_alpha_down", 0.01))))
        self.dynamic_mvc_up_margin_ratio = max(0.0, min(1.0, float(settings.get("dynamic_mvc_up_margin_ratio", 0.03))))
        self.dynamic_mvc_hold_activity_ratio = max(
            0.0, min(1.0, float(settings.get("dynamic_mvc_hold_activity_ratio", 0.85)))
        )
        self.dynamic_mvc_decay_trigger_ratio = max(
            0.0, min(1.0, float(settings.get("dynamic_mvc_decay_trigger_ratio", 0.2)))
        )
        self.dynamic_mvc_decay_grace_seconds = max(
            0.0, float(settings.get("dynamic_mvc_decay_grace_seconds", 2.0))
        )
        # Snapshot startup defaults loaded from config; Reset restores these.
        self._settings_defaults = {
            "emg_max_range_flexor": self.settings_emg_max_range_flexor,
            "emg_max_range_extensor": self.settings_emg_max_range_extensor,
            "training_muscle_mode": self.training_muscle_mode,
            "hand_start_percent": self.hand_start_percent,
            "threshold_percent": self.threshold_percent,
            "relax_flexion_percent": self.relax_flexion_percent,
            "relax_extension_percent": self.relax_extension_percent,
            "countdown_seconds": self.countdown_seconds,
            "stars_to_collect": self.stars_to_collect,
            "target_flexion_percent": self.target_flexion_percent,
            "target_extension_percent": self.target_extension_percent,
            "grip_step_percent": self.grip_step_percent,
            "command_rate_hz": self.command_rate_hz,
            "activation_hysteresis_percent": self.activation_hysteresis_percent,
            "deactivation_hysteresis_percent": self.deactivation_hysteresis_percent,
            "forward_deadband_percent": self.forward_deadband_percent,
            "reversal_deadband_percent": self.reversal_deadband_percent,
            "background_blur_percent": self.background_blur_percent,
            "theme_mode": self.theme_mode,
            "dynamic_mvc_alpha_up": self.dynamic_mvc_alpha_up,
            "dynamic_mvc_alpha_down": self.dynamic_mvc_alpha_down,
            "dynamic_mvc_up_margin_ratio": self.dynamic_mvc_up_margin_ratio,
            "dynamic_mvc_hold_activity_ratio": self.dynamic_mvc_hold_activity_ratio,
            "dynamic_mvc_decay_trigger_ratio": self.dynamic_mvc_decay_trigger_ratio,
            "dynamic_mvc_decay_grace_seconds": self.dynamic_mvc_decay_grace_seconds,
        }

        # EMG processors for flexor/extensor channels.
        # Flexor uses stronger smoothing to reduce sensitivity to co-contraction noise.
        self.emg_flexor = EMGProcessor(
            EMGConfig(
                max_range=self.emg_max_range_flexor,
                rms_method="ema",
                ema_alpha=0.1,
            )
        )
        self.emg_extensor = EMGProcessor(
            EMGConfig(
                max_range=self.emg_max_range_extensor,
                rms_method="ema",
                ema_alpha=0.1,
            )
        )
        self._emg_flexor_value = 0.0
        self._emg_extensor_value = 0.0
        # Raw EMG sample buffers for charts (1000Hz input, display at 10Hz)
        self._emg_flexor_raw_samples: List[float] = []
        self._emg_extensor_raw_samples: List[float] = []
        # Stateful simulation values for synthetic EMG generation.
        now = time.perf_counter()
        self._sim_emg_state = {
            "flexor": {
                "intensity": 0.0,
                "press_duration": 0.0,
                "phase": random.uniform(0.0, math.tau),
                "freq_hz": 8.0,
                "amp": 0.015,
                "level": 0.03,
                "last_update": now,
            },
            "extensor": {
                "intensity": 0.0,
                "press_duration": 0.0,
                "phase": random.uniform(0.0, math.tau),
                "freq_hz": 8.0,
                "amp": 0.015,
                "level": 0.03,
                "last_update": now,
            },
        }
        # Per-channel dynamic MVC timing state (for gated in-session decay).
        now_mvc = time.perf_counter()
        self._dynamic_mvc_last_strong_ts_flexor = now_mvc
        self._dynamic_mvc_last_strong_ts_extensor = now_mvc

        # Device bindings
        self.bound_flexor_emg = None
        self.bound_extensor_emg = None
        self.bound_exo_hand = None
        self.exo_hand_client: Optional[ExoClient] = None
        # Characteristic UUIDs for the single-hand setup.
        flexor_cfg = self.cfg.get("emg_flexor", {})
        extensor_cfg = self.cfg.get("emg_extensor", {})
        hand_cfg = self.cfg.get("exo_hand", {})
        self.flexor_emg_write_uuid = flexor_cfg.get("write_characteristic_uuid")
        self.extensor_emg_write_uuid = extensor_cfg.get("write_characteristic_uuid")
        self.flexor_emg_notify_uuid = flexor_cfg.get("notify_characteristic_uuid")
        self.extensor_emg_notify_uuid = extensor_cfg.get("notify_characteristic_uuid")
        self.exo_hand_write_uuid = hand_cfg.get("write_characteristic_uuid")
        self.exo_hand_feedback_uuid = hand_cfg.get("feedback_characteristic_uuid")

        # Exo positions (0..1), simulate if needed
        start_pos = max(0.0, min(1.0, self.hand_start_percent / 100.0))
        self._hand_pos = start_pos
        self._hand_target = start_pos
        self._last_sent_grip_level: Optional[int] = None

        # Scene management
        self.scenes = SceneManager()
        self._build_scenes()

    def _load_config(self) -> dict:
        """
        Load configuration using resilient path resolution.
        Search order:
          1) HOH_CONFIG_PATH env var (if set)
          2) ./config/devices.json (current working directory)
          3) project_root/config/devices.json (development fallback)
          4) packaged config/devices.json
          5) built-in default config
        """
        def _read_json(path: str) -> Optional[dict]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load config file at {path}: {e}")
                return None

        def _read_packaged_json(filename: str) -> Optional[dict]:
            try:
                import importlib.resources as pkg_resources
                config_pkg = pkg_resources.files("config")
                cfg_file = config_pkg.joinpath(filename)
                if cfg_file.is_file():
                    return json.loads(cfg_file.read_text(encoding="utf-8"))
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError, json.JSONDecodeError):
                pass

            # Python < 3.9 fallback
            try:
                import importlib_resources as pkg_resources  # type: ignore
                config_pkg = pkg_resources.files("config")
                cfg_file = config_pkg.joinpath(filename)
                with cfg_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError, json.JSONDecodeError):
                return None

        configured_path = os.environ.get("HOH_CONFIG_PATH", "").strip()
        candidate_paths = []
        if configured_path:
            candidate_paths.append(configured_path)
        candidate_paths.extend([_CWD_CONFIG_PATH, _PROJECT_CONFIG_PATH])

        for path in candidate_paths:
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
        return _DEFAULT_CONFIG

    def _load_language_packs(self) -> Tuple[Dict[str, Dict[str, object]], str]:
        default_packs = {
            code: {"name": data["name"], "texts": dict(data["texts"])}
            for code, data in _DEFAULT_LANGUAGE_PACKS.items()
        }

        def _read_json(path: str) -> Optional[dict]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load language pack file at {path}: {e}")
                return None

        def _read_packaged_json(filename: str) -> Optional[dict]:
            try:
                import importlib.resources as pkg_resources
                assets_pkg = pkg_resources.files("assets")
                assets_file = assets_pkg.joinpath(filename)
                if assets_file.is_file():
                    return json.loads(assets_file.read_text(encoding="utf-8"))
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError, json.JSONDecodeError):
                pass

            # Python < 3.9 fallback
            try:
                import importlib_resources as pkg_resources  # type: ignore
                assets_pkg = pkg_resources.files("assets")
                assets_file = assets_pkg.joinpath(filename)
                with assets_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError, json.JSONDecodeError):
                return None

        def _parse_language_payload(raw: dict) -> Optional[Tuple[Dict[str, Dict[str, object]], str]]:
            if not isinstance(raw, dict):
                return None

            raw_languages = raw.get("languages")
            if not isinstance(raw_languages, dict):
                return None

            parsed: Dict[str, Dict[str, object]] = {}
            for code, payload in raw_languages.items():
                if not isinstance(code, str) or not isinstance(payload, dict):
                    continue
                name = payload.get("name", code)
                texts = payload.get("texts", {})
                if not isinstance(name, str) or not isinstance(texts, dict):
                    continue
                parsed[code] = {
                    "name": name,
                    "texts": {str(k): str(v) for k, v in texts.items()},
                }

            if "en" not in parsed:
                parsed["en"] = default_packs["en"]

            # Merge parsed values over defaults so missing keys still fall back.
            merged: Dict[str, Dict[str, object]] = {}
            all_codes = set(default_packs.keys()) | set(parsed.keys())
            for code in all_codes:
                base_name = str(default_packs.get(code, {}).get("name", code))
                base_texts = dict(default_packs.get(code, {}).get("texts", {}))
                incoming = parsed.get(code, {})
                merged_name = str(incoming.get("name", base_name))
                incoming_texts = incoming.get("texts", {})
                if isinstance(incoming_texts, dict):
                    base_texts.update({str(k): str(v) for k, v in incoming_texts.items()})
                merged[code] = {"name": merged_name, "texts": base_texts}

            default_language = raw.get("default_language", "en")
            normalized = self._normalize_language_packs(merged)
            if not isinstance(default_language, str) or default_language not in normalized:
                default_language = "en"
            return normalized, default_language

        for path in (_CWD_LANGUAGE_PATH, _PROJECT_LANGUAGE_PATH):
            if not os.path.exists(path):
                continue
            raw = _read_json(path)
            parsed_payload = _parse_language_payload(raw) if raw is not None else None
            if parsed_payload is not None:
                print(f"[INFO] Loaded language packs: {path}")
                return parsed_payload

        packaged_languages = _read_packaged_json("languages.json")
        parsed_packaged_payload = _parse_language_payload(packaged_languages) if packaged_languages is not None else None
        if parsed_packaged_payload is not None:
            print("[INFO] Loaded packaged language packs: assets/languages.json")
            return parsed_packaged_payload

        print("[WARNING] No language pack file found. Using built-in English text.")
        return self._normalize_language_packs(default_packs), "en"

    def _extract_placeholders(self, text: str) -> Set[str]:
        """Collect Python format placeholders like {count} from a text template."""
        return set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", str(text)))

    def _normalize_language_packs(self, packs: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
        """
        Validate and normalize translation packs for runtime safety.

        Rules:
        - English ("en") is canonical key set.
        - Missing keys in non-English packs are auto-filled with English text.
        - Placeholder mismatches are auto-replaced by English text.
        """
        default_en_payload = _DEFAULT_LANGUAGE_PACKS.get("en", {})
        default_en_texts_raw = default_en_payload.get("texts", {})
        default_en_texts = dict(default_en_texts_raw) if isinstance(default_en_texts_raw, dict) else {}

        en_payload = packs.get("en", {})
        en_name = "English"
        en_texts = dict(default_en_texts)
        if isinstance(en_payload, dict):
            en_name = str(en_payload.get("name", en_name))
            en_incoming = en_payload.get("texts", {})
            if isinstance(en_incoming, dict):
                en_texts.update({str(k): str(v) for k, v in en_incoming.items()})

        normalized: Dict[str, Dict[str, object]] = {"en": {"name": en_name, "texts": en_texts}}
        en_keys = set(en_texts.keys())

        for code, payload in packs.items():
            if code == "en":
                continue

            if not isinstance(payload, dict):
                normalized[code] = {"name": str(code), "texts": dict(en_texts)}
                print(f"[WARNING] Language '{code}' has invalid structure; using English placeholders.")
                continue

            name = str(payload.get("name", code))
            incoming_texts_raw = payload.get("texts", {})
            incoming_texts: Dict[str, str] = {}
            if isinstance(incoming_texts_raw, dict):
                incoming_texts = {str(k): str(v) for k, v in incoming_texts_raw.items()}

            missing_keys: List[str] = []
            placeholder_fixed: List[str] = []
            resolved_texts = dict(incoming_texts)
            for key, en_text in en_texts.items():
                candidate = resolved_texts.get(key)
                if not candidate:
                    resolved_texts[key] = en_text
                    missing_keys.append(key)
                    continue

                if self._extract_placeholders(candidate) != self._extract_placeholders(en_text):
                    resolved_texts[key] = en_text
                    placeholder_fixed.append(key)

            extra_keys = [k for k in resolved_texts.keys() if k not in en_keys]
            if missing_keys:
                preview = ", ".join(sorted(missing_keys)[:5])
                if len(missing_keys) > 5:
                    preview += ", ..."
                print(
                    f"[WARNING] Language '{code}' missing {len(missing_keys)} keys; "
                    f"filled with English placeholders. Keys: {preview}"
                )
            if placeholder_fixed:
                preview = ", ".join(sorted(placeholder_fixed)[:5])
                if len(placeholder_fixed) > 5:
                    preview += ", ..."
                print(
                    f"[WARNING] Language '{code}' has {len(placeholder_fixed)} placeholder mismatches; "
                    f"replaced with English placeholders. Keys: {preview}"
                )
            if extra_keys:
                print(f"[INFO] Language '{code}' includes {len(extra_keys)} extra keys not used by the game.")

            normalized[code] = {"name": name, "texts": resolved_texts}

        # Ensure default expected languages always appear in the selector.
        for code, payload in _DEFAULT_LANGUAGE_PACKS.items():
            if code in normalized:
                continue
            default_name = str(payload.get("name", code)) if isinstance(payload, dict) else code
            normalized[code] = {"name": default_name, "texts": dict(en_texts)}
            print(f"[WARNING] Language '{code}' missing entirely; added with English placeholders.")

        return normalized

    def _get_text(self, key: str, **kwargs) -> str:
        default_texts = self.language_packs.get("en", {}).get("texts", {})
        current_texts = self.language_packs.get(self.current_language, {}).get("texts", {})
        template = key
        if isinstance(current_texts, dict):
            template = str(current_texts.get(key, template))
        if template == key and isinstance(default_texts, dict):
            template = str(default_texts.get(key, key))
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template

    def _get_text_keys(self) -> Set[str]:
        keys: Set[str] = set()
        default_texts = self.language_packs.get("en", {}).get("texts", {})
        current_texts = self.language_packs.get(self.current_language, {}).get("texts", {})
        for texts in (default_texts, current_texts):
            if isinstance(texts, dict):
                keys.update(str(key) for key in texts.keys())
        return keys

    def _get_language_options(self) -> List[Tuple[str, str]]:
        options: List[Tuple[str, str]] = []
        for code, payload in self.language_packs.items():
            name = payload.get("name", code) if isinstance(payload, dict) else code
            options.append((code, str(name)))
        # Keep a stable order for usability.
        options.sort(key=lambda item: (0 if item[0] == "en" else 1, item[0]))
        return options

    def _set_game_language(self, language_code: str):
        if language_code not in self.language_packs:
            return
        self.current_language = language_code
        if hasattr(self, "game_scene") and self.game_scene is not None:
            self.game_scene.set_language(language_code)

    def _update_sim_emg_channel(self, channel: str, pressed: bool):
        """
        Update simulation state for one EMG channel.
        Baseline oscillates around chart center; sustained press ramps intensity.
        """
        state = self._sim_emg_state[channel]
        now = time.perf_counter()
        dt = max(0.0, min(0.1, now - state["last_update"]))
        state["last_update"] = now

        # Press duration drives a capped activation target.
        if pressed:
            state["press_duration"] = min(2.0, state["press_duration"] + dt)
        else:
            state["press_duration"] = max(0.0, state["press_duration"] - (dt * 2.5))

        target_intensity = min(1.0, state["press_duration"] / 1.4)
        # Smooth to avoid abrupt transitions.
        lerp_rate = 8.0
        state["intensity"] += (target_intensity - state["intensity"]) * min(1.0, dt * lerp_rate)
        intensity = state["intensity"]

        rest_freq = 8.0
        max_freq = 95.0
        rest_amp = 0.015
        max_amp = 0.42

        state["freq_hz"] = rest_freq + (max_freq - rest_freq) * intensity
        state["amp"] = rest_amp + (max_amp - rest_amp) * intensity
        state["phase"] = (state["phase"] + (math.tau * state["freq_hz"] * dt)) % math.tau

        # Control level follows activation envelope (0..1), not instantaneous sine sign.
        level_noise = random.uniform(-0.02, 0.02)
        state["level"] = max(0.0, min(1.0, 0.03 + (0.92 * intensity) + level_noise))

    def _sim_emg_level(self, channel: str, key: int) -> float:
        keys = pygame.key.get_pressed()
        self._update_sim_emg_channel(channel, bool(keys[key]))
        return self._sim_emg_state[channel]["level"]

    def _sim_emg_raw_samples(self, channel: str, key: int, count: int = 100) -> List[float]:
        keys = pygame.key.get_pressed()
        self._update_sim_emg_channel(channel, bool(keys[key]))
        state = self._sim_emg_state[channel]

        # Generate high-rate synthetic raw stream around the ADC midpoint.
        sample_rate_hz = 1000.0
        phase = state["phase"]
        freq_hz = state["freq_hz"]
        amp = state["amp"]
        intensity = state["intensity"]
        noise_std = 0.006 + (0.014 * intensity)
        phase_step = math.tau * freq_hz / sample_rate_hz

        samples: List[float] = []
        for _ in range(count):
            phase = (phase + phase_step) % math.tau
            sample_norm = 0.5 + (amp * math.sin(phase)) + random.gauss(0.0, noise_std)
            sample_norm = max(0.0, min(1.0, sample_norm))
            samples.append(sample_norm * 65535.0)

        state["phase"] = phase
        return samples

    def _build_scenes(self):
        def open_settings():
            # Extract allowed MAC addresses from config
            allowed_mac_addresses = set()
            for device_key in ["emg_flexor", "emg_extensor", "exo_hand"]:
                mac = self.cfg.get(device_key, {}).get("mac_address", "")
                if mac and mac.strip():
                    allowed_mac_addresses.add(mac.strip().upper())
            
            init = {
                "emg_max_range_flexor": self.emg_max_range_flexor,
                "emg_max_range_extensor": self.emg_max_range_extensor,
                "training_muscle_mode": self.training_muscle_mode,
                "hand_start_percent": self.hand_start_percent,
                "threshold_percent": self.threshold_percent,
                "relax_flexion_percent": self.relax_flexion_percent,
                "relax_extension_percent": self.relax_extension_percent,
                "countdown_seconds": self.countdown_seconds,
                "stars_to_collect": self.stars_to_collect,
                "target_flexion_percent": self.target_flexion_percent,
                "target_extension_percent": self.target_extension_percent,
                "grip_step_percent": self.grip_step_percent,
                "command_rate_hz": self.command_rate_hz,
                "activation_hysteresis_percent": self.activation_hysteresis_percent,
                "deactivation_hysteresis_percent": self.deactivation_hysteresis_percent,
                "forward_deadband_percent": self.forward_deadband_percent,
                "reversal_deadband_percent": self.reversal_deadband_percent,
                "background_blur_percent": self.background_blur_percent,
                "theme_mode": self.theme_mode,
                "dynamic_mvc_alpha_up": self.dynamic_mvc_alpha_up,
                "dynamic_mvc_alpha_down": self.dynamic_mvc_alpha_down,
                "dynamic_mvc_up_margin_ratio": self.dynamic_mvc_up_margin_ratio,
                "dynamic_mvc_hold_activity_ratio": self.dynamic_mvc_hold_activity_ratio,
                "dynamic_mvc_decay_trigger_ratio": self.dynamic_mvc_decay_trigger_ratio,
                "dynamic_mvc_decay_grace_seconds": self.dynamic_mvc_decay_grace_seconds,
            }
            settings_scene = SettingsScene(
                self.screen_rect,
                self.ui_scale,
                self.ble,
                on_close=lambda: self.scenes.set_scene(self.game_scene),
                get_text=self._get_text,
                get_text_keys=self._get_text_keys,
                set_game_language=self._set_game_language,
                get_game_language=lambda: self.current_language,
                get_language_options=self._get_language_options,
                set_emg_max_flexor=self._set_emg_max_flexor,
                set_emg_max_extensor=self._set_emg_max_extensor,
                set_training_muscle_mode=self._set_training_muscle_mode,
                set_hand_start_percent=self._set_hand_start_percent,
                set_threshold_percent=self._set_threshold_percent,
                set_relax_flexion_percent=self._set_relax_flexion_percent,
                set_relax_extension_percent=self._set_relax_extension_percent,
                set_countdown_seconds=self._set_countdown_seconds,
                set_stars_to_collect=self._set_stars_to_collect,
                set_target_flexion_percent=self._set_target_flexion_percent,
                set_target_extension_percent=self._set_target_extension_percent,
                set_grip_step_percent=self._set_grip_step_percent,
                set_command_rate_hz=self._set_command_rate_hz,
                set_activation_hysteresis_percent=self._set_activation_hysteresis_percent,
                set_deactivation_hysteresis_percent=self._set_deactivation_hysteresis_percent,
                set_forward_deadband_percent=self._set_forward_deadband_percent,
                set_reversal_deadband_percent=self._set_reversal_deadband_percent,
                set_background_blur_percent=self._set_background_blur_percent,
                set_theme_mode=self._set_theme_mode,
                set_dynamic_mvc_alpha_up=self._set_dynamic_mvc_alpha_up,
                set_dynamic_mvc_alpha_down=self._set_dynamic_mvc_alpha_down,
                set_dynamic_mvc_up_margin_ratio=self._set_dynamic_mvc_up_margin_ratio,
                set_dynamic_mvc_hold_activity_ratio=self._set_dynamic_mvc_hold_activity_ratio,
                set_dynamic_mvc_decay_trigger_ratio=self._set_dynamic_mvc_decay_trigger_ratio,
                set_dynamic_mvc_decay_grace_seconds=self._set_dynamic_mvc_decay_grace_seconds,
                get_is_dark_theme=self._get_is_dark_theme,
                on_bind_flexor_emg=self._bind_flexor_emg,
                on_bind_extensor_emg=self._bind_extensor_emg,
                on_bind_exo_hand=self._bind_exo_hand,
                on_swap_flexor_extensor=self._swap_flexor_extensor_sensors,
                consume_disconnect_notice=self._consume_disconnect_notice,
                init_values=init,
                allowed_mac_addresses=allowed_mac_addresses,
                get_bound_flexor_emg=lambda: self.bound_flexor_emg,
                get_bound_extensor_emg=lambda: self.bound_extensor_emg,
                get_bound_exo_hand=lambda: self.bound_exo_hand,
            )
            self.scenes.set_scene(settings_scene)

        def reset_game():
            # Reset only EMG max ranges to startup defaults plus gameplay progress.
            self._set_emg_max_flexor(self._settings_defaults["emg_max_range_flexor"])
            self._set_emg_max_extensor(self._settings_defaults["emg_max_range_extensor"])
            self.game_scene.reset()
            self._reset_round()

        # EMG providers:
        # - In simulation mode: synthesize centered oscillatory EMG that ramps with press duration.
        # - In hardware mode: use processed EMG values coming from the EMG processors.
        def emg_flexor_provider() -> float:
            if self.ble.simulation:
                return self._sim_emg_level("flexor", pygame.K_f)
            return self._emg_flexor_value

        def emg_extensor_provider() -> float:
            if self.ble.simulation:
                return self._sim_emg_level("extensor", pygame.K_e)
            return self._emg_extensor_value

        # Raw EMG providers:
        # - In simulation mode: generate synthetic oscillatory EMG around ADC midpoint
        # - In hardware mode: use actual raw sample buffers from BLE notifications
        def emg_flexor_raw_provider() -> List[float]:
            if self.ble.simulation:
                return self._sim_emg_raw_samples("flexor", pygame.K_f, count=100)
            return self._emg_flexor_raw_samples[:]
        
        def emg_extensor_raw_provider() -> List[float]:
            if self.ble.simulation:
                return self._sim_emg_raw_samples("extensor", pygame.K_e, count=100)
            return self._emg_extensor_raw_samples[:]

        self.game_scene = GameScene(
            self.screen_rect,
            self.ui_scale,
            open_settings=open_settings,
            reset_game=reset_game,
            get_text=self._get_text,
            get_current_language=lambda: self.current_language,
            emg_flexor_provider=emg_flexor_provider,
            emg_extensor_provider=emg_extensor_provider,
            send_grip=self._send_grip,
            hand_pos_provider=lambda: self._hand_pos,
            get_hand_start_percent=lambda: self.hand_start_percent,
            get_threshold_percent=lambda: self.threshold_percent,
            get_relax_flexion_percent=lambda: self.relax_flexion_percent,
            get_relax_extension_percent=lambda: self.relax_extension_percent,
            get_target_flexion_percent=lambda: self.target_flexion_percent,
            get_target_extension_percent=lambda: self.target_extension_percent,
            get_countdown_seconds=lambda: self.countdown_seconds,
            get_stars_to_collect=lambda: self.stars_to_collect,
            get_grip_step_percent=lambda: self.grip_step_percent,
            get_command_rate_hz=lambda: self.command_rate_hz,
            get_activation_hysteresis_percent=lambda: self.activation_hysteresis_percent,
            get_deactivation_hysteresis_percent=lambda: self.deactivation_hysteresis_percent,
            get_forward_deadband_percent=lambda: self.forward_deadband_percent,
            get_reversal_deadband_percent=lambda: self.reversal_deadband_percent,
            get_background_blur_percent=lambda: self.background_blur_percent,
            get_is_dark_theme=self._get_is_dark_theme,
            get_training_muscle_mode=lambda: self.training_muscle_mode,
            has_bound_flexor=lambda: self.bound_flexor_emg is not None,
            has_bound_extensor=lambda: self.bound_extensor_emg is not None,
            game_version=GAME_VERSION,
            emg_flexor_raw_provider=emg_flexor_raw_provider,
            emg_extensor_raw_provider=emg_extensor_raw_provider,
        )
        self.game_scene.set_language(self.current_language)
        open_settings()

    def _configure_emg_device(
        self,
        dev: BLEDeviceInfo,
        notify_uuid: Optional[str],
        write_uuid: Optional[str],
        notify_cb,
        led_state: Optional[str] = None,
    ) -> bool:
        """
        Ensure connected, subscribed, and streaming for an EMGS device.
        Returns True when subscription and stream commands were sent successfully.

        Porting notes:
        - Startup order matters for most EMG firmware:
          1) connect
          2) subscribe notifications
          3) configure modes (disable IMU, set EMG mode)
          4) start stream
        - If you reorder these steps in another language/runtime, you may get no data.
        """
        if not self.ble.is_connected(dev.address):
            if not self.ble.connect(dev.address):
                print(f"[ERROR] Failed to connect EMGS device: {dev.name} [{dev.address}]")
                return False

        if notify_uuid:
            # Retry once after reconnect in case previous connection became stale.
            if not self.ble.start_notifications(dev.address, notify_uuid, notify_cb):
                self.ble.disconnect(dev.address)
                if not self.ble.connect(dev.address):
                    print(f"[ERROR] Failed to reconnect EMGS device for notify: {dev.address}")
                    return False
                if not self.ble.start_notifications(dev.address, notify_uuid, notify_cb):
                    print(f"[ERROR] Failed to subscribe notify on {dev.address} ({notify_uuid})")
                    return False
        else:
            print(f"[WARNING] No notify UUID configured for {dev.address}")
            return False

        if not write_uuid:
            print(f"[WARNING] No write UUID configured for {dev.address}")
            return False

        # Give peripheral a short settle time after notify setup.
        time.sleep(0.05)

        ok = True
        if led_state:
            ok = self.ble.write_characteristic(
                dev.address,
                write_uuid,
                emgs_client.build_set_indicator_led(led_state),
                response=False,
            ) and ok
        for idx in range(len(emgs_client.ICM_CHANNELS)):
            ok = self.ble.write_characteristic(
                dev.address,
                write_uuid,
                emgs_client.build_set_icm_mode(idx, False),
                response=False,
            ) and ok
        ok = self.ble.write_characteristic(
            dev.address,
            write_uuid,
            emgs_client.build_set_emg_mode(emgs_client.EMG_MODE_RAW),
            response=False,
        ) and ok
        ok = self.ble.write_characteristic(
            dev.address,
            write_uuid,
            emgs_client.build_start_stream(),
            response=False,
        ) and ok

        if not ok:
            print(f"[ERROR] Failed to configure/start EMG stream for {dev.address}")
        return ok

    def _bind_flexor_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_flexor_emg = dev
        if not dev:
            return
        self._configure_emg_device(
            dev,
            self.flexor_emg_notify_uuid,
            self.flexor_emg_write_uuid,
            self._on_flexor_emg,
            led_state="blue",
        )

    def _bind_extensor_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_extensor_emg = dev
        if not dev:
            return
        self._configure_emg_device(
            dev,
            self.extensor_emg_notify_uuid,
            self.extensor_emg_write_uuid,
            self._on_extensor_emg,
            led_state="red",
        )

    def _bind_exo_hand(self, dev: Optional[BLEDeviceInfo]):
        self.bound_exo_hand = dev
        if not dev:
            self.exo_hand_client = None
            self._last_sent_grip_level = None
            return
        if self.exo_hand_write_uuid and self.exo_hand_feedback_uuid:
            self.exo_hand_client = ExoClient(
                self.ble,
                dev,
                write_uuid=self.exo_hand_write_uuid,
                notify_uuid=self.exo_hand_feedback_uuid,
                on_status=self._on_exo_hand_status,
            )
            self.exo_hand_client.subscribe()
            self.exo_hand_client.move_uniform(max(0, min(100, int(self.hand_start_percent))))

    def _swap_flexor_extensor_sensors(self):
        """Swap currently bound flexor/extensor EMG devices."""
        current_flexor = self.bound_flexor_emg
        current_extensor = self.bound_extensor_emg
        if not current_flexor and not current_extensor:
            return

        swap_addrs: Set[str] = set()
        if current_flexor and current_flexor.address:
            swap_addrs.add(current_flexor.address.upper())
        if current_extensor and current_extensor.address:
            swap_addrs.add(current_extensor.address.upper())

        self._disconnect_ignore_addrs.update(swap_addrs)
        try:
            self._bind_flexor_emg(current_extensor)
            self._bind_extensor_emg(current_flexor)
        finally:
            self._disconnect_ignore_addrs.difference_update(swap_addrs)

    def _consume_disconnect_notice(self) -> Optional[str]:
        notice = self._disconnect_notice
        self._disconnect_notice = None
        return notice

    def _on_flexor_emg(self, payload: bytes):
        # Flexor channel callback delegates packet validation + processing to shared logic.
        self._process_emg_payload(
            payload=payload,
            processor=self.emg_flexor,
            raw_attr="_emg_flexor_raw_samples",
            norm_attr="_emg_flexor_value",
            update_dynamic_mvc=self._update_dynamic_mvc_flexor,
        )

    def _on_extensor_emg(self, payload: bytes):
        # Extensor channel callback mirrors flexor path with independent channel state.
        self._process_emg_payload(
            payload=payload,
            processor=self.emg_extensor,
            raw_attr="_emg_extensor_raw_samples",
            norm_attr="_emg_extensor_value",
            update_dynamic_mvc=self._update_dynamic_mvc_extensor,
        )

    def _process_emg_payload(self, payload: bytes, processor: EMGProcessor, raw_attr: str, norm_attr: str, update_dynamic_mvc):
        """
        Shared EMG packet handler for flexor/extensor channels.

        Input:
        - payload: one BLE notification payload from EMGS firmware.
        - processor: channel-specific EMGProcessor instance.

        Output:
        - Updates chart buffer (`raw_attr`) with packet raw samples (float list).
        - Updates control signal (`norm_attr`) with normalized activation in [0, 1].
        - Updates dynamic MVC using processor.last_rms().

        Conditions for processing:
        - Parsed packet must exist.
        - Packet `type` must be `"E"` (EMG data).
        - `emg_samples` must be a non-empty list/tuple of numeric values.
        """
        parsed = emgs_client.parse_notification(payload)
        if not parsed or parsed.get("type") != "E":
            return

        emg_samples = parsed.get("emg_samples")
        if not isinstance(emg_samples, (list, tuple)) or not emg_samples:
            return

        try:
            packet_samples = [float(sample) for sample in emg_samples]
        except (TypeError, ValueError):
            # Corrupted packet content should be ignored rather than destabilizing control.
            return

        setattr(self, raw_attr, packet_samples)
        setattr(self, norm_attr, processor.update_batch(packet_samples))
        update_dynamic_mvc(processor.last_rms())

    def _on_exo_hand_status(self, status: dict):
        positions = status.get("finger_positions")
        if positions:
            avg = sum(positions) / (len(positions) or 1)
            self._hand_pos = max(0.0, min(1.0, avg / 100.0))

    def _send_grip(self, grip: float):
        # Motor output interface:
        # input  -> normalized target grip [0..1]
        # output -> exo command level [0..100], only when quantized value changes
        # guards -> clamps range and suppresses duplicate commands
        self._hand_target = max(0.0, min(1.0, grip))
        if self.exo_hand_client:
            level = max(0, min(100, int(grip * 100)))
            if self._last_sent_grip_level != level:
                self.exo_hand_client.move_uniform(level)
                self._last_sent_grip_level = level
        elif self.ble.simulation:
            self._hand_target = grip

    def _set_emg_max_flexor(self, v: float):
        value = float(v)
        self.settings_emg_max_range_flexor = value
        self._set_emg_max_flexor_runtime(value)

    def _set_emg_max_extensor(self, v: float):
        value = float(v)
        self.settings_emg_max_range_extensor = value
        self._set_emg_max_extensor_runtime(value)

    def _set_emg_max_flexor_runtime(self, v: float):
        self.emg_max_range_flexor = float(v)
        self.emg_flexor.set_max_range(self.emg_max_range_flexor)

    def _set_emg_max_extensor_runtime(self, v: float):
        self.emg_max_range_extensor = float(v)
        self.emg_extensor.set_max_range(self.emg_max_range_extensor)

    def _set_training_muscle_mode(self, mode: str):
        normalized = str(mode or "").strip().lower()
        if normalized not in {"auto", "flexor_only", "extensor_only", "both"}:
            normalized = "auto"
        self.training_muscle_mode = normalized

    def _set_hand_start_percent(self, v: float):
        self.hand_start_percent = float(v)
        start_pos = max(0.0, min(1.0, self.hand_start_percent / 100.0))
        self._hand_target = start_pos

    def _set_threshold_percent(self, v: float):
        self.threshold_percent = float(v)

    def _set_relax_flexion_percent(self, v: float):
        self.relax_flexion_percent = max(0.0, min(100.0, float(v)))

    def _set_relax_extension_percent(self, v: float):
        self.relax_extension_percent = max(0.0, min(100.0, float(v)))

    def _set_countdown_seconds(self, v: float):
        self.countdown_seconds = float(v)

    def _set_stars_to_collect(self, v: float):
        self.stars_to_collect = int(max(1, min(7, round(float(v)))))
        if hasattr(self, "game_scene") and self.game_scene is not None:
            self.game_scene.set_max_stars(self.stars_to_collect)

    def _set_target_flexion_percent(self, v: float):
        self.target_flexion_percent = max(0.0, min(100.0, float(v)))

    def _set_target_extension_percent(self, v: float):
        self.target_extension_percent = max(0.0, min(100.0, float(v)))

    def _set_grip_step_percent(self, v: float):
        self.grip_step_percent = float(v)

    def _set_command_rate_hz(self, v: float):
        self.command_rate_hz = float(v)

    def _set_activation_hysteresis_percent(self, v: float):
        self.activation_hysteresis_percent = float(v)

    def _set_deactivation_hysteresis_percent(self, v: float):
        self.deactivation_hysteresis_percent = float(v)

    def _set_forward_deadband_percent(self, v: float):
        self.forward_deadband_percent = max(0.0, min(100.0, float(v)))

    def _set_reversal_deadband_percent(self, v: float):
        self.reversal_deadband_percent = max(0.0, min(100.0, float(v)))

    def _set_background_blur_percent(self, v: float):
        self.background_blur_percent = max(0.0, min(100.0, float(v)))
        if hasattr(self, "game_scene") and self.game_scene is not None:
            self.game_scene.set_background_blur_percent(self.background_blur_percent)

    def _normalize_theme_mode(self, mode: object) -> str:
        normalized = str(mode).strip().lower()
        if normalized not in {"system", "dark", "light"}:
            return "system"
        return normalized

    def _read_system_theme_is_dark(self) -> bool:
        system_name = platform.system()
        try:
            if system_name == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True,
                    text=True,
                    timeout=0.3,
                    check=False,
                )
                return result.returncode == 0 and "dark" in (result.stdout or "").strip().lower()
            if system_name == "Windows":
                try:
                    import winreg  # type: ignore

                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                        return int(value) == 0
                except Exception:
                    return True
        except Exception:
            return True
        # Fallback to dark theme on unsupported platforms.
        return True

    def _get_is_dark_theme(self) -> bool:
        if self.theme_mode == "dark":
            return True
        if self.theme_mode == "light":
            return False
        now = time.perf_counter()
        if (now - self._system_theme_last_check) >= 2.0:
            self._system_theme_is_dark_cache = self._read_system_theme_is_dark()
            self._system_theme_last_check = now
        return self._system_theme_is_dark_cache

    def _set_theme_mode(self, mode: str):
        self.theme_mode = self._normalize_theme_mode(mode)
        self._system_theme_last_check = 0.0

    def _set_dynamic_mvc_alpha_up(self, v: float):
        self.dynamic_mvc_alpha_up = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_alpha_down(self, v: float):
        self.dynamic_mvc_alpha_down = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_up_margin_ratio(self, v: float):
        self.dynamic_mvc_up_margin_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_hold_activity_ratio(self, v: float):
        self.dynamic_mvc_hold_activity_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_decay_trigger_ratio(self, v: float):
        self.dynamic_mvc_decay_trigger_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_decay_grace_seconds(self, v: float):
        self.dynamic_mvc_decay_grace_seconds = max(0.0, float(v))

    def _update_dynamic_mvc_flexor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_flexor,
            set_max=self._set_emg_max_flexor_runtime,
            floor=self.settings_emg_max_range_flexor,
            last_strong_attr="_dynamic_mvc_last_strong_ts_flexor",
        )

    def _update_dynamic_mvc_extensor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_extensor,
            set_max=self._set_emg_max_extensor_runtime,
            floor=self.settings_emg_max_range_extensor,
            last_strong_attr="_dynamic_mvc_last_strong_ts_extensor",
        )

    def _update_dynamic_mvc(self, rms: float, current_max: float, set_max, floor: float, last_strong_attr: str):
        # Bidirectional in-session MVC adaptation:
        # - expand quickly on new strong contractions
        # - decay slowly only after sustained low-activity period
        # - never decay below the Settings baseline floor
        now = time.perf_counter()
        alpha_up = self.dynamic_mvc_alpha_up
        alpha_down = self.dynamic_mvc_alpha_down
        up_margin_ratio = self.dynamic_mvc_up_margin_ratio
        hold_activity_ratio = self.dynamic_mvc_hold_activity_ratio
        decay_trigger_ratio = self.dynamic_mvc_decay_trigger_ratio
        decay_grace_s = self.dynamic_mvc_decay_grace_seconds

        floor = max(1.0, float(floor))
        current_max = max(floor, float(current_max))
        rms = max(0.0, float(rms))

        # Compute activity bands relative to current scale:
        # - up_trigger: clearly stronger than current max -> expand scale
        # - hold_trigger: still meaningfully active -> protect against decay
        # - decay_trigger: very low activity zone eligible for decay
        up_trigger = current_max * (1.0 + up_margin_ratio)
        hold_trigger = current_max * hold_activity_ratio
        decay_trigger = current_max * decay_trigger_ratio

        # Fast upward adaptation on new strong contractions.
        if rms >= up_trigger:
            new_max = current_max + (rms - current_max) * alpha_up
            set_max(max(floor, new_max))
            # Mark recent strong effort so decay does not start immediately after.
            setattr(self, last_strong_attr, now)
            return

        if rms >= hold_trigger:
            # Moderate/high activation indicates user intent is still near current scale.
            # Refresh grace timer even without increasing max.
            setattr(self, last_strong_attr, now)
            return

        last_strong_ts = float(getattr(self, last_strong_attr, now))
        # Skip decay when:
        # 1) activity is not yet sufficiently low, or
        # 2) we're inside the post-activity grace window.
        if rms >= decay_trigger or (now - last_strong_ts) < decay_grace_s:
            return

        # Slow downward adaptation only in sustained low-activity periods.
        new_max = max(floor, current_max * (1.0 - alpha_down))
        # Apply only real decreases (no-op guard against rounding/limits).
        if new_max < current_max:
            set_max(new_max)

    def _reset_settings_to_defaults(self):
        defaults = self._settings_defaults
        self._set_emg_max_flexor(defaults["emg_max_range_flexor"])
        self._set_emg_max_extensor(defaults["emg_max_range_extensor"])
        self._set_training_muscle_mode(defaults["training_muscle_mode"])
        self._set_hand_start_percent(defaults["hand_start_percent"])
        self._set_threshold_percent(defaults["threshold_percent"])
        self._set_relax_flexion_percent(defaults["relax_flexion_percent"])
        self._set_relax_extension_percent(defaults["relax_extension_percent"])
        self._set_countdown_seconds(defaults["countdown_seconds"])
        self._set_stars_to_collect(defaults["stars_to_collect"])
        self._set_target_flexion_percent(defaults["target_flexion_percent"])
        self._set_target_extension_percent(defaults["target_extension_percent"])
        self._set_grip_step_percent(defaults["grip_step_percent"])
        self._set_command_rate_hz(defaults["command_rate_hz"])
        self._set_activation_hysteresis_percent(defaults["activation_hysteresis_percent"])
        self._set_deactivation_hysteresis_percent(defaults["deactivation_hysteresis_percent"])
        self._set_forward_deadband_percent(defaults["forward_deadband_percent"])
        self._set_reversal_deadband_percent(defaults["reversal_deadband_percent"])
        self._set_background_blur_percent(defaults["background_blur_percent"])
        self._set_theme_mode(defaults["theme_mode"])
        self._set_dynamic_mvc_alpha_up(defaults["dynamic_mvc_alpha_up"])
        self._set_dynamic_mvc_alpha_down(defaults["dynamic_mvc_alpha_down"])
        self._set_dynamic_mvc_up_margin_ratio(defaults["dynamic_mvc_up_margin_ratio"])
        self._set_dynamic_mvc_hold_activity_ratio(defaults["dynamic_mvc_hold_activity_ratio"])
        self._set_dynamic_mvc_decay_trigger_ratio(defaults["dynamic_mvc_decay_trigger_ratio"])
        self._set_dynamic_mvc_decay_grace_seconds(defaults["dynamic_mvc_decay_grace_seconds"])

    def _reset_round(self):
        # Reset EMG processing state and restore runtime max ranges from Settings.
        self.emg_flexor.reset()
        self.emg_extensor.reset()
        self._set_emg_max_flexor_runtime(self.settings_emg_max_range_flexor)
        self._set_emg_max_extensor_runtime(self.settings_emg_max_range_extensor)
        now = time.perf_counter()
        self._dynamic_mvc_last_strong_ts_flexor = now
        self._dynamic_mvc_last_strong_ts_extensor = now

        self._emg_flexor_value = 0.0
        self._emg_extensor_value = 0.0
        self._emg_flexor_raw_samples = []
        self._emg_extensor_raw_samples = []

        # Reset should return the hand to fully open (0% flexion).
        self._hand_target = 0.0
        if self.ble.simulation:
            self._hand_pos = 0.0
        else:
            if self.exo_hand_client:
                self.exo_hand_client.move_uniform(0)
                self._last_sent_grip_level = 0

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            # Process all events
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                    break
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    if event.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                self.scenes.handle_event(event)
            
            # Check again after processing events (in case QUIT was posted during event handling)
            if not running:
                break
            # Process events one more time to catch any events posted during handle_event
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break

            if not running:
                break

            self.scenes.update(dt)
            # Simple simulation of exo position approaching target
            if self.ble.simulation:
                # move positions toward target with a first-order lag
                speed = 2.5  # per second
                self._hand_pos += (self._hand_target - self._hand_pos) * min(1.0, speed * dt)
            self.scenes.draw(self.screen)
            pygame.display.flip()

        self.shutdown()

    def shutdown(self):
        try:
            # Shutdown BLE connections first
            if hasattr(self, 'ble'):
                self.ble.shutdown()
        except Exception:
            pass
        
        # Skip pygame.quit() as it can hang - os._exit() will clean up everything
        os._exit(0)  # Force immediate exit - kills everything including pygame and daemon threads


def main():
    """Main entry point for the application."""
    try:
        print(f"[INFO] HKIE BME HOH game version: {GAME_VERSION}")
        App().run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        os._exit(0)  # Ensure we exit


if __name__ == "__main__":
    main()

