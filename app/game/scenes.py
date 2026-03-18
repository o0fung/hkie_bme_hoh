import io
import math
import os
import threading
import time
from collections import deque
from typing import Callable, Dict, List, Optional, Set

import pygame

from ..ui.widgets import (
    Button,
    Label,
    Panel,
    BarGauge,
    NumericStepper,
    OptionStepper,
    CircularGauge,
    EMGChart,
    draw_outlined_text,
    get_contrasting_color,
)
from .scene_manager import Scene
from ..ble.ble_manager import BLEManager, BLEDeviceInfo


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 100, 100)
GREEN = (80, 200, 120)
YELLOW = (240, 210, 80)
RED = (230, 80, 80)
GAME_BG = (10, 20, 30)

_LATIN_FONT_CANDIDATES = [
    "Arial",
    "Liberation Sans",
    "DejaVu Sans",
    "Noto Sans",
]
_CJK_FONT_CANDIDATES = [
    "PingFang TC",
    "PingFang SC",
    "PingFang HK",
    "Hiragino Sans GB",
    "Hiragino Sans CNS",
    "Heiti TC",
    "Heiti SC",
    "STHeiti",
    "Songti SC",
    "Noto Sans CJK TC",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Noto Sans TC",
    "Noto Sans SC",
    "Source Han Sans TC",
    "Source Han Sans CN",
    "WenQuanYi Zen Hei",
    "Microsoft JhengHei",
    "PingFang TC",
    "SimHei",
    "SimSun",
    "Arial Unicode MS",
    "Droid Sans Fallback",
]
_CJK_FONT_PATH_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Hiragino Sans CNS.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
]
_CJK_GLYPH_PROBE_TEXT = "繁體中文简体中文設定设置鏡像"


def _font_supports_text(font: pygame.font.Font, text: str) -> bool:
    """Return True only when every glyph in text exists in the font."""
    try:
        metrics = font.metrics(text)
    except Exception:
        return False
    if not metrics:
        return False
    return all(metric is not None for metric in metrics)


