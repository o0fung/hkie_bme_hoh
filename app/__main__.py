"""
Entry point for running the HKIE BME HOH game.
This module allows the package to be run as: python -m app
or via the installed console script: run_hoh_game
"""
import sys
import os
import math
import random
import time
from typing import List, Optional, Dict, Tuple, Set
import numpy as np

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
from .game.game_scene import GameScene
from .game.settings_scene import SettingsScene
from .emg.processor import EMGProcessor, EMGConfig
from .ble.ble_manager import BLEManager, BLEDeviceInfo
from .ble import emgs_client
from .ble.exo_client import ExoClient
from .audio import AudioManager
from .app_settings_mixin import AppSettingsMixin
from .config_loader import load_config
from .i18n import DEFAULT_LANGUAGE_PACKS, load_language_packs
from .emg.simulation import sim_emg_raw_samples, update_sim_emg_channel
from .version import GAME_VERSION

# Config paths
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
_CWD_CONFIG_PATH = os.path.join(os.getcwd(), "config", "devices.json")
_PROJECT_CONFIG_PATH = os.path.join(_CONFIG_DIR, "devices.json")
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_CWD_LANGUAGE_PATH = os.path.join(os.getcwd(), "assets", "languages.json")
_PROJECT_LANGUAGE_PATH = os.path.join(_ASSETS_DIR, "languages.json")


