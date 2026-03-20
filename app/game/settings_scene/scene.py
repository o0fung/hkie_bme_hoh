import math
import threading
import time
from typing import Callable, Dict, List, Optional, Set

import pygame

from ...ui.widgets import (
    Button,
    NumericStepper,
    OptionStepper,
    Panel,
    draw_outlined_text,
)
from ...ui.fonts import pick_font
from ..scene_manager import Scene
from .ops import (
    apply_stepper_scroll,
    apply_theme_styles as apply_settings_theme_styles,
    apply_translations as apply_settings_translations,
    build_device_buttons_from_bound,
    compute_device_list_signature,
    get_display_devices,
    refresh_stepper_layout,
    refresh_theme as refresh_settings_theme,
    scan_devices,
    update_bind_button_states,
)
from .layout_ops import (
    active_reset_button_text,
    build_language_buttons,
    build_tab_buttons,
    resize_close_button,
    update_advanced_toggle_button,
    update_reset_button_label,
    update_language_button_states,
    update_sim_toggle_button_layout,
)
from ...ble.ble_manager import BLEManager, BLEDeviceInfo

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 100, 100)
GREEN = (80, 200, 120)
YELLOW = (240, 210, 80)
RED = (230, 80, 80)
GAME_BG = (10, 20, 30)


class SettingsScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ui_scale: float,
        ble: BLEManager,
        on_close: Callable[[], None],
        get_text: Callable[[str], str],
        set_game_language: Callable[[str], None],
        get_game_language: Callable[[], str],
        get_language_options: Callable[[], List[tuple[str, str]]],
        set_emg_max_flexor: Callable[[float], None],
        set_emg_max_extensor: Callable[[float], None],
        set_training_muscle_mode: Callable[[str], None],
        set_training_trigger_mode: Callable[[str], None],
        set_hand_start_percent: Callable[[float], None],
        set_threshold_percent: Callable[[float], None],
        set_trigger_threshold_percent: Callable[[float], None],
        set_trigger_wait_seconds: Callable[[float], None],
        set_relax_flexion_percent: Callable[[float], None],
        set_relax_extension_percent: Callable[[float], None],
        set_countdown_seconds: Callable[[float], None],
        set_stars_to_collect: Callable[[float], None],
        set_training_duration_minutes: Callable[[float], None],
        set_target_flexion_percent: Callable[[float], None],
        set_target_extension_percent: Callable[[float], None],
        set_grip_step_percent: Callable[[float], None],
        set_command_rate_hz: Callable[[float], None],
        set_activation_hysteresis_percent: Callable[[float], None],
        set_deactivation_hysteresis_percent: Callable[[float], None],
        set_forward_deadband_percent: Callable[[float], None],
        set_reversal_deadband_percent: Callable[[float], None],
        set_background_blur_percent: Callable[[float], None],
        set_sound_enabled: Callable[[bool], None],
        set_music_enabled: Callable[[bool], None],
        set_sound_effect_volume_percent: Callable[[float], None],
        set_music_volume_percent: Callable[[float], None],
        set_theme_mode: Callable[[str], None],
        set_dynamic_mvc_alpha_up: Callable[[float], None],
        set_dynamic_mvc_alpha_down: Callable[[float], None],
        set_dynamic_mvc_up_margin_ratio: Callable[[float], None],
        set_dynamic_mvc_hold_activity_ratio: Callable[[float], None],
        set_dynamic_mvc_decay_trigger_ratio: Callable[[float], None],
        set_dynamic_mvc_decay_grace_seconds: Callable[[float], None],
        get_is_dark_theme: Callable[[], bool],
        on_bind_flexor_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_extensor_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_exo_hand: Callable[[Optional[BLEDeviceInfo]], None],
        on_swap_flexor_extensor: Callable[[], None],
        consume_disconnect_notice: Callable[[], Optional[str]],
        init_values: dict,
        default_values: Optional[dict] = None,
        allowed_mac_addresses: Optional[Set[str]] = None,
        get_bound_flexor_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_extensor_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_exo_hand: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_text_keys: Optional[Callable[[], Set[str]]] = None,
    ):
        self.screen_rect = screen_rect
        self.ui_scale = ui_scale
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.ble = ble
        self.on_close = on_close
        self.get_text = get_text
        self.get_text_keys = get_text_keys or (lambda: set())
        self._default_values = dict(default_values or {})
        self.set_game_language = set_game_language
        self.get_game_language = get_game_language
        self.get_language_options = get_language_options
        self._set_theme_mode = set_theme_mode
        self.get_is_dark_theme = get_is_dark_theme
        self._is_dark_theme = bool(self.get_is_dark_theme())
        self._current_language = self.get_game_language()
        self.font_title = pick_font(s(36), prefer_cjk=True)
        self.font_subtitle = pick_font(s(30), prefer_cjk=True)
        self.font = pick_font(s(24), prefer_cjk=True)
        self.font_hint = pick_font(s(16), prefer_cjk=True)
        self.font_welcome_title = pick_font(s(30), prefer_cjk=True)
        self.font_welcome_body = pick_font(s(20), prefer_cjk=True)
        self.allowed_mac_addresses = allowed_mac_addresses or set()

        self.panel = Panel(pygame.Rect(s(80), s(80), screen_rect.w - s(160), screen_rect.h - s(160)), bg=(0, 0, 0), alpha=210)
        self.close_btn = Button(
            pygame.Rect(self.panel.rect.x + s(20), self.panel.rect.bottom - s(60), s(220), s(40)),
            self._t("settings_btn_apply"),
            self.font,
            on_click=on_close,
        )
        self._resize_close_button()
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
            self._t("settings_btn_scan_ble"),
            self.font,
            on_click=self._scan,
        )
        sim_text = self._sim_toggle_text()
        sim_text_width = self.font.size(sim_text)[0]
        sim_btn_width = max(s(220), sim_text_width + s(40))
        sim_btn_width = min(self._right_col_width - scan_btn_w - s(12), sim_btn_width)
        self.sim_toggle = Button(
            pygame.Rect(self.scan_btn.rect.right + s(12), self.panel.rect.y + s(70), sim_btn_width, s(40)),
            sim_text,
            self.font,
            on_click=self._toggle_sim,
        )
        self.swap_btn = Button(
            pygame.Rect(self._right_col_x, self.panel.rect.y + s(116), max(s(180), self._right_col_width - s(20)), s(36)),
            self._t("settings_btn_swap_flexor_extensor"),
            self.font_hint,
            on_click=on_swap_flexor_extensor,
        )
        self._set_training_muscle_mode = set_training_muscle_mode
        self._training_muscle_modes = ["auto", "flexor_only", "extensor_only", "both"]
        incoming_mode = str(init_values.get("training_muscle_mode", "auto")).strip().lower()
        self._training_muscle_mode = (
            incoming_mode if incoming_mode in self._training_muscle_modes else "auto"
        )
        self._training_muscle_mode_buttons: List[Button] = []
        self._training_muscle_mode_button_modes: List[str] = []
        self._training_muscle_label_text = self._t("settings_training_muscle_label")
        for mode in self._training_muscle_modes:
            btn = Button(
                pygame.Rect(self._content_left + s(10), self.panel.rect.y + s(120), s(120), s(36)),
                "",
                self.font_hint,
                on_click=self._create_training_muscle_mode_click_handler(mode),
            )
            self._training_muscle_mode_buttons.append(btn)
            self._training_muscle_mode_button_modes.append(mode)
        self._training_muscle_toggle_base_y: Optional[int] = None
        self._update_training_muscle_mode_buttons()
        self._set_training_trigger_mode = set_training_trigger_mode
        self._set_sound_enabled = set_sound_enabled
        self._set_music_enabled = set_music_enabled
        self._training_trigger_modes = ["auto", "trigger-and-go", "trigger-and-maintain"]
        incoming_trigger_mode = str(init_values.get("training_trigger_mode", "auto")).strip().lower()
        self._training_trigger_mode = (
            incoming_trigger_mode if incoming_trigger_mode in self._training_trigger_modes else "auto"
        )
        self._audio_enabled_options = [("on", self._t("settings_state_on")), ("off", self._t("settings_state_off"))]
        self._sound_enabled = "on" if bool(init_values.get("sound_enabled", True)) else "off"
        self._music_enabled = "on" if bool(init_values.get("music_enabled", True)) else "off"
        self._training_trigger_mode_buttons: List[Button] = []
        self._training_trigger_mode_button_modes: List[str] = []
        self._training_trigger_label_text = self._t("settings_training_trigger_label")
        for mode in self._training_trigger_modes:
            btn = Button(
                pygame.Rect(self._content_left + s(10), self.panel.rect.y + s(120), s(120), s(36)),
                "",
                self.font_hint,
                on_click=self._create_training_trigger_mode_click_handler(mode),
            )
            self._training_trigger_mode_buttons.append(btn)
            self._training_trigger_mode_button_modes.append(mode)
        self._training_trigger_toggle_base_y: Optional[int] = None
        self._update_training_trigger_mode_buttons()
        self._theme_modes = ["system", "dark", "light"]
        self._theme_mode = self._normalize_theme_mode(init_values.get("theme_mode", "system"))

        self.devices: List[BLEDeviceInfo] = []
        self._device_buttons: List[tuple[object, str, BLEDeviceInfo]] = []
        self._last_device_list_signature: Optional[tuple] = None
        self._scan_status = ""
        self._auto_bind_status = ""
        self._scan_thread: Optional[threading.Thread] = None
        self._scan_start_time = 0.0
        self._devices_ready: List[BLEDeviceInfo] = []

        self._device_scroll_offset = 0
        self._scrollbar_dragging = False
        self._last_scroll_y = 0

        x0, y0 = self._content_left, self.panel.rect.y + s(170)
        stepper_labels = [
            (self._t("settings_stepper_emg_max_flexor"), "{:.0f}", init_values.get("emg_max_range_flexor", init_values.get("emg_max_range", 65535))),
            (self._t("settings_stepper_emg_max_extensor"), "{:.0f}", init_values.get("emg_max_range_extensor", init_values.get("emg_max_range", 65535))),
            (self._t("settings_stepper_hand_start_percent"), "{:.0f}%", init_values.get("hand_start_percent", 70)),
            (self._t("settings_stepper_threshold_percent"), "{:.0f}%", init_values.get("threshold_percent", 60)),
            (self._t("settings_stepper_trigger_threshold_percent"), "{:.0f}%", init_values.get("trigger_threshold_percent", 50)),
            (self._t("settings_stepper_trigger_wait_seconds"), "{:.1f}s", init_values.get("trigger_wait_seconds", 1.0)),
            (self._t("settings_stepper_relax_flexion_percent"), "{:.0f}%", init_values.get("relax_flexion_percent", 12)),
            (self._t("settings_stepper_relax_extension_percent"), "{:.0f}%", init_values.get("relax_extension_percent", 12)),
            (self._t("settings_stepper_countdown_seconds"), "{:.0f}", init_values.get("countdown_seconds", 3)),
            (self._t("settings_stepper_stars_to_collect"), "{:.0f}", init_values.get("stars_to_collect", 3)),
            (self._t("settings_stepper_training_duration_minutes"), "{:.0f} min", init_values.get("training_duration_minutes", 20)),
            (self._t("settings_stepper_target_flexion_percent"), "{:.0f}%", init_values.get("target_flexion_percent", 90)),
            (self._t("settings_stepper_target_extension_percent"), "{:.0f}%", init_values.get("target_extension_percent", 30)),
            (self._t("settings_stepper_grip_step_percent"), "{:.0f}%", init_values.get("grip_step_percent", 5)),
            (self._t("settings_stepper_command_rate_hz"), "{:.0f}", init_values.get("command_rate_hz", 10)),
            (self._t("settings_stepper_activate_hysteresis_percent"), "{:.0f}%", init_values.get("activation_hysteresis_percent", 2)),
            (self._t("settings_stepper_release_hysteresis_percent"), "{:.0f}%", init_values.get("deactivation_hysteresis_percent", 5)),
            (self._t("settings_stepper_forward_deadband_percent"), "{:.0f}%", init_values.get("forward_deadband_percent", 0)),
            (self._t("settings_stepper_reverse_deadband_percent"), "{:.0f}%", init_values.get("reversal_deadband_percent", 8)),
            (self._t("settings_stepper_background_blur_percent"), "{:.0f}%", init_values.get("background_blur_percent", 25)),
            (self._t("settings_stepper_sound_effect_volume_percent"), "{:.0f}%", init_values.get("sound_effect_volume_percent", 60)),
            (self._t("settings_stepper_music_volume_percent"), "{:.0f}%", init_values.get("music_volume_percent", 18)),
            (self._t("settings_stepper_mvc_alpha_up"), "{:.2f}", init_values.get("dynamic_mvc_alpha_up", 0.2)),
            (self._t("settings_stepper_mvc_alpha_down"), "{:.2f}", init_values.get("dynamic_mvc_alpha_down", 0.01)),
            (self._t("settings_stepper_mvc_up_margin"), "{:.2f}", init_values.get("dynamic_mvc_up_margin_ratio", 0.03)),
            (self._t("settings_stepper_mvc_hold_ratio"), "{:.2f}", init_values.get("dynamic_mvc_hold_activity_ratio", 0.85)),
            (self._t("settings_stepper_mvc_decay_trigger"), "{:.2f}", init_values.get("dynamic_mvc_decay_trigger_ratio", 0.60)),
            (self._t("settings_stepper_mvc_decay_grace_seconds"), "{:.1f}", init_values.get("dynamic_mvc_decay_grace_seconds", 2.0)),
        ]
        max_label_width = 0
        for label, fmt, val in stepper_labels:
            label_text = f"{label}: {fmt.format(val)}"
            max_label_width = max(max_label_width, self.font.size(label_text)[0])
        theme_mode_label = self._t("settings_theme_mode_label")
        theme_mode_options = self._theme_mode_options()
        if theme_mode_options:
            longest_theme_label = max((display for _, display in theme_mode_options), key=len)
            max_label_width = max(max_label_width, self.font.size(f"{theme_mode_label}: {longest_theme_label}")[0])
        for label_text in (
            self._t("settings_option_sound_enabled"),
            self._t("settings_option_music_enabled"),
        ):
            longest_audio_state = max((display for _, display in self._audio_enabled_options), key=len)
            max_label_width = max(max_label_width, self.font.size(f"{label_text}: {longest_audio_state}")[0])
        button_x = x0 + max_label_width + s(20)
        max_button_x = self._right_col_x - s(140)
        button_x = min(button_x, max_button_x)
        stepper_button_w = s(40)
        stepper_button_h = s(36)
        stepper_button_gap = s(10)
        stepper_text_button_gap = s(20)

        self.step_emg_max_flexor = NumericStepper(
            self._t("settings_stepper_emg_max_flexor"),
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
            self._t("settings_stepper_emg_max_extensor"),
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
            self._t("settings_stepper_hand_start_percent"),
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
            self._t("settings_stepper_threshold_percent"),
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
        self.step_trigger_threshold = NumericStepper(
            self._t("settings_stepper_trigger_threshold_percent"),
            (x0, y0 + s(200)),
            self.font,
            init_values.get("trigger_threshold_percent", 50),
            5,
            5,
            100,
            fmt="{:.0f}%",
            on_change=set_trigger_threshold_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_trigger_wait_seconds = NumericStepper(
            self._t("settings_stepper_trigger_wait_seconds"),
            (x0, y0 + s(250)),
            self.font,
            init_values.get("trigger_wait_seconds", 1.0),
            0.1,
            0.0,
            10.0,
            fmt="{:.1f}s",
            on_change=set_trigger_wait_seconds,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_relax_flexion = NumericStepper(
            self._t("settings_stepper_relax_flexion_percent"),
            (x0, y0 + s(300)),
            self.font,
            init_values.get("relax_flexion_percent", 20),
            1,
            0,
            50,
            fmt="{:.0f}%",
            on_change=set_relax_flexion_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_relax_extension = NumericStepper(
            self._t("settings_stepper_relax_extension_percent"),
            (x0, y0 + s(350)),
            self.font,
            init_values.get("relax_extension_percent", 20),
            1,
            0,
            50,
            fmt="{:.0f}%",
            on_change=set_relax_extension_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_countdown = NumericStepper(
            self._t("settings_stepper_countdown_seconds"),
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
        self.step_stars_to_collect = NumericStepper(
            self._t("settings_stepper_stars_to_collect"),
            (x0, y0 + s(250)),
            self.font,
            init_values.get("stars_to_collect", 3),
            1,
            1,
            7,
            fmt="{:.0f}",
            on_change=set_stars_to_collect,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_training_duration_minutes = NumericStepper(
            self._t("settings_stepper_training_duration_minutes"),
            (x0, y0 + s(300)),
            self.font,
            init_values.get("training_duration_minutes", 20),
            1,
            1,
            240,
            fmt="{:.0f} min",
            on_change=set_training_duration_minutes,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_target_flexion = NumericStepper(
            self._t("settings_stepper_target_flexion_percent"),
            (x0, y0 + s(250)),
            self.font,
            init_values.get("target_flexion_percent", 90),
            5,
            0,
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
            self._t("settings_stepper_target_extension_percent"),
            (x0, y0 + s(300)),
            self.font,
            init_values.get("target_extension_percent", 30),
            5,
            0,
            100,
            fmt="{:.0f}%",
            on_change=set_target_extension_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_grip_step = NumericStepper(
            self._t("settings_stepper_grip_step_percent"),
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
            self._t("settings_stepper_command_rate_hz"),
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
            self._t("settings_stepper_activate_hysteresis_percent"),
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
            self._t("settings_stepper_release_hysteresis_percent"),
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
        self.step_forward_deadband = NumericStepper(
            self._t("settings_stepper_forward_deadband_percent"),
            (x0, y0 + s(550)),
            self.font,
            init_values.get("forward_deadband_percent", 0),
            1,
            0,
            30,
            fmt="{:.0f}%",
            on_change=set_forward_deadband_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_reversal_deadband = NumericStepper(
            self._t("settings_stepper_reverse_deadband_percent"),
            (x0, y0 + s(600)),
            self.font,
            init_values.get("reversal_deadband_percent", 8),
            1,
            0,
            30,
            fmt="{:.0f}%",
            on_change=set_reversal_deadband_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_alpha_up = NumericStepper(
            self._t("settings_stepper_mvc_alpha_up"),
            (x0, y0 + s(650)),
            self.font,
            init_values.get("dynamic_mvc_alpha_up", 0.2),
            0.01,
            0.0,
            1.0,
            fmt="{:.2f}",
            on_change=set_dynamic_mvc_alpha_up,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_alpha_down = NumericStepper(
            self._t("settings_stepper_mvc_alpha_down"),
            (x0, y0 + s(700)),
            self.font,
            init_values.get("dynamic_mvc_alpha_down", 0.01),
            0.01,
            0.0,
            1.0,
            fmt="{:.2f}",
            on_change=set_dynamic_mvc_alpha_down,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_up_margin = NumericStepper(
            self._t("settings_stepper_mvc_up_margin"),
            (x0, y0 + s(750)),
            self.font,
            init_values.get("dynamic_mvc_up_margin_ratio", 0.03),
            0.01,
            0.0,
            1.0,
            fmt="{:.2f}",
            on_change=set_dynamic_mvc_up_margin_ratio,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_hold_activity = NumericStepper(
            self._t("settings_stepper_mvc_hold_ratio"),
            (x0, y0 + s(800)),
            self.font,
            init_values.get("dynamic_mvc_hold_activity_ratio", 0.85),
            0.01,
            0.0,
            1.0,
            fmt="{:.2f}",
            on_change=set_dynamic_mvc_hold_activity_ratio,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_decay_trigger = NumericStepper(
            self._t("settings_stepper_mvc_decay_trigger"),
            (x0, y0 + s(850)),
            self.font,
            init_values.get("dynamic_mvc_decay_trigger_ratio", 0.60),
            0.01,
            0.0,
            1.0,
            fmt="{:.2f}",
            on_change=set_dynamic_mvc_decay_trigger_ratio,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_dynamic_mvc_decay_grace = NumericStepper(
            self._t("settings_stepper_mvc_decay_grace_seconds"),
            (x0, y0 + s(900)),
            self.font,
            init_values.get("dynamic_mvc_decay_grace_seconds", 2.0),
            0.1,
            0.0,
            10.0,
            fmt="{:.1f}",
            on_change=set_dynamic_mvc_decay_grace_seconds,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_background_blur = NumericStepper(
            self._t("settings_stepper_background_blur_percent"),
            (x0, y0 + s(1000)),
            self.font,
            init_values.get("background_blur_percent", 25),
            5,
            0,
            100,
            fmt="{:.0f}%",
            on_change=set_background_blur_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_sound_effect_volume = NumericStepper(
            self._t("settings_stepper_sound_effect_volume_percent"),
            (x0, y0 + s(1050)),
            self.font,
            init_values.get("sound_effect_volume_percent", 60),
            5,
            0,
            100,
            fmt="{:.0f}%",
            on_change=set_sound_effect_volume_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_sound_enabled = OptionStepper(
            self._t("settings_option_sound_enabled"),
            (x0, y0 + s(1100)),
            self.font,
            self._audio_enabled_options,
            self._sound_enabled,
            on_change=self._set_sound_enabled_selected,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_music_enabled = OptionStepper(
            self._t("settings_option_music_enabled"),
            (x0, y0 + s(1150)),
            self.font,
            self._audio_enabled_options,
            self._music_enabled,
            on_change=self._set_music_enabled_selected,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_music_volume = NumericStepper(
            self._t("settings_stepper_music_volume_percent"),
            (x0, y0 + s(1200)),
            self.font,
            init_values.get("music_volume_percent", 18),
            5,
            0,
            100,
            fmt="{:.0f}%",
            on_change=set_music_volume_percent,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self.step_theme_mode = OptionStepper(
            self._t("settings_theme_mode_label"),
            (x0, y0 + s(1250)),
            self.font,
            self._theme_mode_options(),
            self._theme_mode,
            on_change=self._set_theme_mode_selected,
            button_x=button_x,
            button_w=stepper_button_w,
            button_h=stepper_button_h,
            button_gap=stepper_button_gap,
            text_button_gap=stepper_text_button_gap,
        )
        self._stepper_by_id: Dict[str, NumericStepper] = {
            "emg_max_flexor": self.step_emg_max_flexor,
            "emg_max_extensor": self.step_emg_max_extensor,
            "hand_start": self.step_hand_start,
            "threshold": self.step_threshold,
            "trigger_threshold": self.step_trigger_threshold,
            "trigger_wait_seconds": self.step_trigger_wait_seconds,
            "relax_flexion_percent": self.step_relax_flexion,
            "relax_extension_percent": self.step_relax_extension,
            "countdown": self.step_countdown,
            "stars_to_collect": self.step_stars_to_collect,
            "training_duration_minutes": self.step_training_duration_minutes,
            "target_flexion": self.step_target_flexion,
            "target_extension": self.step_target_extension,
            "grip_step": self.step_grip_step,
            "command_rate": self.step_command_rate,
            "activation_hysteresis": self.step_activation_hysteresis,
            "deactivation_hysteresis": self.step_deactivation_hysteresis,
            "forward_deadband": self.step_forward_deadband,
            "reversal_deadband": self.step_reversal_deadband,
            "dynamic_mvc_alpha_up": self.step_dynamic_mvc_alpha_up,
            "dynamic_mvc_alpha_down": self.step_dynamic_mvc_alpha_down,
            "dynamic_mvc_up_margin": self.step_dynamic_mvc_up_margin,
            "dynamic_mvc_hold_activity": self.step_dynamic_mvc_hold_activity,
            "dynamic_mvc_decay_trigger": self.step_dynamic_mvc_decay_trigger,
            "dynamic_mvc_decay_grace": self.step_dynamic_mvc_decay_grace,
            "background_blur": self.step_background_blur,
            "sound_effect_volume": self.step_sound_effect_volume,
            "sound_enabled": self.step_sound_enabled,
            "music_enabled": self.step_music_enabled,
            "music_volume": self.step_music_volume,
            "theme_mode": self.step_theme_mode,
        }
        self._steppers = [
            self.step_emg_max_flexor,
            self.step_emg_max_extensor,
            self.step_hand_start,
            self.step_threshold,
            self.step_trigger_threshold,
            self.step_trigger_wait_seconds,
            self.step_relax_flexion,
            self.step_relax_extension,
            self.step_countdown,
            self.step_stars_to_collect,
            self.step_training_duration_minutes,
            self.step_target_flexion,
            self.step_target_extension,
            self.step_grip_step,
            self.step_command_rate,
            self.step_activation_hysteresis,
            self.step_deactivation_hysteresis,
            self.step_forward_deadband,
            self.step_reversal_deadband,
            self.step_dynamic_mvc_alpha_up,
            self.step_dynamic_mvc_alpha_down,
            self.step_dynamic_mvc_up_margin,
            self.step_dynamic_mvc_hold_activity,
            self.step_dynamic_mvc_decay_trigger,
            self.step_dynamic_mvc_decay_grace,
            self.step_background_blur,
            self.step_sound_effect_volume,
            self.step_sound_enabled,
            self.step_music_enabled,
            self.step_music_volume,
            self.step_theme_mode,
        ]
        slider_right_x = self._content_left + self._left_col_width - s(34)
        slider_min_width = s(84)
        for stepper in self._steppers:
            if isinstance(stepper, NumericStepper):
                stepper.set_slider_right_x(slider_right_x, min_width=slider_min_width)
        self._tabs: List[tuple[str, str]] = [
            ("welcome", self._t("settings_tab_welcome")),
            ("game", self._t("settings_tab_game")),
            ("emg", self._t("settings_tab_emg_control")),
            ("exo", self._t("settings_tab_exo_output")),
        ]
        self._active_tab = "welcome"
        self._show_game_advanced = False
        self._show_emg_advanced = False
        self._show_exo_advanced = False
        self._tab_buttons: List[Button] = []
        self._tab_button_keys: List[str] = []
        self.reset_tab_btn = Button(
            pygame.Rect(self._content_left, self.panel.rect.y + s(120), s(220), s(34)),
            "",
            self.font_hint,
            on_click=self._reset_active_tab_to_defaults,
        )
        self._tab_stepper_ids: Dict[str, List[str]] = {
            "welcome": [],
            "game": [
                "countdown",
                "stars_to_collect",
                "training_duration_minutes",
                "background_blur",
                "sound_enabled",
                "sound_effect_volume",
                "music_enabled",
                "music_volume",
                "theme_mode",
            ],
            "emg": [
                "trigger_threshold",
                "trigger_wait_seconds",
                "threshold",
            ],
            "exo": [
                "grip_step",
            ],
        }
        self._game_advanced_stepper_ids: List[str] = [
            "relax_flexion_percent",
            "relax_extension_percent",
            "target_flexion",
            "target_extension",
        ]
        self._exo_advanced_stepper_ids: List[str] = [
                "hand_start",
                "command_rate",
                "forward_deadband",
                "reversal_deadband",
        ]
        self._emg_advanced_stepper_ids: List[str] = [
            "emg_max_flexor",
            "emg_max_extensor",
            "activation_hysteresis",
            "deactivation_hysteresis",
            "dynamic_mvc_alpha_up",
            "dynamic_mvc_alpha_down",
            "dynamic_mvc_up_margin",
            "dynamic_mvc_hold_activity",
            "dynamic_mvc_decay_trigger",
            "dynamic_mvc_decay_grace",
        ]
        self.emg_advanced_toggle_btn = Button(
            pygame.Rect(self._content_left + s(10), self.panel.rect.y + s(120), self._left_col_width - s(42), s(36)),
            "",
            self.font_hint,
            on_click=self._toggle_emg_advanced,
        )
        self._emg_advanced_toggle_base_y: Optional[int] = None
        self.game_advanced_toggle_btn = Button(
            pygame.Rect(self._content_left + s(10), self.panel.rect.y + s(120), self._left_col_width - s(42), s(36)),
            "",
            self.font_hint,
            on_click=self._toggle_game_advanced,
        )
        self._game_advanced_toggle_base_y: Optional[int] = None
        self.exo_advanced_toggle_btn = Button(
            pygame.Rect(self._content_left + s(10), self.panel.rect.y + s(120), self._left_col_width - s(42), s(36)),
            "",
            self.font_hint,
            on_click=self._toggle_exo_advanced,
        )
        self._exo_advanced_toggle_base_y: Optional[int] = None
        self._stepper_scroll_offset = 0
        self._stepper_scroll_step = s(40)
        self._stepper_row_gap = s(50)
        self._active_stepper_base_y: Dict[NumericStepper, int] = {}
        self._shortcut_lines = self._build_shortcut_lines()
        self._shortcut_line_gap = s(18)
        self._language_title = self._t("settings_language_title")
        self._language_buttons: List[Button] = []
        self._language_button_codes: List[str] = []
        self._stepper_view_rect = pygame.Rect(
            self._content_left,
            self.panel.rect.y + s(170),
            self._left_col_width - s(20),
            max(s(120), self.close_btn.rect.y - s(20) - (self.panel.rect.y + s(170))),
        )
        self._stepper_scrollbar_w = s(10)
        self._stepper_scrollbar_rect = pygame.Rect(
            self._stepper_view_rect.right - self._stepper_scrollbar_w,
            self._stepper_view_rect.y,
            self._stepper_scrollbar_w,
            self._stepper_view_rect.h,
        )
        self._stepper_nav_btn_h = s(28)
        self._stepper_nav_btn_w = max(self._stepper_scrollbar_w + s(8), s(24))
        nav_btn_x = self._stepper_scrollbar_rect.centerx - self._stepper_nav_btn_w // 2
        nav_btn_top_y = self._stepper_view_rect.y + s(4)
        nav_btn_bottom_y = self._stepper_view_rect.bottom - self._stepper_nav_btn_h - s(4)
        self._stepper_scroll_up_btn = Button(
            pygame.Rect(nav_btn_x, nav_btn_top_y, self._stepper_nav_btn_w, self._stepper_nav_btn_h),
            "^",
            self.font_hint,
            on_click=lambda: self._scroll_steppers(-1),
        )
        self._stepper_scroll_down_btn = Button(
            pygame.Rect(nav_btn_x, nav_btn_bottom_y, self._stepper_nav_btn_w, self._stepper_nav_btn_h),
            "v",
            self.font_hint,
            on_click=lambda: self._scroll_steppers(1),
        )
        self._stepper_button_h = stepper_button_h
        self._stepper_content_height = s(36)
        self._stepper_max_scroll = 0
        self._update_reset_button_label()
        self._build_tab_buttons()
        self._update_tab_button_states()
        self._apply_theme_styles()
        self._update_game_advanced_button_label()
        self._update_emg_advanced_button_label()
        self._update_exo_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

        row_height = s(82)
        self._device_row_height = row_height
        self._scan_results_header_y = self.swap_btn.rect.bottom + s(14)
        # Reserve enough vertical room for right-column status lines to avoid overlap.
        status_meta_h = max(s(92), self.font_hint.get_height() * 3 + s(20))
        self._scan_results_status_y = self._scan_results_header_y + status_meta_h
        # Leave explicit room for both status line + manual-assignment helper text.
        list_top_gap = max(
            s(64),
            self.font.get_height() + self.font_hint.get_height() + s(18),
        )
        self._device_list_start_y = self._scan_results_status_y + list_top_gap
        self._device_list_left = self._right_col_x + s(10)
        self._device_list_width = self._right_col_width - s(20)
        device_bottom_reserved = s(72)  # keep room for summary text at panel bottom
        device_view_h = max(s(120), self.panel.rect.bottom - self._device_list_start_y - device_bottom_reserved)
        self._scrollbar_width = s(20)
        self._device_view_rect = pygame.Rect(
            self._device_list_left,
            self._device_list_start_y,
            self._device_list_width - self._scrollbar_width - s(12),
            device_view_h,
        )
        self._scrollbar_x = self._device_view_rect.right + s(6)
        self._device_list_max_visible = max(1, self._device_view_rect.h // row_height)
        self._scrollbar_width = s(20)
        self._info_text_y = self._device_view_rect.bottom + s(12)

        self.on_bind_flexor_emg = on_bind_flexor_emg
        self.on_bind_extensor_emg = on_bind_extensor_emg
        self.on_bind_exo_hand = on_bind_exo_hand
        self._consume_disconnect_notice = consume_disconnect_notice
        self.get_bound_flexor_emg = get_bound_flexor_emg or (lambda: None)
        self.get_bound_extensor_emg = get_bound_extensor_emg or (lambda: None)
        self.get_bound_exo_hand = get_bound_exo_hand or (lambda: None)
        self._disconnect_notice = ""
        self._disconnect_notice_ts = 0.0

        self._build_device_buttons_from_bound()
        self._build_language_buttons()
        self._apply_translations()
        # Auto-start a BLE scan when entering Settings (same as pressing Scan BLE).
        self._scan()

    def _t(self, key: str, **kwargs) -> str:
        template = self.get_text(key)
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template

    def _sim_toggle_text(self) -> str:
        return self._t("settings_btn_simulation", state=self._t("settings_state_on") if self.ble.simulation else self._t("settings_state_off"))

    def _build_shortcut_lines(self) -> tuple[str, ...]:
        return (
            self._t("settings_shortcuts_main_title"),
            self._t("settings_shortcuts_main_enter"),
            self._t("settings_shortcuts_main_space"),
            self._t("settings_shortcuts_main_escape"),
            self._t("settings_shortcuts_main_s"),
            self._t("settings_shortcuts_main_m"),
            self._t("settings_shortcuts_main_f"),
            self._t("settings_shortcuts_main_e"),
            "    ",
            self._t("settings_shortcuts_settings_title"),
            self._t("settings_shortcuts_settings_a"),
            self._t("settings_shortcuts_settings_b"),
            self._t("settings_shortcuts_settings_t"),
            self._t("settings_shortcuts_settings_v"),
            self._t("settings_shortcuts_settings_x"),
            self._t("settings_shortcuts_settings_lr"),
            "    ",
        )

    def _build_welcome_lines(self) -> tuple[str, ...]:
        title = self._t("settings_welcome_title")
        line_prefix = "settings_welcome_line_"
        indexed_keys: List[tuple[int, str]] = []

        for key in self.get_text_keys():
            if not key.startswith(line_prefix):
                continue
            suffix = key[len(line_prefix):]
            if suffix.isdigit():
                indexed_keys.append((int(suffix), key))

        if indexed_keys:
            ordered_lines = [self._t(key) for _, key in sorted(indexed_keys)]
            return (title, *ordered_lines)

    def _resize_close_button(self):
        resize_close_button(self)

    def _active_reset_button_text(self) -> str:
        return active_reset_button_text(self)

    def _update_reset_button_label(self):
        update_reset_button_label(self)

    def _get_default_value(self, key: str, fallback: object) -> object:
        return self._default_values.get(key, fallback)

    def _set_numeric_stepper_to_default(self, stepper_id: str, default_key: str):
        stepper = self._stepper_by_id.get(stepper_id)
        if not isinstance(stepper, NumericStepper):
            return
        default_value = self._get_default_value(default_key, stepper.value)
        try:
            stepper.set_value(float(default_value), notify=True)
        except (TypeError, ValueError):
            stepper.set_value(float(stepper.value), notify=True)

    def _set_option_stepper_to_default(self, stepper_id: str, default_key: str, *, bool_to_on_off: bool = False):
        stepper = self._stepper_by_id.get(stepper_id)
        if not isinstance(stepper, OptionStepper):
            return
        default_value = self._get_default_value(default_key, stepper.value)
        if bool_to_on_off:
            value = "on" if bool(default_value) else "off"
        else:
            value = str(default_value)
        stepper.set_value(value, notify=True)

    def _reset_game_tab_to_defaults(self):
        default_training_mode = str(self._get_default_value("training_muscle_mode", self._training_muscle_mode))
        self._set_training_muscle_mode_selected(default_training_mode)
        self._set_numeric_stepper_to_default("countdown", "countdown_seconds")
        self._set_numeric_stepper_to_default("stars_to_collect", "stars_to_collect")
        self._set_numeric_stepper_to_default("training_duration_minutes", "training_duration_minutes")
        self._set_numeric_stepper_to_default("background_blur", "background_blur_percent")
        self._set_option_stepper_to_default("sound_enabled", "sound_enabled", bool_to_on_off=True)
        self._set_numeric_stepper_to_default("sound_effect_volume", "sound_effect_volume_percent")
        self._set_option_stepper_to_default("music_enabled", "music_enabled", bool_to_on_off=True)
        self._set_numeric_stepper_to_default("music_volume", "music_volume_percent")
        self._set_option_stepper_to_default("theme_mode", "theme_mode")
        self._set_numeric_stepper_to_default("relax_flexion_percent", "relax_flexion_percent")
        self._set_numeric_stepper_to_default("relax_extension_percent", "relax_extension_percent")
        self._set_numeric_stepper_to_default("target_flexion", "target_flexion_percent")
        self._set_numeric_stepper_to_default("target_extension", "target_extension_percent")

    def _reset_emg_tab_to_defaults(self):
        default_trigger_mode = str(self._get_default_value("training_trigger_mode", self._training_trigger_mode))
        self._set_training_trigger_mode_selected(default_trigger_mode)
        self._set_numeric_stepper_to_default("trigger_threshold", "trigger_threshold_percent")
        self._set_numeric_stepper_to_default("trigger_wait_seconds", "trigger_wait_seconds")
        self._set_numeric_stepper_to_default("threshold", "threshold_percent")
        self._set_numeric_stepper_to_default("emg_max_flexor", "emg_max_range_flexor")
        self._set_numeric_stepper_to_default("emg_max_extensor", "emg_max_range_extensor")
        self._set_numeric_stepper_to_default("activation_hysteresis", "activation_hysteresis_percent")
        self._set_numeric_stepper_to_default("deactivation_hysteresis", "deactivation_hysteresis_percent")
        self._set_numeric_stepper_to_default("dynamic_mvc_alpha_up", "dynamic_mvc_alpha_up")
        self._set_numeric_stepper_to_default("dynamic_mvc_alpha_down", "dynamic_mvc_alpha_down")
        self._set_numeric_stepper_to_default("dynamic_mvc_up_margin", "dynamic_mvc_up_margin_ratio")
        self._set_numeric_stepper_to_default("dynamic_mvc_hold_activity", "dynamic_mvc_hold_activity_ratio")
        self._set_numeric_stepper_to_default("dynamic_mvc_decay_trigger", "dynamic_mvc_decay_trigger_ratio")
        self._set_numeric_stepper_to_default("dynamic_mvc_decay_grace", "dynamic_mvc_decay_grace_seconds")

    def _reset_exo_tab_to_defaults(self):
        self._set_numeric_stepper_to_default("grip_step", "grip_step_percent")
        self._set_numeric_stepper_to_default("hand_start", "hand_start_percent")
        self._set_numeric_stepper_to_default("command_rate", "command_rate_hz")
        self._set_numeric_stepper_to_default("forward_deadband", "forward_deadband_percent")
        self._set_numeric_stepper_to_default("reversal_deadband", "reversal_deadband_percent")

    def _reset_active_tab_to_defaults(self):
        if self._active_tab == "welcome":
            self._reset_game_tab_to_defaults()
            self._reset_emg_tab_to_defaults()
            self._reset_exo_tab_to_defaults()
            return
        if self._active_tab == "game":
            self._reset_game_tab_to_defaults()
            return
        if self._active_tab == "emg":
            self._reset_emg_tab_to_defaults()
            return
        if self._active_tab == "exo":
            self._reset_exo_tab_to_defaults()

    def _build_tab_buttons(self):
        build_tab_buttons(self)

    def _create_tab_click_handler(self, tab_key: str):
        def click_handler():
            self._set_active_tab(tab_key)

        return click_handler

    def _set_active_tab(self, tab_key: str):
        if tab_key == self._active_tab or tab_key not in self._tab_stepper_ids:
            return
        self._active_tab = tab_key
        self._build_tab_buttons()
        self._update_tab_button_states()
        self._refresh_stepper_layout(reset_scroll=True)

    def _set_adjacent_tab(self, delta: int):
        if delta == 0:
            return
        ordered_tabs = [key for key, _ in self._tabs]
        if not ordered_tabs:
            return
        try:
            current_idx = ordered_tabs.index(self._active_tab)
        except ValueError:
            current_idx = 0
        next_idx = (current_idx + delta) % len(ordered_tabs)
        self._set_active_tab(ordered_tabs[next_idx])

    def _active_steppers(self) -> List[NumericStepper]:
        stepper_ids = list(self._tab_stepper_ids.get(self._active_tab, []))
        if self._active_tab == "game" and self._show_game_advanced:
            stepper_ids.extend(self._game_advanced_stepper_ids)
        if self._active_tab == "emg" and self._show_emg_advanced:
            stepper_ids.extend(self._emg_advanced_stepper_ids)
        if self._active_tab == "exo" and self._show_exo_advanced:
            stepper_ids.extend(self._exo_advanced_stepper_ids)
        return [self._stepper_by_id[k] for k in stepper_ids if k in self._stepper_by_id]

    def _refresh_stepper_layout(self, reset_scroll: bool = False):
        refresh_stepper_layout(self, reset_scroll=reset_scroll)

    def _update_tab_button_states(self):
        for button, key in zip(self._tab_buttons, self._tab_button_keys):
            is_active = key == self._active_tab
            if self._is_dark_theme:
                button.bg = (40, 110, 170) if is_active else (30, 30, 30)
                button.hover_bg = (70, 150, 220) if is_active else (65, 65, 65)
                button.fg = WHITE
            else:
                button.bg = (90, 150, 210) if is_active else (225, 225, 225)
                button.hover_bg = (120, 175, 230) if is_active else (205, 205, 205)
                button.fg = BLACK

    def _training_muscle_mode_text(self, mode: str) -> str:
        mode_key_map = {
            "auto": "settings_training_muscle_auto",
            "flexor_only": "settings_training_muscle_flexor_only",
            "extensor_only": "settings_training_muscle_extensor_only",
            "both": "settings_training_muscle_both",
        }
        mode_key = mode_key_map.get(mode, "settings_training_muscle_auto")
        return self._t(mode_key)

    def _create_training_muscle_mode_click_handler(self, mode: str):
        def click_handler():
            self._set_training_muscle_mode_selected(mode)
        return click_handler

    def _set_training_muscle_mode_selected(self, mode: str):
        normalized = str(mode).strip().lower()
        if normalized not in self._training_muscle_modes:
            normalized = "auto"
        if self._training_muscle_mode == normalized:
            return
        self._training_muscle_mode = normalized
        self._set_training_muscle_mode(normalized)
        self._update_training_muscle_mode_buttons()

    def _update_training_muscle_mode_buttons(self):
        self._training_muscle_label_text = self._t("settings_training_muscle_label")
        for button, mode in zip(self._training_muscle_mode_buttons, self._training_muscle_mode_button_modes):
            is_active = mode == self._training_muscle_mode
            button.text = self._training_muscle_mode_text(mode)
            if self._is_dark_theme and is_active:
                button.bg = (40, 120, 40)
                button.hover_bg = (60, 160, 60)
                button.fg = WHITE
            elif self._is_dark_theme:
                button.bg = (45, 80, 130)
                button.hover_bg = (70, 110, 165)
                button.fg = WHITE
            elif is_active:
                button.bg = (85, 160, 90)
                button.hover_bg = (110, 185, 115)
                button.fg = BLACK
            else:
                button.bg = (210, 220, 235)
                button.hover_bg = (190, 205, 225)
                button.fg = BLACK

    def _training_trigger_mode_text(self, mode: str) -> str:
        mode_key_map = {
            "auto": "settings_training_trigger_auto",
            "trigger-and-go": "settings_training_trigger_trigger_and_go",
            "trigger-and-maintain": "settings_training_trigger_trigger_and_maintain",
        }
        mode_key = mode_key_map.get(mode, "settings_training_trigger_auto")
        return self._t(mode_key)

    def _create_training_trigger_mode_click_handler(self, mode: str):
        def click_handler():
            self._set_training_trigger_mode_selected(mode)
        return click_handler

    def _set_training_trigger_mode_selected(self, mode: str):
        normalized = str(mode).strip().lower()
        if normalized not in self._training_trigger_modes:
            normalized = "auto"
        if self._training_trigger_mode == normalized:
            return
        self._training_trigger_mode = normalized
        self._set_training_trigger_mode(normalized)
        self._update_training_trigger_mode_buttons()

    def _update_training_trigger_mode_buttons(self):
        self._training_trigger_label_text = self._t("settings_training_trigger_label")
        for button, mode in zip(self._training_trigger_mode_buttons, self._training_trigger_mode_button_modes):
            is_active = mode == self._training_trigger_mode
            button.text = self._training_trigger_mode_text(mode)
            if self._is_dark_theme and is_active:
                button.bg = (40, 120, 40)
                button.hover_bg = (60, 160, 60)
                button.fg = WHITE
            elif self._is_dark_theme:
                button.bg = (45, 80, 130)
                button.hover_bg = (70, 110, 165)
                button.fg = WHITE
            elif is_active:
                button.bg = (85, 160, 90)
                button.hover_bg = (110, 185, 115)
                button.fg = BLACK
            else:
                button.bg = (210, 220, 235)
                button.hover_bg = (190, 205, 225)
                button.fg = BLACK

    def _normalize_theme_mode(self, mode: object) -> str:
        normalized = str(mode).strip().lower()
        if normalized not in self._theme_modes:
            return "system"
        return normalized

    def _theme_mode_options(self) -> List[tuple[str, str]]:
        return [
            ("system", self._t("settings_theme_mode_system")),
            ("dark", self._t("settings_theme_mode_dark")),
            ("light", self._t("settings_theme_mode_light")),
        ]

    def _set_sound_enabled_selected(self, value: str):
        normalized = "on" if str(value).strip().lower() == "on" else "off"
        if normalized == self._sound_enabled:
            return
        self._sound_enabled = normalized
        self._set_sound_enabled(self._sound_enabled == "on")
        self.step_sound_enabled.set_value(self._sound_enabled, notify=False)

    def _set_music_enabled_selected(self, value: str):
        normalized = "on" if str(value).strip().lower() == "on" else "off"
        if normalized == self._music_enabled:
            return
        self._music_enabled = normalized
        self._set_music_enabled(self._music_enabled == "on")
        self.step_music_enabled.set_value(self._music_enabled, notify=False)

    def _set_theme_mode_selected(self, mode: str):
        normalized = self._normalize_theme_mode(mode)
        if normalized == self._theme_mode:
            return
        self._theme_mode = normalized
        self._set_theme_mode(normalized)
        self.step_theme_mode.set_value(self._theme_mode, notify=False)

    def _apply_theme_styles(self):
        apply_settings_theme_styles(self)

    def _refresh_theme(self):
        refresh_settings_theme(self)

    def _toggle_game_advanced(self):
        self._show_game_advanced = not self._show_game_advanced
        self._update_game_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_game_advanced_button_label(self):
        update_advanced_toggle_button(
            self,
            self.game_advanced_toggle_btn,
            label_key="settings_btn_game_advanced",
            enabled=self._show_game_advanced,
        )

    def _toggle_emg_advanced(self):
        self._show_emg_advanced = not self._show_emg_advanced
        self._update_emg_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_emg_advanced_button_label(self):
        update_advanced_toggle_button(
            self,
            self.emg_advanced_toggle_btn,
            label_key="settings_btn_emg_advanced",
            enabled=self._show_emg_advanced,
        )

    def _toggle_exo_advanced(self):
        self._show_exo_advanced = not self._show_exo_advanced
        self._update_exo_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_exo_advanced_button_label(self):
        update_advanced_toggle_button(
            self,
            self.exo_advanced_toggle_btn,
            label_key="settings_btn_exo_advanced",
            enabled=self._show_exo_advanced,
        )

    def _apply_translations(self):
        apply_settings_translations(self)

    def _apply_stepper_scroll(self):
        apply_stepper_scroll(self)

    def _scroll_steppers(self, delta_steps: int):
        if self._stepper_max_scroll <= 0:
            return
        self._stepper_scroll_offset += delta_steps * self._stepper_scroll_step
        self._apply_stepper_scroll()

    def _build_language_buttons(self):
        build_language_buttons(self)

    def _create_language_click_handler(self, language_code: str):
        def click_handler():
            self.set_game_language(language_code)
            self._apply_translations()
            self._update_language_button_states()
        return click_handler

    def _update_language_button_states(self):
        update_language_button_states(self)

    def _cycle_prompt_button_selection(self, delta: int) -> bool:
        if delta == 0:
            return False
        if self._active_tab == "welcome" and self._language_button_codes:
            current = self.get_game_language()
            try:
                current_idx = self._language_button_codes.index(current)
            except ValueError:
                current_idx = 0
            next_idx = (current_idx + delta) % len(self._language_button_codes)
            self._language_buttons[next_idx].on_click()
            return True
        if self._active_tab == "game" and self._training_muscle_mode_button_modes:
            try:
                current_idx = self._training_muscle_mode_button_modes.index(self._training_muscle_mode)
            except ValueError:
                current_idx = 0
            next_idx = (current_idx + delta) % len(self._training_muscle_mode_button_modes)
            self._set_training_muscle_mode_selected(self._training_muscle_mode_button_modes[next_idx])
            return True
        if self._active_tab == "emg" and self._training_trigger_mode_button_modes:
            try:
                current_idx = self._training_trigger_mode_button_modes.index(self._training_trigger_mode)
            except ValueError:
                current_idx = 0
            next_idx = (current_idx + delta) % len(self._training_trigger_mode_button_modes)
            self._set_training_trigger_mode_selected(self._training_trigger_mode_button_modes[next_idx])
            return True
        return False

    def _toggle_active_advanced_menu(self) -> bool:
        if self._active_tab == "game":
            self._toggle_game_advanced()
            return True
        if self._active_tab == "emg":
            self._toggle_emg_advanced()
            return True
        if self._active_tab == "exo":
            self._toggle_exo_advanced()
            return True
        return False

    def _update_sim_toggle_button_layout(self):
        update_sim_toggle_button_layout(self)

    def _toggle_sim(self):
        self.ble.simulation = not self.ble.simulation
        self._update_sim_toggle_button_layout()

    def _get_display_devices(self) -> List[BLEDeviceInfo]:
        return get_display_devices(self)

    def _is_device_connected(self, dev: Optional[BLEDeviceInfo]) -> bool:
        if not dev:
            return False
        try:
            return self.ble.is_connected(dev.address)
        except Exception:
            return False

    def _bound_roles_for_device(self, dev: BLEDeviceInfo) -> List[str]:
        roles: List[str] = []
        bound_flexor = self.get_bound_flexor_emg()
        bound_extensor = self.get_bound_extensor_emg()
        bound_exo = self.get_bound_exo_hand()
        if bound_flexor and bound_flexor.address == dev.address:
            roles.append("flexor")
        if bound_extensor and bound_extensor.address == dev.address:
            roles.append("extensor")
        if bound_exo and bound_exo.address == dev.address:
            roles.append("exo")
        return roles

    def _fit_text(self, font: pygame.font.Font, text: str, max_width: int) -> str:
        """Trim text to fit a single line in the given width."""
        if max_width <= 0:
            return ""
        value = str(text)
        if font.size(value)[0] <= max_width:
            return value
        suffix = "..."
        while value and font.size(value + suffix)[0] > max_width:
            value = value[:-1]
        return (value + suffix) if value else suffix

    def _format_device_mac_suffix(self, address: str) -> str:
        """
        Compact address hint appended to the device heading.
        Uses the first 4 MAC hex characters as requested, e.g. " · A1B2".
        """
        normalized = "".join(ch for ch in str(address or "").upper() if ch.isalnum())
        if not normalized:
            return ""
        return f" · ({normalized[:4]})"

    def _build_device_buttons_from_bound(self):
        build_device_buttons_from_bound(self)

    def _compute_device_list_signature(self) -> tuple:
        return compute_device_list_signature(self)

    def _create_bind_click_handler(self, dev: BLEDeviceInfo, bind_fn: Callable, role_id: str):
        def click_handler():
            bound_flexor_emg = self.get_bound_flexor_emg()
            bound_extensor_emg = self.get_bound_extensor_emg()
            bound_exo_hand = self.get_bound_exo_hand()

            is_already_bound_to_this_role = False
            if role_id == "bind_flexor" and bound_flexor_emg and bound_flexor_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_id == "bind_extensor" and bound_extensor_emg and bound_extensor_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_id == "bind_exo" and bound_exo_hand and bound_exo_hand.address == dev.address:
                is_already_bound_to_this_role = True

            if is_already_bound_to_this_role:
                # Clicking an already bound role toggles unbind only when connected.
                # If the device is currently offline, treat the click as reconnect.
                if not self.ble.is_connected(dev.address):
                    if not self.ble.connect(dev.address):
                        return
                    bind_fn(dev)
                else:
                    bind_fn(None)
                self._update_bind_button_states()
                return

            if bound_flexor_emg and bound_flexor_emg.address == dev.address and role_id != "bind_flexor":
                self.on_bind_flexor_emg(None)
            if bound_extensor_emg and bound_extensor_emg.address == dev.address and role_id != "bind_extensor":
                self.on_bind_extensor_emg(None)
            if bound_exo_hand and bound_exo_hand.address == dev.address and role_id != "bind_exo":
                self.on_bind_exo_hand(None)

            if not self.ble.is_connected(dev.address):
                if not self.ble.connect(dev.address):
                    return

            bind_fn(dev)
            self._update_bind_button_states()

        return click_handler

    def _update_bind_button_states(self):
        update_bind_button_states(self)

    def _scan(self):
        scan_devices(self)

    def handle_event(self, event: pygame.event.Event):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_a:
                self.on_close()
            elif event.key == pygame.K_b:
                self._scan()
            elif event.key == pygame.K_t:
                self._toggle_sim()
            elif event.key == pygame.K_x:
                self.swap_btn.on_click()
            elif event.key == pygame.K_1:
                self._set_active_tab("welcome")
            elif event.key == pygame.K_2:
                self._set_active_tab("game")
            elif event.key == pygame.K_3:
                self._set_active_tab("emg")
            elif event.key == pygame.K_4:
                self._set_active_tab("exo")
            elif event.key == pygame.K_LEFT:
                self._set_adjacent_tab(-1)
            elif event.key == pygame.K_RIGHT:
                self._set_adjacent_tab(1)
            elif event.key == pygame.K_UP:
                if not self._cycle_prompt_button_selection(-1):
                    self._scroll_steppers(-1)
            elif event.key == pygame.K_DOWN:
                if not self._cycle_prompt_button_selection(1):
                    self._scroll_steppers(1)
            elif event.key == pygame.K_v:
                self._toggle_active_advanced_menu()
            elif event.key == pygame.K_PAGEUP:
                self._scroll_steppers(-3)
            elif event.key == pygame.K_PAGEDOWN:
                self._scroll_steppers(3)

        self.close_btn.handle_event(event)
        self.scan_btn.handle_event(event)
        self.sim_toggle.handle_event(event)
        self.swap_btn.handle_event(event)
        for button in self._tab_buttons:
            button.handle_event(event)
        self.reset_tab_btn.handle_event(event)
        self._stepper_scroll_up_btn.handle_event(event)
        self._stepper_scroll_down_btn.handle_event(event)
        if self._active_tab == "welcome":
            for button in self._language_buttons:
                button.handle_event(event)

        if event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if self._stepper_view_rect.collidepoint(mouse_pos) and self._stepper_max_scroll > 0:
                self._scroll_steppers(-event.y)
                return
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            # Linux/older SDL paths can deliver wheel movement as buttons 4/5.
            if self._stepper_view_rect.collidepoint(event.pos) and self._stepper_max_scroll > 0:
                self._scroll_steppers(-1 if event.button == 4 else 1)
                return

        mouse_in_stepper_view = hasattr(event, "pos") and self._stepper_view_rect.collidepoint(event.pos)
        active_steppers = self._active_steppers()
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if mouse_in_stepper_view:
                if self._active_tab == "game":
                    for button in self._training_muscle_mode_buttons:
                        button.handle_event(event)
                    self.game_advanced_toggle_btn.handle_event(event)
                if self._active_tab == "emg":
                    for button in self._training_trigger_mode_buttons:
                        button.handle_event(event)
                    self.emg_advanced_toggle_btn.handle_event(event)
                if self._active_tab == "exo":
                    self.exo_advanced_toggle_btn.handle_event(event)
                for stepper in active_steppers:
                    stepper.handle_event(event)
        else:
            for stepper in active_steppers:
                stepper.handle_event(event)

        display_devices = self._get_display_devices()
        total_devices = len(display_devices)

        scrollbar_x = self._scrollbar_x
        scrollbar_y = self._device_view_rect.y
        scrollbar_height = self._device_view_rect.h
        scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_y, self._scrollbar_width, scrollbar_height)
        mouse_in_device_view = hasattr(event, "pos") and (
            self._device_view_rect.collidepoint(event.pos) or scrollbar_rect.collidepoint(event.pos)
        )

        if event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if total_devices > self._device_list_max_visible and (
                self._device_view_rect.collidepoint(mouse_pos) or scrollbar_rect.collidepoint(mouse_pos)
            ):
                max_scroll = total_devices - self._device_list_max_visible
                self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset - event.y))
                self._build_device_buttons_from_bound()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            if total_devices > self._device_list_max_visible and mouse_in_device_view:
                max_scroll = total_devices - self._device_list_max_visible
                wheel_dir = 1 if event.button == 4 else -1
                self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset - wheel_dir))
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
            if role != "label":
                b.handle_event(event)

    def update(self, dt: float):
        _ = dt
        self._refresh_theme()
        callback_notice = self._consume_disconnect_notice()
        if callback_notice:
            self._disconnect_notice = callback_notice
            self._disconnect_notice_ts = time.time()
        if self._disconnect_notice and (time.time() - self._disconnect_notice_ts) > 8.0:
            self._disconnect_notice = ""
        current_signature = self._compute_device_list_signature()
        if (not self._device_buttons) or (current_signature != self._last_device_list_signature):
            self._build_device_buttons_from_bound()
        self._update_bind_button_states()
        self._update_language_button_states()

    def draw(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.panel.draw(surface)
        hint_map = {
            "welcome": self._t("settings_hint_tab_welcome"),
            "game": self._t("settings_hint_tab_game"),
            "emg": self._t("settings_hint_tab_emg"),
            "exo": self._t("settings_hint_tab_exo"),
        }
        subtitle_text = hint_map.get(self._active_tab, self._t("settings_hint_tune"))
        draw_outlined_text(
            surface,
            self.font_subtitle,
            subtitle_text,
            self._theme_text_color,
            (self.panel.rect.x + s(20), self.panel.rect.y + s(20)),
            outline_color=self._theme_outline_color,
            outline_width=2,
        )
        self.close_btn.draw(surface)
        self.scan_btn.draw(surface)
        self.sim_toggle.draw(surface)
        self.swap_btn.draw(surface)

        for button in self._tab_buttons:
            button.draw(surface)
        self.reset_tab_btn.draw(surface)

        # Left-column stepper viewport (scrollable) so new steppers can be added safely.
        pygame.draw.rect(surface, self._stepper_view_bg, self._stepper_view_rect, border_radius=8)
        pygame.draw.rect(surface, self._stepper_view_border, self._stepper_view_rect, width=2, border_radius=8)
        active_steppers = self._active_steppers()
        previous_clip = surface.get_clip()
        surface.set_clip(self._stepper_view_rect)
        if self._active_tab == "welcome":
            welcome_lines = self._build_welcome_lines()
            title_y = self._stepper_view_rect.y + s(14)
            if welcome_lines:
                draw_outlined_text(
                    surface,
                    self.font_welcome_title,
                    welcome_lines[0],
                    self._theme_text_color,
                    (self._stepper_view_rect.x + s(12), title_y),
                    outline_color=self._theme_outline_color,
                    outline_width=2,
                )
                line_y = title_y + self.font_welcome_title.get_height() + s(12)
                for text in welcome_lines[1:]:
                    draw_outlined_text(
                        surface,
                        self.font_welcome_body,
                        text,
                        (220, 220, 220) if self._is_dark_theme else (45, 45, 45),
                        (self._stepper_view_rect.x + s(12), line_y),
                        outline_color=self._theme_outline_color,
                        outline_width=1,
                    )
                    line_y += self.font_welcome_body.get_height() + s(8)
        else:
            for stepper in active_steppers:
                stepper.draw(surface)
            if self._active_tab == "game":
                if self._training_muscle_toggle_base_y is not None:
                    label_x = self._stepper_view_rect.x + s(12)
                    label_y = self._training_muscle_toggle_base_y - self._stepper_scroll_offset
                    draw_outlined_text(
                        surface,
                        self.font_hint,
                        self._training_muscle_label_text,
                        self._theme_text_color,
                        (label_x, label_y),
                        outline_color=self._theme_outline_color,
                        outline_width=1,
                    )
                for button in self._training_muscle_mode_buttons:
                    button.draw(surface)
                self.game_advanced_toggle_btn.draw(surface)
            if self._active_tab == "emg":
                if self._training_trigger_toggle_base_y is not None:
                    label_x = self._stepper_view_rect.x + s(12)
                    label_y = self._training_trigger_toggle_base_y - self._stepper_scroll_offset
                    draw_outlined_text(
                        surface,
                        self.font_hint,
                        self._training_trigger_label_text,
                        self._theme_text_color,
                        (label_x, label_y),
                        outline_color=self._theme_outline_color,
                        outline_width=1,
                    )
                for button in self._training_trigger_mode_buttons:
                    button.draw(surface)
                self.emg_advanced_toggle_btn.draw(surface)
            if self._active_tab == "exo":
                self.exo_advanced_toggle_btn.draw(surface)
        surface.set_clip(previous_clip)

        if self._stepper_max_scroll > 0:
            track = self._stepper_scrollbar_rect
            pygame.draw.rect(surface, (60, 60, 60), track, border_radius=4)
            thumb_h = max(s(24), int((self._stepper_view_rect.h / max(1, self._stepper_content_height)) * track.h))
            thumb_travel = max(0, track.h - thumb_h)
            thumb_y = track.y + int((self._stepper_scroll_offset / self._stepper_max_scroll) * thumb_travel)
            pygame.draw.rect(surface, (170, 170, 170), (track.x, thumb_y, track.w, thumb_h), border_radius=4)
            self._stepper_scroll_up_btn.draw(surface)
            self._stepper_scroll_down_btn.draw(surface)

        if self._active_tab == "welcome":
            # Keep shortcuts and language pinned at the bottom of Welcome.
            shortcuts_h = len(self._shortcut_lines) * self._shortcut_line_gap
            shortcuts_y = self.close_btn.rect.y - shortcuts_h - s(8)
            shortcuts_x = self._content_left + s(12)
            language_x = self._content_left + self._left_col_width - max(s(180), min(s(280), self._left_col_width // 3)) - s(32)
            if self._language_title:
                draw_outlined_text(
                    surface,
                    self.font_hint,
                    self._language_title,
                    self._theme_text_color,
                    (language_x, shortcuts_y),
                    outline_color=self._theme_outline_color,
                    outline_width=1,
                )
            shortcuts_clip = pygame.Rect(
                shortcuts_x,
                shortcuts_y,
                max(s(120), language_x - shortcuts_x - s(16)),
                shortcuts_h + s(8),
            )
            previous_clip = surface.get_clip()
            surface.set_clip(shortcuts_clip)
            for idx, text in enumerate(self._shortcut_lines):
                draw_outlined_text(
                    surface,
                    self.font_hint,
                    text,
                    self._theme_text_color,
                    (shortcuts_x, shortcuts_y + idx * self._shortcut_line_gap),
                    outline_color=self._theme_outline_color,
                    outline_width=1,
                )
            surface.set_clip(previous_clip)
            for button in self._language_buttons:
                button.draw(surface)

        # Dedicated right-column BLE area with larger height for more results.
        placeholder_x = self._right_col_x
        placeholder_y = self.panel.rect.y + s(120)
        placeholder_w = self._right_col_width
        placeholder_h = self.panel.rect.bottom - placeholder_y - s(20)
        pygame.draw.rect(surface, self._device_panel_bg, (placeholder_x, placeholder_y, placeholder_w, placeholder_h), border_radius=8)
        pygame.draw.rect(surface, self._device_panel_border, (placeholder_x, placeholder_y, placeholder_w, placeholder_h), width=2, border_radius=8)
        right_text_max_w = self._device_list_width - s(14)
        draw_outlined_text(
            surface,
            self.font,
            self._t("settings_ble_scan_results"),
            self._theme_text_color,
            (self._device_list_left, self._scan_results_header_y),
            outline_color=self._theme_outline_color,
            outline_width=2,
        )
        bound_flexor = self.get_bound_flexor_emg()
        bound_extensor = self.get_bound_extensor_emg()
        bound_exo = self.get_bound_exo_hand()
        def _role_status(role_name: str, dev: Optional[BLEDeviceInfo]) -> str:
            if not dev:
                return self._t("settings_role_status_none", role=role_name)
            state = self._t("settings_device_online") if self._is_device_connected(dev) else self._t("settings_device_offline")
            return f"{role_name}: {dev.name} [{state}]"
        connected_summary_raw = " | ".join(
            [
                _role_status(self._t("settings_role_flexor"), bound_flexor),
                _role_status(self._t("settings_role_extensor"), bound_extensor),
                _role_status(self._t("settings_role_exo"), bound_exo),
            ]
        )
        connected_summary = self._fit_text(self.font_hint, connected_summary_raw, right_text_max_w)
        connected_summary_color = (180, 220, 180) if self._is_dark_theme else (55, 120, 65)
        draw_outlined_text(
            surface,
            self.font_hint,
            connected_summary,
            connected_summary_color,
            (self._device_list_left, self._scan_results_header_y + s(22)),
            outline_color=self._theme_outline_color,
            outline_width=1,
        )
        if self._auto_bind_status:
            auto_bind_text = self._fit_text(self.font_hint, self._auto_bind_status, right_text_max_w)
            auto_bind_color = (160, 220, 255) if self._is_dark_theme else (45, 105, 165)
            draw_outlined_text(
                surface,
                self.font_hint,
                auto_bind_text,
                auto_bind_color,
                (self._device_list_left, self._scan_results_header_y + s(42)),
                outline_color=self._theme_outline_color,
                outline_width=1,
            )
        if self._disconnect_notice:
            disconnect_text = self._fit_text(self.font_hint, self._disconnect_notice, right_text_max_w)
            disconnect_color = (255, 180, 100) if self._is_dark_theme else (165, 100, 35)
            draw_outlined_text(
                surface,
                self.font_hint,
                disconnect_text,
                disconnect_color,
                (self._device_list_left, self._scan_results_header_y + s(62)),
                outline_color=self._theme_outline_color,
                outline_width=1,
            )

        is_scanning = self._scan_thread and self._scan_thread.is_alive()
        elapsed = time.time() - self._scan_start_time if self._scan_start_time else 0
        min_display_time = 3.0

        if not is_scanning and self._scan_start_time > 0 and elapsed >= min_display_time and not self._devices_ready and not self._scan_status:
            self.scan_btn.disabled = False

        if is_scanning:
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self._fit_text(
                self.font,
                self._t("settings_scanning_in_progress", dots=dots),
                right_text_max_w,
            )
            draw_outlined_text(
                surface,
                self.font,
                scanning_text,
                YELLOW if self._is_dark_theme else (185, 140, 45),
                (self._device_list_left, self._scan_results_status_y),
                outline_color=self._theme_outline_color,
                outline_width=2,
            )
        elif self._devices_ready and elapsed < min_display_time:
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self._fit_text(
                self.font,
                self._t("settings_scanning_complete_processing", dots=dots),
                right_text_max_w,
            )
            draw_outlined_text(
                surface,
                self.font,
                scanning_text,
                YELLOW if self._is_dark_theme else (185, 140, 45),
                (self._device_list_left, self._scan_results_status_y),
                outline_color=self._theme_outline_color,
                outline_width=2,
            )
        elif self._devices_ready and elapsed >= min_display_time:
            self.devices = self._devices_ready
            self._devices_ready = []
            self._scan_status = ""
            self.scan_btn.disabled = False
            if not self._device_buttons:
                self._device_scroll_offset = 0
                self._build_device_buttons_from_bound()
        elif self._scan_status and self._scan_has_error:
            error_text = self._fit_text(self.font, self._scan_status, right_text_max_w)
            draw_outlined_text(
                surface,
                self.font,
                error_text,
                RED if self._is_dark_theme else (185, 70, 70),
                (self._device_list_left, self._scan_results_status_y),
                outline_color=self._theme_outline_color,
                outline_width=2,
            )
            self.scan_btn.disabled = False
        else:
            idle_text = self._fit_text(
                self.font,
                self._t("settings_press_scan_hint"),
                right_text_max_w,
            )
            draw_outlined_text(
                surface,
                self.font,
                idle_text,
                (180, 180, 180) if self._is_dark_theme else (95, 95, 95),
                (self._device_list_left, self._scan_results_status_y),
                outline_color=self._theme_outline_color,
                outline_width=2,
            )
            manual_hint_text = self._fit_text(
                self.font_hint,
                self._t("settings_manual_assignment_hint"),
                right_text_max_w,
            )
            draw_outlined_text(
                surface,
                self.font_hint,
                manual_hint_text,
                connected_summary_color,
                (self._device_list_left, self._scan_results_status_y + self.font.get_height() + s(6)),
                outline_color=self._theme_outline_color,
                outline_width=1,
            )

        display_devices = self._get_display_devices()
        total_devices = len(display_devices)
        visible_devices = len([b for b, role, _ in self._device_buttons if role == "label"])

        if total_devices > self._device_list_max_visible:
            scrollbar_x = self._scrollbar_x
            scrollbar_y = self._device_view_rect.y
            scrollbar_height = self._device_view_rect.h
            scrollbar_width = self._scrollbar_width
            scrollbar_track_color = (60, 60, 60) if self._is_dark_theme else (210, 210, 210)
            pygame.draw.rect(surface, scrollbar_track_color, (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height), border_radius=4)

            thumb_height = max(20, int((self._device_list_max_visible / total_devices) * scrollbar_height))
            max_thumb_y = scrollbar_y + scrollbar_height - thumb_height
            scroll_ratio = self._device_scroll_offset / max(1, total_devices - self._device_list_max_visible)
            thumb_y = scrollbar_y + int(scroll_ratio * (max_thumb_y - scrollbar_y))
            scrollbar_thumb_color = (150, 150, 150) if self._is_dark_theme else WHITE
            pygame.draw.rect(surface, scrollbar_thumb_color, (scrollbar_x, thumb_y, scrollbar_width, thumb_height), border_radius=4)

        if total_devices > 0:
            scroll_info = ""
            if total_devices > self._device_list_max_visible:
                scroll_info = (
                    self._t(
                        "settings_scroll_info",
                        start=self._device_scroll_offset + 1,
                        end=min(self._device_scroll_offset + visible_devices, total_devices),
                        total=total_devices,
                    )
                )
            info_text = self._t(
                "settings_info_text",
                total=total_devices,
                visible=visible_devices,
                scroll=scroll_info,
            )
            draw_outlined_text(
                surface,
                self.font,
                info_text,
                self._theme_text_color,
                (self._device_list_left, self._info_text_y),
                outline_color=self._theme_outline_color,
                outline_width=2,
            )

        previous_clip = surface.get_clip()
        surface.set_clip(self._device_view_rect)
        for b, role, _ in self._device_buttons:
            if hasattr(b, "draw"):
                b.draw(surface)
        surface.set_clip(previous_clip)
