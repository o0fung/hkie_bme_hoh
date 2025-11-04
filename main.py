import json
import os
from typing import Optional

import pygame

from src.game.scene_manager import SceneManager
from src.game.scenes import GameScene, SettingsScene
from src.io.input_manager import EMGProcessor, EMGConfig
from src.ble.ble_manager import BLEManager, BLEDeviceInfo

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "devices.json")
SAMPLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "devices.sample.json")


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("HKIE BME Grip & Catch")
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
        cfg = self._load_config()
        simulation = bool(cfg.get("simulation", True))
        self.ble = BLEManager(simulation=simulation)
        settings = cfg.get("settings", {})
        self.emg_max_range = float(settings.get("emg_max_range", 1024))
        self.threshold_percent = float(settings.get("threshold_percent", 60))
        self.countdown_seconds = float(settings.get("countdown_seconds", 3))
        self.target_close_percent = float(settings.get("target_close_percent", 90))

        # EMG processors left/right
        self.emg_left = EMGProcessor(EMGConfig(max_range=self.emg_max_range))
        self.emg_right = EMGProcessor(EMGConfig(max_range=self.emg_max_range))
        self._emg_left_value = 0.0
        self._emg_right_value = 0.0

        # Device bindings
        self.bound_left_emg = None
        self.bound_right_emg = None
        self.bound_left_exo = None
        self.bound_right_exo = None
        # Characteristic UUIDs
        self.left_emg_write_uuid = cfg.get("emg_left", {}).get("write_characteristic_uuid")
        self.right_emg_write_uuid = cfg.get("emg_right", {}).get("write_characteristic_uuid")
        self.left_emg_notify_uuid = cfg.get("emg_left", {}).get("notify_characteristic_uuid")
        self.right_emg_notify_uuid = cfg.get("emg_right", {}).get("notify_characteristic_uuid")
        self.left_exo_write_uuid = cfg.get("exo_left", {}).get("write_characteristic_uuid")
        self.right_exo_write_uuid = cfg.get("exo_right", {}).get("write_characteristic_uuid")
        self.left_exo_feedback_uuid = cfg.get("exo_left", {}).get("feedback_characteristic_uuid")
        self.right_exo_feedback_uuid = cfg.get("exo_right", {}).get("feedback_characteristic_uuid")

        # Exo positions (0..1), simulate if needed
        self._left_pos = 0.0
        self._right_pos = 0.0
        self._left_target = 0.0
        self._right_target = 0.0

        # Scene management
        self.scenes = SceneManager()
        self._build_scenes()

    def _load_config(self) -> dict:
        path = CONFIG_PATH
        if not os.path.exists(path):
            # copy sample for convenience
            try:
                with open(SAMPLE_CONFIG_PATH, "r") as f:
                    sample = json.load(f)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    json.dump(sample, f, indent=2)
            except Exception:
                return {"simulation": True}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return {"simulation": True}

    def _build_scenes(self):
        def open_settings():
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
            )
            self.scenes.set_scene(settings_scene)

        def emg_left_provider() -> float:
            if self.ble.simulation:
                # Left click simulates left, right click simulates right; here map left button
                keys = pygame.key.get_pressed()
                return 1.0 if keys[pygame.K_l] else 0.0
                # pressed = pygame.mouse.get_pressed()
                # return 1.0 if pressed[0] else 0.0
            return self._emg_left_value

        def emg_right_provider() -> float:
            if self.ble.simulation:
                keys = pygame.key.get_pressed()
                return 1.0 if keys[pygame.K_r] else 0.0
                # pressed = pygame.mouse.get_pressed()
                # return 1.0 if pressed[2] else 0.0
            return self._emg_right_value

        def send_left_grip(grip: float):
            self._left_target = max(0.0, min(1.0, grip))
            if self.bound_left_exo and self.left_exo_write_uuid:
                level = max(0, min(100, int(grip * 100)))
                self.ble.write_characteristic(self.bound_left_exo.address, self.left_exo_write_uuid, bytes([level]), response=False)

        def send_right_grip(grip: float):
            self._right_target = max(0.0, min(1.0, grip))
            if self.bound_right_exo and self.right_exo_write_uuid:
                level = max(0, min(100, int(grip * 100)))
                self.ble.write_characteristic(self.bound_right_exo.address, self.right_exo_write_uuid, bytes([level]), response=False)

        def left_pos_provider() -> float:
            return self._left_pos

        def right_pos_provider() -> float:
            return self._right_pos

        def get_threshold_percent() -> float:
            return self.threshold_percent

        def get_target_close_percent() -> float:
            return self.target_close_percent

        def get_countdown_seconds() -> float:
            return self.countdown_seconds

        self.game_scene = GameScene(
            self.screen_rect,
            open_settings,
            reset_game=self._reset_round,
            emg_left_provider=emg_left_provider,
            emg_right_provider=emg_right_provider,
            send_left_grip=send_left_grip,
            send_right_grip=send_right_grip,
            left_pos_provider=left_pos_provider,
            right_pos_provider=right_pos_provider,
            get_threshold_percent=get_threshold_percent,
            get_target_close_percent=get_target_close_percent,
            get_countdown_seconds=get_countdown_seconds,
        )
        self.scenes.set_scene(self.game_scene)

    def _bind_left_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_left_emg = dev
        if dev and self.left_emg_notify_uuid:
            self.ble.start_notifications(dev.address, self.left_emg_notify_uuid, self._on_left_emg)

    def _bind_right_emg(self, dev: Optional[BLEDeviceInfo]):
        self.bound_right_emg = dev
        if dev and self.right_emg_notify_uuid:
            self.ble.start_notifications(dev.address, self.right_emg_notify_uuid, self._on_right_emg)

    def _bind_left_exo(self, dev: Optional[BLEDeviceInfo]):
        self.bound_left_exo = dev
        # Subscribe to feedback if available
        if dev and self.left_exo_feedback_uuid:
            self.ble.start_notifications(dev.address, self.left_exo_feedback_uuid, self._on_left_exo_feedback)

    def _bind_right_exo(self, dev: Optional[BLEDeviceInfo]):
        self.bound_right_exo = dev
        if dev and self.right_exo_feedback_uuid:
            self.ble.start_notifications(dev.address, self.right_exo_feedback_uuid, self._on_right_exo_feedback)

    def _on_left_emg(self, payload: bytes):
        if len(payload) >= 2:
            raw = int.from_bytes(payload[:2], byteorder="little", signed=False)
            self._emg_left_value = self.emg_left.update(raw)

    def _on_right_emg(self, payload: bytes):
        if len(payload) >= 2:
            raw = int.from_bytes(payload[:2], byteorder="little", signed=False)
            self._emg_right_value = self.emg_right.update(raw)

    def _on_left_exo_feedback(self, payload: bytes):
        # Expect a single byte or 2-byte value mapping to 0..100% position; adapt once spec is known
        if payload:
            val = payload[0]
            self._left_pos = max(0.0, min(1.0, val / 100.0))

    def _on_right_exo_feedback(self, payload: bytes):
        if payload:
            val = payload[0]
            self._right_pos = max(0.0, min(1.0, val / 100.0))

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
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                self.scenes.handle_event(event)

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
            self.ble.shutdown()
        finally:
            pygame.quit()


if __name__ == "__main__":
    App().run()