# Default config as fallback if sample file cannot be found
class App(AppSettingsMixin):
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
        self.cfg = load_config(
            candidate_paths=[_CWD_CONFIG_PATH, _PROJECT_CONFIG_PATH],
        )
        self.language_packs, self.current_language = load_language_packs(
            candidate_paths=[_CWD_LANGUAGE_PATH, _PROJECT_LANGUAGE_PATH],
            default_language_packs=DEFAULT_LANGUAGE_PACKS,
        )
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
        self.training_trigger_mode = str(settings.get("training_trigger_mode", "auto"))
        self.hand_start_percent = float(settings.get("hand_start_percent", 70))
        self.threshold_percent = float(settings.get("threshold_percent", 20))
        self.trigger_threshold_percent = max(
            0.0,
            min(100.0, float(settings.get("trigger_threshold_percent", 50))),
        )
        self.trigger_wait_seconds = max(
            0.0,
            float(settings.get("trigger_wait_seconds", 1.0)),
        )
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
        self.training_duration_minutes = int(
            max(1, min(240, round(float(settings.get("training_duration_minutes", 20)))))
        )
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
        self.sound_effect_quick_enabled = bool(settings.get("sound_enabled", True))
        self.music_quick_enabled = bool(settings.get("music_enabled", True))
        self.sound_effect_volume_percent = max(0.0, min(100.0, float(settings.get("sound_effect_volume_percent", 60))))
        self.music_volume_percent = max(0.0, min(100.0, float(settings.get("music_volume_percent", 18))))
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
        self.audio_manager = AudioManager()
        self.audio_manager.set_sound_effect_volume_percent(self.sound_effect_volume_percent)
        self.audio_manager.set_music_volume_percent(self.music_volume_percent)
        self.audio_manager.set_sound_effect_enabled(self.sound_effect_quick_enabled)
        self.audio_manager.set_music_enabled(self.music_quick_enabled)
        # Snapshot startup defaults loaded from config; Reset restores these.
        self._settings_defaults = {
            "emg_max_range_flexor": self.settings_emg_max_range_flexor,
            "emg_max_range_extensor": self.settings_emg_max_range_extensor,
            "training_muscle_mode": self.training_muscle_mode,
            "training_trigger_mode": self.training_trigger_mode,
            "hand_start_percent": self.hand_start_percent,
            "threshold_percent": self.threshold_percent,
            "trigger_threshold_percent": self.trigger_threshold_percent,
            "trigger_wait_seconds": self.trigger_wait_seconds,
            "relax_flexion_percent": self.relax_flexion_percent,
            "relax_extension_percent": self.relax_extension_percent,
            "countdown_seconds": self.countdown_seconds,
            "stars_to_collect": self.stars_to_collect,
            "training_duration_minutes": self.training_duration_minutes,
            "target_flexion_percent": self.target_flexion_percent,
            "target_extension_percent": self.target_extension_percent,
            "grip_step_percent": self.grip_step_percent,
            "command_rate_hz": self.command_rate_hz,
            "activation_hysteresis_percent": self.activation_hysteresis_percent,
            "deactivation_hysteresis_percent": self.deactivation_hysteresis_percent,
            "forward_deadband_percent": self.forward_deadband_percent,
            "reversal_deadband_percent": self.reversal_deadband_percent,
            "background_blur_percent": self.background_blur_percent,
            "sound_enabled": self.sound_effect_quick_enabled,
            "music_enabled": self.music_quick_enabled,
            "sound_effect_volume_percent": self.sound_effect_volume_percent,
            "music_volume_percent": self.music_volume_percent,
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
        update_sim_emg_channel(self._sim_emg_state[channel], pressed)

    def _sim_emg_level(self, channel: str, key: int) -> float:
        keys = pygame.key.get_pressed()
        self._update_sim_emg_channel(channel, bool(keys[key]))
        return self._sim_emg_state[channel]["level"]

    def _sim_emg_raw_samples(self, channel: str, key: int, count: int = 100) -> List[float]:
        keys = pygame.key.get_pressed()
        self._update_sim_emg_channel(channel, bool(keys[key]))
        return sim_emg_raw_samples(self._sim_emg_state[channel], count=count)

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
                "training_trigger_mode": self.training_trigger_mode,
                "hand_start_percent": self.hand_start_percent,
                "threshold_percent": self.threshold_percent,
                "trigger_threshold_percent": self.trigger_threshold_percent,
                "trigger_wait_seconds": self.trigger_wait_seconds,
                "relax_flexion_percent": self.relax_flexion_percent,
                "relax_extension_percent": self.relax_extension_percent,
                "countdown_seconds": self.countdown_seconds,
                "stars_to_collect": self.stars_to_collect,
                "training_duration_minutes": self.training_duration_minutes,
                "target_flexion_percent": self.target_flexion_percent,
                "target_extension_percent": self.target_extension_percent,
                "grip_step_percent": self.grip_step_percent,
                "command_rate_hz": self.command_rate_hz,
                "activation_hysteresis_percent": self.activation_hysteresis_percent,
                "deactivation_hysteresis_percent": self.deactivation_hysteresis_percent,
                "forward_deadband_percent": self.forward_deadband_percent,
                "reversal_deadband_percent": self.reversal_deadband_percent,
                "background_blur_percent": self.background_blur_percent,
                "sound_enabled": self.sound_effect_quick_enabled,
                "music_enabled": self.music_quick_enabled,
                "sound_effect_volume_percent": self.sound_effect_volume_percent,
                "music_volume_percent": self.music_volume_percent,
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
                set_training_trigger_mode=self._set_training_trigger_mode,
                set_hand_start_percent=self._set_hand_start_percent,
                set_threshold_percent=self._set_threshold_percent,
                set_trigger_threshold_percent=self._set_trigger_threshold_percent,
                set_trigger_wait_seconds=self._set_trigger_wait_seconds,
                set_relax_flexion_percent=self._set_relax_flexion_percent,
                set_relax_extension_percent=self._set_relax_extension_percent,
                set_countdown_seconds=self._set_countdown_seconds,
                set_stars_to_collect=self._set_stars_to_collect,
                set_training_duration_minutes=self._set_training_duration_minutes,
                set_target_flexion_percent=self._set_target_flexion_percent,
                set_target_extension_percent=self._set_target_extension_percent,
                set_grip_step_percent=self._set_grip_step_percent,
                set_command_rate_hz=self._set_command_rate_hz,
                set_activation_hysteresis_percent=self._set_activation_hysteresis_percent,
                set_deactivation_hysteresis_percent=self._set_deactivation_hysteresis_percent,
                set_forward_deadband_percent=self._set_forward_deadband_percent,
                set_reversal_deadband_percent=self._set_reversal_deadband_percent,
                set_background_blur_percent=self._set_background_blur_percent,
                set_sound_enabled=self._set_sound_effect_quick_enabled,
                set_music_enabled=self._set_music_quick_enabled,
                set_sound_effect_volume_percent=self._set_sound_effect_volume_percent,
                set_music_volume_percent=self._set_music_volume_percent,
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
                default_values=dict(self._settings_defaults),
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
            get_training_duration_minutes=lambda: self.training_duration_minutes,
            get_grip_step_percent=lambda: self.grip_step_percent,
            get_command_rate_hz=lambda: self.command_rate_hz,
            get_activation_hysteresis_percent=lambda: self.activation_hysteresis_percent,
            get_deactivation_hysteresis_percent=lambda: self.deactivation_hysteresis_percent,
            get_forward_deadband_percent=lambda: self.forward_deadband_percent,
            get_reversal_deadband_percent=lambda: self.reversal_deadband_percent,
            get_background_blur_percent=lambda: self.background_blur_percent,
            play_start_chime=self.audio_manager.play_start_chime,
            play_progress_bell=self.audio_manager.play_progress_bell,
            play_completion_jingle=self.audio_manager.play_completion_jingle,
            toggle_sound_effect_quick=self._toggle_sound_effect_quick_enabled,
            get_sound_effect_quick_enabled=self._get_sound_effect_quick_enabled,
            toggle_music_quick=self._toggle_music_quick_enabled,
            get_music_quick_enabled=self._get_music_quick_enabled,
            get_is_dark_theme=self._get_is_dark_theme,
            get_training_muscle_mode=lambda: self.training_muscle_mode,
            get_training_trigger_mode=lambda: self.training_trigger_mode,
            get_trigger_threshold_percent=lambda: self.trigger_threshold_percent,
            get_trigger_wait_seconds=lambda: self.trigger_wait_seconds,
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

    def _reset_settings_to_defaults(self):
        defaults = self._settings_defaults
        self._set_emg_max_flexor(defaults["emg_max_range_flexor"])
        self._set_emg_max_extensor(defaults["emg_max_range_extensor"])
        self._set_training_muscle_mode(defaults["training_muscle_mode"])
        self._set_training_trigger_mode(defaults["training_trigger_mode"])
        self._set_hand_start_percent(defaults["hand_start_percent"])
        self._set_threshold_percent(defaults["threshold_percent"])
        self._set_trigger_threshold_percent(defaults["trigger_threshold_percent"])
        self._set_trigger_wait_seconds(defaults["trigger_wait_seconds"])
        self._set_relax_flexion_percent(defaults["relax_flexion_percent"])
        self._set_relax_extension_percent(defaults["relax_extension_percent"])
        self._set_countdown_seconds(defaults["countdown_seconds"])
        self._set_stars_to_collect(defaults["stars_to_collect"])
        self._set_training_duration_minutes(defaults["training_duration_minutes"])
        self._set_target_flexion_percent(defaults["target_flexion_percent"])
        self._set_target_extension_percent(defaults["target_extension_percent"])
        self._set_grip_step_percent(defaults["grip_step_percent"])
        self._set_command_rate_hz(defaults["command_rate_hz"])
        self._set_activation_hysteresis_percent(defaults["activation_hysteresis_percent"])
        self._set_deactivation_hysteresis_percent(defaults["deactivation_hysteresis_percent"])
        self._set_forward_deadband_percent(defaults["forward_deadband_percent"])
        self._set_reversal_deadband_percent(defaults["reversal_deadband_percent"])
        self._set_background_blur_percent(defaults["background_blur_percent"])
        self._set_sound_effect_quick_enabled(defaults["sound_enabled"])
        self._set_music_quick_enabled(defaults["music_enabled"])
        self._set_sound_effect_volume_percent(defaults["sound_effect_volume_percent"])
        self._set_music_volume_percent(defaults["music_volume_percent"])
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

            self.audio_manager.set_main_scene_active(self.scenes._scene is self.game_scene)
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
            self.audio_manager.shutdown()
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

