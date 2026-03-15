import io
import math
import os
import threading
import time
from typing import Callable, List, Optional, Set

import pygame

from ..ui.widgets import (
    Button,
    Label,
    Panel,
    BarGauge,
    NumericStepper,
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
        get_target_flexion_percent: Callable[[], float],
        get_target_extension_percent: Callable[[], float],
        get_countdown_seconds: Callable[[], float],
        get_grip_step_percent: Callable[[], float],
        get_command_rate_hz: Callable[[], float],
        get_activation_hysteresis_percent: Callable[[], float],
        get_deactivation_hysteresis_percent: Callable[[], float],
        get_forward_deadband_percent: Callable[[], float],
        get_reversal_deadband_percent: Callable[[], float],
        get_background_blur_percent: Callable[[], float],
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
        self.get_target_flexion_percent = get_target_flexion_percent
        self.get_target_extension_percent = get_target_extension_percent
        self.get_countdown_seconds = get_countdown_seconds
        self.get_grip_step_percent = get_grip_step_percent
        self.get_command_rate_hz = get_command_rate_hz
        self.get_activation_hysteresis_percent = get_activation_hysteresis_percent
        self.get_deactivation_hysteresis_percent = get_deactivation_hysteresis_percent
        self.get_forward_deadband_percent = get_forward_deadband_percent
        self.get_reversal_deadband_percent = get_reversal_deadband_percent
        self.get_background_blur_percent = get_background_blur_percent
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
        self.max_stars = 3

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
            line_color=(35, 105, 200),
            bg_color=GAME_BG,
            reverse_direction=True,
        )
        self.extensor_chart = EMGChart(
            pygame.Rect(self.screen_rect.w - side_margin - chart_width - s(100), chart_y + s(100), chart_width, chart_height),
            max_samples=500,
            line_color=(185, 45, 45),
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
        self._is_mirrored = False
        self.hand_gauge.set_labels("", "")
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

    def _toggle_menu(self):
        self._menu_open = not self._menu_open

    def _open_settings_from_menu(self):
        self._menu_open = False
        self.open_settings()

    def _reset_from_menu(self):
        self._menu_open = False
        self._reset()

    def _update_start_stop_button_style(self):
        if self.is_motor_output_enabled:
            self.start_pause_button.text = self._t("btn_stop")
            self.start_pause_button.bg = (150, 50, 50)
            self.start_pause_button.hover_bg = (185, 70, 70)
            self.start_pause_button.fg = WHITE
        else:
            self.start_pause_button.text = self._t("btn_start")
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
        self._last_target_direction = 0
        self._last_command_time = 0.0
        self._show_great_job = False
        self._great_job_muscle = None

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

    def _choose_active_muscle(self, emg_flexor: float, emg_extensor: float, thr: float) -> Optional[str]:
        """
        Decide which muscle currently owns control ("flexor", "extensor", or None).

        Porting notes:
        - Inputs are normalized activations in [0, 1] for each muscle.
        - Two thresholds are derived from base threshold:
          * activate_thr = thr + activation_hysteresis
          * deactivate_thr = thr - deactivation_hysteresis
        - When one muscle is already active, keep it latched until it falls below
          deactivation threshold, unless the opposite side becomes clearly dominant.
        - This latching+hysteresis prevents rapid direction chatter near threshold.
        """
        deactivate_thr = max(0.0, thr - self.deactivation_hysteresis)
        activate_thr = min(1.0, thr + self.activation_hysteresis)
        # Allow switching away from a latched muscle when the opposite side is
        # clearly dominant, even if the latched side is still in its
        # deactivation hysteresis window.
        dominance_margin = max(self.activation_hysteresis, self.deactivation_hysteresis)

        if self._active_muscle == "flexor":
            # Switching direction requires both:
            # 1) the opposite side to clear activation threshold, and
            # 2) a minimum lead over the currently latched side.
            if emg_extensor >= activate_thr and (emg_extensor - emg_flexor) >= dominance_margin:
                return "extensor"
            # Otherwise keep the latch while flexor remains above its
            # deactivation threshold (hysteresis hold zone).
            if emg_flexor >= deactivate_thr:
                return "flexor"

        if self._active_muscle == "extensor":
            # Symmetric rule for switching from extensor to flexor.
            if emg_flexor >= activate_thr and (emg_flexor - emg_extensor) >= dominance_margin:
                return "flexor"
            # Keep extensor latched until it decays below deactivate threshold.
            if emg_extensor >= deactivate_thr:
                return "extensor"

        # No valid latch remains: acquire a fresh active side.
        # Priority is Flexor when both satisfy equivalent conditions.
        if emg_flexor >= activate_thr:
            return "flexor"
        if emg_extensor >= activate_thr:
            return "extensor"

        # Borderline tie-break near base threshold (below activate threshold):
        # keep Flexor priority for deterministic behavior.
        if emg_flexor >= thr and emg_extensor >= thr:
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
        self.is_motor_output_enabled = not self.is_motor_output_enabled
        self._update_start_stop_button_style()
        if self.is_motor_output_enabled:
            # On Start, re-home to configured start flexion before EMG-driven control.
            start_pos = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
            self._grip_target_hold = self._snap_grip_target(start_pos)
            self._last_target_direction = 0
            self.send_grip(self._grip_target_hold)
            self._last_command_time = time.time()
            self._show_great_job = False
            self._great_job_muscle = None

    def _get_status_label_text(self) -> str:
        if not self.is_motor_output_enabled:
            return self._t("status_lets_start")

        if self._show_great_job:
            return self._t("status_great_job")

        if self.countdown_timer > 0.0:
            cd = int(self.countdown_timer) + (1 if self.countdown_timer - int(self.countdown_timer) > 0 else 0)
            if self._cycle_phase == "flexion":
                return self._t("status_hold_on_flexion", count=cd)
            return self._t("status_hold_on_extension", count=cd)

        phase_games_on_text = (
            self._t("status_games_on_flexion")
            if self._cycle_phase == "flexion"
            else self._t("status_games_on_extension")
        )

        if self._active_muscle is None:
            return phase_games_on_text

        target_muscle = "flexor" if self._cycle_phase == "flexion" else "extensor"
        if self._active_muscle == target_muscle:
            return phase_games_on_text

        if self._cycle_phase == "flexion":
            return self._t("status_try_harder_flexion")
        return self._t("status_try_harder_extension")

    def _draw_phase_arrow(self, surface: pygame.Surface):
        if not self.is_motor_output_enabled:
            return

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
        pygame.draw.polygon(surface, (30, 30, 30), points, width=max(2, s(3)))
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
        latest_blur = max(0.0, min(100.0, float(self.get_background_blur_percent())))
        if abs(latest_blur - self._background_blur_percent) >= 0.1:
            self.set_background_blur_percent(latest_blur)

        # Main closed-loop control tick:
        # EMG activations -> active muscle -> grip target -> exo command + game progression.
        emg_flexor = self.emg_flexor_provider()
        emg_extensor = self.emg_extensor_provider()
        # Read tunables every frame so Settings changes apply immediately.
        hand_start = max(0.0, min(1.0, self.get_hand_start_percent() / 100.0))
        thr = self.get_threshold_percent() / 100.0
        # Keep threshold < 1.0 to preserve usable normalization denominator.
        thr = max(0.0, min(0.99, thr))
        self.grip_step = max(0.01, min(1.0, self.get_grip_step_percent() / 100.0))
        command_rate_hz = max(1.0, self.get_command_rate_hz())
        self.command_update_interval = 1.0 / command_rate_hz
        self.activation_hysteresis = max(0.0, min(0.5, self.get_activation_hysteresis_percent() / 100.0))
        self.deactivation_hysteresis = max(0.0, min(0.5, self.get_deactivation_hysteresis_percent() / 100.0))
        self.forward_deadband = max(0.0, min(1.0, self.get_forward_deadband_percent() / 100.0))
        self.reversal_deadband = max(0.0, min(1.0, self.get_reversal_deadband_percent() / 100.0))

        self.flexor_bar.set_value(emg_flexor)
        self.extensor_bar.set_value(emg_extensor)
        self.flexor_bar.set_threshold(thr)
        self.extensor_bar.set_threshold(thr)

        # Charts run at their own cadence to avoid over-rendering while still
        # reflecting raw packet behavior.
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
        # "Great Job" feedback is muscle-specific; clear it once control changes side.
        if self._show_great_job and self._active_muscle != self._great_job_muscle:
            self._show_great_job = False
            self._great_job_muscle = None
        
        # Compute the target position for the robot hand depending on the currently active muscle
        if self._active_muscle == "flexor":
            # Above-threshold flexor activation maps linearly to [hand_start .. fully closed].
            flex_norm = (emg_flexor - thr) / max(0.01, 1.0 - thr)
            flex_norm = max(0.0, min(1.0, flex_norm))
            raw_target = hand_start + (1.0 - hand_start) * flex_norm
        elif self._active_muscle == "extensor":
            # Above-threshold extensor activation maps linearly to [hand_start .. fully open].
            ext_norm = (emg_extensor - thr) / max(0.01, 1.0 - thr)
            ext_norm = max(0.0, min(1.0, ext_norm))
            raw_target = hand_start * (1.0 - ext_norm)
        else:
            # No valid active side: hold last snapped target for stable behavior.
            raw_target = self._grip_target_hold

        # Quantize first, then stabilize direction changes in command space.
        snapped_target = self._snap_grip_target(raw_target)
        grip_target = self._stabilize_grip_target(snapped_target)
        self._grip_target_hold = grip_target

        # Rate-limit outgoing motor commands to a fixed command_rate_hz.
        if self.is_motor_output_enabled and (current_time - self._last_command_time >= self.command_update_interval):
            self.send_grip(grip_target)
            self._last_command_time = current_time

        hand_pos = self.hand_pos_provider()
        target_flexion = max(0.0, min(1.0, self.get_target_flexion_percent() / 100.0))
        target_extension = max(0.0, min(1.0, self.get_target_extension_percent() / 100.0))
        self.hand_gauge.set_value(hand_pos)
        self.hand_gauge.set_partition(hand_start)
        self.hand_gauge.set_targets(target_flexion, target_extension)

        # Game progression stops once all cycles are completed.
        if self.stars_collected >= self.max_stars:
            self.countdown_timer = 0.0
            return

        # Evaluate current phase success condition against measured hand position.
        if self._cycle_phase == "flexion":
            phase_target_reached = hand_pos >= target_flexion
        else:
            phase_target_reached = hand_pos <= target_extension

        if phase_target_reached:
            if self.countdown_timer <= 0.0:
                # Enter hold period the first frame target becomes true.
                self.countdown_timer = self.get_countdown_seconds()
            else:
                self.countdown_timer = max(0.0, self.countdown_timer - dt)
                if self.countdown_timer == 0.0:
                    self._show_great_job = True
                    self._great_job_muscle = self._active_muscle
                    if self._cycle_phase == "flexion":
                        # Half-cycle complete: switch to extension phase.
                        self._cycle_phase = "extension"
                    else:
                        # Full cycle complete: award one star and restart flexion phase.
                        self.stars_collected = min(self.max_stars, self.stars_collected + 1)
                        self._cycle_phase = "flexion"
        else:
            # Hold requirement must be continuous; any break resets timer.
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

        half_progress_units = self.stars_collected * 2
        if self.stars_collected < self.max_stars and self._cycle_phase == "extension":
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
            pygame.draw.polygon(surface, (30, 30, 30), points, width=max(2, s(3)))

        round_idx = min(self.max_stars, self.stars_collected + 1)
        round_text = self._t("round_text", current=round_idx, total=self.max_stars)
        round_img = self.font_round.render(round_text, True, WHITE)
        round_x = self.screen_rect.centerx - round_img.get_width() // 2
        round_y = start_y - r_outer - round_img.get_height() - s(10)
        draw_outlined_text(surface, self.font_round, round_text, WHITE, (round_x, round_y), outline_width=2)

    def draw(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        if self._background_image is not None:
            surface.blit(self._background_image, (0, 0))
        else:
            surface.fill(GAME_BG)
        title_text = self._t("title_main")
        title = self.font_big.render(title_text, True, BLACK)
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
        title_box.fill((255, 255, 255, 153))
        surface.blit(title_box, title_box_rect.topleft)
        pygame.draw.rect(surface, (30, 30, 30), title_box_rect, width=max(1, s(2)), border_radius=s(22))
        draw_outlined_text(surface, self.font_big, title_text, BLACK, title_pos, outline_color=WHITE, outline_width=1)

        self._draw_stars(surface)
        self.hand_gauge.draw(surface, self.font_small)
        self._draw_phase_arrow(surface)
        self.flexor_bar.draw(surface)
        self.extensor_bar.draw(surface)
        self.flexor_chart.draw(surface)
        self.extensor_chart.draw(surface)
        self.flexor_label.draw(surface)
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
                outline_width=status_outline_width,
            )
            scaled_w = max(1, int(round(src_w * status_scale)))
            scaled_h = max(1, int(round(src_h * status_scale)))
            scaled_status = pygame.transform.smoothscale(status_surface, (scaled_w, scaled_h))
            status_x = self.screen_rect.centerx - scaled_w // 2
            status_y = self._title_y + self.font_big.get_height() + s(85) - scaled_h // 2
            surface.blit(scaled_status, (status_x, status_y))

        if self.stars_collected >= self.max_stars:
            _draw_scaled_status_text(self._t("win_text"), GREEN)
        else:
            _draw_scaled_status_text(self._get_status_label_text(), YELLOW)

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
                WHITE,
                (self.menu_button.rect.x + icon_pad_x, y),
                (self.menu_button.rect.x + icon_pad_x + icon_width, y),
                width=line_w,
            )
        if self._menu_open:
            pygame.draw.rect(surface, (20, 20, 20), self._menu_panel_rect, border_radius=max(6, s(10)))
            pygame.draw.rect(surface, (180, 180, 180), self._menu_panel_rect, width=2, border_radius=max(6, s(10)))
            self.settings_button.draw(surface)
            self.reset_button.draw(surface)
            self.start_pause_button.draw(surface)
            self.mirror_button.draw(surface)
            self.exit_button.draw(surface)

        version_text = f"v{self.game_version}"
        version_img = self.font_tiny.render(version_text, True, GRAY)
        version_x = self.screen_rect.w - version_img.get_width() - s(20)
        version_y = self.screen_rect.h - version_img.get_height() - s(20)
        draw_outlined_text(surface, self.font_tiny, version_text, GRAY, (version_x, version_y), outline_width=2)


class SettingsScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ui_scale: float,
        ble: BLEManager,
        on_close: Callable[[], None],
        set_game_language: Callable[[str], None],
        get_game_language: Callable[[], str],
        get_language_options: Callable[[], List[tuple[str, str]]],
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
        set_forward_deadband_percent: Callable[[float], None],
        set_reversal_deadband_percent: Callable[[float], None],
        set_background_blur_percent: Callable[[float], None],
        set_dynamic_mvc_alpha_up: Callable[[float], None],
        set_dynamic_mvc_alpha_down: Callable[[float], None],
        set_dynamic_mvc_up_margin_ratio: Callable[[float], None],
        set_dynamic_mvc_hold_activity_ratio: Callable[[float], None],
        set_dynamic_mvc_decay_trigger_ratio: Callable[[float], None],
        set_dynamic_mvc_decay_grace_seconds: Callable[[float], None],
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
        self.set_game_language = set_game_language
        self.get_game_language = get_game_language
        self.get_language_options = get_language_options
        # Settings stays English, but language names can be Chinese.
        self.font_title = _pick_font(s(36), prefer_cjk=True)
        self.font = _pick_font(s(24), prefer_cjk=True)
        self.font_hint = _pick_font(s(16), prefer_cjk=True)
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
        self._auto_bind_status = ""
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
            ("Forward Deadband %", "{:.0f}%", init_values.get("forward_deadband_percent", 0)),
            ("Reverse Deadband %", "{:.0f}%", init_values.get("reversal_deadband_percent", 8)),
            ("Background Blur %", "{:.0f}%", init_values.get("background_blur_percent", 25)),
            ("MVC Alpha Up", "{:.2f}", init_values.get("dynamic_mvc_alpha_up", 0.2)),
            ("MVC Alpha Down", "{:.2f}", init_values.get("dynamic_mvc_alpha_down", 0.01)),
            ("MVC Up Margin", "{:.2f}", init_values.get("dynamic_mvc_up_margin_ratio", 0.03)),
            ("MVC Hold Ratio", "{:.2f}", init_values.get("dynamic_mvc_hold_activity_ratio", 0.85)),
            ("MVC Decay Trigger", "{:.2f}", init_values.get("dynamic_mvc_decay_trigger_ratio", 0.60)),
            ("MVC Decay Grace s", "{:.1f}", init_values.get("dynamic_mvc_decay_grace_seconds", 2.0)),
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
        self.step_forward_deadband = NumericStepper(
            "Forward Deadband %",
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
            "Reverse Deadband %",
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
            "MVC Alpha Up",
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
            "MVC Alpha Down",
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
            "MVC Up Margin",
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
            "MVC Hold Ratio",
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
            "MVC Decay Trigger",
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
            "MVC Decay Grace s",
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
            "Background Blur %",
            (x0, y0 + s(950)),
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
        self._steppers = [
            self.step_emg_max_flexor,
            self.step_emg_max_extensor,
            self.step_hand_start,
            self.step_threshold,
            self.step_countdown,
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
        ]
        self._stepper_base_y = [stepper.y for stepper in self._steppers]
        self._stepper_scroll_offset = 0
        self._stepper_scroll_step = s(40)
        self._stepper_row_gap = s(50)
        self._shortcut_lines = (
            "Keyboard Shortcuts in Main Game:",
            "    Enter = Start/Stop",
            "    Space = Reset",
            "    Escape = Exit Game",
            "    S = Open Settings",
            "    M = Toggle Mirror",
            "    F = Simulate Flexor Muscle Activation (in Simulation Mode)",
            "    E = Simulate Extensor Muscle Activation (in Simulation Mode)",
            "    ",
            "Keyboard Shortcuts in Settings (this page):",
            "    A = Apply/Close",
            "    B = Scan BLE",
            "    T = Toggle Simulation",
            "    ",
        )
        self._shortcut_line_gap = s(18)
        self._language_title = ""
        self._language_buttons: List[Button] = []
        self._language_button_codes: List[str] = []
        shortcuts_h = len(self._shortcut_lines) * self._shortcut_line_gap
        self._stepper_view_rect = pygame.Rect(
            self._content_left,
            self.panel.rect.y + s(120),
            self._left_col_width - s(20),
            max(s(120), self.close_btn.rect.y - shortcuts_h - s(20) - (self.panel.rect.y + s(120))),
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
        # Include the vertical offset between view top and first row, otherwise
        # we may underestimate content height and incorrectly disable scrolling.
        stepper_top = min(self._stepper_base_y) if self._stepper_base_y else self._stepper_view_rect.y
        stepper_bottom = (max(self._stepper_base_y) + stepper_button_h) if self._stepper_base_y else stepper_top
        self._stepper_content_height = max(s(36), stepper_bottom - self._stepper_view_rect.y + s(12))
        self._stepper_max_scroll = max(0, self._stepper_content_height - self._stepper_view_rect.h)
        self._apply_stepper_scroll()

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
        self._build_language_buttons()
        # Auto-start a BLE scan when entering Settings (same as pressing Scan BLE).
        self._scan()

    def _apply_stepper_scroll(self):
        self._stepper_scroll_offset = max(0, min(self._stepper_max_scroll, self._stepper_scroll_offset))
        for stepper, base_y in zip(self._steppers, self._stepper_base_y):
            stepper.set_y(base_y - self._stepper_scroll_offset)
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
        base_x = self._content_left + self._left_col_width - button_w - s(20)
        shortcuts_h = len(self._shortcut_lines) * self._shortcut_line_gap
        base_y = self.close_btn.rect.y - shortcuts_h - s(8) + self._shortcut_line_gap
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
            self._update_language_button_states()
        return click_handler

    def _update_language_button_states(self):
        current = self.get_game_language()
        for button, code in zip(self._language_buttons, self._language_button_codes):
            is_active = code == current
            button.bg = (40, 120, 40) if is_active else (35, 35, 35)
            button.hover_bg = (60, 160, 60) if is_active else (65, 65, 65)
            button.fg = WHITE

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
        self._auto_bind_status = "Auto-bind active: HOH->Exo, EMGS#1->Extensor, EMGS#2->Flexor"
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
                self._auto_bind_status = f"Auto-bound Exo Hand: {dev.name} [{dev.address}]"
            elif role == "extensor":
                self.on_bind_extensor_emg(dev)
                self._auto_bind_status = f"Auto-bound Extensor EMG: {dev.name} [{dev.address}]"
            elif role == "flexor":
                self.on_bind_flexor_emg(dev)
                self._auto_bind_status = f"Auto-bound Flexor EMG: {dev.name} [{dev.address}]"
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
                        self._auto_bind_status = "Auto-bind complete: Exo + Extensor + Flexor connected. Scan stopped."
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
                            self._auto_bind_status = "Auto-bind complete: Exo + Extensor + Flexor connected. Scan stopped."
                            break

                    self.devices = list(discovered_by_address.values())
                    self._device_scroll_offset = 0
                    self._build_device_buttons_from_bound()
                    if _is_fully_connected():
                        self._auto_bind_status = "Auto-bind complete: Exo + Extensor + Flexor connected. Scan stopped."
                        break

                self._devices_ready = list(discovered_by_address.values())
                if not self._auto_bind_status:
                    self._auto_bind_status = "Auto-bind finished. Manual role assignment remains available."
                self._device_scroll_offset = 0
                self._build_device_buttons_from_bound()
            except Exception as e:
                self._scan_status = f"Scan error: {e}"
                self._auto_bind_status = "Auto-bind interrupted due to scan error. Manual role assignment remains available."

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
        self._stepper_scroll_up_btn.handle_event(event)
        self._stepper_scroll_down_btn.handle_event(event)
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
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if mouse_in_stepper_view:
                for stepper in self._steppers:
                    stepper.handle_event(event)
        else:
            for stepper in self._steppers:
                stepper.handle_event(event)

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
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            if total_devices > self._device_list_max_visible:
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
            if role not in ("label", "mac_label"):
                b.handle_event(event)

    def update(self, dt: float):
        _ = dt
        if not self._device_buttons:
            self._build_device_buttons_from_bound()
        self._update_bind_button_states()
        self._update_language_button_states()

    def draw(self, surface: pygame.Surface):
        s = lambda v: max(1, int(round(v * self.ui_scale)))
        self.panel.draw(surface)
        settings_title = "Settings"
        draw_outlined_text(
            surface,
            self.font_title,
            settings_title,
            WHITE,
            (self.panel.rect.x + s(20), self.panel.rect.y + s(20)),
            outline_color=BLACK,
            outline_width=2,
        )
        self.close_btn.draw(surface)
        self.scan_btn.draw(surface)
        self.sim_toggle.draw(surface)

        hint_text = "Tune EMG scaling and control behavior:"
        draw_outlined_text(
            surface,
            self.font,
            hint_text,
            WHITE,
            (self._content_left, self.panel.rect.y + s(80)),
            outline_color=BLACK,
            outline_width=2,
        )

        # Left-column stepper viewport (scrollable) so new steppers can be added safely.
        pygame.draw.rect(surface, (25, 25, 25), self._stepper_view_rect, border_radius=8)
        pygame.draw.rect(surface, (70, 70, 70), self._stepper_view_rect, width=2, border_radius=8)
        previous_clip = surface.get_clip()
        surface.set_clip(self._stepper_view_rect)
        for stepper in self._steppers:
            stepper.draw(surface)
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

        # Keep shortcuts fixed above the Apply button with a language column beside it.
        shortcuts_h = len(self._shortcut_lines) * self._shortcut_line_gap
        shortcuts_y = self.close_btn.rect.y - shortcuts_h - s(8)
        language_x = self._content_left + self._left_col_width - max(s(180), min(s(280), self._left_col_width // 3)) - s(20)
        if self._language_title:
            draw_outlined_text(
                surface,
                self.font_hint,
                self._language_title,
                RED,
                (language_x, shortcuts_y),
                outline_color=BLACK,
                outline_width=1,
            )
        shortcuts_clip = pygame.Rect(
            self._content_left,
            shortcuts_y,
            max(s(120), language_x - self._content_left - s(16)),
            shortcuts_h + s(8),
        )
        previous_clip = surface.get_clip()
        surface.set_clip(shortcuts_clip)
        for idx, text in enumerate(self._shortcut_lines):
            draw_outlined_text(
                surface,
                self.font_hint,
                text,
                RED,
                (self._content_left, shortcuts_y + idx * self._shortcut_line_gap),
                outline_color=BLACK,
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
        pygame.draw.rect(surface, (25, 25, 25), (placeholder_x, placeholder_y, placeholder_w, placeholder_h), border_radius=8)
        pygame.draw.rect(surface, (70, 70, 70), (placeholder_x, placeholder_y, placeholder_w, placeholder_h), width=2, border_radius=8)
        draw_outlined_text(
            surface,
            self.font,
            "BLE Scan Results",
            WHITE,
            (self._device_list_left, self._scan_results_header_y),
            outline_color=BLACK,
            outline_width=2,
        )
        if self._auto_bind_status:
            draw_outlined_text(
                surface,
                self.font_hint,
                self._auto_bind_status,
                (160, 220, 255),
                (self._device_list_left, self._scan_results_header_y + s(22)),
                outline_color=BLACK,
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
            scanning_text = f"[SCANNING{dots}] BLE scan in progress, please wait..."
            draw_outlined_text(
                surface,
                self.font,
                scanning_text,
                YELLOW,
                (self._device_list_left, self._scan_results_status_y),
                outline_color=BLACK,
                outline_width=2,
            )
        elif self._devices_ready and elapsed < min_display_time:
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = f"[SCANNING{dots}] BLE scan complete, processing..."
            draw_outlined_text(
                surface,
                self.font,
                scanning_text,
                YELLOW,
                (self._device_list_left, self._scan_results_status_y),
                outline_color=BLACK,
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
        elif self._scan_status and "error" in self._scan_status.lower():
            draw_outlined_text(
                surface,
                self.font,
                self._scan_status,
                RED,
                (self._device_list_left, self._scan_results_status_y),
                outline_color=BLACK,
                outline_width=2,
            )
            self.scan_btn.disabled = False
        else:
            idle_text = "Press 'Scan BLE' to discover devices."
            draw_outlined_text(
                surface,
                self.font,
                idle_text,
                (180, 180, 180),
                (self._device_list_left, self._scan_results_status_y),
                outline_color=BLACK,
                outline_width=2,
            )
            manual_hint_text = "Manual assignment is always available via Flexor/Extensor/Exo buttons below."
            draw_outlined_text(
                surface,
                self.font_hint,
                manual_hint_text,
                (180, 220, 180),
                (self._device_list_left, self._scan_results_status_y + s(22)),
                outline_color=BLACK,
                outline_width=1,
            )

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
            info_text = f"Total discovered: {total_devices} | Displaying: {visible_devices}{scroll_info}"
            draw_outlined_text(
                surface,
                self.font,
                info_text,
                WHITE,
                (self._device_list_left, self._info_text_y),
                outline_color=BLACK,
                outline_width=2,
            )

        for b, role, _ in self._device_buttons:
            if hasattr(b, "draw"):
                b.draw(surface)
