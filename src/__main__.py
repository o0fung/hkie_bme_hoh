"""
Entry point for running the HKIE BME HOH game.
This module allows the package to be run as: python -m src
"""
import sys
import os
import json
from typing import List, Optional

import pygame

from src.game.scene_manager import SceneManager
from src.game.scenes import GameScene, SettingsScene
from src.io.input_manager import EMGProcessor, EMGConfig
from src.ble.ble_manager import BLEManager, BLEDeviceInfo
from src.ble import emgs_client
from src.ble.exo_client import ExoClient

# Config paths - prefer current working directory for user-writable config
# Fall back to package location for sample config when installed
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
CONFIG_PATH = os.path.join(os.getcwd(), "config", "devices.json")  # User config in current directory
SAMPLE_CONFIG_PATH = os.path.join(_CONFIG_DIR, "devices.sample.json")  # Sample from package (may not exist when installed)

GAME_VERSION = "v1.0.0"

# Default config as fallback if sample file cannot be found
_DEFAULT_CONFIG = {
    "simulation": False,
    "settings": {
        "emg_max_range": 65535,
        "threshold_percent": 60,
        "countdown_seconds": 3,
        "target_close_percent": 90
    },
    "emg_left": {
        "name": "EMGS",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    },
    "emg_right": {
        "name": "EMGS",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    },
    "exo_left": {
        "name": "Exo-Hand Left",
        "mac_address": "",
        "service_uuid": "",
        "write_characteristic_uuid": "",
        "feedback_characteristic_uuid": ""
    },
    "exo_right": {
        "name": "Exo-Hand Right",
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
            if self.bound_left_emg and self.bound_left_emg.address == address:
                self.bound_left_emg = None
            if self.bound_right_emg and self.bound_right_emg.address == address:
                self.bound_right_emg = None
            if self.bound_left_exo and self.bound_left_exo.address == address:
                self.bound_left_exo = None
                self.exo_left_client = None
            if self.bound_right_exo and self.bound_right_exo.address == address:
                self.bound_right_exo = None
                self.exo_right_client = None
        
        self.ble = BLEManager(simulation=simulation, on_disconnect=handle_disconnect)
        settings = self.cfg.get("settings", {})
        self.emg_max_range = float(settings.get("emg_max_range", 65535))
        self.threshold_percent = float(settings.get("threshold_percent", 60))
        self.countdown_seconds = float(settings.get("countdown_seconds", 3))
        self.target_close_percent = float(settings.get("target_close_percent", 90))

        # EMG processors left/right
        self.emg_left = EMGProcessor(EMGConfig(max_range=self.emg_max_range, rms_method="ema", ema_alpha=0.1))
        self.emg_right = EMGProcessor(EMGConfig(max_range=self.emg_max_range, rms_method="ema", ema_alpha=0.1))
        self._emg_left_value = 0.0
        self._emg_right_value = 0.0
        # Raw EMG sample buffers for charts (1000Hz input, display at 10Hz)
        self._emg_left_raw_samples: List[float] = []
        self._emg_right_raw_samples: List[float] = []

        # Device bindings
        self.bound_left_emg = None
        self.bound_right_emg = None
        self.bound_left_exo = None
        self.bound_right_exo = None
        self.exo_left_client: Optional[ExoClient] = None
        self.exo_right_client: Optional[ExoClient] = None
        # Characteristic UUIDs
        self.left_emg_write_uuid = self.cfg.get("emg_left", {}).get("write_characteristic_uuid")
        self.right_emg_write_uuid = self.cfg.get("emg_right", {}).get("write_characteristic_uuid")
        self.left_emg_notify_uuid = self.cfg.get("emg_left", {}).get("notify_characteristic_uuid")
        self.right_emg_notify_uuid = self.cfg.get("emg_right", {}).get("notify_characteristic_uuid")
        self.left_exo_write_uuid = self.cfg.get("exo_left", {}).get("write_characteristic_uuid")
        self.right_exo_write_uuid = self.cfg.get("exo_right", {}).get("write_characteristic_uuid")
        self.left_exo_feedback_uuid = self.cfg.get("exo_left", {}).get("feedback_characteristic_uuid")
        self.right_exo_feedback_uuid = self.cfg.get("exo_right", {}).get("feedback_characteristic_uuid")

        # Exo positions (0..1), simulate if needed
        self._left_pos = 0.0
        self._right_pos = 0.0
        self._left_target = 0.0
        self._right_target = 0.0

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
            for device_key in ["emg_left", "emg_right", "exo_left", "exo_right"]:
                mac = self.cfg.get(device_key, {}).get("mac_address", "")
                if mac and mac.strip():
                    allowed_mac_addresses.add(mac.strip().upper())
            
            init = {
                "emg_max_range": self.emg_max_range,
                "threshold_percent": self.threshold_percent,
                "countdown_seconds": self.countdown_seconds,
                "target_close_percent": self.target_close_percent,
            }
            settings_scene = SettingsScene(
                self.screen_rect,
                self.ble,
                on_close=lambda: self.scenes.set_scene(self.game_scene),
                set_emg_max=self._set_emg_max,
                set_threshold_percent=self._set_threshold_percent,
                set_countdown_seconds=self._set_countdown_seconds,
                set_target_close_percent=self._set_target_close_percent,
                on_bind_left_emg=self._bind_left_emg,
                on_bind_right_emg=self._bind_right_emg,
                on_bind_left_exo=self._bind_left_exo,
                on_bind_right_exo=self._bind_right_exo,
                init_values=init,
                allowed_mac_addresses=allowed_mac_addresses,
                get_bound_left_emg=lambda: self.bound_left_emg,
                get_bound_right_emg=lambda: self.bound_right_emg,
                get_bound_left_exo=lambda: self.bound_left_exo,
                get_bound_right_exo=lambda: self.bound_right_exo,
            )
            self.scenes.set_scene(settings_scene)

        def reset_game():
            self.game_scene.reset()

        self.game_scene = GameScene(
            self.screen_rect,
            open_settings=open_settings,
            reset_game=reset_game,
            emg_left_provider=lambda: self._emg_left_value,
            emg_right_provider=lambda: self._emg_right_value,
            send_left_grip=self._send_left_grip,
            send_right_grip=self._send_right_grip,
            left_pos_provider=lambda: self._left_pos,
            right_pos_provider=lambda: self._right_pos,
            get_threshold_percent=lambda: self.threshold_percent,
            get_target_close_percent=lambda: self.target_close_percent,
            get_countdown_seconds=lambda: self.countdown_seconds,
            game_version=GAME_VERSION,
            emg_left_raw_provider=lambda: self._emg_left_raw_samples[:],
            emg_right_raw_provider=lambda: self._emg_right_raw_samples[:],
        )
        self.scenes.set_scene(self.game_scene)

    def _bind_left_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_left_emg = dev
        if not dev:
            return
        # Start notifications first so we can see any immediate responses
        if self.left_emg_notify_uuid:
            self.ble.start_notifications(dev.address, self.left_emg_notify_uuid, self._on_left_emg)
        # Configure EMGS: set RMS mode and start stream
        if self.left_emg_write_uuid:
            self.ble.write_characteristic(dev.address, self.left_emg_write_uuid, emgs_client.build_set_emg_mode(emgs_client.EMG_MODE_RAW), response=False)
            self.ble.write_characteristic(dev.address, self.left_emg_write_uuid, emgs_client.build_start_stream(), response=False)

    def _bind_right_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_right_emg = dev
        if not dev:
            return
        if self.right_emg_notify_uuid:
            self.ble.start_notifications(dev.address, self.right_emg_notify_uuid, self._on_right_emg)
        if self.right_emg_write_uuid:
            self.ble.write_characteristic(dev.address, self.right_emg_write_uuid, emgs_client.build_set_emg_mode(emgs_client.EMG_MODE_RAW), response=False)
            self.ble.write_characteristic(dev.address, self.right_emg_write_uuid, emgs_client.build_start_stream(), response=False)

    def _bind_left_exo(self, dev: Optional[BLEDeviceInfo]):
        self.bound_left_exo = dev
        if not dev:
            self.exo_left_client = None
            return
        if self.left_exo_write_uuid and self.left_exo_feedback_uuid:
            self.exo_left_client = ExoClient(
                self.ble,
                dev,
                write_uuid=self.left_exo_write_uuid,
                notify_uuid=self.left_exo_feedback_uuid,
                on_status=self._on_left_exo_status,
            )
            self.exo_left_client.subscribe()

    def _bind_right_exo(self, dev: Optional[BLEDeviceInfo]):
        self.bound_right_exo = dev
        if not dev:
            self.exo_right_client = None
            return
        if self.right_exo_write_uuid and self.right_exo_feedback_uuid:
            self.exo_right_client = ExoClient(
                self.ble,
                dev,
                write_uuid=self.right_exo_write_uuid,
                notify_uuid=self.right_exo_feedback_uuid,
                on_status=self._on_right_exo_status,
            )
            self.exo_right_client.subscribe()

    def _on_left_emg(self, payload: bytes):
        parsed = emgs_client.parse_notification(payload)
        if not parsed:
            return
        if parsed.get("type") == "E" and "emg_samples" in parsed:
            # Get all samples from the packet (typically ~100 samples per packet)
            emg_samples = parsed["emg_samples"]  # List of raw EMG codes
            if emg_samples:
                # Store raw samples for chart (convert to float)
                self._emg_left_raw_samples = [float(s) for s in emg_samples]
                # Process all samples: compute RMS on batch, then apply EMA filtering
                self._emg_left_value = self.emg_left.update_batch(emg_samples)

    def _on_right_emg(self, payload: bytes):
        parsed = emgs_client.parse_notification(payload)
        if not parsed:
            return
        if parsed.get("type") == "E" and "emg_samples" in parsed:
            # Get all samples from the packet (typically ~100 samples per packet)
            emg_samples = parsed["emg_samples"]  # List of raw EMG codes
            if emg_samples:
                # Store raw samples for chart (convert to float)
                self._emg_right_raw_samples = [float(s) for s in emg_samples]
                # Process all samples: compute RMS on batch, then apply EMA filtering
                self._emg_right_value = self.emg_right.update_batch(emg_samples)

    def _on_left_exo_status(self, status: dict):
        positions = status.get("finger_positions")
        if positions:
            avg = sum(positions) / (len(positions) or 1)
            self._left_pos = max(0.0, min(1.0, avg / 100.0))

    def _on_right_exo_status(self, status: dict):
        positions = status.get("finger_positions")
        if positions:
            avg = sum(positions) / (len(positions) or 1)
            self._right_pos = max(0.0, min(1.0, avg / 100.0))

    def _send_left_grip(self, grip: float):
        self._left_target = max(0.0, min(1.0, grip))
        if self.exo_left_client:
            level = max(0, min(100, int(grip * 100)))
            self.exo_left_client.move_uniform(level)
        elif self.ble.simulation:
            self._left_target = grip

    def _send_right_grip(self, grip: float):
        self._right_target = max(0.0, min(1.0, grip))
        if self.exo_right_client:
            level = max(0, min(100, int(grip * 100)))
            self.exo_right_client.move_uniform(level)
        elif self.ble.simulation:
            self._right_target = grip

    def _set_emg_max(self, v: float):
        self.emg_max_range = float(v)
        self.emg_left.set_max_range(self.emg_max_range)
        self.emg_right.set_max_range(self.emg_max_range)

    def _set_threshold_percent(self, v: float):
        self.threshold_percent = float(v)

    def _set_countdown_seconds(self, v: float):
        self.countdown_seconds = float(v)

    def _set_target_close_percent(self, v: float):
        self.target_close_percent = float(v)

    def _reset_round(self):
        # Nothing heavy yet; positions are left as-is
        pass

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
                self._left_pos += (self._left_target - self._left_pos) * min(1.0, speed * dt)
                self._right_pos += (self._right_target - self._right_pos) * min(1.0, speed * dt)
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

