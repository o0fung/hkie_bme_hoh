import pygame

from ...ui.widgets import Button


def active_reset_button_text(scene) -> str:
    if scene._active_tab == "welcome":
        return scene._t("settings_btn_reset_all_to_default")
    return scene._t("settings_btn_reset_to_default")


def resize_close_button(scene) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    min_w = s(220)
    text_w = scene.font.size(scene.close_btn.text)[0]
    scene.close_btn.rect.w = max(min_w, text_w + s(48))


def update_reset_button_label(scene) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    text = active_reset_button_text(scene)
    scene.reset_tab_btn.text = text
    min_w = s(180)
    max_w = max(min_w, int(scene._stepper_view_rect.w * 0.36))
    scene.reset_tab_btn.rect.w = min(max_w, max(min_w, scene.font_hint.size(text)[0] + s(28)))
    scene.reset_tab_btn.rect.h = s(34)
    scene.reset_tab_btn.rect.y = scene.panel.rect.y + s(120)


def build_tab_buttons(scene) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    scene._tab_buttons = []
    scene._tab_button_keys = []
    tab_h = s(34)
    tab_gap = s(8)
    tab_count = max(1, len(scene._tabs))
    scene._update_reset_button_label()
    available_w = scene._stepper_view_rect.w - scene.reset_tab_btn.rect.w - tab_gap * tab_count
    available_w = max(s(320), available_w)
    tab_w = max(s(90), available_w // tab_count)
    tab_y = scene.panel.rect.y + s(120)
    x = scene._content_left
    for key, label in scene._tabs:
        btn = Button(
            pygame.Rect(x, tab_y, tab_w, tab_h),
            label,
            scene.font_hint,
            on_click=scene._create_tab_click_handler(key),
        )
        scene._tab_buttons.append(btn)
        scene._tab_button_keys.append(key)
        x += tab_w + tab_gap
    scene.reset_tab_btn.rect.x = min(scene._stepper_view_rect.right - scene.reset_tab_btn.rect.w, x)


def build_language_buttons(scene) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    options = scene.get_language_options()
    scene._language_buttons = []
    scene._language_button_codes = []
    if not options:
        return

    button_w = max(s(180), min(s(280), scene._left_col_width // 3))
    button_h = s(34)
    base_x = scene._content_left + scene._left_col_width - button_w - s(32)
    shortcuts_h = len(scene._shortcut_lines) * scene._shortcut_line_gap
    base_y = scene.close_btn.rect.y - shortcuts_h - s(8) + scene._shortcut_line_gap + s(8)
    gap = s(6)

    for idx, (code, display_name) in enumerate(options):
        btn = Button(
            pygame.Rect(base_x, base_y + idx * (button_h + gap), button_w, button_h),
            display_name,
            scene.font_hint,
            on_click=scene._create_language_click_handler(code),
        )
        scene._language_buttons.append(btn)
        scene._language_button_codes.append(code)
    scene._update_language_button_states()


def update_language_button_states(scene) -> None:
    current = scene.get_game_language()
    for button, code in zip(scene._language_buttons, scene._language_button_codes):
        is_active = code == current
        if scene._is_dark_theme:
            button.bg = (40, 120, 40) if is_active else (35, 35, 35)
            button.hover_bg = (60, 160, 60) if is_active else (65, 65, 65)
            button.fg = (255, 255, 255)
        else:
            button.bg = (70, 150, 80) if is_active else (225, 225, 225)
            button.hover_bg = (95, 180, 105) if is_active else (205, 205, 205)
            button.fg = (0, 0, 0)


def update_sim_toggle_button_layout(scene) -> None:
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    sim_text = scene._sim_toggle_text()
    scene.sim_toggle.text = sim_text
    scan_btn_w = scene.scan_btn.rect.w
    max_sim_w = scene._right_col_width - scan_btn_w - s(12)
    sim_text_width = scene.font.size(sim_text)[0]
    scene.sim_toggle.rect.x = scene.scan_btn.rect.right + s(12)
    scene.sim_toggle.rect.w = max(s(160), min(max_sim_w, sim_text_width + s(40)))


def apply_advanced_toggle_button_style(scene, button, *, enabled: bool) -> None:
    if scene._is_dark_theme and enabled:
        button.bg = (35, 115, 60)
        button.hover_bg = (55, 145, 80)
        button.fg = (255, 255, 255)
    elif scene._is_dark_theme:
        button.bg = (70, 45, 45)
        button.hover_bg = (95, 65, 65)
        button.fg = (255, 255, 255)
    elif enabled:
        button.bg = (85, 160, 90)
        button.hover_bg = (110, 190, 115)
        button.fg = (0, 0, 0)
    else:
        button.bg = (230, 205, 205)
        button.hover_bg = (220, 185, 185)
        button.fg = (0, 0, 0)


def update_advanced_toggle_button(scene, button, *, label_key: str, enabled: bool) -> None:
    state_key = "settings_state_on" if enabled else "settings_state_off"
    button.text = scene._t(label_key, state=scene._t(state_key))
    apply_advanced_toggle_button_style(scene, button, enabled=enabled)
