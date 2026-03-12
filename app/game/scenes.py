import math
import threading
import time
from typing import Callable, List, Optional, Set

import pygame

from ..ui.widgets import Button, Label, Panel, BarGauge, NumericStepper, CircularGauge, EMGChart
from .scene_manager import Scene
from ..ble.ble_manager import BLEManager, BLEDeviceInfo


WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
GREEN = (80, 200, 120)
YELLOW = (240, 210, 80)
RED = (230, 80, 80)
GAME_BG = (10, 20, 30)


class GameScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ui_scale: float,
        open_settings: Callable[[], None],
        reset_game: Callable[[], None],
        emg_flexor_provider: Callable[[], float],
        emg_extensor_provider: Callable[[], float],
        send_grip: Callable[[float], None],
        hand_pos_provider: Callable[[], float],
        get_hand_start_percent: Callable[[], float],
        get_threshold_percent: Callable[[], float],
        get_target_flexion_percent: Callable[[], float],
        get_target_extension_percent: Callable[[], float],
        get_countdown_seconds: Callable[[], float],
        get_grip_step_percent: Callable[[], float],
        get_command_rate_hz: Callable[[], float],
        get_activation_hysteresis_percent: Callable[[], float],
        get_deactivation_hysteresis_percent: Callable[[], float],
        game_version: str = "0.0.0",
        emg_flexor_raw_provider: Optional[Callable[[], list[float]]] = None,
        emg_extensor_raw_provider: Optional[Callable[[], list[float]]] = None,
    ):
        self.screen_rect = screen_rect
        self.ui_scale = ui_scale
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.open_settings = open_settings
        self.reset_game_cb = reset_game
        self.emg_flexor_provider = emg_flexor_provider
        self.emg_extensor_provider = emg_extensor_provider
        self.send_grip = send_grip
        self.hand_pos_provider = hand_pos_provider
        self.get_hand_start_percent = get_hand_start_percent
        self.get_threshold_percent = get_threshold_percent
        self.get_target_flexion_percent = get_target_flexion_percent
        self.get_target_extension_percent = get_target_extension_percent
        self.get_countdown_seconds = get_countdown_seconds
        self.get_grip_step_percent = get_grip_step_percent
        self.get_command_rate_hz = get_command_rate_hz
        self.get_activation_hysteresis_percent = get_activation_hysteresis_percent
        self.get_deactivation_hysteresis_percent = get_deactivation_hysteresis_percent
        self.game_version = game_version

        self.font_big = pygame.font.SysFont("Arial", s(80))
        self.font_small = pygame.font.SysFont("Arial", s(40))
        self.font_tiny = pygame.font.SysFont("Arial", s(24))

        self.stars_collected = 0
        self.max_stars = 3

        button_height = s(60)
        self._title_y = s(30)
        button_y = self._title_y + self.font_big.get_height() + s(20)
        button_spacing = s(10)
        available_controls_w = max(s(300), int(self.screen_rect.w * 0.94))
        # Reserve width for dynamic labels so text stays inside button bounds.
        control_labels = ("Settings", "Reset", "Stop", "Mirror: OFF", "Exit")
        preferred_widths = [max(s(120), self.font_small.size(text)[0] + s(40)) for text in control_labels]
        # Make Start/Stop control visually bigger than neighboring buttons.
        preferred_widths[2] += s(40)
        total_preferred = sum(preferred_widths) + button_spacing * (len(preferred_widths) - 1)
        if total_preferred > available_controls_w:
            button_spacing = max(s(4), int(self.screen_rect.w * 0.004))
            min_widths = [max(s(88), self.font_small.size(text)[0] + s(24)) for text in control_labels]
            min_widths[2] += s(20)
            min_total = sum(min_widths) + button_spacing * (len(min_widths) - 1)
            if min_total <= available_controls_w:
                widths_budget = available_controls_w - button_spacing * (len(preferred_widths) - 1)
                pref_sum = max(1, sum(preferred_widths))
                scaled = [max(min_w, int(widths_budget * (w / pref_sum))) for w, min_w in zip(preferred_widths, min_widths)]
                while sum(scaled) > widths_budget:
                    i = max(range(len(scaled)), key=lambda idx: scaled[idx] - min_widths[idx])
                    if scaled[i] <= min_widths[i]:
                        break
                    scaled[i] -= 1
                while sum(scaled) < widths_budget:
                    i = min(range(len(scaled)), key=lambda idx: scaled[idx] - preferred_widths[idx])
                    scaled[i] += 1
                preferred_widths = scaled
            else:
                equal_w = max(s(78), (available_controls_w - button_spacing * (len(preferred_widths) - 1)) // len(preferred_widths))
                preferred_widths = [equal_w] * len(preferred_widths)
        controls_total_w = sum(preferred_widths) + button_spacing * (len(preferred_widths) - 1)
        button_x = (self.screen_rect.w - controls_total_w) // 2

        self.settings_button = Button(
            pygame.Rect(button_x, button_y, preferred_widths[0], button_height),
            "Settings",
            self.font_small,
            on_click=self.open_settings,
        )
        button_x += preferred_widths[0] + button_spacing
        self.reset_button = Button(
            pygame.Rect(button_x, button_y, preferred_widths[1], button_height),
            "Reset",
            self.font_small,
            on_click=self._reset,
        )
        button_x += preferred_widths[1] + button_spacing
        self.is_motor_output_enabled = False
        self.start_pause_button = Button(
            pygame.Rect(button_x, button_y - s(6), preferred_widths[2], button_height + s(12)),
            "Start",
            self.font_small,
            on_click=self._toggle_run_pause,
        )
        button_x += preferred_widths[2] + button_spacing
        self.mirror_button = Button(
            pygame.Rect(button_x, button_y, preferred_widths[3], button_height),
            "Mirror: OFF",
            self.font_small,
            on_click=self._toggle_mirror_layout,
        )
        button_x += preferred_widths[3] + button_spacing
        self.exit_button = Button(
            pygame.Rect(button_x, button_y, preferred_widths[4], button_height),
            "Exit",
            self.font_small,
            on_click=self._exit,
        )
        self._update_start_stop_button_style()

        bar_w = s(80)
        bar_h = int(self.screen_rect.h * 0.6)
        top = (self.screen_rect.h - bar_h) // 2
        side_margin = s(140)
        self._bar_w = bar_w
        self._bar_h = bar_h
        self._bar_top = top
        self._side_margin = side_margin
        self.flexor_bar = BarGauge(pygame.Rect(side_margin, top, bar_w, bar_h), max_color=(90, 180, 255))
        self.extensor_bar = BarGauge(
            pygame.Rect(self.screen_rect.w - side_margin - bar_w, top, bar_w, bar_h),
            max_color=(255, 140, 140),
        )

        # Make the arc gauge larger while preserving a true 1:1 shape.
        gauge_radius = s(240)
        min_clear_y = button_y + button_height + s(30) + gauge_radius
        gauge_y = max(top + s(200), min_clear_y)
        self.hand_gauge = CircularGauge(
            center=(self.screen_rect.centerx, gauge_y),
            radius=gauge_radius,
            value_color=(255, 140, 140),
            target_color=(250, 230, 90),
            line_width=s(8),
        )

        chart_height = s(450)
        chart_width = bar_w + s(500)
        chart_y = top + bar_h - chart_height - s(10)
        self._chart_height = chart_height
        self._chart_width = chart_width
        self._chart_y = chart_y
        self.flexor_chart = EMGChart(
            pygame.Rect(side_margin + s(100), chart_y + s(100), chart_width, chart_height),
            max_samples=500,
            line_color=(90, 180, 255),
            bg_color=GAME_BG,
            reverse_direction=True,
        )
        self.extensor_chart = EMGChart(
            pygame.Rect(self.screen_rect.w - side_margin - chart_width - s(100), chart_y + s(100), chart_width, chart_height),
            max_samples=500,
            line_color=(255, 140, 140),
            bg_color=GAME_BG,
            reverse_direction=False,
        )

        label_y = top + bar_h + s(20)
        self._label_y = label_y
        flexor_label_x = side_margin + bar_w // 2 - self.font_small.size("Flexor EMG")[0] // 2
        extensor_label_x = self.screen_rect.w - side_margin - bar_w // 2 - self.font_small.size("Extensor EMG")[0] // 2
        self.flexor_label = Label("Flexor EMG", (flexor_label_x, label_y), self.font_small, color=WHITE)
        self.extensor_label = Label("Extensor EMG", (extensor_label_x, label_y), self.font_small, color=WHITE)

        self.emg_flexor_raw_provider = emg_flexor_raw_provider or (lambda: [])
        self.emg_extensor_raw_provider = emg_extensor_raw_provider or (lambda: [])

        self.countdown_timer = 0.0
        self._cycle_phase = "flexion"  # "flexion" -> "extension" per star cycle.
        # Grip command stabilization settings.
        self.grip_step = max(0.01, min(1.0, self.get_grip_step_percent() / 100.0))
        command_rate_hz = max(1.0, self.get_command_rate_hz())
        self.command_update_interval = 1.0 / command_rate_hz
        self.activation_hysteresis = max(0.0, min(0.5, self.get_activation_hysteresis_percent() / 100.0))
        self.deactivation_hysteresis = max(0.0, min(0.5, self.get_deactivation_hysteresis_percent() / 100.0))
        self._active_muscle: Optional[str] = None  # "flexor" | "extensor" | None
        self._grip_target_hold = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
        self._last_command_time = 0.0
        self._show_great_job = False
        self._great_job_muscle: Optional[str] = None
        self._is_mirrored = False
        self._apply_side_layout()

    def _apply_side_layout(self):
        bar_w = self._bar_w
        top = self._bar_top
        side_margin = self._side_margin
        chart_width = self._chart_width
        chart_y = self._chart_y
        chart_top = chart_y + int(round(100 * self.ui_scale))
        chart_offset = int(round(100 * self.ui_scale))

        left_bar_x = side_margin
        right_bar_x = self.screen_rect.w - side_margin - bar_w
        left_chart_x = side_margin + chart_offset
        right_chart_x = self.screen_rect.w - side_margin - chart_width - chart_offset

        if self._is_mirrored:
            # Mirror layout: extensor on left, flexor on right.
            self.extensor_bar.rect.x = left_bar_x
            self.extensor_bar.rect.y = top
            self.flexor_bar.rect.x = right_bar_x
            self.flexor_bar.rect.y = top
            self.extensor_chart.rect.x = left_chart_x
            self.extensor_chart.rect.y = chart_top
            self.flexor_chart.rect.x = right_chart_x
            self.flexor_chart.rect.y = chart_top
            self.extensor_chart.reverse_direction = True
            self.flexor_chart.reverse_direction = False
        else:
            # Default layout: flexor on left, extensor on right.
            self.flexor_bar.rect.x = left_bar_x
            self.flexor_bar.rect.y = top
            self.extensor_bar.rect.x = right_bar_x
            self.extensor_bar.rect.y = top
            self.flexor_chart.rect.x = left_chart_x
            self.flexor_chart.rect.y = chart_top
            self.extensor_chart.rect.x = right_chart_x
            self.extensor_chart.rect.y = chart_top
            self.flexor_chart.reverse_direction = True
            self.extensor_chart.reverse_direction = False

        flexor_label_x = self.flexor_bar.rect.centerx - self.font_small.size("Flexor EMG")[0] // 2
        extensor_label_x = self.extensor_bar.rect.centerx - self.font_small.size("Extensor EMG")[0] // 2
        self.flexor_label.pos = (flexor_label_x, self._label_y)
        self.extensor_label.pos = (extensor_label_x, self._label_y)
        self.hand_gauge.set_mirrored(self._is_mirrored)

    def _toggle_mirror_layout(self):
        self._is_mirrored = not self._is_mirrored
        self.mirror_button.text = "Mirror: ON" if self._is_mirrored else "Mirror: OFF"
        self._apply_side_layout()

    def _update_start_stop_button_style(self):
        if self.is_motor_output_enabled:
            self.start_pause_button.text = "Stop"
            self.start_pause_button.bg = (150, 50, 50)
            self.start_pause_button.hover_bg = (185, 70, 70)
            self.start_pause_button.fg = WHITE
        else:
            self.start_pause_button.text = "Start"
            self.start_pause_button.bg = (40, 130, 40)
            self.start_pause_button.hover_bg = (60, 170, 60)
            self.start_pause_button.fg = WHITE

    def reset(self):
        self.stars_collected = 0
        self.countdown_timer = 0.0
        self._cycle_phase = "flexion"
        self.flexor_chart.samples = []
        self.extensor_chart.samples = []
        self.is_motor_output_enabled = False
        self._update_start_stop_button_style()
        self._active_muscle = None
        # Reset should return the hand to fully open (0% flexion).
        self._grip_target_hold = 0.0
        self._last_command_time = 0.0
        self._show_great_job = False
        self._great_job_muscle = None

    def _snap_grip_target(self, grip_target: float) -> float:
        step = max(0.01, self.grip_step)
        return max(0.0, min(1.0, round(grip_target / step) * step))

    def _choose_active_muscle(self, emg_flexor: float, emg_extensor: float, thr: float) -> Optional[str]:
        deactivate_thr = max(0.0, thr - self.deactivation_hysteresis)
        activate_thr = min(1.0, thr + self.activation_hysteresis)
        # Allow switching away from a latched muscle when the opposite side is
        # clearly dominant, even if the latched side is still in its
        # deactivation hysteresis window.
        dominance_margin = max(self.activation_hysteresis, self.deactivation_hysteresis)

        if self._active_muscle == "flexor":
            if emg_extensor >= activate_thr and (emg_extensor - emg_flexor) >= dominance_margin:
                return "extensor"
            if emg_flexor >= deactivate_thr:
                return "flexor"

        if self._active_muscle == "extensor":
            if emg_flexor >= activate_thr and (emg_flexor - emg_extensor) >= dominance_margin:
                return "flexor"
            if emg_extensor >= deactivate_thr:
                return "extensor"

        # Select a new active muscle with Flexor priority.
        if emg_flexor >= activate_thr:
            return "flexor"
        if emg_extensor >= activate_thr:
            return "extensor"

        # If both are near threshold, keep Flexor priority.
        if emg_flexor >= thr and emg_extensor >= thr:
            return "flexor"
        return None

    def _reset(self):
        self.reset()
        self.reset_game_cb()

    def _exit(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        pygame.event.pump()

    def _toggle_run_pause(self):
        self.is_motor_output_enabled = not self.is_motor_output_enabled
        self._update_start_stop_button_style()
        if self.is_motor_output_enabled:
            # On Start, re-home to configured start flexion before EMG-driven control.
            start_pos = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
            self._grip_target_hold = self._snap_grip_target(start_pos)
            self.send_grip(self._grip_target_hold)
            self._last_command_time = time.time()
            self._show_great_job = False
            self._great_job_muscle = None

    def _get_status_label_text(self) -> str:
        if not self.is_motor_output_enabled:
            return "Motor output stopped"

        if self._show_great_job:
            return "Great Job !!!"

        if self.countdown_timer > 0.0:
            cd = int(self.countdown_timer) + (1 if self.countdown_timer - int(self.countdown_timer) > 0 else 0)
            return f"Hold On... {cd}"

        if self._active_muscle is None:
            return "Game's On !!!"

        return "Try Harder !!!"

    def _draw_phase_arrow(self, surface: pygame.Surface):
        if not self.is_motor_output_enabled:
            return

        target_muscle = "flexor" if self._cycle_phase == "flexion" else "extensor"
        target_bar = self.flexor_bar if target_muscle == "flexor" else self.extensor_bar
        target_on_left = target_bar.rect.centerx < self.hand_gauge.center[0]

        s = lambda v: max(1, int(round(v * self.ui_scale)))
        cy = self.hand_gauge.center[1]
        tip_clearance = s(10)
        size_scale = 2
        arrow_len = s(140 * size_scale)
        arrow_half_height = s(48 * size_scale)
        shaft_half_height = s(18 * size_scale)

        if target_on_left:
            tip_x = target_bar.rect.right + tip_clearance
            tail_x = tip_x + arrow_len
            points = [
                (tip_x, cy),
                (tip_x + arrow_half_height, cy - arrow_half_height),
                (tip_x + arrow_half_height, cy - shaft_half_height),
                (tail_x, cy - shaft_half_height),
                (tail_x, cy + shaft_half_height),
                (tip_x + arrow_half_height, cy + shaft_half_height),
                (tip_x + arrow_half_height, cy + arrow_half_height),
            ]
        else:
            tip_x = target_bar.rect.left - tip_clearance
            tail_x = tip_x - arrow_len
            points = [
                (tip_x, cy),
                (tip_x - arrow_half_height, cy - arrow_half_height),
                (tip_x - arrow_half_height, cy - shaft_half_height),
                (tail_x, cy - shaft_half_height),
                (tail_x, cy + shaft_half_height),
                (tip_x - arrow_half_height, cy + shaft_half_height),
                (tip_x - arrow_half_height, cy + arrow_half_height),
            ]

        pygame.draw.polygon(surface, YELLOW, points)
        pygame.draw.polygon(surface, (30, 30, 30), points, width=max(2, s(3)))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._toggle_run_pause()
            elif event.key == pygame.K_SPACE:
                self._reset()
            elif event.key == pygame.K_s:
                self.open_settings()
            elif event.key == pygame.K_m:
                self._toggle_mirror_layout()

        self.settings_button.handle_event(event)
        self.reset_button.handle_event(event)
        self.start_pause_button.handle_event(event)
        self.mirror_button.handle_event(event)
        self.exit_button.handle_event(event)

    def update(self, dt: float):
        emg_flexor = self.emg_flexor_provider()
        emg_extensor = self.emg_extensor_provider()
        hand_start = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
        thr = self.get_threshold_percent() / 100.0
        thr = max(0.0, min(0.99, thr))
        self.grip_step = max(0.01, min(1.0, self.get_grip_step_percent() / 100.0))
        command_rate_hz = max(1.0, self.get_command_rate_hz())
        self.command_update_interval = 1.0 / command_rate_hz
        self.activation_hysteresis = max(0.0, min(0.5, self.get_activation_hysteresis_percent() / 100.0))
        self.deactivation_hysteresis = max(0.0, min(0.5, self.get_deactivation_hysteresis_percent() / 100.0))

        self.flexor_bar.set_value(emg_flexor)
        self.extensor_bar.set_value(emg_extensor)
        self.flexor_bar.set_threshold(thr)
        self.extensor_bar.set_threshold(thr)

        current_time = time.time()
        if self.flexor_chart.should_update(current_time):
            flexor_raw = self.emg_flexor_raw_provider()
            if flexor_raw:
                self.flexor_chart.add_samples(flexor_raw)
        if self.extensor_chart.should_update(current_time):
            extensor_raw = self.emg_extensor_raw_provider()
            if extensor_raw:
                self.extensor_chart.add_samples(extensor_raw)

        # Flexor has priority. Add hysteresis to avoid rapid direction toggling near threshold.
        self._active_muscle = self._choose_active_muscle(emg_flexor, emg_extensor, thr)
        if self._show_great_job and self._active_muscle != self._great_job_muscle:
            self._show_great_job = False
            self._great_job_muscle = None
        if self._active_muscle == "flexor":
            flex_norm = (emg_flexor - thr) / max(0.01, 1.0 - thr)
            flex_norm = max(0.0, min(1.0, flex_norm))
            raw_target = hand_start + (1.0 - hand_start) * flex_norm
        elif self._active_muscle == "extensor":
            ext_norm = (emg_extensor - thr) / max(0.01, 1.0 - thr)
            ext_norm = max(0.0, min(1.0, ext_norm))
            raw_target = hand_start * (1.0 - ext_norm)
        else:
            raw_target = self._grip_target_hold

        grip_target = self._snap_grip_target(raw_target)
        self._grip_target_hold = grip_target

        if self.is_motor_output_enabled and (current_time - self._last_command_time >= self.command_update_interval):
            self.send_grip(grip_target)
            self._last_command_time = current_time

        hand_pos = self.hand_pos_provider()
        target_flexion = max(0.0, min(1.0, self.get_target_flexion_percent() / 100.0))
        target_extension = max(0.0, min(1.0, self.get_target_extension_percent() / 100.0))
        self.hand_gauge.set_value(hand_pos)
        self.hand_gauge.set_partition(hand_start)
        self.hand_gauge.set_targets(target_flexion, target_extension)

        if self.stars_collected >= self.max_stars:
            self.countdown_timer = 0.0
            return

        if self._cycle_phase == "flexion":
            phase_target_reached = hand_pos >= target_flexion
        else:
            phase_target_reached = hand_pos <= target_extension

        if phase_target_reached:
            if self.countdown_timer <= 0.0:
                self.countdown_timer = self.get_countdown_seconds()
            else:
                self.countdown_timer = max(0.0, self.countdown_timer - dt)
                if self.countdown_timer == 0.0:
                    self._show_great_job = True
                    self._great_job_muscle = self._active_muscle
                    if self._cycle_phase == "flexion":
                        self._cycle_phase = "extension"
                    else:
                        self.stars_collected = min(self.max_stars, self.stars_collected + 1)
                        self._cycle_phase = "flexion"
        else:
            self.countdown_timer = 0.0

    def _draw_stars(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        r_outer = s(54)
        r_inner = s(24)
        star_width = 2 * r_outer
        star_height = 2 * r_outer

        margin_bottom = s(56)
        star_spacing = s(20)

        total_stars_width = self.max_stars * star_width + (self.max_stars - 1) * star_spacing
        start_x = self.screen_rect.centerx - total_stars_width // 2
        charts_bottom = max(self.flexor_chart.rect.bottom, self.extensor_chart.rect.bottom)
        desired_center_y = charts_bottom + s(20) + star_height // 2
        max_center_y = self.screen_rect.h - margin_bottom - star_height // 2
        start_y = min(desired_center_y, max_center_y)

        for i in range(self.max_stars):
            color = YELLOW if i < self.stars_collected else GRAY
            points = []

            ox = start_x + star_width // 2 + i * (star_width + star_spacing)
            oy = start_y
            for k in range(10):
                ang = math.pi / 2 + k * math.pi / 5
                r = r_outer if k % 2 == 0 else r_inner
                x = int(ox + r * math.cos(ang))
                y = int(oy - r * math.sin(ang))
                points.append((x, y))

            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (30, 30, 30), points, width=max(2, s(3)))

    def draw(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        surface.fill(GAME_BG)
        title = self.font_big.render("Try Control the Exoskeleton Hand !!!", True, WHITE)
        title_y = self._title_y
        surface.blit(title, (self.screen_rect.centerx - title.get_width() // 2, title_y))

        self.settings_button.draw(surface)
        self.reset_button.draw(surface)
        self.start_pause_button.draw(surface)
        self.mirror_button.draw(surface)
        self.exit_button.draw(surface)

        self._draw_stars(surface)
        self.hand_gauge.draw(surface, self.font_small)
        self._draw_phase_arrow(surface)
        self.flexor_bar.draw(surface)
        self.extensor_bar.draw(surface)
        self.flexor_chart.draw(surface)
        self.extensor_chart.draw(surface)
        self.flexor_label.draw(surface)
        self.extensor_label.draw(surface)

        target_flexion = int(max(0.0, min(100.0, self.get_target_flexion_percent())))
        target_extension = int(max(0.0, min(100.0, self.get_target_extension_percent())))
        if not self.is_motor_output_enabled:
            msg = "Press Start, then follow the flexion/extension sequence."
        elif self._cycle_phase == "flexion":
            if self.countdown_timer > 0.0:
                msg = f"Holding flexion >= {target_flexion}%... keep steady."
            else:
                msg = f"Phase 1: Flex to at least {target_flexion}% and hold."
        else:
            if self.countdown_timer > 0.0:
                msg = f"Holding extension <= {target_extension}%... keep steady."
            else:
                msg = f"Phase 2: Extend to {target_extension}% or below and hold."
        msg_img = self.font_small.render(msg, True, WHITE)
        surface.blit(msg_img, (self.screen_rect.centerx - msg_img.get_width() // 2, self.screen_rect.centery - s(80)))

        cycle_text = f"Cycle {min(self.max_stars, self.stars_collected + 1)}/{self.max_stars} | "
        cycle_text += "Flexion" if self._cycle_phase == "flexion" else "Extension"
        cycle_img = self.font_tiny.render(cycle_text, True, GRAY)
        surface.blit(cycle_img, (self.screen_rect.centerx - cycle_img.get_width() // 2, self.screen_rect.centery - s(15)))

        status_font = pygame.font.SysFont("Arial", int(self.font_big.get_height() * 1.5))
        if self.stars_collected >= self.max_stars:
            win = status_font.render("You Win!", True, GREEN)
            win_y = self.screen_rect.centery - win.get_height() // 2 + s(95)
            surface.blit(win, (self.screen_rect.centerx - win.get_width() // 2, win_y))
        else:
            status_text = self._get_status_label_text()
            status_img = status_font.render(status_text, True, YELLOW)
            status_y = self.screen_rect.centery - status_img.get_height() // 2 + s(95)
            surface.blit(status_img, (self.screen_rect.centerx - status_img.get_width() // 2, status_y))

        version_text = f"v{self.game_version}"
        version_img = self.font_tiny.render(version_text, True, GRAY)
        version_x = self.screen_rect.w - version_img.get_width() - s(20)
        version_y = self.screen_rect.h - version_img.get_height() - s(20)
        surface.blit(version_img, (version_x, version_y))


class SettingsScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ui_scale: float,
        ble: BLEManager,
        on_close: Callable[[], None],
        set_emg_max_flexor: Callable[[float], None],
        set_emg_max_extensor: Callable[[float], None],
        set_hand_start_percent: Callable[[float], None],
        set_threshold_percent: Callable[[float], None],
        set_countdown_seconds: Callable[[float], None],
        set_target_flexion_percent: Callable[[float], None],
        set_target_extension_percent: Callable[[float], None],
        set_grip_step_percent: Callable[[float], None],
        set_command_rate_hz: Callable[[float], None],
        set_activation_hysteresis_percent: Callable[[float], None],
        set_deactivation_hysteresis_percent: Callable[[float], None],
        on_bind_flexor_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_extensor_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_exo_hand: Callable[[Optional[BLEDeviceInfo]], None],
        init_values: dict,
        allowed_mac_addresses: Optional[Set[str]] = None,
        get_bound_flexor_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_extensor_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_exo_hand: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
    ):
        self.screen_rect = screen_rect
        self.ui_scale = ui_scale
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.ble = ble
        self.on_close = on_close
        self.font_title = pygame.font.SysFont("Arial", s(36))
        self.font = pygame.font.SysFont("Arial", s(24))
        self.font_hint = pygame.font.SysFont("Arial", s(16))
        self.allowed_mac_addresses = allowed_mac_addresses or set()

        self.panel = Panel(pygame.Rect(s(80), s(80), screen_rect.w - s(160), screen_rect.h - s(160)), bg=(0, 0, 0), alpha=210)
        self.close_btn = Button(
            pygame.Rect(self.panel.rect.x + s(20), self.panel.rect.bottom - s(60), s(140), s(40)),
            "Apply",
            self.font,
            on_click=on_close,
        )
        self._inner_left = self.panel.rect.x + s(30)
        self._inner_right = self.panel.rect.right - s(30)
        self._content_left = self._inner_left
        col_gap = s(36)
        inner_width = self._inner_right - self._inner_left
        self._left_col_width = max(s(520), int(inner_width * 0.52))
        self._left_col_width = min(self._left_col_width, inner_width - s(360))
        self._right_col_x = self._inner_left + self._left_col_width + col_gap
        self._right_col_width = max(s(320), self._inner_right - self._right_col_x)

        scan_btn_w = max(s(180), min(s(300), self._right_col_width // 2 - s(8)))
        self.scan_btn = Button(
            pygame.Rect(self._right_col_x, self.panel.rect.y + s(70), scan_btn_w, s(40)),
            "Scan BLE",
            self.font,
            on_click=self._scan,
        )
        sim_text = f"Test Simulation: {'ON' if ble.simulation else 'OFF'}"
        sim_text_width = self.font.size(sim_text)[0]
        sim_btn_width = max(s(220), sim_text_width + s(40))
        sim_btn_width = min(self._right_col_width - scan_btn_w - s(12), sim_btn_width)
        self.sim_toggle = Button(
            pygame.Rect(self.scan_btn.rect.right + s(12), self.panel.rect.y + s(70), sim_btn_width, s(40)),
            sim_text,
            self.font,
            on_click=self._toggle_sim,
        )

        self.devices: List[BLEDeviceInfo] = []
        self._device_buttons: List[tuple[object, str, BLEDeviceInfo]] = []
        self._scan_status = ""
        self._scan_thread: Optional[threading.Thread] = None
        self._scan_start_time = 0.0
        self._devices_ready: List[BLEDeviceInfo] = []

        self._device_scroll_offset = 0
        self._scrollbar_dragging = False
        self._last_scroll_y = 0

        x0, y0 = self._content_left, self.panel.rect.y + s(170)
        stepper_labels = [
            ("EMG Max Flexor", "{:.0f}", init_values.get("emg_max_range_flexor", init_values.get("emg_max_range", 65535))),
            ("EMG Max Extensor", "{:.0f}", init_values.get("emg_max_range_extensor", init_values.get("emg_max_range", 65535))),
            ("Hand Start %", "{:.0f}%", init_values.get("hand_start_percent", 70)),
            ("Threshold %", "{:.0f}%", init_values.get("threshold_percent", 60)),
            ("Countdown s", "{:.0f}", init_values.get("countdown_seconds", 3)),
            ("Target Flexion %", "{:.0f}%", init_values.get("target_flexion_percent", 90)),
            ("Target Extension %", "{:.0f}%", init_values.get("target_extension_percent", 30)),
            ("Grip Step %", "{:.0f}%", init_values.get("grip_step_percent", 5)),
            ("Command Rate Hz", "{:.0f}", init_values.get("command_rate_hz", 10)),
            ("Activate Hyst %", "{:.0f}%", init_values.get("activation_hysteresis_percent", 2)),
            ("Release Hyst %", "{:.0f}%", init_values.get("deactivation_hysteresis_percent", 5)),
        ]
        max_label_width = 0
        for label, fmt, val in stepper_labels:
            label_text = f"{label}: {fmt.format(val)}"
            max_label_width = max(max_label_width, self.font.size(label_text)[0])
        button_x = x0 + max_label_width + s(20)
        max_button_x = self._right_col_x - s(140)
        button_x = min(button_x, max_button_x)
        stepper_button_w = s(40)
        stepper_button_h = s(36)
        stepper_button_gap = s(10)
        stepper_text_button_gap = s(20)

        self.step_emg_max_flexor = NumericStepper(
            "EMG Max Flexor",
            (x0, y0),
            self.font,
            init_values.get("emg_max_range_flexor", init_values.get("emg_max_range", 65535)),
            100,
            100,
            65535,
            fmt="{:.0f}",
            on_change=set_emg_max_flexor,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_emg_max_extensor = NumericStepper(
            "EMG Max Extensor",
            (x0, y0 + s(50)),
            self.font,
            init_values.get("emg_max_range_extensor", init_values.get("emg_max_range", 65535)),
            100,
            100,
            65535,
            fmt="{:.0f}",
            on_change=set_emg_max_extensor,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_hand_start = NumericStepper(
            "Hand Start %",
            (x0, y0 + s(100)),
            self.font,
            init_values.get("hand_start_percent", 70),
            5,
            0,
            100,
            fmt="{:.0f}%",
            on_change=set_hand_start_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_threshold = NumericStepper(
            "Threshold %",
            (x0, y0 + s(150)),
            self.font,
            init_values.get("threshold_percent", 60),
            5,
            5,
            100,
            fmt="{:.0f}%",
            on_change=set_threshold_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_countdown = NumericStepper(
            "Countdown s",
            (x0, y0 + s(200)),
            self.font,
            init_values.get("countdown_seconds", 3),
            1,
            1,
            10,
            fmt="{:.0f}",
            on_change=set_countdown_seconds,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_target_flexion = NumericStepper(
            "Target Flexion %",
            (x0, y0 + s(250)),
            self.font,
            init_values.get("target_flexion_percent", 90),
            5,
            50,
            100,
            fmt="{:.0f}%",
            on_change=set_target_flexion_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_target_extension = NumericStepper(
            "Target Extension %",
            (x0, y0 + s(300)),
            self.font,
            init_values.get("target_extension_percent", 30),
            5,
            0,
            50,
            fmt="{:.0f}%",
            on_change=set_target_extension_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_grip_step = NumericStepper(
            "Grip Step %",
            (x0, y0 + s(350)),
            self.font,
            init_values.get("grip_step_percent", 5),
            1,
            1,
            20,
            fmt="{:.0f}%",
            on_change=set_grip_step_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_command_rate = NumericStepper(
            "Command Rate Hz",
            (x0, y0 + s(400)),
            self.font,
            init_values.get("command_rate_hz", 10),
            1,
            2,
            30,
            fmt="{:.0f}",
            on_change=set_command_rate_hz,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_activation_hysteresis = NumericStepper(
            "Activate Hyst %",
            (x0, y0 + s(450)),
            self.font,
            init_values.get("activation_hysteresis_percent", 2),
            1,
            0,
            20,
            fmt="{:.0f}%",
            on_change=set_activation_hysteresis_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_deactivation_hysteresis = NumericStepper(
            "Release Hyst %",
            (x0, y0 + s(500)),
            self.font,
            init_values.get("deactivation_hysteresis_percent", 5),
            1,
            0,
            20,
            fmt="{:.0f}%",
            on_change=set_deactivation_hysteresis_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        row_height = s(82)
        self._device_row_height = row_height
        self._scan_results_header_y = self.panel.rect.y + s(130)
        self._scan_results_status_y = self._scan_results_header_y + s(34)
        self._device_list_start_y = self._scan_results_status_y + s(34)
        available_h = self.panel.rect.bottom - self._device_list_start_y - s(90)
        self._device_list_max_visible = max(3, available_h // row_height)
        self._device_list_left = self._right_col_x + s(10)
        self._device_list_width = self._right_col_width - s(20)
        self._scrollbar_x = self._device_list_left + self._device_list_width - s(22)
        self._scrollbar_width = s(20)
        self._info_text_y = self.panel.rect.bottom - s(40)

        self.on_bind_flexor_emg = on_bind_flexor_emg
        self.on_bind_extensor_emg = on_bind_extensor_emg
        self.on_bind_exo_hand = on_bind_exo_hand
        self.get_bound_flexor_emg = get_bound_flexor_emg or (lambda: None)
        self.get_bound_extensor_emg = get_bound_extensor_emg or (lambda: None)
        self.get_bound_exo_hand = get_bound_exo_hand or (lambda: None)

        self._build_device_buttons_from_bound()

    def _toggle_sim(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.ble.simulation = not self.ble.simulation
        sim_text = f"Simulation: {'ON' if self.ble.simulation else 'OFF'}"
        self.sim_toggle.text = sim_text
        scan_btn_w = self.scan_btn.rect.w
        max_sim_w = self._right_col_width - scan_btn_w - s(12)
        sim_text_width = self.font.size(sim_text)[0]
        self.sim_toggle.rect.x = self.scan_btn.rect.right + s(12)
        self.sim_toggle.rect.w = max(s(160), min(max_sim_w, sim_text_width + s(40)))

    def _get_display_devices(self) -> List[BLEDeviceInfo]:
        def has_valid_name(dev: BLEDeviceInfo) -> bool:
            name = (dev.name or "").strip()
            return bool(name) and name.lower() != "unknown"

        scanned = [d for d in self.devices if has_valid_name(d)]

        bound_list: List[BLEDeviceInfo] = []
        for getter in (self.get_bound_flexor_emg, self.get_bound_extensor_emg, self.get_bound_exo_hand):
            try:
                dev = getter()
            except Exception:
                dev = None
            if dev and has_valid_name(dev):
                bound_list.append(dev)

        seen = set()
        merged: List[BLEDeviceInfo] = []
        for d in scanned:
            addr = (d.address or "").upper()
            if addr and addr not in seen:
                merged.append(d)
                seen.add(addr)
        for d in bound_list:
            addr = (d.address or "").upper()
            if addr and addr not in seen:
                merged.append(d)
                seen.add(addr)

        def sort_key(dev: BLEDeviceInfo) -> tuple:
            name = dev.name or ""
            if name.startswith("RR_HOH"):
                return (0, name)
            if name.startswith("EMGS"):
                return (1, name)
            return (2, name)

        merged.sort(key=sort_key)
        return merged

    def _build_device_buttons_from_bound(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        display_devices = self._get_display_devices()
        if not display_devices:
            self._device_buttons = []
            return

        self._device_buttons = []
        x, y = self._device_list_left, self._device_list_start_y
        display_devices_scrolled = display_devices[self._device_scroll_offset :]
        row_h = self._device_row_height
        line_h = s(36)
        button_gap = s(8)
        row_width = self._device_list_width - self._scrollbar_width - s(12)
        label_w = max(s(220), row_width)
        role_btn_w = max(s(88), (label_w - 2 * button_gap) // 3)
        for d in display_devices_scrolled:
            device_label = d.name or "Unknown"
            mac_addr = (d.address or "").upper()
            short_mac = mac_addr if len(mac_addr) <= 11 else f"{mac_addr[:11]}..."
            heading_text = f"{device_label} [{short_mac}]" if short_mac else device_label
            if self.font.size(heading_text)[0] > label_w - s(16):
                trimmed_name = device_label
                while trimmed_name and self.font.size(f"{trimmed_name}... [{short_mac}]")[0] > label_w - s(16):
                    trimmed_name = trimmed_name[:-1]
                if trimmed_name:
                    heading_text = f"{trimmed_name}... [{short_mac}]"
            label_btn = Button(pygame.Rect(x, y, label_w, line_h), heading_text, self.font, on_click=lambda: None)
            label_btn.bg = (40, 90, 180)
            label_btn.hover_bg = (55, 115, 210)
            label_btn.fg = WHITE
            self._device_buttons.append((label_btn, "label", d))

            mac_text = f"[{d.address}]"
            mac_label = Label(mac_text, (x + s(4), y + line_h + s(2)), self.font, color=(180, 180, 180))
            self._device_buttons.append((mac_label, "mac_label", d))

            rx = x
            bind_y = y + line_h + s(2)
            roles = [
                ("Flexor", "Bind Flexor EMG", self.on_bind_flexor_emg),
                ("Extensor", "Bind Extensor EMG", self.on_bind_extensor_emg),
                ("Exo Hand", "Bind Exo Hand", self.on_bind_exo_hand),
            ]
            for label_text, role_key, fn in roles:
                b = Button(
                    pygame.Rect(rx, bind_y, role_btn_w, line_h),
                    label_text,
                    self.font,
                    on_click=self._create_bind_click_handler(d, fn, role_key),
                )
                self._device_buttons.append((b, role_key, d))
                rx += role_btn_w + button_gap
            y += row_h
            if len([b for b, role, _ in self._device_buttons if role == "label"]) >= self._device_list_max_visible:
                break

        self._update_bind_button_states()

    def _create_bind_click_handler(self, dev: BLEDeviceInfo, bind_fn: Callable, role_text: str):
        def click_handler():
            bound_flexor_emg = self.get_bound_flexor_emg()
            bound_extensor_emg = self.get_bound_extensor_emg()
            bound_exo_hand = self.get_bound_exo_hand()

            is_already_bound_to_this_role = False
            if role_text == "Bind Flexor EMG" and bound_flexor_emg and bound_flexor_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_text == "Bind Extensor EMG" and bound_extensor_emg and bound_extensor_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_text == "Bind Exo Hand" and bound_exo_hand and bound_exo_hand.address == dev.address:
                is_already_bound_to_this_role = True

            if is_already_bound_to_this_role:
                bind_fn(None)
                self._update_bind_button_states()
                return

            if bound_flexor_emg and bound_flexor_emg.address == dev.address and role_text != "Bind Flexor EMG":
                self.on_bind_flexor_emg(None)
            if bound_extensor_emg and bound_extensor_emg.address == dev.address and role_text != "Bind Extensor EMG":
                self.on_bind_extensor_emg(None)
            if bound_exo_hand and bound_exo_hand.address == dev.address and role_text != "Bind Exo Hand":
                self.on_bind_exo_hand(None)

            if not self.ble.is_connected(dev.address):
                if not self.ble.connect(dev.address):
                    return

            bind_fn(dev)
            self._update_bind_button_states()

        return click_handler

    def _update_bind_button_states(self):
        bound_flexor_emg = self.get_bound_flexor_emg()
        bound_extensor_emg = self.get_bound_extensor_emg()
        bound_exo_hand = self.get_bound_exo_hand()

        for button, role, device in self._device_buttons:
            if role in ("label", "mac_label"):
                continue

            button.disabled = False
            is_bound = False
            if role == "Bind Flexor EMG":
                is_bound = bound_flexor_emg is not None and bound_flexor_emg.address == device.address
            elif role == "Bind Extensor EMG":
                is_bound = bound_extensor_emg is not None and bound_extensor_emg.address == device.address
            elif role == "Bind Exo Hand":
                is_bound = bound_exo_hand is not None and bound_exo_hand.address == device.address

            if is_bound:
                button.bg = (40, 120, 40)
                button.hover_bg = (60, 160, 60)
                button.fg = WHITE
            else:
                button.bg = (30, 30, 30)
                button.hover_bg = (60, 60, 60)
                button.fg = WHITE

    def _scan(self):
        if self._scan_thread and self._scan_thread.is_alive():
            return

        self.scan_btn.disabled = True
        self.devices = []
        self._device_buttons = []
        self._devices_ready = []
        self._scan_status = "Scanning..."
        self._scan_start_time = time.time()

        def do_scan():
            try:
                self.devices = self.ble.scan(timeout=10.0)
                self._devices_ready = self.devices
                self._device_scroll_offset = 0
                self._build_device_buttons_from_bound()
            except Exception as e:
                self._scan_status = f"Scan error: {e}"

        self._scan_thread = threading.Thread(target=do_scan, daemon=True)
        self._scan_thread.start()

    def handle_event(self, event: pygame.event.Event):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_a:
                self.on_close()
            elif event.key == pygame.K_b:
                self._scan()
            elif event.key == pygame.K_t:
                self._toggle_sim()

        self.close_btn.handle_event(event)
        self.scan_btn.handle_event(event)
        self.sim_toggle.handle_event(event)
        self.step_emg_max_flexor.handle_event(event)
        self.step_emg_max_extensor.handle_event(event)
        self.step_hand_start.handle_event(event)
        self.step_threshold.handle_event(event)
        self.step_countdown.handle_event(event)
        self.step_target_flexion.handle_event(event)
        self.step_target_extension.handle_event(event)
        self.step_grip_step.handle_event(event)
        self.step_command_rate.handle_event(event)
        self.step_activation_hysteresis.handle_event(event)
        self.step_deactivation_hysteresis.handle_event(event)

        display_devices = self._get_display_devices()
        total_devices = len(display_devices)

        scrollbar_x = self._scrollbar_x
        scrollbar_y = self._device_list_start_y
        scrollbar_height = self._device_list_max_visible * self._device_row_height
        scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_y, self._scrollbar_width, scrollbar_height)

        if event.type == pygame.MOUSEWHEEL:
            if total_devices > self._device_list_max_visible:
                max_scroll = total_devices - self._device_list_max_visible
                self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset - event.y))
                self._build_device_buttons_from_bound()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if total_devices > self._device_list_max_visible and scrollbar_rect.collidepoint(event.pos):
                self._scrollbar_dragging = True
                self._last_scroll_y = event.pos[1]
        elif event.type == pygame.MOUSEMOTION:
            if self._scrollbar_dragging and total_devices > self._device_list_max_visible:
                dy = event.pos[1] - self._last_scroll_y
                scroll_delta = int(dy / max(1, self._device_row_height))
                if scroll_delta != 0:
                    max_scroll = total_devices - self._device_list_max_visible
                    self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset + scroll_delta))
                    self._last_scroll_y = event.pos[1]
                    self._build_device_buttons_from_bound()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._scrollbar_dragging = False

        for b, role, _ in self._device_buttons:
            if role not in ("label", "mac_label"):
                b.handle_event(event)

    def update(self, dt: float):
        _ = dt
        if not self._device_buttons:
            self._build_device_buttons_from_bound()
        self._update_bind_button_states()

    def draw(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.panel.draw(surface)
        title = self.font_title.render("Settings", True, WHITE)
        surface.blit(title, (self.panel.rect.x + s(20), self.panel.rect.y + s(20)))
        self.close_btn.draw(surface)
        self.scan_btn.draw(surface)
        self.sim_toggle.draw(surface)

        hint = self.font.render("Tune EMG scaling and control behavior:", True, WHITE)
        surface.blit(hint, (self._content_left, self.panel.rect.y + s(80)))

        self.step_emg_max_flexor.draw(surface)
        self.step_emg_max_extensor.draw(surface)
        self.step_hand_start.draw(surface)
        self.step_threshold.draw(surface)
        self.step_countdown.draw(surface)
        self.step_target_flexion.draw(surface)
        self.step_target_extension.draw(surface)
        self.step_grip_step.draw(surface)
        self.step_command_rate.draw(surface)
        self.step_activation_hysteresis.draw(surface)
        self.step_deactivation_hysteresis.draw(surface)

        # Keep shortcuts in the lower-left gap, above the Apply button.
        shortcut_lines = (
            "Keyboard Shortcuts",
            "Main: Enter/Numpad Enter = Start/Stop",
            "Main: Space = Reset",
            "Main: S = Open Settings",
            "Main: M = Toggle Mirror",
            "Settings: A = Apply/Close",
            "Settings: B = Scan BLE",
            "Settings: T = Toggle Simulation",
        )
        line_gap = s(18)
        shortcuts_h = len(shortcut_lines) * line_gap
        min_shortcuts_y = self.step_deactivation_hysteresis.y + s(48)
        max_shortcuts_y = self.close_btn.rect.y - shortcuts_h - s(8)
        shortcuts_y = min(min_shortcuts_y, max_shortcuts_y) if max_shortcuts_y < min_shortcuts_y else max_shortcuts_y
        for idx, text in enumerate(shortcut_lines):
            shortcut_img = self.font_hint.render(text, True, (180, 180, 180))
            surface.blit(shortcut_img, (self._content_left, shortcuts_y + idx * line_gap))

        # Dedicated right-column BLE area with larger height for more results.
        placeholder_x = self._right_col_x
        placeholder_y = self.panel.rect.y + s(120)
        placeholder_w = self._right_col_width
        placeholder_h = self.panel.rect.bottom - placeholder_y - s(20)
        pygame.draw.rect(surface, (25, 25, 25), (placeholder_x, placeholder_y, placeholder_w, placeholder_h), border_radius=8)
        pygame.draw.rect(surface, (70, 70, 70), (placeholder_x, placeholder_y, placeholder_w, placeholder_h), width=2, border_radius=8)
        results_header = self.font.render("BLE Scan Results", True, WHITE)
        surface.blit(results_header, (self._device_list_left, self._scan_results_header_y))

        is_scanning = self._scan_thread and self._scan_thread.is_alive()
        elapsed = time.time() - self._scan_start_time if self._scan_start_time else 0
        min_display_time = 3.0

        if not is_scanning and self._scan_start_time > 0 and elapsed >= min_display_time and not self._devices_ready and not self._scan_status:
            self.scan_btn.disabled = False

        if is_scanning:
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self.font.render(f"[SCANNING{dots}] BLE scan in progress, please wait...", True, YELLOW)
            surface.blit(scanning_text, (self._device_list_left, self._scan_results_status_y))
        elif self._devices_ready and elapsed < min_display_time:
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self.font.render(f"[SCANNING{dots}] BLE scan complete, processing...", True, YELLOW)
            surface.blit(scanning_text, (self._device_list_left, self._scan_results_status_y))
        elif self._devices_ready and elapsed >= min_display_time:
            self.devices = self._devices_ready
            self._devices_ready = []
            self._scan_status = ""
            self.scan_btn.disabled = False
            if not self._device_buttons:
                self._device_scroll_offset = 0
                self._build_device_buttons_from_bound()
        elif self._scan_status and "error" in self._scan_status.lower():
            status_text = self.font.render(self._scan_status, True, RED)
            surface.blit(status_text, (self._device_list_left, self._scan_results_status_y))
            self.scan_btn.disabled = False
        else:
            idle_text = self.font.render("Press 'Scan BLE' to discover devices.", True, (180, 180, 180))
            surface.blit(idle_text, (self._device_list_left, self._scan_results_status_y))

        display_devices = self._get_display_devices()
        total_devices = len(display_devices)
        visible_devices = len([b for b, role, _ in self._device_buttons if role == "label"])

        if total_devices > self._device_list_max_visible:
            scrollbar_x = self._scrollbar_x
            scrollbar_y = self._device_list_start_y
            scrollbar_height = self._device_list_max_visible * self._device_row_height
            scrollbar_width = self._scrollbar_width
            pygame.draw.rect(surface, (60, 60, 60), (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height), border_radius=4)

            thumb_height = max(20, int((self._device_list_max_visible / total_devices) * scrollbar_height))
            max_thumb_y = scrollbar_y + scrollbar_height - thumb_height
            scroll_ratio = self._device_scroll_offset / max(1, total_devices - self._device_list_max_visible)
            thumb_y = scrollbar_y + int(scroll_ratio * (max_thumb_y - scrollbar_y))
            pygame.draw.rect(surface, (150, 150, 150), (scrollbar_x, thumb_y, scrollbar_width, thumb_height), border_radius=4)

        if total_devices > 0:
            scroll_info = ""
            if total_devices > self._device_list_max_visible:
                scroll_info = (
                    f" | Scroll: {self._device_scroll_offset + 1}-"
                    f"{min(self._device_scroll_offset + visible_devices, total_devices)}/{total_devices} (Use mouse wheel)"
                )
            info_text = self.font.render(f"Total discovered: {total_devices} | Displaying: {visible_devices}{scroll_info}", True, WHITE)
            surface.blit(info_text, (self._device_list_left, self._info_text_y))

        for b, role, _ in self._device_buttons:
            if hasattr(b, "draw"):
                b.draw(surface)
