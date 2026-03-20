import io
import math
import os
from typing import Optional

import pygame

from ..ui.widgets import draw_outlined_text


def load_background_image(scene) -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = ("background_b.jpg", "background_B.jpg")
    for filename in candidates:
        asset_path = os.path.join(project_root, "assets", filename)
        if not os.path.exists(asset_path):
            continue
        try:
            raw_image = pygame.image.load(asset_path).convert()
            scaled = pygame.transform.smoothscale(raw_image, scene.screen_rect.size)
            scene._background_source_image = scaled
            scene.set_background_blur_percent(scene._background_blur_percent)
            return
        except pygame.error:
            scene._background_source_image = None
            scene._background_image = None
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
            scaled = pygame.transform.smoothscale(raw_image, scene.screen_rect.size)
            scene._background_source_image = scaled
            scene.set_background_blur_percent(scene._background_blur_percent)
            return
        except pygame.error:
            scene._background_source_image = None
            scene._background_image = None
            return


def create_soft_focus_background(image: pygame.Surface, blur_percent: float) -> pygame.Surface:
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


def apply_side_layout(scene) -> None:
    bar_w = scene._bar_w
    top = scene._bar_top
    side_margin = scene._side_margin
    chart_width = scene._chart_width
    chart_y = scene._chart_y
    chart_top = chart_y + int(round(100 * scene.ui_scale))
    chart_offset = int(round(100 * scene.ui_scale))

    left_bar_x = side_margin
    right_bar_x = scene.screen_rect.w - side_margin - bar_w
    left_chart_x = side_margin + chart_offset
    right_chart_x = scene.screen_rect.w - side_margin - chart_width - chart_offset

    if scene._is_mirrored:
        # Mirror layout: extensor on left, flexor on right.
        scene.extensor_bar.rect.x = left_bar_x
        scene.extensor_bar.rect.y = top
        scene.flexor_bar.rect.x = right_bar_x
        scene.flexor_bar.rect.y = top
        scene.extensor_chart.rect.x = left_chart_x
        scene.extensor_chart.rect.y = chart_top
        scene.flexor_chart.rect.x = right_chart_x
        scene.flexor_chart.rect.y = chart_top
        scene.extensor_chart.reverse_direction = True
        scene.flexor_chart.reverse_direction = False
    else:
        # Default layout: flexor on left, extensor on right.
        scene.flexor_bar.rect.x = left_bar_x
        scene.flexor_bar.rect.y = top
        scene.extensor_bar.rect.x = right_bar_x
        scene.extensor_bar.rect.y = top
        scene.flexor_chart.rect.x = left_chart_x
        scene.flexor_chart.rect.y = chart_top
        scene.extensor_chart.rect.x = right_chart_x
        scene.extensor_chart.rect.y = chart_top
        scene.flexor_chart.reverse_direction = True
        scene.extensor_chart.reverse_direction = False

    flexor_label_x = scene.flexor_bar.rect.centerx - scene.font_small.size(scene.flexor_label.text)[0] // 2
    extensor_label_x = scene.extensor_bar.rect.centerx - scene.font_small.size(scene.extensor_label.text)[0] // 2
    scene.flexor_label.pos = (flexor_label_x, scene._label_y)
    scene.extensor_label.pos = (extensor_label_x, scene._label_y)
    scene.hand_gauge.set_mirrored(scene._is_mirrored)


