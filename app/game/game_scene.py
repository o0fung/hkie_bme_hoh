import math
import time
from collections import deque
from typing import Callable, Optional

import pygame

from ..ui.widgets import (
    Button,
    Label,
    BarGauge,
    CircularGauge,
    EMGChart,
    draw_outlined_text,
)
from ..ui.fonts import pick_font
from .scene_manager import Scene
from .control_logic import (
    choose_active_muscle,
    compute_effective_thresholds,
    snap_grip_target,
    stabilize_grip_target,
)
from .game_scene_ops import (
    apply_side_layout as apply_game_side_layout,
    apply_theme_styles as apply_game_theme_styles,
    create_soft_focus_background,
    draw_stars as draw_game_stars,
    draw_trigger_session_stats as draw_game_trigger_session_stats,
    load_background_image,
)


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 100, 100)
GREEN = (80, 200, 120)
YELLOW = (240, 210, 80)
RED = (230, 80, 80)
GAME_BG = (10, 20, 30)



class GameScene(Scene):
    _DEFAULT_NOISE_FLOOR_HISTORY_SIZE = 180
    _DEFAULT_NOISE_FLOOR_PERCENTILE = 20.0
    _DEFAULT_NOISE_FLOOR_GUARD = 0.03

    def __init__(
        self,
        screen_rect: pygame.Rect,
        ui_scale: float,
        open_settings: Callable[[], None],
        reset_game: Callable[[], None],
        get_text: Callable[[str], str],
        get_current_language: Callable[[], str],
        emg_flexor_provider: Callable[[], float],
        emg_extensor_provider: Callable[[], float],
        send_grip: Callable[[float], None],
        hand_pos_provider: Callable[[], float],
        get_hand_start_percent: Callable[[], float],
        get_threshold_percent: Callable[[], float],
        get_relax_flexion_percent: Callable[[], float],
        get_relax_extension_percent: Callable[[], float],
        get_target_flexion_percent: Callable[[], float],
        get_target_extension_percent: Callable[[], float],
        get_countdown_seconds: Callable[[], float],
        get_stars_to_collect: Callable[[], float],
        get_training_duration_minutes: Callable[[], float],
        get_grip_step_percent: Callable[[], float],
        get_command_rate_hz: Callable[[], float],
        get_activation_hysteresis_percent: Callable[[], float],
        get_deactivation_hysteresis_percent: Callable[[], float],
        get_forward_deadband_percent: Callable[[], float],
        get_reversal_deadband_percent: Callable[[], float],
        get_background_blur_percent: Callable[[], float],
        play_start_chime: Callable[[], None],
        play_progress_bell: Callable[[], None],
        play_completion_jingle: Callable[[], None],
        toggle_sound_effect_quick: Callable[[], None],
        get_sound_effect_quick_enabled: Callable[[], bool],
        toggle_music_quick: Callable[[], None],
        get_music_quick_enabled: Callable[[], bool],
        get_is_dark_theme: Callable[[], bool],
        get_training_muscle_mode: Callable[[], str],
        get_training_trigger_mode: Callable[[], str],
        get_trigger_threshold_percent: Callable[[], float],
        get_trigger_wait_seconds: Callable[[], float],
        has_bound_flexor: Callable[[], bool],
        has_bound_extensor: Callable[[], bool],
        game_version: str = "0.0.0",
        emg_flexor_raw_provider: Optional[Callable[[], list[float]]] = None,
        emg_extensor_raw_provider: Optional[Callable[[], list[float]]] = None,
    ):
        self.screen_rect = screen_rect
        self.ui_scale = ui_scale
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.open_settings = open_settings
        self.reset_game_cb = reset_game
        self.get_text = get_text
        self.get_current_language = get_current_language
        self._current_language = self.get_current_language()
        self.emg_flexor_provider = emg_flexor_provider
        self.emg_extensor_provider = emg_extensor_provider
        self.send_grip = send_grip
        self.hand_pos_provider = hand_pos_provider
        self.get_hand_start_percent = get_hand_start_percent
        self.get_threshold_percent = get_threshold_percent
        self.get_relax_flexion_percent = get_relax_flexion_percent
        self.get_relax_extension_percent = get_relax_extension_percent
        self.get_target_flexion_percent = get_target_flexion_percent
        self.get_target_extension_percent = get_target_extension_percent
        self.get_countdown_seconds = get_countdown_seconds
        self.get_stars_to_collect = get_stars_to_collect
        self.get_training_duration_minutes = get_training_duration_minutes
        self.get_grip_step_percent = get_grip_step_percent
        self.get_command_rate_hz = get_command_rate_hz
        self.get_activation_hysteresis_percent = get_activation_hysteresis_percent
        self.get_deactivation_hysteresis_percent = get_deactivation_hysteresis_percent
        self.get_forward_deadband_percent = get_forward_deadband_percent
        self.get_reversal_deadband_percent = get_reversal_deadband_percent
        self.get_background_blur_percent = get_background_blur_percent
        self.play_start_chime = play_start_chime
        self.play_progress_bell = play_progress_bell
        self.play_completion_jingle = play_completion_jingle
        self.toggle_sound_effect_quick = toggle_sound_effect_quick
        self.get_sound_effect_quick_enabled = get_sound_effect_quick_enabled
        self.toggle_music_quick = toggle_music_quick
        self.get_music_quick_enabled = get_music_quick_enabled
        self.get_is_dark_theme = get_is_dark_theme
        self.get_training_muscle_mode = get_training_muscle_mode
        self.get_training_trigger_mode = get_training_trigger_mode
        self.get_trigger_threshold_percent = get_trigger_threshold_percent
        self.get_trigger_wait_seconds = get_trigger_wait_seconds
        self.has_bound_flexor = has_bound_flexor
        self.has_bound_extensor = has_bound_extensor
        self.game_version = game_version
        self._background_source_image: Optional[pygame.Surface] = None
        self._background_blur_percent = max(0.0, min(100.0, float(self.get_background_blur_percent())))
        self._background_image: Optional[pygame.Surface] = None
        self._load_background_image()

        use_cjk_font = self._is_cjk_language(self._current_language)
        self.font_big = pick_font(s(112), prefer_cjk=use_cjk_font)
        self.font_small = pick_font(s(40), prefer_cjk=use_cjk_font)
        self.font_tiny = pick_font(s(24), prefer_cjk=use_cjk_font)
        self.font_round = pick_font(s(68), prefer_cjk=use_cjk_font)
        self.font_menu = pick_font(s(80), prefer_cjk=use_cjk_font)

        self.stars_collected = 0
        self.max_stars = self._clamp_stars_to_collect(self.get_stars_to_collect())
        self._trigger_repetition_count = 0
        self._trigger_session_remaining_s = max(
            0.0, float(self.get_training_duration_minutes()) * 60.0
        )
        self._is_trigger_session_mode = False
        self._trigger_session_started = False

        self._title_y = s(28)
        # Keep square icon button and make it larger for easier tapping.
        menu_size = max(s(58), int(round(s(58) * 1.8)))
        menu_margin = s(20)
        menu_y = self._title_y + max(0, (self.font_big.get_height() - menu_size) // 2)
        self.menu_button = Button(
            pygame.Rect(self.screen_rect.w - menu_size - menu_margin, menu_y, menu_size, menu_size),
            "",
            self.font_small,
            on_click=self._toggle_menu,
            bg=(25, 25, 25),
            hover_bg=(55, 55, 55),
        )
        self._menu_open = False

        menu_item_h = s(108)
        menu_gap = s(8)
        menu_labels = (
            self._t("btn_settings"),
            self._t("btn_reset"),
            self._t("btn_stop"),
            self._t("btn_mirror_off"),
            self._t("btn_sound_on"),
            self._t("btn_music_on"),
            self._t("btn_exit"),
        )
        # Size menu width from enlarged menu font so labels never clip.
        menu_w = max(s(420), max(self.font_menu.size(lbl)[0] for lbl in menu_labels) + s(140))
        menu_x = self.menu_button.rect.right - menu_w
        menu_y_start = self.menu_button.rect.bottom + s(10)

        self.settings_button = Button(
            pygame.Rect(menu_x, menu_y_start, menu_w, menu_item_h),
            self._t("btn_settings"),
            self.font_menu,
            on_click=self._open_settings_from_menu,
        )
        self.reset_button = Button(
            pygame.Rect(menu_x, menu_y_start + (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_reset"),
            self.font_menu,
            on_click=self._reset_from_menu,
        )
        self.is_motor_output_enabled = False
        _, _, self._effective_training_mode = self._resolve_training_channels()
        self.start_pause_button = Button(
            pygame.Rect(menu_x, menu_y_start + 2 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_start"),
            self.font_menu,
            on_click=self._toggle_run_pause,
        )
        self.mirror_button = Button(
            pygame.Rect(menu_x, menu_y_start + 3 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_mirror_off"),
            self.font_menu,
            on_click=self._toggle_mirror_layout,
        )
        self.sound_toggle_button = Button(
            pygame.Rect(menu_x, menu_y_start + 4 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_sound_on"),
            self.font_menu,
            on_click=self._toggle_sound_quick,
        )
        self.music_toggle_button = Button(
            pygame.Rect(menu_x, menu_y_start + 5 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_music_on"),
            self.font_menu,
            on_click=self._toggle_music_quick,
        )
        self.exit_button = Button(
            pygame.Rect(menu_x, menu_y_start + 6 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_exit"),
            self.font_menu,
            on_click=self._exit,
        )
        self._menu_panel_rect = pygame.Rect(
            menu_x - s(10),
            menu_y_start - s(10),
            menu_w + s(20),
            7 * menu_item_h + 6 * menu_gap + s(20),
        )
        self._is_dark_theme = bool(self.get_is_dark_theme())
        self._menu_panel_bg = (20, 20, 20)
        self._menu_panel_border = (180, 180, 180)
        self._background_light_overlay_alpha = 0
        self._update_start_stop_button_style()
        self._update_sound_toggle_button()
        self._update_music_toggle_button()

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
        gauge_y = max(self.screen_rect.centery + s(90), top + s(240))
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
            line_color=(20, 70, 140),
            bg_color=GAME_BG,
            reverse_direction=True,
        )
        self.extensor_chart = EMGChart(
            pygame.Rect(self.screen_rect.w - side_margin - chart_width - s(100), chart_y + s(100), chart_width, chart_height),
            max_samples=500,
            line_color=(120, 25, 25),
            bg_color=GAME_BG,
            reverse_direction=False,
        )

        label_y = top + bar_h + s(20)
        self._label_y = label_y
        flexor_label_text = self._t("label_flexor_emg")
        extensor_label_text = self._t("label_extensor_emg")
        flexor_label_x = side_margin + bar_w // 2 - self.font_small.size(flexor_label_text)[0] // 2
        extensor_label_x = self.screen_rect.w - side_margin - bar_w // 2 - self.font_small.size(extensor_label_text)[0] // 2
        self.flexor_label = Label(flexor_label_text, (flexor_label_x, label_y), self.font_small, color=BLACK)
        self.extensor_label = Label(extensor_label_text, (extensor_label_x, label_y), self.font_small, color=BLACK)

        self.emg_flexor_raw_provider = emg_flexor_raw_provider or (lambda: [])
        self.emg_extensor_raw_provider = emg_extensor_raw_provider or (lambda: [])

        self.countdown_timer = 0.0
        self._cycle_phase = "flexion"  # "flexion" -> "extension" per star cycle.
        # Grip command stabilization settings.
        self.grip_step = max(0.01, min(1.0, self.get_grip_step_percent() / 100.0))
        command_rate_hz = max(1.0, self.get_command_rate_hz())
        self.command_update_interval = 1.0 / command_rate_hz
        # Command deadbands in normalized grip space [0..1]. 0 disables each gate.
        self.forward_deadband = max(0.0, min(1.0, self.get_forward_deadband_percent() / 100.0))
        self.reversal_deadband = max(0.0, min(1.0, self.get_reversal_deadband_percent() / 100.0))
        self.activation_hysteresis = max(0.0, min(0.5, self.get_activation_hysteresis_percent() / 100.0))
        self.deactivation_hysteresis = max(0.0, min(0.5, self.get_deactivation_hysteresis_percent() / 100.0))
        self._active_muscle: Optional[str] = None  # "flexor" | "extensor" | None
        self._grip_target_hold = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
        self._last_target_direction = 0  # -1 opening, +1 closing, 0 unknown/idle
        self._last_command_time = 0.0
        self._show_great_job = False
        self._great_job_muscle: Optional[str] = None
        self._trigger_go_latched_phase: Optional[str] = None
        self._trigger_maintain_active_phase: Optional[str] = None
        self._trigger_phase_wait_timer = 0.0
        self._trigger_require_relax_phase: Optional[str] = None
        self._is_mirrored = False
        self._show_flexor_channel = True
        self._show_extensor_channel = True
        self.noise_floor_history_size = self._DEFAULT_NOISE_FLOOR_HISTORY_SIZE
        self.noise_floor_percentile = self._DEFAULT_NOISE_FLOOR_PERCENTILE
        self.noise_floor_guard = self._DEFAULT_NOISE_FLOOR_GUARD
        self._flexor_noise_floor_hist: deque[float] = deque(
            maxlen=self.noise_floor_history_size
        )
        self._extensor_noise_floor_hist: deque[float] = deque(
            maxlen=self.noise_floor_history_size
        )
        self.hand_gauge.set_labels("", "")
        self._apply_theme_styles()
        self._apply_side_layout()

    def _is_cjk_language(self, language_code: str) -> bool:
        return str(language_code).startswith("zh")

    def _t(self, key: str, **kwargs) -> str:
        template = self.get_text(key)
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template

    def set_language(self, language_code: str):
        previous_is_cjk = self._is_cjk_language(self._current_language)
        self._current_language = str(language_code)
        current_is_cjk = self._is_cjk_language(self._current_language)
        if previous_is_cjk != current_is_cjk:
            s = lambda v: max(1, int(round(v * self.ui_scale)))
            self.font_big = pick_font(s(112), prefer_cjk=current_is_cjk)
            self.font_small = pick_font(s(40), prefer_cjk=current_is_cjk)
            self.font_tiny = pick_font(s(24), prefer_cjk=current_is_cjk)
            self.font_round = pick_font(s(68), prefer_cjk=current_is_cjk)
            self.font_menu = pick_font(s(80), prefer_cjk=current_is_cjk)
            self.settings_button.font = self.font_menu
            self.reset_button.font = self.font_menu
            self.start_pause_button.font = self.font_menu
            self.mirror_button.font = self.font_menu
            self.sound_toggle_button.font = self.font_menu
            self.music_toggle_button.font = self.font_menu
            self.exit_button.font = self.font_menu
            self.menu_button.font = self.font_small
            self.flexor_label.font = self.font_small
            self.extensor_label.font = self.font_small
        self.settings_button.text = self._t("btn_settings")
        self.reset_button.text = self._t("btn_reset")
        self.exit_button.text = self._t("btn_exit")
        self.mirror_button.text = self._t("btn_mirror_on") if self._is_mirrored else self._t("btn_mirror_off")
        self._update_sound_toggle_button()
        self._update_music_toggle_button()
        self.flexor_label.text = self._t("label_flexor_emg")
        self.extensor_label.text = self._t("label_extensor_emg")
        self.hand_gauge.set_labels("", "")
        self._update_start_stop_button_style()
        self._apply_side_layout()

    def _load_background_image(self):
        load_background_image(self)

    def _create_soft_focus_background(self, image: pygame.Surface, blur_percent: float) -> pygame.Surface:
        return create_soft_focus_background(image, blur_percent)

    def set_background_blur_percent(self, blur_percent: float):
        self._background_blur_percent = max(0.0, min(100.0, float(blur_percent)))
        if self._background_source_image is None:
            return
        self._background_image = self._create_soft_focus_background(
            self._background_source_image,
            self._background_blur_percent,
        )

    def _apply_side_layout(self):
        apply_game_side_layout(self)

    def _toggle_mirror_layout(self):
        self._menu_open = False
        self._is_mirrored = not self._is_mirrored
        self.mirror_button.text = self._t("btn_mirror_on") if self._is_mirrored else self._t("btn_mirror_off")
        self._apply_side_layout()

    def _toggle_sound_quick(self):
        self._menu_open = False
        self.toggle_sound_effect_quick()
        self._update_sound_toggle_button()

    def _toggle_music_quick(self):
        self._menu_open = False
        self.toggle_music_quick()
        self._update_music_toggle_button()

    def _update_sound_toggle_button(self):
        self.sound_toggle_button.text = (
            self._t("btn_sound_on") if self.get_sound_effect_quick_enabled() else self._t("btn_sound_off")
        )

    def _update_music_toggle_button(self):
        self.music_toggle_button.text = (
            self._t("btn_music_on") if self.get_music_quick_enabled() else self._t("btn_music_off")
        )

    def _resolve_training_channels(self) -> tuple[bool, bool, str]:
        configured = str(self.get_training_muscle_mode() or "auto").strip().lower()
        if configured == "flexor_only":
            return True, False, "flexor_only"
        if configured == "extensor_only":
            return False, True, "extensor_only"
        if configured == "both":
            return True, True, "both"

        use_flexor = bool(self.has_bound_flexor())
        use_extensor = bool(self.has_bound_extensor())
        if use_flexor and use_extensor:
            return True, True, "both"
        if use_flexor:
            return True, False, "flexor_only"
        if use_extensor:
            return False, True, "extensor_only"
        return False, False, "none"

    def _toggle_menu(self):
        self._menu_open = not self._menu_open

    def _open_settings_from_menu(self):
        self._menu_open = False
        self.open_settings()

    def _reset_from_menu(self):
        self._menu_open = False
        self._reset()

    def _update_start_stop_button_style(self):
        trigger_mode_selected = str(self.get_training_trigger_mode() or "auto").strip().lower() in {
            "trigger-and-go",
            "trigger-and-maintain",
        }
        if self.is_motor_output_enabled:
            self.start_pause_button.text = self._t("btn_pause") if trigger_mode_selected else self._t("btn_stop")
            if self._is_dark_theme:
                self.start_pause_button.bg = (150, 50, 50)
                self.start_pause_button.hover_bg = (185, 70, 70)
                self.start_pause_button.fg = WHITE
            else:
                self.start_pause_button.bg = (235, 135, 135)
                self.start_pause_button.hover_bg = (245, 155, 155)
                self.start_pause_button.fg = BLACK
        elif self._effective_training_mode == "none":
            self.start_pause_button.text = self._t("btn_start_blocked_no_emg")
            if self._is_dark_theme:
                self.start_pause_button.bg = (140, 110, 30)
                self.start_pause_button.hover_bg = (170, 135, 45)
                self.start_pause_button.fg = WHITE
            else:
                self.start_pause_button.bg = (240, 215, 145)
                self.start_pause_button.hover_bg = (248, 225, 165)
                self.start_pause_button.fg = BLACK
        else:
            if trigger_mode_selected and self._trigger_session_started and self._trigger_session_remaining_s > 0.0:
                self.start_pause_button.text = self._t("btn_resume")
            else:
                self.start_pause_button.text = self._t("btn_start")
            if self._is_dark_theme:
                self.start_pause_button.bg = (40, 130, 40)
                self.start_pause_button.hover_bg = (60, 170, 60)
                self.start_pause_button.fg = WHITE
            else:
                self.start_pause_button.bg = (155, 225, 155)
                self.start_pause_button.hover_bg = (175, 235, 175)
                self.start_pause_button.fg = BLACK
        self.start_pause_button.border_color_override = None if self._is_dark_theme else WHITE

    def _apply_theme_styles(self):
        apply_game_theme_styles(self, WHITE, BLACK, GRAY, GREEN, YELLOW)

    def _refresh_theme(self):
        latest_theme = bool(self.get_is_dark_theme())
        if latest_theme == self._is_dark_theme:
            return
        self._is_dark_theme = latest_theme
        self._apply_theme_styles()

    def _clamp_stars_to_collect(self, value: float) -> int:
        return int(max(1, min(7, round(float(value)))))

    def _progress_units(self) -> int:
        units = self.stars_collected * 2
        if self._effective_training_mode == "both" and self.stars_collected < self.max_stars and self._cycle_phase == "extension":
            units += 1
        return units

    def _is_session_complete(self) -> bool:
        if self._is_trigger_session_mode and self._trigger_session_remaining_s <= 0.0:
            return True
        return self.stars_collected >= self.max_stars

    def set_max_stars(self, stars_to_collect: float):
        self.max_stars = self._clamp_stars_to_collect(stars_to_collect)
        self.stars_collected = min(self.stars_collected, self.max_stars)

    def reset(self):
        self.stars_collected = 0
        self.set_max_stars(self.get_stars_to_collect())
        self._trigger_repetition_count = 0
        self._trigger_session_remaining_s = max(
            0.0, float(self.get_training_duration_minutes()) * 60.0
        )
        self._is_trigger_session_mode = False
        self._trigger_session_started = False
        self.countdown_timer = 0.0
        self._cycle_phase = "flexion"
        self.flexor_chart.samples = []
        self.extensor_chart.samples = []
        self.is_motor_output_enabled = False
        self._update_start_stop_button_style()
        self._active_muscle = None
        # Reset should return the hand to fully open (0% flexion).
        self._grip_target_hold = 0.0
        self._last_target_direction = 0
        self._last_command_time = 0.0
        self._show_great_job = False
        self._great_job_muscle = None
        self._trigger_go_latched_phase = None
        self._trigger_maintain_active_phase = None
        self._trigger_phase_wait_timer = 0.0
        self._trigger_require_relax_phase = None
        self._trigger_require_relax_phase = None
        self._flexor_noise_floor_hist.clear()
        self._extensor_noise_floor_hist.clear()

    def _reset(self):
        self.reset()
        self.reset_game_cb()
        self._menu_open = False

    def _exit(self):
        self._menu_open = False
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        pygame.event.pump()

    def _toggle_run_pause(self):
        self._menu_open = False
        is_starting = not self.is_motor_output_enabled
        if is_starting and self._effective_training_mode == "none":
            self._update_start_stop_button_style()
            return
        trigger_mode_selected = str(self.get_training_trigger_mode() or "auto").strip().lower() in {
            "trigger-and-go",
            "trigger-and-maintain",
        }
        trigger_can_run = trigger_mode_selected and self._effective_training_mode == "both"
        first_start_this_session = False
        if is_starting and trigger_can_run:
            start_new_session = (not self._trigger_session_started) or self._trigger_session_remaining_s <= 0.0
            if start_new_session:
                self._trigger_repetition_count = 0
                self._trigger_session_remaining_s = max(
                    0.0, float(self.get_training_duration_minutes()) * 60.0
                )
                self._trigger_phase_wait_timer = 0.0
                first_start_this_session = True
            self._trigger_session_started = True
        self.is_motor_output_enabled = not self.is_motor_output_enabled
        self._update_start_stop_button_style()
        if self.is_motor_output_enabled:
            self.play_start_chime()
            should_rehome = (not trigger_can_run) or first_start_this_session
            if should_rehome:
                # Re-home on non-trigger start and trigger first-start only.
                start_pos = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
                self._grip_target_hold = snap_grip_target(
                    grip_target=start_pos,
                    grip_step=self.grip_step,
                )
                self._last_target_direction = 0
                self.send_grip(self._grip_target_hold)
            self._last_command_time = time.time()
            self._show_great_job = False
            self._great_job_muscle = None

    def _get_status_label_text(self) -> str:
        if not self.is_motor_output_enabled:
            if self._effective_training_mode == "none":
                return self._t("status_no_emg_sensor_connected")
            return self._t("status_lets_start")
        if self._effective_training_mode == "none":
            return self._t("status_no_emg_sensor_connected")

        if self._show_great_job:
            return self._t("status_great_job")

        if self.countdown_timer > 0.0:
            cd = int(self.countdown_timer) + (1 if self.countdown_timer - int(self.countdown_timer) > 0 else 0)
            phase = self._status_phase()
            if phase == "flexion":
                return self._t("status_hold_on_flexion", count=cd)
            return self._t("status_hold_on_extension", count=cd)

        phase = self._status_phase()
        phase_games_on_text = (
            self._t("status_games_on_flexion")
            if phase == "flexion"
            else self._t("status_games_on_extension")
        )

        if self._active_muscle is None:
            return phase_games_on_text

        if self._effective_training_mode == "flexor_only":
            target_muscle = "flexor"
        elif self._effective_training_mode == "extensor_only":
            target_muscle = "extensor"
        else:
            target_muscle = "flexor" if self._cycle_phase == "flexion" else "extensor"
        if self._active_muscle == target_muscle:
            return phase_games_on_text

        if phase == "flexion":
            return self._t("status_try_harder_flexion")
        return self._t("status_try_harder_extension")

    def _status_phase(self) -> str:
        if self._effective_training_mode == "flexor_only":
            return "flexion"
        if self._effective_training_mode == "extensor_only":
            return "extension"
        return self._cycle_phase

    def _draw_phase_arrow(self, surface: pygame.Surface):
        if not self.is_motor_output_enabled:
            return
        if self._effective_training_mode == "none":
            return

        if self._effective_training_mode == "flexor_only":
            target_muscle = "flexor"
        elif self._effective_training_mode == "extensor_only":
            target_muscle = "extensor"
        else:
            target_muscle = "flexor" if self._cycle_phase == "flexion" else "extensor"
        target_bar = self.flexor_bar if target_muscle == "flexor" else self.extensor_bar
        target_on_left = target_bar.rect.centerx < self.hand_gauge.center[0]

        s = lambda v: max(1, int(round(v * self.ui_scale)))
        # Keep direction arrow near the top status text area.
        cy = self._title_y + self.font_big.get_height() + s(120)
        tip_clearance = s(10)
        size_scale = 2
        arrow_len = s(140 * size_scale)
        arrow_half_height = s(48 * size_scale)
        shaft_half_height = s(18 * size_scale)
        # Move arrow further down by one full arrow height.
        cy += arrow_half_height * 2
        # Move arrow back up by half of its own height.
        cy += arrow_half_height

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
        arrow_outline = (30, 30, 30) if self._is_dark_theme else WHITE
        pygame.draw.polygon(surface, arrow_outline, points, width=max(2, s(3)))

    def _apply_active_muscle_label_style(self):
        """
        Visually indicate current arbitration winner by emphasizing that channel label.
        """
        pulse = 0.5 + 0.5 * math.sin(time.time() * 2.0 * math.pi * 1.5)
        boost = int(70 * pulse)
        inactive_color = (55, 55, 55) if self._is_dark_theme else (120, 120, 120)

        if self._active_muscle == "flexor":
            base_r, base_g, base_b = ((35, 120, 195) if self._is_dark_theme else (95, 165, 235))
            self.flexor_label.color = (
                max(0, min(255, base_r + boost // 4)),
                max(0, min(255, base_g + boost // 2)),
                max(0, min(255, base_b + boost)),
            )
            self.extensor_label.color = inactive_color
        elif self._active_muscle == "extensor":
            base_r, base_g, base_b = ((175, 60, 60) if self._is_dark_theme else (220, 110, 110))
            self.extensor_label.color = (
                max(0, min(255, base_r + boost)),
                max(0, min(255, base_g + boost // 3)),
                max(0, min(255, base_b + boost // 3)),
            )
            self.flexor_label.color = inactive_color
        else:
            base_idle = (60, 60, 60) if self._is_dark_theme else (130, 130, 130)
            self.flexor_label.color = base_idle
            self.extensor_label.color = base_idle

    def _draw_active_muscle_bar_glow(self, surface: pygame.Surface):
        """
        Draw a high-contrast pulsing glow around the currently active muscle bar.
        """
        if self._active_muscle == "flexor":
            target_bar = self.flexor_bar
            glow_rgb = (35, 125, 225)
        elif self._active_muscle == "extensor":
            target_bar = self.extensor_bar
            glow_rgb = (230, 75, 75)
        else:
            return

        pulse = 0.5 + 0.5 * math.sin(time.time() * 2.0 * math.pi * 1.5)
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        glow_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for inflate_px, fill_alpha, border_alpha, border_width in (
            (s(28), int(10 + 14 * pulse), int(72 + 72 * pulse), max(2, s(3))),
            (s(18), int(14 + 20 * pulse), int(110 + 90 * pulse), max(2, s(3))),
            (s(10), int(22 + 28 * pulse), int(155 + 80 * pulse), max(3, s(4))),
        ):
            r = target_bar.rect.inflate(inflate_px, inflate_px)
            radius = max(6, min(24, int(min(r.w, r.h) * 0.14)))
            pygame.draw.rect(
                glow_surface,
                (glow_rgb[0], glow_rgb[1], glow_rgb[2], max(0, min(120, fill_alpha))),
                r,
                border_radius=radius,
            )
            pygame.draw.rect(
                glow_surface,
                (glow_rgb[0], glow_rgb[1], glow_rgb[2], max(0, min(255, border_alpha))),
                r,
                width=border_width,
                border_radius=radius,
            )
        surface.blit(glow_surface, (0, 0))

    def handle_event(self, event: pygame.event.Event):
        click_should_toggle_start_stop = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            menu_was_open = self._menu_open
            clicked_menu_button = self.menu_button.rect.collidepoint(event.pos)
            clicked_dropdown_button = False
            if menu_was_open:
                dropdown_buttons = (
                    self.settings_button,
                    self.reset_button,
                    self.start_pause_button,
                    self.mirror_button,
                    self.sound_toggle_button,
                    self.music_toggle_button,
                    self.exit_button,
                )
                clicked_dropdown_button = any(button.rect.collidepoint(event.pos) for button in dropdown_buttons)
            click_should_toggle_start_stop = not clicked_menu_button and not clicked_dropdown_button

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._toggle_run_pause()
            elif event.key == pygame.K_SPACE:
                self._reset()
            elif event.key == pygame.K_s:
                self._open_settings_from_menu()
            elif event.key == pygame.K_m:
                self._toggle_mirror_layout()

        self.menu_button.handle_event(event)
        if self._menu_open:
            self.settings_button.handle_event(event)
            self.reset_button.handle_event(event)
            self.start_pause_button.handle_event(event)
            self.mirror_button.handle_event(event)
            self.sound_toggle_button.handle_event(event)
            self.music_toggle_button.handle_event(event)
            self.exit_button.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                inside_menu = self._menu_panel_rect.collidepoint(event.pos) or self.menu_button.rect.collidepoint(event.pos)
                if not inside_menu:
                    self._menu_open = False

        if click_should_toggle_start_stop:
            self._toggle_run_pause()

    def _sync_hand_gauge_state(
        self,
        *,
        use_flexor: bool,
        use_extensor: bool,
        hand_pos: float,
        hand_start: float,
        raw_target: float,
    ) -> tuple[float, float]:
        # Targets are normalized to each available manipulation range from hand_start:
        # - flexion: [hand_start .. 1.0]
        # - extension: [hand_start .. 0.0]
        target_flexion_ratio = max(0.0, min(1.0, self.get_target_flexion_percent() / 100.0))
        target_extension_ratio = max(0.0, min(1.0, self.get_target_extension_percent() / 100.0))
        target_flexion = hand_start + (1.0 - hand_start) * target_flexion_ratio
        target_extension = hand_start * (1.0 - target_extension_ratio)
        if use_flexor and use_extensor:
            self.hand_gauge.set_mirrored(self._is_mirrored)
            self.hand_gauge.set_channel_visibility(show_flexion=True, show_extension=True)
            self.hand_gauge.set_marker_visibility(
                show_partition=True,
                show_flexion_target=True,
                show_extension_target=True,
            )
            self.hand_gauge.set_value(hand_pos)
            self.hand_gauge.set_partition(hand_start)
            self.hand_gauge.set_targets(target_flexion, target_extension)
        elif use_flexor:
            # Flexor-only: display a single full-range arc where 0% starts at relax threshold.
            # Flip single-channel arc orientation so 0% stays on the flexor-bar side.
            self.hand_gauge.set_mirrored(not self._is_mirrored)
            single_value = max(0.0, min(1.0, raw_target))
            self.hand_gauge.set_channel_visibility(show_flexion=True, show_extension=False)
            self.hand_gauge.set_marker_visibility(
                show_partition=False,
                show_flexion_target=True,
                show_extension_target=False,
            )
            self.hand_gauge.set_value(single_value)
            self.hand_gauge.set_partition(0.0)
            self.hand_gauge.set_targets(target_flexion_ratio, 0.0)
        elif use_extensor:
            # Extensor-only: invert command-space value so progress grows from relax threshold.
            self.hand_gauge.set_mirrored(self._is_mirrored)
            single_value = max(0.0, min(1.0, 1.0 - raw_target))
            self.hand_gauge.set_channel_visibility(show_flexion=False, show_extension=True)
            self.hand_gauge.set_marker_visibility(
                show_partition=False,
                show_flexion_target=False,
                show_extension_target=True,
            )
            self.hand_gauge.set_value(single_value)
            self.hand_gauge.set_partition(0.0)
            self.hand_gauge.set_targets(0.0, target_extension_ratio)
        else:
            self.hand_gauge.set_mirrored(self._is_mirrored)
            self.hand_gauge.set_channel_visibility(show_flexion=False, show_extension=False)
            self.hand_gauge.set_marker_visibility(
                show_partition=False,
                show_flexion_target=False,
                show_extension_target=False,
            )
            self.hand_gauge.set_value(hand_pos)
            self.hand_gauge.set_partition(hand_start)
            self.hand_gauge.set_targets(target_flexion, target_extension)
        return target_flexion, target_extension

    def _advance_progression_and_rewards(
        self,
        *,
        dt: float,
        hand_pos: float,
        target_flexion: float,
        target_extension: float,
        dual_channel_trigger_mode: bool,
        trigger_wait_seconds: float,
        progress_units_before: int,
        was_complete_before_tick: bool,
    ) -> bool:
        # Game progression stops once all cycles are completed.
        if self._is_trigger_session_mode and self._trigger_session_remaining_s <= 0.0:
            if not was_complete_before_tick:
                self.play_completion_jingle()
            self.countdown_timer = 0.0
            self._trigger_phase_wait_timer = 0.0
            return True
        if self.stars_collected >= self.max_stars:
            if not was_complete_before_tick:
                self.play_completion_jingle()
            self.countdown_timer = 0.0
            self._trigger_phase_wait_timer = 0.0
            return True

        # Single-sensor training should only run the available side's phase.
        if self._effective_training_mode == "flexor_only":
            self._cycle_phase = "flexion"
        elif self._effective_training_mode == "extensor_only":
            self._cycle_phase = "extension"

        # Evaluate current phase success condition against measured hand position.
        # Trigger modes must complete a full-range stroke before phase switch.
        if dual_channel_trigger_mode:
            end_tolerance = max(0.01, self.grip_step * 0.5)
            if self._cycle_phase == "flexion":
                phase_target_reached = hand_pos >= (1.0 - end_tolerance)
            else:
                phase_target_reached = hand_pos <= end_tolerance
        elif self._cycle_phase == "flexion":
            phase_target_reached = hand_pos >= target_flexion
        else:
            phase_target_reached = hand_pos <= target_extension

        use_trigger_wait = dual_channel_trigger_mode
        if phase_target_reached:
            if use_trigger_wait:
                # Trigger modes do not require hold countdown at end position.
                self.countdown_timer = 0.0
                trigger_wait_done = False
                if trigger_wait_seconds <= 0.0:
                    trigger_wait_done = True
                elif self._trigger_phase_wait_timer <= 0.0:
                    self._trigger_phase_wait_timer = trigger_wait_seconds
                else:
                    self._trigger_phase_wait_timer = max(0.0, self._trigger_phase_wait_timer - dt)
                    trigger_wait_done = self._trigger_phase_wait_timer == 0.0

                if trigger_wait_done:
                    self._trigger_phase_wait_timer = 0.0
                    self._show_great_job = True
                    self._great_job_muscle = self._active_muscle
                    if self._effective_training_mode == "both" and self._cycle_phase == "flexion":
                        self._cycle_phase = "extension"
                        if self._is_trigger_session_mode:
                            self._trigger_require_relax_phase = "extension"
                    else:
                        if self._is_trigger_session_mode:
                            self._trigger_repetition_count += 1
                        else:
                            self.stars_collected = min(self.max_stars, self.stars_collected + 1)
                        if self._effective_training_mode == "both":
                            self._cycle_phase = "flexion"
                            if self._is_trigger_session_mode:
                                self._trigger_require_relax_phase = "flexion"
                        elif self._effective_training_mode == "extensor_only":
                            self._cycle_phase = "extension"
                        else:
                            self._cycle_phase = "flexion"
            elif self.countdown_timer <= 0.0:
                # Enter hold period the first frame target becomes true.
                self.countdown_timer = self.get_countdown_seconds()
            else:
                self.countdown_timer = max(0.0, self.countdown_timer - dt)
                if self.countdown_timer == 0.0:
                    self._show_great_job = True
                    self._great_job_muscle = self._active_muscle
                    if self._effective_training_mode == "both" and self._cycle_phase == "flexion":
                        # Half-cycle complete: switch to extension phase.
                        self._cycle_phase = "extension"
                    else:
                        # Single-phase countdowns and full dual-phase cycles both award one star.
                        self.stars_collected = min(self.max_stars, self.stars_collected + 1)
                        if self._effective_training_mode == "both":
                            self._cycle_phase = "flexion"
                        elif self._effective_training_mode == "extensor_only":
                            self._cycle_phase = "extension"
                        else:
                            self._cycle_phase = "flexion"
        else:
            # Hold requirement must be continuous; any break resets timer.
            self.countdown_timer = 0.0
            self._trigger_phase_wait_timer = 0.0

        progress_units_after = self._progress_units()
        if progress_units_after > progress_units_before:
            self.play_progress_bell()
        if (not was_complete_before_tick) and self._is_session_complete():
            self.play_completion_jingle()
        return False

    def update(self, dt: float):
        # ---- Phase 1: theme/button refresh and per-frame globals ----
        self._refresh_theme()
        self._update_sound_toggle_button()
        self._update_music_toggle_button()
        latest_blur = max(0.0, min(100.0, float(self.get_background_blur_percent())))
        if abs(latest_blur - self._background_blur_percent) >= 0.1:
            self.set_background_blur_percent(latest_blur)
        self.set_max_stars(self.get_stars_to_collect())
        progress_units_before = self._progress_units()
        was_complete_before_tick = self._is_session_complete()

        # ---- Phase 2: sensor acquisition + runtime parameter snapshot ----
        # Main closed-loop control tick:
        # EMG activations -> active muscle -> grip target -> exo command + game progression.
        use_flexor, use_extensor, effective_mode = self._resolve_training_channels()
        self._effective_training_mode = effective_mode
        self._show_flexor_channel = use_flexor
        self._show_extensor_channel = use_extensor
        self._update_start_stop_button_style()
        emg_flexor = self.emg_flexor_provider() if use_flexor else 0.0
        emg_extensor = self.emg_extensor_provider() if use_extensor else 0.0
        if use_flexor:
            self._flexor_noise_floor_hist.append(emg_flexor)
        else:
            self._flexor_noise_floor_hist.clear()
        if use_extensor:
            self._extensor_noise_floor_hist.append(emg_extensor)
        else:
            self._extensor_noise_floor_hist.clear()
        # Read tunables every frame so Settings changes apply immediately.
        hand_start = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
        base_thr = self.get_threshold_percent() / 100.0
        relax_flexion_thr = self.get_relax_flexion_percent() / 100.0
        relax_flexion_thr = max(0.0, min(0.99, relax_flexion_thr))
        relax_extension_thr = self.get_relax_extension_percent() / 100.0
        relax_extension_thr = max(0.0, min(0.99, relax_extension_thr))
        # Keep threshold < 1.0 to preserve usable normalization denominator.
        base_thr = max(0.0, min(0.99, base_thr))
        trigger_thr = max(
            0.0, min(0.99, float(self.get_trigger_threshold_percent()) / 100.0)
        )
        training_trigger_mode = str(self.get_training_trigger_mode() or "auto").strip().lower()
        if training_trigger_mode not in {"auto", "trigger-and-go", "trigger-and-maintain"}:
            training_trigger_mode = "auto"
        trigger_wait_seconds = max(0.0, float(self.get_trigger_wait_seconds()))
        (
            _flexor_floor,
            _extensor_floor,
            _flexor_guard_thr,
            _extensor_guard_thr,
            flexor_thr,
            extensor_thr,
        ) = compute_effective_thresholds(
            base_thr=base_thr,
            flexor_noise_history=self._flexor_noise_floor_hist,
            extensor_noise_history=self._extensor_noise_floor_hist,
            noise_floor_percentile=self.noise_floor_percentile,
            noise_floor_guard=self.noise_floor_guard,
        )
        self.grip_step = max(0.01, min(1.0, self.get_grip_step_percent() / 100.0))
        command_rate_hz = max(1.0, self.get_command_rate_hz())
        self.command_update_interval = 1.0 / command_rate_hz
        self.activation_hysteresis = max(0.0, min(0.5, self.get_activation_hysteresis_percent() / 100.0))
        self.deactivation_hysteresis = max(0.0, min(0.5, self.get_deactivation_hysteresis_percent() / 100.0))
        self.forward_deadband = max(0.0, min(1.0, self.get_forward_deadband_percent() / 100.0))
        self.reversal_deadband = max(0.0, min(1.0, self.get_reversal_deadband_percent() / 100.0))
        flexor_activate_thr = min(1.0, flexor_thr + self.activation_hysteresis)
        flexor_deactivate_thr = max(0.0, flexor_thr - self.deactivation_hysteresis)
        extensor_activate_thr = min(1.0, extensor_thr + self.activation_hysteresis)
        extensor_deactivate_thr = max(0.0, extensor_thr - self.deactivation_hysteresis)

        self.flexor_bar.set_value(emg_flexor if use_flexor else 0.0)
        self.extensor_bar.set_value(emg_extensor if use_extensor else 0.0)
        self.flexor_bar.set_threshold_band(
            base_thr,
            flexor_activate_thr,
            flexor_deactivate_thr,
        )
        self.extensor_bar.set_threshold_band(
            base_thr,
            extensor_activate_thr,
            extensor_deactivate_thr,
        )

        # Charts run at their own cadence to avoid over-rendering while still
        # reflecting raw packet behavior.
        current_time = time.time()
        if use_flexor and self.flexor_chart.should_update(current_time):
            flexor_raw = self.emg_flexor_raw_provider()
            if flexor_raw:
                self.flexor_chart.add_samples(flexor_raw)
        if use_extensor and self.extensor_chart.should_update(current_time):
            extensor_raw = self.emg_extensor_raw_provider()
            if extensor_raw:
                self.extensor_chart.add_samples(extensor_raw)

        # ---- Phase 3: active-muscle arbitration ----
        if not use_flexor and not use_extensor:
            self._active_muscle = None
        elif use_flexor and use_extensor:
            # Flexor has priority. Add hysteresis to avoid rapid direction toggling near threshold.
            self._active_muscle = choose_active_muscle(
                current_active_muscle=self._active_muscle,
                emg_flexor=emg_flexor,
                emg_extensor=emg_extensor,
                flexor_thr=flexor_thr,
                extensor_thr=extensor_thr,
                activation_hysteresis=self.activation_hysteresis,
                deactivation_hysteresis=self.deactivation_hysteresis,
            )
        elif use_flexor:
            self._active_muscle = "flexor" if emg_flexor >= base_thr else None
        else:
            self._active_muscle = "extensor" if emg_extensor >= base_thr else None
        # "Great Job" feedback is muscle-specific; clear it once control changes side.
        if self._show_great_job and self._active_muscle != self._great_job_muscle:
            self._show_great_job = False
            self._great_job_muscle = None

        # ---- Phase 4: control target synthesis (auto + trigger modes) ----
        # Compute the target position for the robot hand depending on control mode.
        dual_channel_trigger_mode = (
            use_flexor and use_extensor and training_trigger_mode in {"trigger-and-go", "trigger-and-maintain"}
        )
        self._is_trigger_session_mode = dual_channel_trigger_mode
        if dual_channel_trigger_mode:
            phase = "flexion" if self._cycle_phase == "flexion" else "extension"
            target_muscle = "flexor" if phase == "flexion" else "extensor"
            target_emg = emg_flexor if target_muscle == "flexor" else emg_extensor
            trigger_activate_thr = min(1.0, trigger_thr + self.activation_hysteresis)
            trigger_deactivate_thr = max(0.0, trigger_thr - self.deactivation_hysteresis)
            needs_relax_before_rearm = self._trigger_require_relax_phase == phase

            # Keep trigger-and-go latched only within the current phase.
            if self._trigger_go_latched_phase != phase:
                self._trigger_go_latched_phase = None
            if self._trigger_maintain_active_phase != phase:
                self._trigger_maintain_active_phase = None

            # After phase flip in trigger modes, require the new target muscle to
            # relax below deactivation threshold before accepting triggers again.
            if needs_relax_before_rearm and target_emg > trigger_deactivate_thr:
                self._active_muscle = None
                raw_target = self._grip_target_hold
            elif training_trigger_mode == "trigger-and-go":
                self._trigger_require_relax_phase = None
                self._trigger_maintain_active_phase = None
                if self._trigger_go_latched_phase is None and target_emg >= trigger_activate_thr:
                    self._trigger_go_latched_phase = phase
                if self._trigger_go_latched_phase == "flexion":
                    self._active_muscle = "flexor"
                    raw_target = 1.0
                elif self._trigger_go_latched_phase == "extension":
                    self._active_muscle = "extensor"
                    raw_target = 0.0
                else:
                    self._active_muscle = None
                    raw_target = self._grip_target_hold
            elif training_trigger_mode == "trigger-and-maintain":
                self._trigger_require_relax_phase = None
                self._trigger_go_latched_phase = None
                maintain_was_active = self._trigger_maintain_active_phase == phase
                if self._trigger_maintain_active_phase is None:
                    if target_emg >= trigger_activate_thr:
                        self._trigger_maintain_active_phase = phase
                elif target_emg < trigger_deactivate_thr:
                    self._trigger_maintain_active_phase = None
                maintain_is_active = self._trigger_maintain_active_phase == phase

                if maintain_is_active:
                    self._active_muscle = target_muscle
                    raw_target = 1.0 if target_muscle == "flexor" else 0.0
                else:
                    self._active_muscle = None
                    if maintain_was_active and not maintain_is_active:
                        # Falling edge: freeze at current measured position and
                        # immediately send one hold command to prevent endpoint drift.
                        hold_target = snap_grip_target(
                            grip_target=self.hand_pos_provider(),
                            grip_step=self.grip_step,
                        )
                        self._grip_target_hold = hold_target
                        self._last_target_direction = 0
                        raw_target = hold_target
                        if self.is_motor_output_enabled:
                            self.send_grip(hold_target)
                            self._last_command_time = current_time
                    else:
                        raw_target = self._grip_target_hold
        elif use_flexor and use_extensor and self._active_muscle == "flexor":
            # Above-threshold flexor activation maps linearly to [hand_start .. fully closed].
            self._trigger_go_latched_phase = None
            self._trigger_maintain_active_phase = None
            self._trigger_require_relax_phase = None
            flex_norm = (emg_flexor - base_thr) / max(0.01, 1.0 - base_thr)
            flex_norm = max(0.0, min(1.0, flex_norm))
            raw_target = hand_start + (1.0 - hand_start) * flex_norm
        elif use_flexor and use_extensor and self._active_muscle == "extensor":
            # Above-threshold extensor activation maps linearly to [hand_start .. fully open].
            self._trigger_go_latched_phase = None
            self._trigger_maintain_active_phase = None
            self._trigger_require_relax_phase = None
            ext_norm = (emg_extensor - base_thr) / max(0.01, 1.0 - base_thr)
            ext_norm = max(0.0, min(1.0, ext_norm))
            raw_target = hand_start * (1.0 - ext_norm)
        elif use_flexor and not use_extensor:
            # Single-channel mode ignores hand_start and maps relax->open, contract->close.
            self._trigger_go_latched_phase = None
            self._trigger_maintain_active_phase = None
            self._trigger_require_relax_phase = None
            flex_norm = (emg_flexor - relax_flexion_thr) / max(0.01, 1.0 - relax_flexion_thr)
            raw_target = max(0.0, min(1.0, flex_norm))
        elif use_extensor and not use_flexor:
            # Extensor-only mode: contract->open, relax->close.
            self._trigger_go_latched_phase = None
            self._trigger_maintain_active_phase = None
            self._trigger_require_relax_phase = None
            ext_norm = (emg_extensor - relax_extension_thr) / max(0.01, 1.0 - relax_extension_thr)
            raw_target = 1.0 - max(0.0, min(1.0, ext_norm))
        else:
            # No valid active side: hold last snapped target for stable behavior.
            self._trigger_go_latched_phase = None
            self._trigger_maintain_active_phase = None
            self._trigger_require_relax_phase = None
            raw_target = self._grip_target_hold

        # Quantize first, then stabilize direction changes in command space.
        snapped_target = snap_grip_target(
            grip_target=raw_target,
            grip_step=self.grip_step,
        )
        grip_target, self._last_target_direction = stabilize_grip_target(
            candidate_target=snapped_target,
            hold_target=self._grip_target_hold,
            last_direction=self._last_target_direction,
            forward_deadband=self.forward_deadband,
            reversal_deadband=self.reversal_deadband,
        )
        self._grip_target_hold = grip_target

        # ---- Phase 5: command output ----
        # Rate-limit outgoing motor commands to a fixed command_rate_hz.
        if self.is_motor_output_enabled and (current_time - self._last_command_time >= self.command_update_interval):
            self.send_grip(grip_target)
            self._last_command_time = current_time

        if self._is_trigger_session_mode and self.is_motor_output_enabled and self._trigger_session_remaining_s > 0.0:
            self._trigger_session_remaining_s = max(0.0, self._trigger_session_remaining_s - dt)

        # ---- Phase 6: visual gauge state sync ----
        hand_pos = self.hand_pos_provider()
        target_flexion, target_extension = self._sync_hand_gauge_state(
            use_flexor=use_flexor,
            use_extensor=use_extensor,
            hand_pos=hand_pos,
            hand_start=hand_start,
            raw_target=raw_target,
        )

        # ---- Phase 7: progression state machine and rewards ----
        if self._advance_progression_and_rewards(
            dt=dt,
            hand_pos=hand_pos,
            target_flexion=target_flexion,
            target_extension=target_extension,
            dual_channel_trigger_mode=dual_channel_trigger_mode,
            trigger_wait_seconds=trigger_wait_seconds,
            progress_units_before=progress_units_before,
            was_complete_before_tick=was_complete_before_tick,
        ):
            return

    def _draw_stars(self, surface: pygame.Surface):
        draw_game_stars(self, surface, YELLOW, GRAY, WHITE)

    def _draw_trigger_session_stats(self, surface: pygame.Surface):
        draw_game_trigger_session_stats(self, surface)

    def _draw_background_and_title(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        if self._background_image is not None:
            surface.blit(self._background_image, (0, 0))
        else:
            surface.fill(GAME_BG)
        if self._background_light_overlay_alpha > 0:
            light_overlay = pygame.Surface((self.screen_rect.w, self.screen_rect.h), pygame.SRCALPHA)
            light_overlay.fill((255, 255, 255, self._background_light_overlay_alpha))
            surface.blit(light_overlay, (0, 0))

        title_text = self._t("title_main")
        title = self.font_big.render(title_text, True, self._title_text_color)
        title_y = self._title_y
        title_x = self.screen_rect.centerx - title.get_width() // 2
        title_pos = (title_x, title_y)
        box_pad_x = s(36)
        box_pad_y = s(18)
        title_box_rect = pygame.Rect(
            title_x - box_pad_x,
            title_y - box_pad_y,
            title.get_width() + 2 * box_pad_x,
            title.get_height() + 2 * box_pad_y,
        )
        title_box = pygame.Surface(title_box_rect.size, pygame.SRCALPHA)
        title_box.fill(self._title_box_fill_rgba)
        surface.blit(title_box, title_box_rect.topleft)
        title_box_outline = (30, 30, 30) if self._is_dark_theme else WHITE
        pygame.draw.rect(surface, title_box_outline, title_box_rect, width=max(1, s(2)), border_radius=s(22))
        draw_outlined_text(
            surface,
            self.font_big,
            title_text,
            self._title_text_color,
            title_pos,
            outline_color=self._title_text_outline,
            outline_width=1,
        )

    def _draw_gameplay_hud(self, surface: pygame.Surface):
        if self._is_trigger_session_mode:
            self._draw_trigger_session_stats(surface)
        else:
            self._draw_stars(surface)
        self.hand_gauge.draw(surface, self.font_small)
        self._draw_phase_arrow(surface)
        self._draw_active_muscle_bar_glow(surface)
        self._apply_active_muscle_label_style()
        if self._show_flexor_channel:
            self.flexor_bar.draw(surface, self.font_tiny)
            self.flexor_chart.draw(surface)
            self.flexor_label.draw(surface)
        if self._show_extensor_channel:
            self.extensor_bar.draw(surface, self.font_tiny)
            self.extensor_chart.draw(surface)
            self.extensor_label.draw(surface)

    def _draw_status_text(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        status_font = pick_font(
            int(self.font_big.get_height() * 1.2),
            prefer_cjk=self._is_cjk_language(self._current_language),
        )
        status_scale = 0.8
        status_outline_width = 3

        def _draw_scaled_status_text(text: str, color):
            text_img = status_font.render(text, True, color)
            src_w = text_img.get_width() + 2 * status_outline_width
            src_h = text_img.get_height() + 2 * status_outline_width
            status_surface = pygame.Surface((src_w, src_h), pygame.SRCALPHA)
            draw_outlined_text(
                status_surface,
                status_font,
                text,
                color,
                (status_outline_width, status_outline_width),
                outline_color=self._status_text_outline,
                outline_width=status_outline_width,
            )
            scaled_w = max(1, int(round(src_w * status_scale)))
            scaled_h = max(1, int(round(src_h * status_scale)))
            scaled_status = pygame.transform.smoothscale(status_surface, (scaled_w, scaled_h))
            status_x = self.screen_rect.centerx - scaled_w // 2
            status_y = self._title_y + self.font_big.get_height() + s(200) - scaled_h // 2
            surface.blit(scaled_status, (status_x, status_y))

        if self._is_trigger_session_mode and self._trigger_session_remaining_s <= 0.0:
            _draw_scaled_status_text(self._t("trigger_session_complete"), self._status_win_color)
        elif self.stars_collected >= self.max_stars:
            _draw_scaled_status_text(self._t("win_text"), self._status_win_color)
        else:
            _draw_scaled_status_text(self._get_status_label_text(), self._status_progress_color)

    def _draw_menu_and_footer(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        # Draw menu last so it always stays on top.
        self.menu_button.draw(surface)
        icon_pad_x = max(6, self.menu_button.rect.w // 4)
        icon_gap = max(4, self.menu_button.rect.h // 6)
        icon_width = self.menu_button.rect.w - 2 * icon_pad_x
        line_w = max(2, self.menu_button.rect.h // 12)
        icon_center_y = self.menu_button.rect.centery
        for offset in (-icon_gap, 0, icon_gap):
            y = icon_center_y + offset
            pygame.draw.line(
                surface,
                WHITE if self._is_dark_theme else BLACK,
                (self.menu_button.rect.x + icon_pad_x, y),
                (self.menu_button.rect.x + icon_pad_x + icon_width, y),
                width=line_w,
            )
        if self._menu_open:
            pygame.draw.rect(surface, self._menu_panel_bg, self._menu_panel_rect, border_radius=max(6, s(10)))
            pygame.draw.rect(surface, self._menu_panel_border, self._menu_panel_rect, width=2, border_radius=max(6, s(10)))
            self.settings_button.draw(surface)
            self.reset_button.draw(surface)
            self.start_pause_button.draw(surface)
            self.mirror_button.draw(surface)
            self.sound_toggle_button.draw(surface)
            self.music_toggle_button.draw(surface)
            self.exit_button.draw(surface)

        version_text = f"v{self.game_version}"
        version_img = self.font_tiny.render(version_text, True, self._version_text_color)
        version_x = self.screen_rect.w - version_img.get_width() - s(20)
        version_y = self.screen_rect.h - version_img.get_height() - s(20)
        draw_outlined_text(
            surface,
            self.font_tiny,
            version_text,
            self._version_text_color,
            (version_x, version_y),
            outline_color=self._version_text_outline,
            outline_width=2,
        )

    def draw(self, surface: pygame.Surface):
        # ---- Draw pass A: background + title ----
        self._draw_background_and_title(surface)

        # ---- Draw pass B: gameplay HUD + widgets ----
        self._draw_gameplay_hud(surface)

        # ---- Draw pass C: central status text ----
        self._draw_status_text(surface)

        # ---- Draw pass D: top-layer menu + version footer ----
        self._draw_menu_and_footer(surface)

