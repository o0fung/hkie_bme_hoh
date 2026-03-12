"""
Entry point for running the HKIE BME HOH game.
This module allows the package to be run as: python -m app
or via the installed console script: run_hoh_game
"""
import sys
import os
import json
import random
import time
from typing import List, Optional

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

# Config paths - prefer current working directory for user-writable config
# Fall back to package location for sample config when installed
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
CONFIG_PATH = os.path.join(os.getcwd(), "config", "devices.json")  # User config in current directory
SAMPLE_CONFIG_PATH = os.path.join(_CONFIG_DIR, "devices.sample.json")  # Sample from package (may not exist when installed)

GAME_VERSION = "1.0.1"

# Default config as fallback if sample file cannot be found
_DEFAULT_CONFIG = {
    "simulation": False,
    "settings": {
        "emg_max_range_flexor": 65535,
        "emg_max_range_extensor": 65535,
        "hand_start_percent": 70,
        "threshold_percent": 60,
        "countdown_seconds": 3,
        "target_flexion_percent": 90,
        "target_extension_percent": 30,
        "grip_step_percent": 5,
        "command_rate_hz": 10,
        "activation_hysteresis_percent": 2,
        "deactivation_hysteresis_percent": 5
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
        pygame.display.set_caption("HKIE BME Grip & Maintain")
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
        # Get simulation value - handle both bool and string values
        sim_value = self.cfg.get("simulation", False)
        if isinstance(sim_value, str):
            # Handle string values like "true", "false", "True", "False"
            simulation = sim_value.lower() in ("true", "1", "yes")
        else:
            # Already a boolean or other type - convert to bool
            simulation = bool(sim_value)
        
        # Set up disconnect handler to clear bound devices
        def handle_disconnect(address: str):
            """Handle BLE device disconnection - clear bound devices and update UI."""
            # Clear bound device if it matches the disconnected address
            if self.bound_flexor_emg and self.bound_flexor_emg.address == address:
                self.bound_flexor_emg = None
            if self.bound_extensor_emg and self.bound_extensor_emg.address == address:
                self.bound_extensor_emg = None
            if self.bound_exo_hand and self.bound_exo_hand.address == address:
                self.bound_exo_hand = None
                self.exo_hand_client = None
        
        self.ble = BLEManager(simulation=simulation, on_disconnect=handle_disconnect)
        settings = self.cfg.get("settings", {})
        shared_emg_max_range = float(settings.get("emg_max_range", 65535))
        # Persisted settings values (baseline for Reset behavior).
        self.settings_emg_max_range_flexor = float(settings.get("emg_max_range_flexor", shared_emg_max_range))
        self.settings_emg_max_range_extensor = float(settings.get("emg_max_range_extensor", shared_emg_max_range))
        # Runtime maxima can expand via dynamic MVC; reset returns them to settings_*.
        self.emg_max_range_flexor = float(self.settings_emg_max_range_flexor)
        self.emg_max_range_extensor = float(self.settings_emg_max_range_extensor)
        self.hand_start_percent = float(settings.get("hand_start_percent", 70))
        self.threshold_percent = float(settings.get("threshold_percent", 60))
        self.countdown_seconds = float(settings.get("countdown_seconds", 3))
        # Backward compatibility: legacy config used target_close_percent only.
        self.target_flexion_percent = float(settings.get("target_flexion_percent", settings.get("target_close_percent", 90)))
        self.target_extension_percent = float(settings.get("target_extension_percent", 30))
        self.grip_step_percent = float(settings.get("grip_step_percent", 5))
        self.command_rate_hz = float(settings.get("command_rate_hz", 10))
        self.activation_hysteresis_percent = float(settings.get("activation_hysteresis_percent", 2))
        self.deactivation_hysteresis_percent = float(settings.get("deactivation_hysteresis_percent", 5))

        # EMG processors for flexor/extensor channels.
        # Flexor uses stronger smoothing to reduce sensitivity to co-contraction noise.
        self.emg_flexor = EMGProcessor(EMGConfig(max_range=self.emg_max_range_flexor, rms_method="ema", ema_alpha=0.1))
        self.emg_extensor = EMGProcessor(EMGConfig(max_range=self.emg_max_range_extensor, rms_method="ema", ema_alpha=0.1))
        self._emg_flexor_value = 0.0
        self._emg_extensor_value = 0.0
        # Raw EMG sample buffers for charts (1000Hz input, display at 10Hz)
        self._emg_flexor_raw_samples: List[float] = []
        self._emg_extensor_raw_samples: List[float] = []

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
        Load configuration from current working directory.
        If config doesn't exist, copy sample from package location.
        """
        path = CONFIG_PATH
        
        # If config doesn't exist, try to copy from sample
        if not os.path.exists(path):
            sample_data = None
            sample_path = None
            
            # First, try to find sample via importlib.resources (for installed package)
            # Try 'config' package first since we make it a package
            try:
                import importlib.resources as pkg_resources
                try:
                    # Try 'config' package directly (most likely to work)
                    config_pkg = pkg_resources.files('config')
                    sample_file = config_pkg.joinpath('devices.sample.json')
                    if sample_file.is_file():
                        sample_data = sample_file.read_text(encoding='utf-8')
                except (ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError):
                    # If config package not found, try development paths
                    pass
            except ImportError:
                # Python < 3.9 - try importlib_resources
                try:
                    import importlib_resources as pkg_resources
                    config_pkg = pkg_resources.files('config')
                    sample_file = config_pkg.joinpath('devices.sample.json')
                    with sample_file.open('r', encoding='utf-8') as f:
                        sample_data = f.read()
                except (ImportError, FileNotFoundError, AttributeError, TypeError, OSError):
                    pass
            
            # If importlib didn't work, try direct file path (development mode)
            if not sample_data:
                # Try development path
                dev_sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "devices.sample.json")
                if os.path.exists(dev_sample_path):
                    sample_path = dev_sample_path
                elif os.path.exists(SAMPLE_CONFIG_PATH):
                    sample_path = SAMPLE_CONFIG_PATH
            
            # Load sample data
            if sample_data:
                # Parse JSON from string
                try:
                    sample = json.loads(sample_data)
                    # Write to current directory
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(sample, f, indent=2)
                except Exception as e:
                    print(f"[WARNING] Failed to parse sample config: {e}")
                    return {"simulation": True}
            elif sample_path and os.path.exists(sample_path):
                # Copy sample file
                try:
                    with open(sample_path, "r") as f:
                        sample = json.load(f)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(sample, f, indent=2)
                except Exception as e:
                    print(f"[WARNING] Failed to copy sample config: {e}")
                    return {"simulation": True}
            else:
                # No sample found - use default config and write it to file
                print("[WARNING] Config file not found and sample config unavailable. Using default config.")
                try:
                    # Write default config to current directory
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as f:
                        json.dump(_DEFAULT_CONFIG, f, indent=2)
                    return _DEFAULT_CONFIG
                except Exception as e:
                    print(f"[WARNING] Failed to write default config: {e}. Using simulation mode.")
                    return {"simulation": True}
        
        # Load config
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load config file: {e}")
            return {"simulation": True}

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
                "hand_start_percent": self.hand_start_percent,
                "threshold_percent": self.threshold_percent,
                "countdown_seconds": self.countdown_seconds,
                "target_flexion_percent": self.target_flexion_percent,
                "target_extension_percent": self.target_extension_percent,
                "grip_step_percent": self.grip_step_percent,
                "command_rate_hz": self.command_rate_hz,
                "activation_hysteresis_percent": self.activation_hysteresis_percent,
                "deactivation_hysteresis_percent": self.deactivation_hysteresis_percent,
            }
            settings_scene = SettingsScene(
                self.screen_rect,
                self.ui_scale,
                self.ble,
                on_close=lambda: self.scenes.set_scene(self.game_scene),
                set_emg_max_flexor=self._set_emg_max_flexor,
                set_emg_max_extensor=self._set_emg_max_extensor,
                set_hand_start_percent=self._set_hand_start_percent,
                set_threshold_percent=self._set_threshold_percent,
                set_countdown_seconds=self._set_countdown_seconds,
                set_target_flexion_percent=self._set_target_flexion_percent,
                set_target_extension_percent=self._set_target_extension_percent,
                set_grip_step_percent=self._set_grip_step_percent,
                set_command_rate_hz=self._set_command_rate_hz,
                set_activation_hysteresis_percent=self._set_activation_hysteresis_percent,
                set_deactivation_hysteresis_percent=self._set_deactivation_hysteresis_percent,
                on_bind_flexor_emg=self._bind_flexor_emg,
                on_bind_extensor_emg=self._bind_extensor_emg,
                on_bind_exo_hand=self._bind_exo_hand,
                init_values=init,
                allowed_mac_addresses=allowed_mac_addresses,
                get_bound_flexor_emg=lambda: self.bound_flexor_emg,
                get_bound_extensor_emg=lambda: self.bound_extensor_emg,
                get_bound_exo_hand=lambda: self.bound_exo_hand,
            )
            self.scenes.set_scene(settings_scene)

        def reset_game():
            # Reset the current game scene state (stars, countdown, etc.)
            self.game_scene.reset()
            self._reset_round()

        # EMG providers:
        # - In simulation mode: generate a random baseline EMG with optional boosts from F/E keys.
        # - In hardware mode: use processed EMG values coming from the EMG processors.
        def emg_flexor_provider() -> float:
            if self.ble.simulation:
                keys = pygame.key.get_pressed()
                # Small random baseline noise (0..0.1) plus optional "active" boost when key is held
                base = random.uniform(0.0, 0.1)
                if keys[pygame.K_f]:
                    return min(1.0, 0.8 + base)
                return base
            return self._emg_flexor_value

        def emg_extensor_provider() -> float:
            if self.ble.simulation:
                keys = pygame.key.get_pressed()
                base = random.uniform(0.0, 0.1)
                if keys[pygame.K_e]:
                    return min(1.0, 0.8 + base)
                return base
            return self._emg_extensor_value

        # Raw EMG providers:
        # - In simulation mode: generate synthetic raw EMG data based on current EMG level
        # - In hardware mode: use actual raw sample buffers from BLE notifications
        def emg_flexor_raw_provider() -> List[float]:
            if self.ble.simulation:
                # Generate synthetic raw samples based on current EMG level
                emg_level = emg_flexor_provider()
                # Generate ~100 samples (typical packet size) with noise around the current level
                samples = []
                for _ in range(100):
                    # Add realistic noise and convert to raw ADC-like values (0-65535 range)
                    noise = random.uniform(-0.05, 0.05)
                    sample_value = max(0.0, min(1.0, emg_level + noise))
                    # Convert to ADC-like range for realistic chart display
                    adc_value = sample_value * 65535.0
                    samples.append(adc_value)
                return samples
            return self._emg_flexor_raw_samples[:]
        
        def emg_extensor_raw_provider() -> List[float]:
            if self.ble.simulation:
                # Generate synthetic raw samples based on current EMG level
                emg_level = emg_extensor_provider()
                # Generate ~100 samples (typical packet size) with noise around the current level
                samples = []
                for _ in range(100):
                    # Add realistic noise and convert to raw ADC-like values (0-65535 range)
                    noise = random.uniform(-0.05, 0.05)
                    sample_value = max(0.0, min(1.0, emg_level + noise))
                    # Convert to ADC-like range for realistic chart display
                    adc_value = sample_value * 65535.0
                    samples.append(adc_value)
                return samples
            return self._emg_extensor_raw_samples[:]

        self.game_scene = GameScene(
            self.screen_rect,
            self.ui_scale,
            open_settings=open_settings,
            reset_game=reset_game,
            emg_flexor_provider=emg_flexor_provider,
            emg_extensor_provider=emg_extensor_provider,
            send_grip=self._send_grip,
            hand_pos_provider=lambda: self._hand_pos,
            get_hand_start_percent=lambda: self.hand_start_percent,
            get_threshold_percent=lambda: self.threshold_percent,
            get_target_flexion_percent=lambda: self.target_flexion_percent,
            get_target_extension_percent=lambda: self.target_extension_percent,
            get_countdown_seconds=lambda: self.countdown_seconds,
            get_grip_step_percent=lambda: self.grip_step_percent,
            get_command_rate_hz=lambda: self.command_rate_hz,
            get_activation_hysteresis_percent=lambda: self.activation_hysteresis_percent,
            get_deactivation_hysteresis_percent=lambda: self.deactivation_hysteresis_percent,
            game_version=GAME_VERSION,
            emg_flexor_raw_provider=emg_flexor_raw_provider,
            emg_extensor_raw_provider=emg_extensor_raw_provider,
        )
        self.scenes.set_scene(self.game_scene)

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

    def _on_flexor_emg(self, payload: bytes):
        parsed = emgs_client.parse_notification(payload)
        if not parsed:
            return
        if parsed.get("type") == "E" and "emg_samples" in parsed:
            # Get all samples from the packet (typically ~100 samples per packet)
            emg_samples = parsed["emg_samples"]  # List of raw EMG codes
            if emg_samples:
                # Store raw samples for chart (convert to float)
                self._emg_flexor_raw_samples = [float(s) for s in emg_samples]
                # Process all samples: compute RMS on batch, then apply EMA filtering
                self._emg_flexor_value = self.emg_flexor.update_batch(emg_samples)
                self._update_dynamic_mvc_flexor(self.emg_flexor.last_rms())

    def _on_extensor_emg(self, payload: bytes):
        parsed = emgs_client.parse_notification(payload)
        if not parsed:
            return
        if parsed.get("type") == "E" and "emg_samples" in parsed:
            # Get all samples from the packet (typically ~100 samples per packet)
            emg_samples = parsed["emg_samples"]  # List of raw EMG codes
            if emg_samples:
                # Store raw samples for chart (convert to float)
                self._emg_extensor_raw_samples = [float(s) for s in emg_samples]
                # Process all samples: compute RMS on batch, then apply EMA filtering
                self._emg_extensor_value = self.emg_extensor.update_batch(emg_samples)
                self._update_dynamic_mvc_extensor(self.emg_extensor.last_rms())

    def _on_exo_hand_status(self, status: dict):
        positions = status.get("finger_positions")
        if positions:
            avg = sum(positions) / (len(positions) or 1)
            self._hand_pos = max(0.0, min(1.0, avg / 100.0))

    def _send_grip(self, grip: float):
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

    def _set_hand_start_percent(self, v: float):
        self.hand_start_percent = float(v)
        start_pos = max(0.0, min(1.0, self.hand_start_percent / 100.0))
        self._hand_target = start_pos

    def _set_threshold_percent(self, v: float):
        self.threshold_percent = float(v)

    def _set_countdown_seconds(self, v: float):
        self.countdown_seconds = float(v)

    def _set_target_flexion_percent(self, v: float):
        self.target_flexion_percent = float(v)

    def _set_target_extension_percent(self, v: float):
        self.target_extension_percent = float(v)

    def _set_grip_step_percent(self, v: float):
        self.grip_step_percent = float(v)

    def _set_command_rate_hz(self, v: float):
        self.command_rate_hz = float(v)

    def _set_activation_hysteresis_percent(self, v: float):
        self.activation_hysteresis_percent = float(v)

    def _set_deactivation_hysteresis_percent(self, v: float):
        self.deactivation_hysteresis_percent = float(v)

    def _update_dynamic_mvc_flexor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_flexor,
            set_max=self._set_emg_max_flexor_runtime,
        )

    def _update_dynamic_mvc_extensor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_extensor,
            set_max=self._set_emg_max_extensor_runtime,
        )

    def _update_dynamic_mvc(self, rms: float, current_max: float, set_max):
        # Online MVC update: only expand range upward when a stronger contraction is observed.
        if rms <= current_max:
            return
        growth_alpha = 0.2
        new_max = current_max + (rms - current_max) * growth_alpha
        set_max(new_max)

    def _reset_round(self):
        # Reset EMG processing state and restore runtime max ranges from Settings.
        self.emg_flexor.reset()
        self.emg_extensor.reset()
        self._set_emg_max_flexor_runtime(self.settings_emg_max_range_flexor)
        self._set_emg_max_extensor_runtime(self.settings_emg_max_range_extensor)

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