def apply_theme_styles(scene, white, black, gray, green, yellow) -> None:
    if scene._is_dark_theme:
        scene.flexor_bar.bg = (34, 34, 42)
        scene.extensor_bar.bg = (34, 34, 42)
        scene.flexor_bar.threshold_color = (250, 230, 90)
        scene.extensor_bar.threshold_color = (250, 230, 90)
        scene.flexor_bar.border_color_override = None
        scene.extensor_bar.border_color_override = None
        scene.hand_gauge.bg_color = (55, 55, 65)
        scene.hand_gauge.flexion_color = (90, 180, 255)
        scene.hand_gauge.extension_color = (255, 140, 140)
        scene.hand_gauge.target_color = (250, 230, 90)
        scene.hand_gauge.pointer_color = white
        scene.hand_gauge.center_text_color = white
        scene.hand_gauge.text_outline_color = black
        scene.flexor_chart.bg_color = (20, 20, 26)
        scene.extensor_chart.bg_color = (20, 20, 26)
        scene.flexor_chart.line_color = (20, 70, 140)
        scene.extensor_chart.line_color = (120, 25, 25)
        scene.flexor_chart.background_alpha = 0
        scene.extensor_chart.background_alpha = 0
        scene.flexor_chart.border_color = None
        scene.extensor_chart.border_color = None
        scene.flexor_chart.fade_min_alpha = 45
        scene.extensor_chart.fade_min_alpha = 45
        scene.menu_button.bg = (25, 25, 25)
        scene.menu_button.hover_bg = (55, 55, 55)
        scene._menu_panel_bg = (20, 20, 20)
        scene._menu_panel_border = (180, 180, 180)
        scene._background_light_overlay_alpha = 0
        scene._title_text_color = black
        scene._title_text_outline = white
        scene._title_box_fill_rgba = (255, 255, 255, 153)
        scene._round_text_color = white
        scene._round_text_outline = black
        scene._status_progress_color = yellow
        scene._status_win_color = green
        scene._status_text_outline = black
        scene._version_text_color = gray
        scene._version_text_outline = black
        scene.menu_button.border_color_override = None
        for btn in (
            scene.settings_button,
            scene.reset_button,
            scene.mirror_button,
            scene.sound_toggle_button,
            scene.music_toggle_button,
            scene.exit_button,
        ):
            btn.bg = (30, 30, 30)
            btn.hover_bg = (60, 60, 60)
            btn.fg = white
            btn.border_color_override = None
    else:
        scene.flexor_bar.bg = (224, 230, 242)
        scene.extensor_bar.bg = (224, 230, 242)
        scene.flexor_bar.threshold_color = (215, 175, 45)
        scene.extensor_bar.threshold_color = (215, 175, 45)
        scene.flexor_bar.border_color_override = white
        scene.extensor_bar.border_color_override = white
        scene.hand_gauge.bg_color = (175, 185, 205)
        scene.hand_gauge.flexion_color = (65, 130, 215)
        scene.hand_gauge.extension_color = (220, 105, 105)
        scene.hand_gauge.target_color = (215, 175, 45)
        scene.hand_gauge.pointer_color = (45, 45, 45)
        scene.hand_gauge.center_text_color = (45, 45, 45)
        scene.hand_gauge.text_outline_color = white
        scene.flexor_chart.bg_color = (230, 236, 247)
        scene.extensor_chart.bg_color = (230, 236, 247)
        scene.flexor_chart.line_color = (22, 74, 145)
        scene.extensor_chart.line_color = (145, 42, 42)
        # Keep chart background transparent in light theme.
        scene.flexor_chart.background_alpha = 0
        scene.extensor_chart.background_alpha = 0
        scene.flexor_chart.border_color = None
        scene.extensor_chart.border_color = None
        scene.flexor_chart.fade_min_alpha = 95
        scene.extensor_chart.fade_min_alpha = 95
        scene.menu_button.bg = (235, 235, 235)
        scene.menu_button.hover_bg = (210, 210, 210)
        scene._menu_panel_bg = (245, 245, 245)
        scene._menu_panel_border = white
        scene._background_light_overlay_alpha = 84
        scene._title_text_color = (40, 40, 40)
        scene._title_text_outline = white
        scene._title_box_fill_rgba = (255, 255, 255, 196)
        scene._round_text_color = (45, 45, 45)
        scene._round_text_outline = white
        scene._status_progress_color = (180, 140, 45)
        scene._status_win_color = (45, 135, 75)
        scene._status_text_outline = white
        scene._version_text_color = (90, 90, 90)
        scene._version_text_outline = white
        scene.menu_button.border_color_override = white
        for btn in (
            scene.settings_button,
            scene.reset_button,
            scene.mirror_button,
            scene.sound_toggle_button,
            scene.music_toggle_button,
            scene.exit_button,
        ):
            btn.bg = (225, 225, 225)
            btn.hover_bg = (205, 205, 205)
            btn.fg = black
            btn.border_color_override = white
    # Keep stop/start semantic colors while refreshing label and state.
    scene._update_start_stop_button_style()
    scene._update_sound_toggle_button()
    scene._update_music_toggle_button()