def _pick_font(size: int, prefer_cjk: bool = False) -> pygame.font.Font:
    candidates = (
        _CJK_FONT_CANDIDATES + _LATIN_FONT_CANDIDATES
        if prefer_cjk
        else _LATIN_FONT_CANDIDATES + _CJK_FONT_CANDIDATES
    )
    seen_paths = set()
    for name in candidates:
        path = pygame.font.match_font(name)
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            font = pygame.font.Font(path, size)
        except Exception:
            continue
        if not prefer_cjk or _font_supports_text(font, _CJK_GLYPH_PROBE_TEXT):
            return font
    if prefer_cjk:
        for path in _CJK_FONT_PATH_CANDIDATES:
            if not os.path.exists(path):
                continue
            try:
                font = pygame.font.Font(path, size)
            except Exception:
                continue
            if _font_supports_text(font, _CJK_GLYPH_PROBE_TEXT):
                return font
    return pygame.font.Font(None, size)


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
        self.font_big = _pick_font(s(112), prefer_cjk=use_cjk_font)
        self.font_small = _pick_font(s(40), prefer_cjk=use_cjk_font)
        self.font_tiny = _pick_font(s(24), prefer_cjk=use_cjk_font)
        self.font_round = _pick_font(s(68), prefer_cjk=use_cjk_font)
        self.font_menu = _pick_font(s(80), prefer_cjk=use_cjk_font)

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
        self.exit_button = Button(
            pygame.Rect(menu_x, menu_y_start + 4 * (menu_item_h + menu_gap), menu_w, menu_item_h),
            self._t("btn_exit"),
            self.font_menu,
            on_click=self._exit,
        )
        self._menu_panel_rect = pygame.Rect(
            menu_x - s(10),
            menu_y_start - s(10),
            menu_w + s(20),
            5 * menu_item_h + 4 * menu_gap + s(20),
        )
        self._is_dark_theme = bool(self.get_is_dark_theme())
        self._menu_panel_bg = (20, 20, 20)
        self._menu_panel_border = (180, 180, 180)
        self._background_light_overlay_alpha = 0
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
            self.font_big = _pick_font(s(112), prefer_cjk=current_is_cjk)
            self.font_small = _pick_font(s(40), prefer_cjk=current_is_cjk)
            self.font_tiny = _pick_font(s(24), prefer_cjk=current_is_cjk)
            self.font_round = _pick_font(s(68), prefer_cjk=current_is_cjk)
            self.font_menu = _pick_font(s(80), prefer_cjk=current_is_cjk)
            self.settings_button.font = self.font_menu
            self.reset_button.font = self.font_menu
            self.start_pause_button.font = self.font_menu
            self.mirror_button.font = self.font_menu
            self.exit_button.font = self.font_menu
            self.menu_button.font = self.font_small
            self.flexor_label.font = self.font_small
            self.extensor_label.font = self.font_small
        self.settings_button.text = self._t("btn_settings")
        self.reset_button.text = self._t("btn_reset")
        self.exit_button.text = self._t("btn_exit")
        self.mirror_button.text = self._t("btn_mirror_on") if self._is_mirrored else self._t("btn_mirror_off")
        self.flexor_label.text = self._t("label_flexor_emg")
        self.extensor_label.text = self._t("label_extensor_emg")
        self.hand_gauge.set_labels("", "")
        self._update_start_stop_button_style()
        self._apply_side_layout()

    def _load_background_image(self):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = ("background_b.jpg", "background_B.jpg")
        for filename in candidates:
            asset_path = os.path.join(project_root, "assets", filename)
            if not os.path.exists(asset_path):
                continue
            try:
                raw_image = pygame.image.load(asset_path).convert()
                scaled = pygame.transform.smoothscale(raw_image, self.screen_rect.size)
                self._background_source_image = scaled
                self.set_background_blur_percent(self._background_blur_percent)
                return
            except pygame.error:
                self._background_source_image = None
                self._background_image = None
                return

        def _read_packaged_asset(filename: str) -> Optional[bytes]:
            try:
                import importlib.resources as pkg_resources
                asset_pkg = pkg_resources.files("assets")
                asset_file = asset_pkg.joinpath(filename)
                if asset_file.is_file():
                    return asset_file.read_bytes()
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError):
                pass

            # Python < 3.9 fallback
            try:
                import importlib_resources as pkg_resources  # type: ignore
                asset_pkg = pkg_resources.files("assets")
                asset_file = asset_pkg.joinpath(filename)
                with asset_file.open("rb") as f:
                    return f.read()
            except (ImportError, ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError, OSError):
                return None

        for filename in candidates:
            asset_bytes = _read_packaged_asset(filename)
            if not asset_bytes:
                continue
            try:
                raw_image = pygame.image.load(io.BytesIO(asset_bytes), filename).convert()
                scaled = pygame.transform.smoothscale(raw_image, self.screen_rect.size)
                self._background_source_image = scaled
                self.set_background_blur_percent(self._background_blur_percent)
                return
            except pygame.error:
                self._background_source_image = None
                self._background_image = None
                return

    def _create_soft_focus_background(self, image: pygame.Surface, blur_percent: float) -> pygame.Surface:
        """
        Apply adjustable "out of focus" blur using downscale/upscale passes.
        Runs only when blur setting changes, not every frame.
        """
        blur_percent = max(0.0, min(100.0, float(blur_percent)))
        if blur_percent <= 0.0:
            return image
        w, h = image.get_size()
        if w <= 2 or h <= 2:
            return image

        # Map 0..100 blur% to downscale factors: lower factor => stronger blur.
        strength = blur_percent / 100.0
        factor_strong = max(0.18, min(1.0, 1.0 - 0.78 * strength))
        factor_soft = max(0.28, min(1.0, factor_strong + 0.16))
        blurred = image.copy()
        for factor in (factor_strong, factor_soft):
            down_w = max(1, int(w * factor))
            down_h = max(1, int(h * factor))
            blurred = pygame.transform.smoothscale(blurred, (down_w, down_h))
            blurred = pygame.transform.smoothscale(blurred, (w, h))
        return blurred

    def set_background_blur_percent(self, blur_percent: float):
        self._background_blur_percent = max(0.0, min(100.0, float(blur_percent)))
        if self._background_source_image is None:
            return
        self._background_image = self._create_soft_focus_background(
            self._background_source_image,
            self._background_blur_percent,
        )

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

        flexor_label_x = self.flexor_bar.rect.centerx - self.font_small.size(self.flexor_label.text)[0] // 2
        extensor_label_x = self.extensor_bar.rect.centerx - self.font_small.size(self.extensor_label.text)[0] // 2
        self.flexor_label.pos = (flexor_label_x, self._label_y)
        self.extensor_label.pos = (extensor_label_x, self._label_y)
        self.hand_gauge.set_mirrored(self._is_mirrored)

    def _toggle_mirror_layout(self):
        self._menu_open = False
        self._is_mirrored = not self._is_mirrored
        self.mirror_button.text = self._t("btn_mirror_on") if self._is_mirrored else self._t("btn_mirror_off")
        self._apply_side_layout()

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
        if self._is_dark_theme:
            self.flexor_bar.bg = (34, 34, 42)
            self.extensor_bar.bg = (34, 34, 42)
            self.flexor_bar.threshold_color = (250, 230, 90)
            self.extensor_bar.threshold_color = (250, 230, 90)
            self.flexor_bar.border_color_override = None
            self.extensor_bar.border_color_override = None
            self.hand_gauge.bg_color = (55, 55, 65)
            self.hand_gauge.flexion_color = (90, 180, 255)
            self.hand_gauge.extension_color = (255, 140, 140)
            self.hand_gauge.target_color = (250, 230, 90)
            self.hand_gauge.pointer_color = WHITE
            self.hand_gauge.center_text_color = WHITE
            self.hand_gauge.text_outline_color = BLACK
            self.flexor_chart.bg_color = (20, 20, 26)
            self.extensor_chart.bg_color = (20, 20, 26)
            self.flexor_chart.line_color = (20, 70, 140)
            self.extensor_chart.line_color = (120, 25, 25)
            self.flexor_chart.background_alpha = 0
            self.extensor_chart.background_alpha = 0
            self.flexor_chart.border_color = None
            self.extensor_chart.border_color = None
            self.flexor_chart.fade_min_alpha = 45
            self.extensor_chart.fade_min_alpha = 45
            self.menu_button.bg = (25, 25, 25)
            self.menu_button.hover_bg = (55, 55, 55)
            self._menu_panel_bg = (20, 20, 20)
            self._menu_panel_border = (180, 180, 180)
            self._background_light_overlay_alpha = 0
            self._title_text_color = BLACK
            self._title_text_outline = WHITE
            self._title_box_fill_rgba = (255, 255, 255, 153)
            self._round_text_color = WHITE
            self._round_text_outline = BLACK
            self._status_progress_color = YELLOW
            self._status_win_color = GREEN
            self._status_text_outline = BLACK
            self._version_text_color = GRAY
            self._version_text_outline = BLACK
            self.menu_button.border_color_override = None
            for btn in (self.settings_button, self.reset_button, self.mirror_button, self.exit_button):
                btn.bg = (30, 30, 30)
                btn.hover_bg = (60, 60, 60)
                btn.fg = WHITE
                btn.border_color_override = None
        else:
            self.flexor_bar.bg = (224, 230, 242)
            self.extensor_bar.bg = (224, 230, 242)
            self.flexor_bar.threshold_color = (215, 175, 45)
            self.extensor_bar.threshold_color = (215, 175, 45)
            self.flexor_bar.border_color_override = WHITE
            self.extensor_bar.border_color_override = WHITE
            self.hand_gauge.bg_color = (175, 185, 205)
            self.hand_gauge.flexion_color = (65, 130, 215)
            self.hand_gauge.extension_color = (220, 105, 105)
            self.hand_gauge.target_color = (215, 175, 45)
            self.hand_gauge.pointer_color = (45, 45, 45)
            self.hand_gauge.center_text_color = (45, 45, 45)
            self.hand_gauge.text_outline_color = WHITE
            self.flexor_chart.bg_color = (230, 236, 247)
            self.extensor_chart.bg_color = (230, 236, 247)
            self.flexor_chart.line_color = (22, 74, 145)
            self.extensor_chart.line_color = (145, 42, 42)
            # Keep chart background transparent in light theme.
            self.flexor_chart.background_alpha = 0
            self.extensor_chart.background_alpha = 0
            self.flexor_chart.border_color = None
            self.extensor_chart.border_color = None
            self.flexor_chart.fade_min_alpha = 95
            self.extensor_chart.fade_min_alpha = 95
            self.menu_button.bg = (235, 235, 235)
            self.menu_button.hover_bg = (210, 210, 210)
            self._menu_panel_bg = (245, 245, 245)
            self._menu_panel_border = WHITE
            self._background_light_overlay_alpha = 84
            self._title_text_color = (40, 40, 40)
            self._title_text_outline = WHITE
            self._title_box_fill_rgba = (255, 255, 255, 196)
            self._round_text_color = (45, 45, 45)
            self._round_text_outline = WHITE
            self._status_progress_color = (180, 140, 45)
            self._status_win_color = (45, 135, 75)
            self._status_text_outline = WHITE
            self._version_text_color = (90, 90, 90)
            self._version_text_outline = WHITE
            self.menu_button.border_color_override = WHITE
            for btn in (self.settings_button, self.reset_button, self.mirror_button, self.exit_button):
                btn.bg = (225, 225, 225)
                btn.hover_bg = (205, 205, 205)
                btn.fg = BLACK
                btn.border_color_override = WHITE
        # Keep stop/start semantic colors while refreshing label and state.
        self._update_start_stop_button_style()

    def _refresh_theme(self):
        latest_theme = bool(self.get_is_dark_theme())
        if latest_theme == self._is_dark_theme:
            return
        self._is_dark_theme = latest_theme
        self._apply_theme_styles()

    def _clamp_stars_to_collect(self, value: float) -> int:
        return int(max(1, min(7, round(float(value)))))

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

    def _snap_grip_target(self, grip_target: float) -> float:
        step = max(0.01, self.grip_step)
        return max(0.0, min(1.0, round(grip_target / step) * step))

    def _stabilize_grip_target(self, candidate_target: float) -> float:
        """
        Stabilize command output without touching active-muscle arbitration.

        A direction flip (closing->opening or opening->closing) is accepted only
        after the candidate moves far enough from current hold target. This avoids
        one-step polarity chatter around crossover/co-contraction boundaries.
        """
        delta = candidate_target - self._grip_target_hold
        if abs(delta) < 1e-9:
            return self._grip_target_hold

        direction = 1 if delta > 0.0 else -1
        forward_gate = max(0.0, self.forward_deadband)
        reversal_gate = max(0.0, self.reversal_deadband)
        if self._last_target_direction != 0 and direction != self._last_target_direction:
            if reversal_gate > 0.0 and abs(delta) < reversal_gate:
                return self._grip_target_hold
        elif forward_gate > 0.0 and abs(delta) < forward_gate:
            return self._grip_target_hold

        self._last_target_direction = direction
        return candidate_target

    def _percentile(self, values: List[float], percentile: float) -> float:
        if not values:
            return 0.0
        p = max(0.0, min(100.0, float(percentile)))
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * (p / 100.0)
        low = int(math.floor(pos))
        high = int(math.ceil(pos))
        if low == high:
            return ordered[low]
        weight = pos - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    def _compute_effective_thresholds(
        self, base_thr: float
    ) -> tuple[float, float, float, float, float, float]:
        """
        Raise per-channel arbitration thresholds when each channel's low-percentile
        baseline rises due to sustained noise.
        """
        flexor_floor = self._percentile(
            list(self._flexor_noise_floor_hist), self.noise_floor_percentile
        )
        extensor_floor = self._percentile(
            list(self._extensor_noise_floor_hist), self.noise_floor_percentile
        )
        flexor_guard_thr = flexor_floor + self.noise_floor_guard
        extensor_guard_thr = extensor_floor + self.noise_floor_guard
        flexor_thr = max(base_thr, flexor_guard_thr)
        extensor_thr = max(base_thr, extensor_guard_thr)
        return (
            max(0.0, min(0.99, flexor_floor)),
            max(0.0, min(0.99, extensor_floor)),
            max(0.0, min(0.99, flexor_guard_thr)),
            max(0.0, min(0.99, extensor_guard_thr)),
            max(0.0, min(0.99, flexor_thr)),
            max(0.0, min(0.99, extensor_thr)),
        )

    def _choose_active_muscle(
        self,
        emg_flexor: float,
        emg_extensor: float,
        flexor_thr: float,
        extensor_thr: float,
    ) -> Optional[str]:
        """
        Decide which muscle currently owns control ("flexor", "extensor", or None).

        Porting notes:
        - Inputs are normalized activations in [0, 1] for each muscle.
        - Two thresholds are derived from base threshold:
          * flexor activate/deactivate from flexor_thr
          * extensor activate/deactivate from extensor_thr
        - When one muscle is already active, keep it latched until it falls below
          deactivation threshold, unless the opposite side becomes clearly dominant.
        - This latching+hysteresis prevents rapid direction chatter near threshold.
        """
        deactivate_flexor_thr = max(0.0, flexor_thr - self.deactivation_hysteresis)
        deactivate_extensor_thr = max(0.0, extensor_thr - self.deactivation_hysteresis)
        activate_flexor_thr = min(1.0, flexor_thr + self.activation_hysteresis)
        activate_extensor_thr = min(1.0, extensor_thr + self.activation_hysteresis)
        # Allow switching away from a latched muscle when the opposite side is
        # clearly dominant, even if the latched side is still in its
        # deactivation hysteresis window.
        dominance_margin = max(self.activation_hysteresis, self.deactivation_hysteresis)

        if self._active_muscle == "flexor":
            # Switching direction requires both:
            # 1) the opposite side to clear activation threshold, and
            # 2) a minimum lead over the currently latched side.
            if (
                emg_extensor >= activate_extensor_thr
                and (emg_extensor - emg_flexor) >= dominance_margin
            ):
                return "extensor"
            # Otherwise keep the latch while flexor remains above its
            # deactivation threshold (hysteresis hold zone).
            if emg_flexor >= deactivate_flexor_thr:
                return "flexor"

        if self._active_muscle == "extensor":
            # Symmetric rule for switching from extensor to flexor.
            if (
                emg_flexor >= activate_flexor_thr
                and (emg_flexor - emg_extensor) >= dominance_margin
            ):
                return "flexor"
            # Keep extensor latched until it decays below deactivate threshold.
            if emg_extensor >= deactivate_extensor_thr:
                return "extensor"

        # No valid latch remains: acquire a fresh active side.
        # Priority is Flexor when both satisfy equivalent conditions.
        if emg_flexor >= activate_flexor_thr:
            return "flexor"
        if emg_extensor >= activate_extensor_thr:
            return "extensor"

        # Borderline tie-break near base threshold (below activate threshold):
        # keep Flexor priority for deterministic behavior.
        if emg_flexor >= flexor_thr and emg_extensor >= extensor_thr:
            return "flexor"
        return None

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
            should_rehome = (not trigger_can_run) or first_start_this_session
            if should_rehome:
                # Re-home on non-trigger start and trigger first-start only.
                start_pos = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
                self._grip_target_hold = self._snap_grip_target(start_pos)
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
            self.exit_button.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                inside_menu = self._menu_panel_rect.collidepoint(event.pos) or self.menu_button.rect.collidepoint(event.pos)
                if not inside_menu:
                    self._menu_open = False

        if click_should_toggle_start_stop:
            self._toggle_run_pause()

    def update(self, dt: float):
        self._refresh_theme()
        latest_blur = max(0.0, min(100.0, float(self.get_background_blur_percent())))
        if abs(latest_blur - self._background_blur_percent) >= 0.1:
            self.set_background_blur_percent(latest_blur)
        self.set_max_stars(self.get_stars_to_collect())

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
        ) = self._compute_effective_thresholds(base_thr)
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

        if not use_flexor and not use_extensor:
            self._active_muscle = None
        elif use_flexor and use_extensor:
            # Flexor has priority. Add hysteresis to avoid rapid direction toggling near threshold.
            self._active_muscle = self._choose_active_muscle(
                emg_flexor, emg_extensor, flexor_thr, extensor_thr
            )
        elif use_flexor:
            self._active_muscle = "flexor" if emg_flexor >= base_thr else None
        else:
            self._active_muscle = "extensor" if emg_extensor >= base_thr else None
        # "Great Job" feedback is muscle-specific; clear it once control changes side.
        if self._show_great_job and self._active_muscle != self._great_job_muscle:
            self._show_great_job = False
            self._great_job_muscle = None

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
                        hold_target = self._snap_grip_target(self.hand_pos_provider())
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
        snapped_target = self._snap_grip_target(raw_target)
        grip_target = self._stabilize_grip_target(snapped_target)
        self._grip_target_hold = grip_target

        # Rate-limit outgoing motor commands to a fixed command_rate_hz.
        if self.is_motor_output_enabled and (current_time - self._last_command_time >= self.command_update_interval):
            self.send_grip(grip_target)
            self._last_command_time = current_time

        if self._is_trigger_session_mode and self.is_motor_output_enabled and self._trigger_session_remaining_s > 0.0:
            self._trigger_session_remaining_s = max(0.0, self._trigger_session_remaining_s - dt)

        hand_pos = self.hand_pos_provider()
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

        # Game progression stops once all cycles are completed.
        if self._is_trigger_session_mode and self._trigger_session_remaining_s <= 0.0:
            self.countdown_timer = 0.0
            self._trigger_phase_wait_timer = 0.0
            return
        if self.stars_collected >= self.max_stars:
            self.countdown_timer = 0.0
            self._trigger_phase_wait_timer = 0.0
            return

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

    def _draw_stars(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        star_count = max(1, self.max_stars)
        star_spacing = s(20)
        min_outer = s(30)
        max_outer = s(54)
        side_margin = s(100)
        available_width = max(2 * min_outer, self.screen_rect.w - 2 * side_margin)
        max_outer_by_width = (available_width - (star_count - 1) * star_spacing) // max(2, 2 * star_count)
        r_outer = max(min_outer, min(max_outer, int(max_outer_by_width)))
        r_inner = max(s(14), int(round(r_outer * 0.45)))
        star_width = 2 * r_outer
        star_height = 2 * r_outer

        margin_bottom = s(56)

        total_stars_width = self.max_stars * star_width + (self.max_stars - 1) * star_spacing
        start_x = self.screen_rect.centerx - total_stars_width // 2
        charts_bottom = max(self.flexor_chart.rect.bottom, self.extensor_chart.rect.bottom)
        desired_center_y = charts_bottom + s(20) + star_height // 2
        max_center_y = self.screen_rect.h - margin_bottom - star_height // 2
        start_y = min(desired_center_y, max_center_y)

        dual_phase_progress = self._effective_training_mode == "both"
        half_progress_units = self.stars_collected * 2
        if dual_phase_progress and self.stars_collected < self.max_stars and self._cycle_phase == "extension":
            half_progress_units += 1

        for i in range(self.max_stars):
            points = []
            ox = start_x + star_width // 2 + i * (star_width + star_spacing)
            oy = start_y
            for k in range(10):
                ang = math.pi / 2 + k * math.pi / 5
                r = r_outer if k % 2 == 0 else r_inner
                x = int(ox + r * math.cos(ang))
                y = int(oy - r * math.sin(ang))
                points.append((x, y))

            star_fill_units = max(0, min(2, half_progress_units - (i * 2)))
            if star_fill_units >= 2:
                pygame.draw.polygon(surface, YELLOW, points)
            elif star_fill_units == 1:
                pygame.draw.polygon(surface, GRAY, points)
                star_left = ox - star_width // 2
                star_top = oy - star_height // 2
                half_fill = pygame.Surface((star_width, star_height), pygame.SRCALPHA)
                shifted_points = [(x - star_left, y - star_top) for x, y in points]
                pygame.draw.polygon(half_fill, YELLOW, shifted_points)
                surface.blit(half_fill, (star_left, star_top), area=pygame.Rect(0, 0, star_width // 2, star_height))
            else:
                pygame.draw.polygon(surface, GRAY, points)
            star_outline = (30, 30, 30) if self._is_dark_theme else WHITE
            pygame.draw.polygon(surface, star_outline, points, width=max(2, s(3)))

        round_idx = min(self.max_stars, self.stars_collected + 1)
        round_text = self._t("round_text", current=round_idx, total=self.max_stars)
        round_img = self.font_round.render(round_text, True, self._round_text_color)
        round_x = self.screen_rect.centerx - round_img.get_width() // 2
        round_y = start_y - r_outer - round_img.get_height() - s(10)
        draw_outlined_text(
            surface,
            self.font_round,
            round_text,
            self._round_text_color,
            (round_x, round_y),
            outline_color=self._round_text_outline,
            outline_width=2,
        )

    def _draw_trigger_session_stats(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        remaining_total = max(0, int(math.ceil(self._trigger_session_remaining_s)))
        remaining_min = remaining_total // 60
        remaining_sec = remaining_total % 60
        time_text = self._t(
            "trigger_time_left_text",
            minutes=remaining_min,
            seconds=f"{remaining_sec:02d}",
        )
        rep_text = self._t("trigger_repetition_text", count=self._trigger_repetition_count)

        charts_bottom = max(self.flexor_chart.rect.bottom, self.extensor_chart.rect.bottom)
        base_y = min(charts_bottom + s(10), self.screen_rect.h - s(180))
        time_img = self.font_round.render(time_text, True, self._round_text_color)
        rep_img = self.font_small.render(rep_text, True, self._round_text_color)
        time_x = self.screen_rect.centerx - time_img.get_width() // 2
        rep_x = self.screen_rect.centerx - rep_img.get_width() // 2

        draw_outlined_text(
            surface,
            self.font_round,
            time_text,
            self._round_text_color,
            (time_x, base_y),
            outline_color=self._round_text_outline,
            outline_width=2,
        )
        draw_outlined_text(
            surface,
            self.font_small,
            rep_text,
            self._round_text_color,
            (rep_x, base_y + self.font_round.get_height() + s(8)),
            outline_color=self._round_text_outline,
            outline_width=2,
        )

    def draw(self, surface: pygame.Surface):
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

        status_font = _pick_font(int(self.font_big.get_height() * 1.2), prefer_cjk=self._is_cjk_language(self._current_language))
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
        self.set_game_language = set_game_language
        self.get_game_language = get_game_language
        self.get_language_options = get_language_options
        self._set_theme_mode = set_theme_mode
        self.get_is_dark_theme = get_is_dark_theme
        self._is_dark_theme = bool(self.get_is_dark_theme())
        self._current_language = self.get_game_language()
        self.font_title = _pick_font(s(36), prefer_cjk=True)
        self.font_subtitle = _pick_font(s(30), prefer_cjk=True)
        self.font = _pick_font(s(24), prefer_cjk=True)
        self.font_hint = _pick_font(s(16), prefer_cjk=True)
        self.font_welcome_title = _pick_font(s(30), prefer_cjk=True)
        self.font_welcome_body = _pick_font(s(20), prefer_cjk=True)
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
        self._training_trigger_modes = ["auto", "trigger-and-go", "trigger-and-maintain"]
        incoming_trigger_mode = str(init_values.get("training_trigger_mode", "auto")).strip().lower()
        self._training_trigger_mode = (
            incoming_trigger_mode if incoming_trigger_mode in self._training_trigger_modes else "auto"
        )
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
        self.step_theme_mode = OptionStepper(
            self._t("settings_theme_mode_label"),
            (x0, y0 + s(1050)),
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
            self.step_theme_mode,
        ]
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
        self._tab_stepper_ids: Dict[str, List[str]] = {
            "welcome": [],
            "game": [
                "countdown",
                "stars_to_collect",
                "training_duration_minutes",
                "background_blur",
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
            self._t("settings_shortcuts_settings_x"),
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
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        min_w = s(220)
        text_w = self.font.size(self.close_btn.text)[0]
        self.close_btn.rect.w = max(min_w, text_w + s(48))

    def _build_tab_buttons(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self._tab_buttons = []
        self._tab_button_keys = []
        tab_h = s(34)
        tab_gap = s(8)
        tab_count = max(1, len(self._tabs))
        available_w = self._stepper_view_rect.w - tab_gap * (tab_count - 1)
        tab_w = max(s(90), available_w // tab_count)
        tab_y = self.panel.rect.y + s(120)
        x = self._content_left
        for key, label in self._tabs:
            btn = Button(
                pygame.Rect(x, tab_y, tab_w, tab_h),
                label,
                self.font_hint,
                on_click=self._create_tab_click_handler(key),
            )
            self._tab_buttons.append(btn)
            self._tab_button_keys.append(key)
            x += tab_w + tab_gap

    def _create_tab_click_handler(self, tab_key: str):
        def click_handler():
            self._set_active_tab(tab_key)

        return click_handler

    def _set_active_tab(self, tab_key: str):
        if tab_key == self._active_tab or tab_key not in self._tab_stepper_ids:
            return
        self._active_tab = tab_key
        self._update_tab_button_states()
        self._refresh_stepper_layout(reset_scroll=True)

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
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        row_gap = self._stepper_row_gap
        content_pad = s(12)
        self._active_stepper_base_y = {}
        self._training_muscle_toggle_base_y = None
        self._training_trigger_toggle_base_y = None
        self._game_advanced_toggle_base_y = None
        self._emg_advanced_toggle_base_y = None
        self._exo_advanced_toggle_base_y = None
        current_y = self._stepper_view_rect.y + content_pad
        row_count = 0

        if self._active_tab == "game":
            self._training_muscle_toggle_base_y = current_y
            # Training muscle selector uses a label row and two button rows.
            current_y += row_gap * 3
            row_count += 3
            basic_steppers = [
                self._stepper_by_id[k]
                for k in self._tab_stepper_ids.get("game", [])
                if k in self._stepper_by_id
            ]
            for stepper in basic_steppers:
                self._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1
            self._game_advanced_toggle_base_y = current_y
            current_y += row_gap
            row_count += 1
            if self._show_game_advanced:
                for key in self._game_advanced_stepper_ids:
                    stepper = self._stepper_by_id.get(key)
                    if not stepper:
                        continue
                    self._active_stepper_base_y[stepper] = current_y
                    stepper.set_y(current_y)
                    current_y += row_gap
                    row_count += 1
        elif self._active_tab == "emg":
            self._training_trigger_toggle_base_y = current_y
            # Trigger selector uses a label row and two button rows.
            current_y += row_gap * 3
            row_count += 3
            basic_steppers = [
                self._stepper_by_id[k]
                for k in self._tab_stepper_ids.get("emg", [])
                if k in self._stepper_by_id
            ]
            for stepper in basic_steppers:
                self._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1

            self._emg_advanced_toggle_base_y = current_y
            current_y += row_gap
            row_count += 1

            if self._show_emg_advanced:
                for key in self._emg_advanced_stepper_ids:
                    stepper = self._stepper_by_id.get(key)
                    if not stepper:
                        continue
                    self._active_stepper_base_y[stepper] = current_y
                    stepper.set_y(current_y)
                    current_y += row_gap
                    row_count += 1
        elif self._active_tab == "exo":
            basic_steppers = [
                self._stepper_by_id[k]
                for k in self._tab_stepper_ids.get("exo", [])
                if k in self._stepper_by_id
            ]
            for stepper in basic_steppers:
                self._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1

            self._exo_advanced_toggle_base_y = current_y
            current_y += row_gap
            row_count += 1

            if self._show_exo_advanced:
                for key in self._exo_advanced_stepper_ids:
                    stepper = self._stepper_by_id.get(key)
                    if not stepper:
                        continue
                    self._active_stepper_base_y[stepper] = current_y
                    stepper.set_y(current_y)
                    current_y += row_gap
                    row_count += 1
        else:
            for stepper in self._active_steppers():
                self._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1

        if row_count > 0:
            content_height = content_pad * 2 + self._stepper_button_h + max(0, row_count - 1) * row_gap
        else:
            content_height = s(36)
        self._stepper_content_height = max(s(36), content_height)
        self._stepper_max_scroll = max(0, self._stepper_content_height - self._stepper_view_rect.h)
        if reset_scroll:
            self._stepper_scroll_offset = 0
        self._apply_stepper_scroll()

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

    def _set_theme_mode_selected(self, mode: str):
        normalized = self._normalize_theme_mode(mode)
        if normalized == self._theme_mode:
            return
        self._theme_mode = normalized
        self._set_theme_mode(normalized)
        self.step_theme_mode.set_value(self._theme_mode, notify=False)

    def _apply_theme_styles(self):
        if self._is_dark_theme:
            self.panel.bg = (0, 0, 0)
            self.panel.alpha = 210
            self._theme_text_color = WHITE
            self._theme_outline_color = BLACK
            self._stepper_view_bg = (25, 25, 25)
            self._stepper_view_border = (70, 70, 70)
            self._device_panel_bg = (25, 25, 25)
            self._device_panel_border = (70, 70, 70)
            self._device_header_bg = (40, 90, 180)
            self._device_header_hover_bg = (55, 115, 210)
            self._device_label_text_color = WHITE
            for button in (self.close_btn, self.scan_btn, self.sim_toggle, self.swap_btn):
                button.bg = (30, 30, 30)
                button.hover_bg = (60, 60, 60)
                button.fg = WHITE
                button.border_color_override = None
            self._stepper_scroll_up_btn.bg = (35, 35, 35)
            self._stepper_scroll_up_btn.hover_bg = (65, 65, 65)
            self._stepper_scroll_up_btn.fg = WHITE
            self._stepper_scroll_up_btn.border_color_override = None
            self._stepper_scroll_down_btn.bg = (35, 35, 35)
            self._stepper_scroll_down_btn.hover_bg = (65, 65, 65)
            self._stepper_scroll_down_btn.fg = WHITE
            self._stepper_scroll_down_btn.border_color_override = None
            for stepper in self._steppers:
                stepper.set_style(
                    text_color=WHITE,
                    text_outline_color=BLACK,
                    button_bg=(35, 35, 35),
                    button_hover_bg=(65, 65, 65),
                    button_fg=WHITE,
                    button_border_color=None,
                )
        else:
            self.panel.bg = (245, 245, 245)
            self.panel.alpha = 228
            self._theme_text_color = BLACK
            self._theme_outline_color = WHITE
            self._stepper_view_bg = (240, 240, 240)
            self._stepper_view_border = (140, 140, 140)
            self._device_panel_bg = (240, 240, 240)
            self._device_panel_border = (140, 140, 140)
            self._device_header_bg = (130, 180, 235)
            self._device_header_hover_bg = (150, 195, 240)
            self._device_label_text_color = BLACK
            for button in (self.close_btn, self.scan_btn, self.sim_toggle, self.swap_btn):
                button.bg = (225, 225, 225)
                button.hover_bg = (205, 205, 205)
                button.fg = BLACK
                button.border_color_override = WHITE
            self._stepper_scroll_up_btn.bg = (220, 220, 220)
            self._stepper_scroll_up_btn.hover_bg = (205, 205, 205)
            self._stepper_scroll_up_btn.fg = BLACK
            self._stepper_scroll_up_btn.border_color_override = WHITE
            self._stepper_scroll_down_btn.bg = (220, 220, 220)
            self._stepper_scroll_down_btn.hover_bg = (205, 205, 205)
            self._stepper_scroll_down_btn.fg = BLACK
            self._stepper_scroll_down_btn.border_color_override = WHITE
            for stepper in self._steppers:
                stepper.set_style(
                    text_color=BLACK,
                    text_outline_color=WHITE,
                    button_bg=(220, 220, 220),
                    button_hover_bg=(205, 205, 205),
                    button_fg=BLACK,
                    button_border_color=WHITE,
                )
        self._update_tab_button_states()
        self._update_training_muscle_mode_buttons()
        self._update_training_trigger_mode_buttons()
        self._update_game_advanced_button_label()
        self._update_emg_advanced_button_label()
        self._update_exo_advanced_button_label()
        self._update_language_button_states()
        # During __init__, theme styles can apply before bound-device getters are assigned.
        if hasattr(self, "get_bound_flexor_emg"):
            self._update_bind_button_states()
            if self._device_buttons:
                self._build_device_buttons_from_bound()

    def _refresh_theme(self):
        latest_theme = bool(self.get_is_dark_theme())
        if latest_theme == self._is_dark_theme:
            return
        self._is_dark_theme = latest_theme
        self._apply_theme_styles()

    def _toggle_game_advanced(self):
        self._show_game_advanced = not self._show_game_advanced
        self._update_game_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_game_advanced_button_label(self):
        state_key = "settings_state_on" if self._show_game_advanced else "settings_state_off"
        self.game_advanced_toggle_btn.text = self._t("settings_btn_game_advanced", state=self._t(state_key))
        if self._is_dark_theme and self._show_game_advanced:
            self.game_advanced_toggle_btn.bg = (35, 115, 60)
            self.game_advanced_toggle_btn.hover_bg = (55, 145, 80)
            self.game_advanced_toggle_btn.fg = WHITE
        elif self._is_dark_theme:
            self.game_advanced_toggle_btn.bg = (70, 45, 45)
            self.game_advanced_toggle_btn.hover_bg = (95, 65, 65)
            self.game_advanced_toggle_btn.fg = WHITE
        elif self._show_game_advanced:
            self.game_advanced_toggle_btn.bg = (85, 160, 90)
            self.game_advanced_toggle_btn.hover_bg = (110, 190, 115)
            self.game_advanced_toggle_btn.fg = BLACK
        else:
            self.game_advanced_toggle_btn.bg = (230, 205, 205)
            self.game_advanced_toggle_btn.hover_bg = (220, 185, 185)
            self.game_advanced_toggle_btn.fg = BLACK

    def _toggle_emg_advanced(self):
        self._show_emg_advanced = not self._show_emg_advanced
        self._update_emg_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_emg_advanced_button_label(self):
        state_key = "settings_state_on" if self._show_emg_advanced else "settings_state_off"
        self.emg_advanced_toggle_btn.text = self._t("settings_btn_emg_advanced", state=self._t(state_key))
        if self._is_dark_theme and self._show_emg_advanced:
            self.emg_advanced_toggle_btn.bg = (35, 115, 60)
            self.emg_advanced_toggle_btn.hover_bg = (55, 145, 80)
            self.emg_advanced_toggle_btn.fg = WHITE
        elif self._is_dark_theme:
            self.emg_advanced_toggle_btn.bg = (70, 45, 45)
            self.emg_advanced_toggle_btn.hover_bg = (95, 65, 65)
            self.emg_advanced_toggle_btn.fg = WHITE
        elif self._show_emg_advanced:
            self.emg_advanced_toggle_btn.bg = (85, 160, 90)
            self.emg_advanced_toggle_btn.hover_bg = (110, 190, 115)
            self.emg_advanced_toggle_btn.fg = BLACK
        else:
            self.emg_advanced_toggle_btn.bg = (230, 205, 205)
            self.emg_advanced_toggle_btn.hover_bg = (220, 185, 185)
            self.emg_advanced_toggle_btn.fg = BLACK

    def _toggle_exo_advanced(self):
        self._show_exo_advanced = not self._show_exo_advanced
        self._update_exo_advanced_button_label()
        self._refresh_stepper_layout(reset_scroll=True)

    def _update_exo_advanced_button_label(self):
        state_key = "settings_state_on" if self._show_exo_advanced else "settings_state_off"
        self.exo_advanced_toggle_btn.text = self._t("settings_btn_exo_advanced", state=self._t(state_key))
        if self._is_dark_theme and self._show_exo_advanced:
            self.exo_advanced_toggle_btn.bg = (35, 115, 60)
            self.exo_advanced_toggle_btn.hover_bg = (55, 145, 80)
            self.exo_advanced_toggle_btn.fg = WHITE
        elif self._is_dark_theme:
            self.exo_advanced_toggle_btn.bg = (70, 45, 45)
            self.exo_advanced_toggle_btn.hover_bg = (95, 65, 65)
            self.exo_advanced_toggle_btn.fg = WHITE
        elif self._show_exo_advanced:
            self.exo_advanced_toggle_btn.bg = (85, 160, 90)
            self.exo_advanced_toggle_btn.hover_bg = (110, 190, 115)
            self.exo_advanced_toggle_btn.fg = BLACK
        else:
            self.exo_advanced_toggle_btn.bg = (230, 205, 205)
            self.exo_advanced_toggle_btn.hover_bg = (220, 185, 185)
            self.exo_advanced_toggle_btn.fg = BLACK

    def _apply_translations(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self._current_language = self.get_game_language()
        self.close_btn.text = self._t("settings_btn_apply")
        self._resize_close_button()
        self.scan_btn.text = self._t("settings_btn_scan_ble")
        self.sim_toggle.text = self._sim_toggle_text()
        max_sim_w = self._right_col_width - self.scan_btn.rect.w - s(12)
        sim_text_width = self.font.size(self.sim_toggle.text)[0]
        self.sim_toggle.rect.w = max(s(160), min(max_sim_w, sim_text_width + s(40)))
        self.swap_btn.text = self._t("settings_btn_swap_flexor_extensor")
        self._shortcut_lines = self._build_shortcut_lines()
        self._language_title = self._t("settings_language_title")
        self.step_emg_max_flexor.label = self._t("settings_stepper_emg_max_flexor")
        self.step_emg_max_extensor.label = self._t("settings_stepper_emg_max_extensor")
        self.step_hand_start.label = self._t("settings_stepper_hand_start_percent")
        self.step_threshold.label = self._t("settings_stepper_threshold_percent")
        self.step_trigger_threshold.label = self._t("settings_stepper_trigger_threshold_percent")
        self.step_trigger_wait_seconds.label = self._t("settings_stepper_trigger_wait_seconds")
        self.step_relax_flexion.label = self._t("settings_stepper_relax_flexion_percent")
        self.step_relax_extension.label = self._t("settings_stepper_relax_extension_percent")
        self.step_countdown.label = self._t("settings_stepper_countdown_seconds")
        self.step_stars_to_collect.label = self._t("settings_stepper_stars_to_collect")
        self.step_training_duration_minutes.label = self._t("settings_stepper_training_duration_minutes")
        self.step_target_flexion.label = self._t("settings_stepper_target_flexion_percent")
        self.step_target_extension.label = self._t("settings_stepper_target_extension_percent")
        self.step_grip_step.label = self._t("settings_stepper_grip_step_percent")
        self.step_command_rate.label = self._t("settings_stepper_command_rate_hz")
        self.step_activation_hysteresis.label = self._t("settings_stepper_activate_hysteresis_percent")
        self.step_deactivation_hysteresis.label = self._t("settings_stepper_release_hysteresis_percent")
        self.step_forward_deadband.label = self._t("settings_stepper_forward_deadband_percent")
        self.step_reversal_deadband.label = self._t("settings_stepper_reverse_deadband_percent")
        self.step_background_blur.label = self._t("settings_stepper_background_blur_percent")
        self.step_theme_mode.label = self._t("settings_theme_mode_label")
        self.step_theme_mode.set_options(self._theme_mode_options())
        self.step_theme_mode.set_value(self._theme_mode, notify=False)
        self.step_dynamic_mvc_alpha_up.label = self._t("settings_stepper_mvc_alpha_up")
        self.step_dynamic_mvc_alpha_down.label = self._t("settings_stepper_mvc_alpha_down")
        self.step_dynamic_mvc_up_margin.label = self._t("settings_stepper_mvc_up_margin")
        self.step_dynamic_mvc_hold_activity.label = self._t("settings_stepper_mvc_hold_ratio")
        self.step_dynamic_mvc_decay_trigger.label = self._t("settings_stepper_mvc_decay_trigger")
        self.step_dynamic_mvc_decay_grace.label = self._t("settings_stepper_mvc_decay_grace_seconds")
        self._tabs = [
            ("welcome", self._t("settings_tab_welcome")),
            ("game", self._t("settings_tab_game")),
            ("emg", self._t("settings_tab_emg_control")),
            ("exo", self._t("settings_tab_exo_output")),
        ]
        self._build_tab_buttons()
        self._update_tab_button_states()
        self._apply_theme_styles()
        self._update_training_muscle_mode_buttons()
        self._update_training_trigger_mode_buttons()
        self._update_game_advanced_button_label()
        self._update_emg_advanced_button_label()
        self._update_exo_advanced_button_label()
        for stepper in self._steppers:
            stepper._update_button_positions()
        self._refresh_stepper_layout(reset_scroll=False)
        self._build_device_buttons_from_bound()

    def _apply_stepper_scroll(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self._stepper_scroll_offset = max(0, min(self._stepper_max_scroll, self._stepper_scroll_offset))
        visible = self._active_steppers()
        for stepper in visible:
            base_y = self._active_stepper_base_y.get(stepper, stepper.y)
            stepper.set_y(base_y - self._stepper_scroll_offset)
        if self._active_tab == "emg" and self._emg_advanced_toggle_base_y is not None:
            self.emg_advanced_toggle_btn.rect.y = self._emg_advanced_toggle_base_y - self._stepper_scroll_offset
            self.emg_advanced_toggle_btn.rect.x = self._stepper_view_rect.x + s(10)
            self.emg_advanced_toggle_btn.rect.w = max(s(120), self._stepper_view_rect.w - s(28))
            self.emg_advanced_toggle_btn.rect.h = max(s(32), self._stepper_button_h)
        if self._active_tab == "emg" and self._training_trigger_toggle_base_y is not None:
            section_y = self._training_trigger_toggle_base_y - self._stepper_scroll_offset
            section_x = self._stepper_view_rect.x + s(10)
            section_w = max(s(120), self._stepper_view_rect.w - s(28))
            button_h = max(s(32), self._stepper_button_h)
            button_gap = s(8)
            col_gap = s(10)
            col_w = max(s(100), (section_w - col_gap) // 2)
            for idx, button in enumerate(self._training_trigger_mode_buttons):
                row = idx // 2
                col = idx % 2
                button.rect.x = section_x + col * (col_w + col_gap)
                button.rect.y = section_y + s(24) + row * (button_h + button_gap)
                button.rect.w = col_w
                button.rect.h = button_h
        if self._active_tab == "game" and self._training_muscle_toggle_base_y is not None:
            section_y = self._training_muscle_toggle_base_y - self._stepper_scroll_offset
            section_x = self._stepper_view_rect.x + s(10)
            section_w = max(s(120), self._stepper_view_rect.w - s(28))
            button_h = max(s(32), self._stepper_button_h)
            button_gap = s(8)
            col_gap = s(10)
            col_w = max(s(100), (section_w - col_gap) // 2)
            for idx, button in enumerate(self._training_muscle_mode_buttons):
                row = idx // 2
                col = idx % 2
                button.rect.x = section_x + col * (col_w + col_gap)
                button.rect.y = section_y + s(24) + row * (button_h + button_gap)
                button.rect.w = col_w
                button.rect.h = button_h
        if self._active_tab == "game" and self._game_advanced_toggle_base_y is not None:
            self.game_advanced_toggle_btn.rect.y = self._game_advanced_toggle_base_y - self._stepper_scroll_offset
            self.game_advanced_toggle_btn.rect.x = self._stepper_view_rect.x + s(10)
            self.game_advanced_toggle_btn.rect.w = max(s(120), self._stepper_view_rect.w - s(28))
            self.game_advanced_toggle_btn.rect.h = max(s(32), self._stepper_button_h)
        if self._active_tab == "exo" and self._exo_advanced_toggle_base_y is not None:
            self.exo_advanced_toggle_btn.rect.y = self._exo_advanced_toggle_base_y - self._stepper_scroll_offset
            self.exo_advanced_toggle_btn.rect.x = self._stepper_view_rect.x + s(10)
            self.exo_advanced_toggle_btn.rect.w = max(s(120), self._stepper_view_rect.w - s(28))
            self.exo_advanced_toggle_btn.rect.h = max(s(32), self._stepper_button_h)
        can_scroll = self._stepper_max_scroll > 0
        self._stepper_scroll_up_btn.disabled = (not can_scroll) or self._stepper_scroll_offset <= 0
        self._stepper_scroll_down_btn.disabled = (not can_scroll) or self._stepper_scroll_offset >= self._stepper_max_scroll

    def _scroll_steppers(self, delta_steps: int):
        if self._stepper_max_scroll <= 0:
            return
        self._stepper_scroll_offset += delta_steps * self._stepper_scroll_step
        self._apply_stepper_scroll()

    def _build_language_buttons(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        options = self.get_language_options()
        self._language_buttons = []
        self._language_button_codes = []
        if not options:
            return

        button_w = max(s(180), min(s(280), self._left_col_width // 3))
        button_h = s(34)
        base_x = self._content_left + self._left_col_width - button_w - s(32)
        shortcuts_h = len(self._shortcut_lines) * self._shortcut_line_gap
        base_y = self.close_btn.rect.y - shortcuts_h - s(8) + self._shortcut_line_gap +s(8)
        gap = s(6)

        for idx, (code, display_name) in enumerate(options):
            btn = Button(
                pygame.Rect(base_x, base_y + idx * (button_h + gap), button_w, button_h),
                display_name,
                self.font_hint,
                on_click=self._create_language_click_handler(code),
            )
            self._language_buttons.append(btn)
            self._language_button_codes.append(code)
        self._update_language_button_states()

    def _create_language_click_handler(self, language_code: str):
        def click_handler():
            self.set_game_language(language_code)
            self._apply_translations()
            self._update_language_button_states()
        return click_handler

    def _update_language_button_states(self):
        current = self.get_game_language()
        for button, code in zip(self._language_buttons, self._language_button_codes):
            is_active = code == current
            if self._is_dark_theme:
                button.bg = (40, 120, 40) if is_active else (35, 35, 35)
                button.hover_bg = (60, 160, 60) if is_active else (65, 65, 65)
                button.fg = WHITE
            else:
                button.bg = (70, 150, 80) if is_active else (225, 225, 225)
                button.hover_bg = (95, 180, 105) if is_active else (205, 205, 205)
                button.fg = BLACK

    def _toggle_sim(self):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.ble.simulation = not self.ble.simulation
        sim_text = self._sim_toggle_text()
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
            upper_name = name.upper()
            if "HOH" in upper_name:
                return (0, name.casefold())
            if "AKR" in upper_name:
                return (1, name.casefold())
            if "EMGS" in upper_name:
                return (2, name.casefold())
            return (3, name.casefold())

        merged.sort(key=sort_key)
        return merged

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
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        display_devices = self._get_display_devices()
        if not display_devices:
            self._device_buttons = []
            return

        self._device_buttons = []
        x, y = self._device_view_rect.x, self._device_view_rect.y
        display_devices_scrolled = display_devices[self._device_scroll_offset :]
        row_h = self._device_row_height
        line_h = s(36)
        button_gap = s(8)
        label_w = max(s(220), self._device_view_rect.w)
        role_btn_w = max(s(88), (label_w - 2 * button_gap) // 3)
        for d in display_devices_scrolled:
            device_label = d.name or "Unknown"
            max_heading_width = label_w - s(16)
            heading_tail = ""
            mac_suffix = self._format_device_mac_suffix(d.address)

            # Prefer showing a compact MAC suffix by truncating the name first.
            heading_text = f"{device_label}{heading_tail}"
            if mac_suffix:
                heading_with_mac = f"{device_label}{heading_tail}{mac_suffix}"
                if self.font.size(heading_with_mac)[0] <= max_heading_width:
                    heading_text = heading_with_mac
                else:
                    trimmed_name = device_label
                    compact_with_mac = f"{trimmed_name}...{heading_tail}{mac_suffix}"
                    while trimmed_name and self.font.size(compact_with_mac)[0] > max_heading_width:
                        trimmed_name = trimmed_name[:-1]
                        compact_with_mac = f"{trimmed_name}...{heading_tail}{mac_suffix}"
                    if trimmed_name:
                        heading_text = compact_with_mac

            if self.font.size(heading_text)[0] > max_heading_width:
                trimmed_name = device_label
                compact_text = f"{trimmed_name}...{heading_tail}"
                while trimmed_name and self.font.size(compact_text)[0] > max_heading_width:
                    trimmed_name = trimmed_name[:-1]
                    compact_text = f"{trimmed_name}...{heading_tail}"
                if trimmed_name:
                    heading_text = compact_text
            label_btn = Button(pygame.Rect(x, y, label_w, line_h), heading_text, self.font, on_click=lambda: None)
            label_btn.bg = self._device_header_bg
            label_btn.hover_bg = self._device_header_hover_bg
            label_btn.fg = self._device_label_text_color
            label_btn.border_color_override = None if self._is_dark_theme else WHITE
            self._device_buttons.append((label_btn, "label", d))

            rx = x
            bind_y = y + line_h + s(2)
            roles = [
                (self._t("settings_role_flexor"), "bind_flexor", self.on_bind_flexor_emg),
                (self._t("settings_role_extensor"), "bind_extensor", self.on_bind_extensor_emg),
                (self._t("settings_role_exo_hand"), "bind_exo", self.on_bind_exo_hand),
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
        self._last_device_list_signature = self._compute_device_list_signature()

    def _compute_device_list_signature(self) -> tuple:
        display_devices = self._get_display_devices()
        items = []
        for dev in display_devices:
            addr = (dev.address or "").upper()
            roles = tuple(self._bound_roles_for_device(dev))
            connected = self._is_device_connected(dev)
            items.append((addr, roles, connected))
        return tuple(items)

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
        bound_flexor_emg = self.get_bound_flexor_emg()
        bound_extensor_emg = self.get_bound_extensor_emg()
        bound_exo_hand = self.get_bound_exo_hand()

        for button, role, device in self._device_buttons:
            if role == "label":
                continue

            button.disabled = False
            is_bound = False
            if role == "bind_flexor":
                is_bound = bound_flexor_emg is not None and bound_flexor_emg.address == device.address
            elif role == "bind_extensor":
                is_bound = bound_extensor_emg is not None and bound_extensor_emg.address == device.address
            elif role == "bind_exo":
                is_bound = bound_exo_hand is not None and bound_exo_hand.address == device.address

            is_connected = self._is_device_connected(device)
            if is_bound:
                if is_connected:
                    if self._is_dark_theme:
                        button.bg = (40, 120, 40)
                        button.hover_bg = (60, 160, 60)
                        button.fg = WHITE
                        button.border_color_override = None
                    else:
                        button.bg = (145, 220, 145)
                        button.hover_bg = (168, 232, 168)
                        button.fg = BLACK
                        button.border_color_override = WHITE
                else:
                    if self._is_dark_theme:
                        button.bg = (150, 95, 30)
                        button.hover_bg = (180, 120, 45)
                        button.fg = WHITE
                        button.border_color_override = None
                    else:
                        button.bg = (238, 208, 145)
                        button.hover_bg = (245, 220, 168)
                        button.fg = BLACK
                        button.border_color_override = WHITE
            else:
                if self._is_dark_theme:
                    button.bg = (30, 30, 30)
                    button.hover_bg = (60, 60, 60)
                    button.fg = WHITE
                    button.border_color_override = None
                else:
                    button.bg = (225, 225, 225)
                    button.hover_bg = (205, 205, 205)
                    button.fg = BLACK
                    button.border_color_override = WHITE

    def _scan(self):
        if self._scan_thread and self._scan_thread.is_alive():
            return

        self.scan_btn.disabled = True
        self.devices = []
        self._device_buttons = []
        self._devices_ready = []
        self._scan_status = self._t("settings_scan_status_scanning")
        self._scan_has_error = False
        self._auto_bind_status = self._t("settings_auto_bind_active")
        self._scan_start_time = time.time()

        def _is_fully_connected() -> bool:
            exo = self.get_bound_exo_hand()
            flexor = self.get_bound_flexor_emg()
            extensor = self.get_bound_extensor_emg()
            if not exo or not flexor or not extensor:
                return False
            return (
                self.ble.is_connected(exo.address)
                and self.ble.is_connected(flexor.address)
                and self.ble.is_connected(extensor.address)
            )

        def _bind_device_to_role(dev: BLEDeviceInfo, role: str) -> bool:
            if not self.ble.is_connected(dev.address):
                if not self.ble.connect(dev.address):
                    return False
            if role == "exo":
                self.on_bind_exo_hand(dev)
                self._auto_bind_status = self._t("settings_auto_bound_exo_hand", name=dev.name, address=dev.address)
            elif role == "extensor":
                self.on_bind_extensor_emg(dev)
                self._auto_bind_status = self._t("settings_auto_bound_extensor_emg", name=dev.name, address=dev.address)
            elif role == "flexor":
                self.on_bind_flexor_emg(dev)
                self._auto_bind_status = self._t("settings_auto_bound_flexor_emg", name=dev.name, address=dev.address)
            self._update_bind_button_states()
            return True

        def _auto_bind_discovered_device(dev: BLEDeviceInfo):
            name_upper = (dev.name or "").upper()
            if not name_upper:
                return

            # Exo hand auto-bind rule: match "HOH" but exclude any "HOHA" variant.
            if "HOH" in name_upper and "HOHA" not in name_upper:
                if self.get_bound_exo_hand() is None:
                    _bind_device_to_role(dev, "exo")
                return

            # EMG auto-bind rule: first EMGS -> Extensor, second EMGS -> Flexor.
            if "EMGS" in name_upper:
                bound_extensor = self.get_bound_extensor_emg()
                bound_flexor = self.get_bound_flexor_emg()
                if bound_extensor is None:
                    _bind_device_to_role(dev, "extensor")
                    return
                if bound_flexor is None and bound_extensor.address != dev.address:
                    _bind_device_to_role(dev, "flexor")

        def do_scan():
            try:
                # Run short scan passes so we can auto-bind devices and stop early.
                max_scan_seconds = 10.0
                pass_timeout = 1.0
                start_time = time.time()
                discovered_by_address: dict[str, BLEDeviceInfo] = {}

                while time.time() - start_time < max_scan_seconds:
                    if _is_fully_connected():
                        self._auto_bind_status = self._t("settings_auto_bind_complete")
                        break

                    found = self.ble.scan(timeout=pass_timeout)
                    for dev in found:
                        addr = (dev.address or "").upper()
                        if not addr:
                            continue
                        if addr not in discovered_by_address:
                            discovered_by_address[addr] = dev
                        else:
                            # Prefer the newest non-empty name if previous one was unknown.
                            prev = discovered_by_address[addr]
                            if (prev.name or "").strip().lower() in ("", "unknown") and (dev.name or "").strip():
                                discovered_by_address[addr] = dev
                        _auto_bind_discovered_device(discovered_by_address[addr])
                        if _is_fully_connected():
                            self._auto_bind_status = self._t("settings_auto_bind_complete")
                            break

                    self.devices = list(discovered_by_address.values())
                    self._device_scroll_offset = 0
                    self._build_device_buttons_from_bound()
                    if _is_fully_connected():
                        self._auto_bind_status = self._t("settings_auto_bind_complete")
                        break

                self._devices_ready = list(discovered_by_address.values())
                if not self._auto_bind_status:
                    self._auto_bind_status = self._t("settings_auto_bind_finished_manual_available")
                self._device_scroll_offset = 0
                self._build_device_buttons_from_bound()
            except Exception as e:
                self._scan_status = self._t("settings_scan_error", error=e)
                self._scan_has_error = True
                self._auto_bind_status = self._t("settings_auto_bind_interrupted")

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
            elif event.key == pygame.K_UP:
                self._scroll_steppers(-1)
            elif event.key == pygame.K_DOWN:
                self._scroll_steppers(1)
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
