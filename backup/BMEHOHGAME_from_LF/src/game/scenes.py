import math
from typing import Callable, List, Optional

import pygame

from src.ui.widgets import Button, Label, Panel, BarGauge, NumericStepper
from src.game.scene_manager import Scene
from src.ble.ble_manager import BLEManager, BLEDeviceInfo


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 100, 100)
GREEN = (80, 200, 120)
YELLOW = (240, 210, 80)
RED = (230, 80, 80)


class GameScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        open_settings: Callable[[], None],
        reset_game: Callable[[], None],
        emg_left_provider: Callable[[], float],
        emg_right_provider: Callable[[], float],
        send_left_grip: Callable[[float], None],
        send_right_grip: Callable[[float], None],
        left_pos_provider: Callable[[], float],
        right_pos_provider: Callable[[], float],
        get_threshold_percent: Callable[[], float],
        get_target_close_percent: Callable[[], float],
        get_countdown_seconds: Callable[[], float],
    ):
        self.screen_rect = screen_rect
        self.open_settings = open_settings
        self.reset_game_cb = reset_game
        self.emg_left_provider = emg_left_provider
        self.emg_right_provider = emg_right_provider
        self.send_left_grip = send_left_grip
        self.send_right_grip = send_right_grip
        self.left_pos_provider = left_pos_provider
        self.right_pos_provider = right_pos_provider
        self.get_threshold_percent = get_threshold_percent
        self.get_target_close_percent = get_target_close_percent
        self.get_countdown_seconds = get_countdown_seconds

        self.font_big = pygame.font.SysFont("Arial", 48)
        self.font_small = pygame.font.SysFont("Arial", 24)

        # Top-left controls
        self.settings_button = Button(pygame.Rect(20, 20, 140, 44), "Settings", self.font_small, on_click=self.open_settings)
        self.reset_button = Button(pygame.Rect(170, 20, 120, 44), "Reset", self.font_small, on_click=self._reset)

        # Bars
        bar_w = 60
        bar_h = int(self.screen_rect.h * 0.6)
        top = (self.screen_rect.h - bar_h) // 2
        self.left_bar = BarGauge(pygame.Rect(120, top, bar_w, bar_h), max_color=(90, 180, 255))
        self.right_bar = BarGauge(pygame.Rect(self.screen_rect.w - 120 - bar_w, top, bar_w, bar_h), max_color=(255, 140, 140))

        # Stars
        self.stars_collected = 0
        self.max_stars = 3

        # Countdown
        self.countdown_timer = 0.0
        # Require the player to relax (open both hands) after earning a star
        self.require_open_reset = False

    def _reset(self):
        self.stars_collected = 0
        self.countdown_timer = 0.0
        self.require_open_reset = False
        self.reset_game_cb()

    def handle_event(self, event: pygame.event.Event):
        self.settings_button.handle_event(event)
        self.reset_button.handle_event(event)

    def update(self, dt: float):
        # Update bars
        emg_l = self.emg_left_provider()
        emg_r = self.emg_right_provider()
        thr = self.get_threshold_percent() / 100.0
        self.left_bar.set_value(emg_l)
        self.right_bar.set_value(emg_r)
        self.left_bar.set_threshold(thr)
        self.right_bar.set_threshold(thr)

        # Control exo target based on threshold
        target_l = 1.0 if emg_l >= thr else 0.0
        target_r = 1.0 if emg_r >= thr else 0.0
        self.send_left_grip(target_l)
        self.send_right_grip(target_r)

        # Check both hands at target close
        pos_l = self.left_pos_provider()
        pos_r = self.right_pos_provider()
        target_close = self.get_target_close_percent() / 100.0
        both_closed = pos_l >= target_close and pos_r >= target_close

        # Enforce relax-to-continue rule after a star is earned
        if self.require_open_reset:
            # Wait until BOTH EMG levels drop below threshold before allowing next countdown
            if emg_l < thr and emg_r < thr:
                self.require_open_reset = False
            # No countdown while waiting to relax
            self.countdown_timer = 0.0
            return

        if both_closed and self.stars_collected < self.max_stars:
            if self.countdown_timer <= 0.0:
                self.countdown_timer = self.get_countdown_seconds()
            else:
                self.countdown_timer = max(0.0, self.countdown_timer - dt)
                if self.countdown_timer == 0.0:
                    # Award star and require relax before the next attempt
                    self.stars_collected = min(self.max_stars, self.stars_collected + 1)
                    self.require_open_reset = True
        else:
            # Lose progress of countdown if either hand opens or already won
            self.countdown_timer = 0.0

    def _draw_stars(self, surface: pygame.Surface):
        cx = self.screen_rect.w - 200
        cy = 40
        for i in range(self.max_stars):
            color = YELLOW if i < self.stars_collected else GRAY
            points = []
            # Simple 5-point star
            r_outer = 18
            r_inner = 8
            ox = cx + i * 40
            oy = cy
            for k in range(10):
                ang = math.pi/2 + k * math.pi/5
                r = r_outer if k % 2 == 0 else r_inner
                x = int(ox + r * math.cos(ang))
                y = int(oy - r * math.sin(ang))
                points.append((x, y))
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (30, 30, 30), points, width=2)

    def draw(self, surface: pygame.Surface):
        surface.fill((10, 20, 30))
        # Title
        title = self.font_big.render("Dual Grip Hold", True, WHITE)
        surface.blit(title, (self.screen_rect.centerx - title.get_width()//2, 20))

        # Buttons
        self.settings_button.draw(surface)
        self.reset_button.draw(surface)

        # Stars
        self._draw_stars(surface)

        # Bars
        self.left_bar.draw(surface)
        self.right_bar.draw(surface)

        # Center instructions and countdown
        msg = "Hold BOTH hands closed!"
        msg_img = self.font_small.render(msg, True, WHITE)
        surface.blit(msg_img, (self.screen_rect.centerx - msg_img.get_width()//2, self.screen_rect.centery - 80))

        if self.countdown_timer > 0.0:
            cd = int(self.countdown_timer) + (1 if self.countdown_timer - int(self.countdown_timer) > 0 else 0)
            cd_img = self.font_big.render(str(cd), True, YELLOW)
            surface.blit(cd_img, (self.screen_rect.centerx - cd_img.get_width()//2, self.screen_rect.centery - cd_img.get_height()//2))

        if self.stars_collected >= self.max_stars:
            win = self.font_big.render("You Win!", True, GREEN)
            surface.blit(win, (self.screen_rect.centerx - win.get_width()//2, self.screen_rect.centery + 60))
        elif self.require_open_reset:
            hint = self.font_small.render("Relax and open both hands to start next star", True, WHITE)
            surface.blit(hint, (self.screen_rect.centerx - hint.get_width()//2, self.screen_rect.centery + 20))


class SettingsScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ble: BLEManager,
        on_close: Callable[[], None],
        set_emg_max: Callable[[float], None],
        set_threshold_percent: Callable[[float], None],
        set_countdown_seconds: Callable[[float], None],
        set_target_close_percent: Callable[[float], None],
        on_bind_left_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_right_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_left_exo: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_right_exo: Callable[[Optional[BLEDeviceInfo]], None],
        init_values: dict,
    ):
        self.screen_rect = screen_rect
        self.ble = ble
        self.on_close = on_close
        self.font_title = pygame.font.SysFont("Arial", 36)
        self.font = pygame.font.SysFont("Arial", 24)

        self.panel = Panel(pygame.Rect(80, 80, screen_rect.w - 160, screen_rect.h - 160), bg=(0, 0, 0), alpha=210)
        self.close_btn = Button(pygame.Rect(screen_rect.w - 80 - 140, 100, 120, 40), "Close", self.font, on_click=on_close)
        self.scan_btn = Button(pygame.Rect(120, 150, 180, 40), "Scan BLE", self.font, on_click=self._scan)
        self.sim_toggle = Button(pygame.Rect(120, 200, 180, 40), f"Simulation: {'ON' if ble.simulation else 'OFF'}", self.font, on_click=self._toggle_sim)

        self.devices: List[BLEDeviceInfo] = []
        self._device_buttons: List[tuple[Button, str, BLEDeviceInfo]] = []  # button, role, dev

        # Steppers
        x0, y0 = 120, 260
        self.step_emg_max = NumericStepper("EMG Max Range", (x0, y0), self.font, init_values.get("emg_max_range", 1024), 50, 100, 5000, fmt="{:.0f}", on_change=set_emg_max)
        self.step_threshold = NumericStepper("Threshold %", (x0, y0+50), self.font, init_values.get("threshold_percent", 60), 5, 5, 100, fmt="{:.0f}%", on_change=set_threshold_percent)
        self.step_countdown = NumericStepper("Countdown s", (x0, y0+100), self.font, init_values.get("countdown_seconds", 3), 1, 1, 10, fmt="{:.0f}", on_change=set_countdown_seconds)
        self.step_target_close = NumericStepper("Target Close %", (x0, y0+150), self.font, init_values.get("target_close_percent", 90), 5, 50, 100, fmt="{:.0f}%", on_change=set_target_close_percent)

        self.on_bind_left_emg = on_bind_left_emg
        self.on_bind_right_emg = on_bind_right_emg
        self.on_bind_left_exo = on_bind_left_exo
        self.on_bind_right_exo = on_bind_right_exo

    def _toggle_sim(self):
        self.ble.simulation = not self.ble.simulation
        self.sim_toggle.text = f"Simulation: {'ON' if self.ble.simulation else 'OFF'}"

    def _scan(self):
        self.devices = self.ble.scan(timeout=4.0)
        # Build four bind buttons per device row
        self._device_buttons = []
        x, y = 120, 450
        for d in self.devices:
            label_btn = Button(pygame.Rect(x, y, 320, 36), f"{d.name} [{d.address}]", self.font, on_click=lambda: None)
            self._device_buttons.append((label_btn, "label", d))
            roles = [
                ("Bind EMG L", self.on_bind_left_emg),
                ("Bind EMG R", self.on_bind_right_emg),
                ("Bind Exo L", self.on_bind_left_exo),
                ("Bind Exo R", self.on_bind_right_exo),
            ]
            rx = x + 340
            for text, fn in roles:
                def make_click(dev=d, f=fn):
                    return lambda: (self.ble.connect(dev.address) and f(dev))
                b = Button(pygame.Rect(rx, y, 120, 36), text, self.font, on_click=make_click())
                self._device_buttons.append((b, text, d))
                rx += 130
            y += 46

    def handle_event(self, event: pygame.event.Event):
        self.close_btn.handle_event(event)
        self.scan_btn.handle_event(event)
        self.sim_toggle.handle_event(event)
        self.step_emg_max.handle_event(event)
        self.step_threshold.handle_event(event)
        self.step_countdown.handle_event(event)
        self.step_target_close.handle_event(event)
        for b, _, _ in self._device_buttons:
            b.handle_event(event)

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        self.panel.draw(surface)
        title = self.font_title.render("Settings", True, WHITE)
        surface.blit(title, (100, 100))
        self.close_btn.draw(surface)
        self.scan_btn.draw(surface)
        self.sim_toggle.draw(surface)

        self.step_emg_max.draw(surface)
        self.step_threshold.draw(surface)
        self.step_countdown.draw(surface)
        self.step_target_close.draw(surface)

        hint = self.font.render("Scan and bind devices; adjust EMG range/threshold and countdown.", True, WHITE)
        surface.blit(hint, (120, 410))

        for b, _, _ in self._device_buttons:
            b.draw(surface)