def draw_stars(scene, surface: pygame.Surface, yellow, gray, white) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    star_count = max(1, scene.max_stars)
    star_spacing = s(20)
    min_outer = s(30)
    max_outer = s(54)
    side_margin = s(100)
    available_width = max(2 * min_outer, scene.screen_rect.w - 2 * side_margin)
    max_outer_by_width = (available_width - (star_count - 1) * star_spacing) // max(2, 2 * star_count)
    r_outer = max(min_outer, min(max_outer, int(max_outer_by_width)))
    r_inner = max(s(14), int(round(r_outer * 0.45)))
    star_width = 2 * r_outer
    star_height = 2 * r_outer

    margin_bottom = s(56)

    total_stars_width = scene.max_stars * star_width + (scene.max_stars - 1) * star_spacing
    start_x = scene.screen_rect.centerx - total_stars_width // 2
    charts_bottom = max(scene.flexor_chart.rect.bottom, scene.extensor_chart.rect.bottom)
    desired_center_y = charts_bottom + s(20) + star_height // 2
    max_center_y = scene.screen_rect.h - margin_bottom - star_height // 2
    start_y = min(desired_center_y, max_center_y)

    dual_phase_progress = scene._effective_training_mode == "both"
    half_progress_units = scene.stars_collected * 2
    if dual_phase_progress and scene.stars_collected < scene.max_stars and scene._cycle_phase == "extension":
        half_progress_units += 1

    for i in range(scene.max_stars):
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
            pygame.draw.polygon(surface, yellow, points)
        elif star_fill_units == 1:
            pygame.draw.polygon(surface, gray, points)
            star_left = ox - star_width // 2
            star_top = oy - star_height // 2
            half_fill = pygame.Surface((star_width, star_height), pygame.SRCALPHA)
            shifted_points = [(x - star_left, y - star_top) for x, y in points]
            pygame.draw.polygon(half_fill, yellow, shifted_points)
            surface.blit(half_fill, (star_left, star_top), area=pygame.Rect(0, 0, star_width // 2, star_height))
        else:
            pygame.draw.polygon(surface, gray, points)
        star_outline = (30, 30, 30) if scene._is_dark_theme else white
        pygame.draw.polygon(surface, star_outline, points, width=max(2, s(3)))

    round_idx = min(scene.max_stars, scene.stars_collected + 1)
    round_text = scene._t("round_text", current=round_idx, total=scene.max_stars)
    round_img = scene.font_round.render(round_text, True, scene._round_text_color)
    round_x = scene.screen_rect.centerx - round_img.get_width() // 2
    round_y = start_y - r_outer - round_img.get_height() - s(10)
    draw_outlined_text(
        surface,
        scene.font_round,
        round_text,
        scene._round_text_color,
        (round_x, round_y),
        outline_color=scene._round_text_outline,
        outline_width=2,
    )


def draw_trigger_session_stats(scene, surface: pygame.Surface) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    remaining_total = max(0, int(math.ceil(scene._trigger_session_remaining_s)))
    remaining_min = remaining_total // 60
    remaining_sec = remaining_total % 60
    time_text = scene._t(
        "trigger_time_left_text",
        minutes=remaining_min,
        seconds=f"{remaining_sec:02d}",
    )
    rep_text = scene._t("trigger_repetition_text", count=scene._trigger_repetition_count)

    charts_bottom = max(scene.flexor_chart.rect.bottom, scene.extensor_chart.rect.bottom)
    base_y = min(charts_bottom + s(10), scene.screen_rect.h - s(180))
    time_img = scene.font_round.render(time_text, True, scene._round_text_color)
    rep_img = scene.font_small.render(rep_text, True, scene._round_text_color)
    time_x = scene.screen_rect.centerx - time_img.get_width() // 2
    rep_x = scene.screen_rect.centerx - rep_img.get_width() // 2

    draw_outlined_text(
        surface,
        scene.font_round,
        time_text,
        scene._round_text_color,
        (time_x, base_y),
        outline_color=scene._round_text_outline,
        outline_width=2,
    )
    draw_outlined_text(
        surface,
        scene.font_small,
        rep_text,
        scene._round_text_color,
        (rep_x, base_y + scene.font_round.get_height() + s(8)),
        outline_color=scene._round_text_outline,
        outline_width=2,
    )
