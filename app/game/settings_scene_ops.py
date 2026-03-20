import threading
import time

import pygame
from ..ui.widgets import Button


def refresh_stepper_layout(scene, reset_scroll: bool = False):
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    row_gap = scene._stepper_row_gap
    content_pad = s(12)
    scene._active_stepper_base_y = {}
    scene._training_muscle_toggle_base_y = None
    scene._training_trigger_toggle_base_y = None
    scene._game_advanced_toggle_base_y = None
    scene._emg_advanced_toggle_base_y = None
    scene._exo_advanced_toggle_base_y = None
    current_y = scene._stepper_view_rect.y + content_pad
    row_count = 0

    if scene._active_tab == "game":
        scene._training_muscle_toggle_base_y = current_y
        current_y += row_gap * 3
        row_count += 3
        basic_steppers = [
            scene._stepper_by_id[k]
            for k in scene._tab_stepper_ids.get("game", [])
            if k in scene._stepper_by_id
        ]
        for stepper in basic_steppers:
            scene._active_stepper_base_y[stepper] = current_y
            stepper.set_y(current_y)
            current_y += row_gap
            row_count += 1
        scene._game_advanced_toggle_base_y = current_y
        current_y += row_gap
        row_count += 1
        if scene._show_game_advanced:
            for key in scene._game_advanced_stepper_ids:
                stepper = scene._stepper_by_id.get(key)
                if not stepper:
                    continue
                scene._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1
    elif scene._active_tab == "emg":
        scene._training_trigger_toggle_base_y = current_y
        current_y += row_gap * 3
        row_count += 3
        basic_steppers = [
            scene._stepper_by_id[k]
            for k in scene._tab_stepper_ids.get("emg", [])
            if k in scene._stepper_by_id
        ]
        for stepper in basic_steppers:
            scene._active_stepper_base_y[stepper] = current_y
            stepper.set_y(current_y)
            current_y += row_gap
            row_count += 1

        scene._emg_advanced_toggle_base_y = current_y
        current_y += row_gap
        row_count += 1

        if scene._show_emg_advanced:
            for key in scene._emg_advanced_stepper_ids:
                stepper = scene._stepper_by_id.get(key)
                if not stepper:
                    continue
                scene._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1
    elif scene._active_tab == "exo":
        basic_steppers = [
            scene._stepper_by_id[k]
            for k in scene._tab_stepper_ids.get("exo", [])
            if k in scene._stepper_by_id
        ]
        for stepper in basic_steppers:
            scene._active_stepper_base_y[stepper] = current_y
            stepper.set_y(current_y)
            current_y += row_gap
            row_count += 1

        scene._exo_advanced_toggle_base_y = current_y
        current_y += row_gap
        row_count += 1

        if scene._show_exo_advanced:
            for key in scene._exo_advanced_stepper_ids:
                stepper = scene._stepper_by_id.get(key)
                if not stepper:
                    continue
                scene._active_stepper_base_y[stepper] = current_y
                stepper.set_y(current_y)
                current_y += row_gap
                row_count += 1
    else:
        for stepper in scene._active_steppers():
            scene._active_stepper_base_y[stepper] = current_y
            stepper.set_y(current_y)
            current_y += row_gap
            row_count += 1

    if row_count > 0:
        content_height = content_pad * 2 + scene._stepper_button_h + max(0, row_count - 1) * row_gap
    else:
        content_height = s(36)
    scene._stepper_content_height = max(s(36), content_height)
    scene._stepper_max_scroll = max(0, scene._stepper_content_height - scene._stepper_view_rect.h)
    if reset_scroll:
        scene._stepper_scroll_offset = 0
    scene._apply_stepper_scroll()


def update_bind_button_states(scene):
    bound_flexor_emg = scene.get_bound_flexor_emg()
    bound_extensor_emg = scene.get_bound_extensor_emg()
    bound_exo_hand = scene.get_bound_exo_hand()

    for button, role, device in scene._device_buttons:
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

        is_connected = scene._is_device_connected(device)
        if is_bound:
            if is_connected:
                if scene._is_dark_theme:
                    button.bg = (40, 120, 40)
                    button.hover_bg = (60, 160, 60)
                    button.fg = (255, 255, 255)
                    button.border_color_override = None
                else:
                    button.bg = (145, 220, 145)
                    button.hover_bg = (168, 232, 168)
                    button.fg = (0, 0, 0)
                    button.border_color_override = (255, 255, 255)
            else:
                if scene._is_dark_theme:
                    button.bg = (150, 95, 30)
                    button.hover_bg = (180, 120, 45)
                    button.fg = (255, 255, 255)
                    button.border_color_override = None
                else:
                    button.bg = (238, 208, 145)
                    button.hover_bg = (245, 220, 168)
                    button.fg = (0, 0, 0)
                    button.border_color_override = (255, 255, 255)
        else:
            if scene._is_dark_theme:
                button.bg = (30, 30, 30)
                button.hover_bg = (60, 60, 60)
                button.fg = (255, 255, 255)
                button.border_color_override = None
            else:
                button.bg = (225, 225, 225)
                button.hover_bg = (205, 205, 205)
                button.fg = (0, 0, 0)
                button.border_color_override = (255, 255, 255)


def scan_devices(scene):
    if scene._scan_thread and scene._scan_thread.is_alive():
        return

    scene.scan_btn.disabled = True
    scene.devices = []
    scene._device_buttons = []
    scene._devices_ready = []
    scene._scan_status = scene._t("settings_scan_status_scanning")
    scene._scan_has_error = False
    scene._auto_bind_status = scene._t("settings_auto_bind_active")
    scene._scan_start_time = time.time()

    def _is_fully_connected() -> bool:
        exo = scene.get_bound_exo_hand()
        flexor = scene.get_bound_flexor_emg()
        extensor = scene.get_bound_extensor_emg()
        if not exo or not flexor or not extensor:
            return False
        return (
            scene.ble.is_connected(exo.address)
            and scene.ble.is_connected(flexor.address)
            and scene.ble.is_connected(extensor.address)
        )

    def _bind_device_to_role(dev, role: str) -> bool:
        if not scene.ble.is_connected(dev.address):
            if not scene.ble.connect(dev.address):
                return False
        if role == "exo":
            scene.on_bind_exo_hand(dev)
            scene._auto_bind_status = scene._t("settings_auto_bound_exo_hand", name=dev.name, address=dev.address)
        elif role == "extensor":
            scene.on_bind_extensor_emg(dev)
            scene._auto_bind_status = scene._t("settings_auto_bound_extensor_emg", name=dev.name, address=dev.address)
        elif role == "flexor":
            scene.on_bind_flexor_emg(dev)
            scene._auto_bind_status = scene._t("settings_auto_bound_flexor_emg", name=dev.name, address=dev.address)
        scene._update_bind_button_states()
        return True

    def _auto_bind_discovered_device(dev):
        name_upper = (dev.name or "").upper()
        if not name_upper:
            return

        if "HOH" in name_upper and "HOHA" not in name_upper:
            if scene.get_bound_exo_hand() is None:
                _bind_device_to_role(dev, "exo")
            return

        if "EMGS" in name_upper:
            bound_extensor = scene.get_bound_extensor_emg()
            bound_flexor = scene.get_bound_flexor_emg()
            if bound_extensor is None:
                _bind_device_to_role(dev, "extensor")
                return
            if bound_flexor is None and bound_extensor.address != dev.address:
                _bind_device_to_role(dev, "flexor")

    def do_scan():
        try:
            max_scan_seconds = 10.0
            pass_timeout = 1.0
            start_time = time.time()
            discovered_by_address: dict[str, object] = {}

            while time.time() - start_time < max_scan_seconds:
                if _is_fully_connected():
                    scene._auto_bind_status = scene._t("settings_auto_bind_complete")
                    break

                found = scene.ble.scan(timeout=pass_timeout)
                for dev in found:
                    addr = (dev.address or "").upper()
                    if not addr:
                        continue
                    if addr not in discovered_by_address:
                        discovered_by_address[addr] = dev
                    else:
                        prev = discovered_by_address[addr]
                        if (prev.name or "").strip().lower() in ("", "unknown") and (dev.name or "").strip():
                            discovered_by_address[addr] = dev
                    _auto_bind_discovered_device(discovered_by_address[addr])
                    if _is_fully_connected():
                        scene._auto_bind_status = scene._t("settings_auto_bind_complete")
                        break

                scene.devices = list(discovered_by_address.values())
                scene._device_scroll_offset = 0
                scene._build_device_buttons_from_bound()
                if _is_fully_connected():
                    scene._auto_bind_status = scene._t("settings_auto_bind_complete")
                    break

            scene._devices_ready = list(discovered_by_address.values())
            if not scene._auto_bind_status:
                scene._auto_bind_status = scene._t("settings_auto_bind_finished_manual_available")
            scene._device_scroll_offset = 0
            scene._build_device_buttons_from_bound()
        except Exception as e:
            scene._scan_status = scene._t("settings_scan_error", error=e)
            scene._scan_has_error = True
            scene._auto_bind_status = scene._t("settings_auto_bind_interrupted")

    scene._scan_thread = threading.Thread(target=do_scan, daemon=True)
    scene._scan_thread.start()


def apply_theme_styles(scene):
    if scene._is_dark_theme:
        scene.panel.bg = (0, 0, 0)
        scene.panel.alpha = 210
        scene._theme_text_color = (255, 255, 255)
        scene._theme_outline_color = (0, 0, 0)
        scene._stepper_view_bg = (25, 25, 25)
        scene._stepper_view_border = (70, 70, 70)
        scene._device_panel_bg = (25, 25, 25)
        scene._device_panel_border = (70, 70, 70)
        scene._device_header_bg = (40, 90, 180)
        scene._device_header_hover_bg = (55, 115, 210)
        scene._device_label_text_color = (255, 255, 255)
        for button in (scene.close_btn, scene.scan_btn, scene.sim_toggle, scene.swap_btn, scene.reset_tab_btn):
            button.bg = (30, 30, 30)
            button.hover_bg = (60, 60, 60)
            button.fg = (255, 255, 255)
            button.border_color_override = None
        scene._stepper_scroll_up_btn.bg = (35, 35, 35)
        scene._stepper_scroll_up_btn.hover_bg = (65, 65, 65)
        scene._stepper_scroll_up_btn.fg = (255, 255, 255)
        scene._stepper_scroll_up_btn.border_color_override = None
        scene._stepper_scroll_down_btn.bg = (35, 35, 35)
        scene._stepper_scroll_down_btn.hover_bg = (65, 65, 65)
        scene._stepper_scroll_down_btn.fg = (255, 255, 255)
        scene._stepper_scroll_down_btn.border_color_override = None
        for stepper in scene._steppers:
            stepper.set_style(
                text_color=(255, 255, 255),
                text_outline_color=(0, 0, 0),
                button_bg=(35, 35, 35),
                button_hover_bg=(65, 65, 65),
                button_fg=(255, 255, 255),
                button_border_color=None,
            )
    else:
        scene.panel.bg = (245, 245, 245)
        scene.panel.alpha = 228
        scene._theme_text_color = (0, 0, 0)
        scene._theme_outline_color = (255, 255, 255)
        scene._stepper_view_bg = (240, 240, 240)
        scene._stepper_view_border = (140, 140, 140)
        scene._device_panel_bg = (240, 240, 240)
        scene._device_panel_border = (140, 140, 140)
        scene._device_header_bg = (130, 180, 235)
        scene._device_header_hover_bg = (150, 195, 240)
        scene._device_label_text_color = (0, 0, 0)
        for button in (scene.close_btn, scene.scan_btn, scene.sim_toggle, scene.swap_btn, scene.reset_tab_btn):
            button.bg = (225, 225, 225)
            button.hover_bg = (205, 205, 205)
            button.fg = (0, 0, 0)
            button.border_color_override = (255, 255, 255)
        scene._stepper_scroll_up_btn.bg = (220, 220, 220)
        scene._stepper_scroll_up_btn.hover_bg = (205, 205, 205)
        scene._stepper_scroll_up_btn.fg = (0, 0, 0)
        scene._stepper_scroll_up_btn.border_color_override = (255, 255, 255)
        scene._stepper_scroll_down_btn.bg = (220, 220, 220)
        scene._stepper_scroll_down_btn.hover_bg = (205, 205, 205)
        scene._stepper_scroll_down_btn.fg = (0, 0, 0)
        scene._stepper_scroll_down_btn.border_color_override = (255, 255, 255)
        for stepper in scene._steppers:
            stepper.set_style(
                text_color=(0, 0, 0),
                text_outline_color=(255, 255, 255),
                button_bg=(220, 220, 220),
                button_hover_bg=(205, 205, 205),
                button_fg=(0, 0, 0),
                button_border_color=(255, 255, 255),
            )
    scene._update_tab_button_states()
    scene._update_training_muscle_mode_buttons()
    scene._update_training_trigger_mode_buttons()
    scene._update_game_advanced_button_label()
    scene._update_emg_advanced_button_label()
    scene._update_exo_advanced_button_label()
    scene._update_language_button_states()
    if hasattr(scene, "get_bound_flexor_emg"):
        scene._update_bind_button_states()
        if scene._device_buttons:
            scene._build_device_buttons_from_bound()


def refresh_theme(scene):
    latest_theme = bool(scene.get_is_dark_theme())
    if latest_theme == scene._is_dark_theme:
        return
    scene._is_dark_theme = latest_theme
    scene._apply_theme_styles()


def apply_translations(scene):
    scene._current_language = scene.get_game_language()
    scene.close_btn.text = scene._t("settings_btn_apply")
    scene._resize_close_button()
    scene.scan_btn.text = scene._t("settings_btn_scan_ble")
    scene._update_sim_toggle_button_layout()
    scene.swap_btn.text = scene._t("settings_btn_swap_flexor_extensor")
    scene._shortcut_lines = scene._build_shortcut_lines()
    scene._language_title = scene._t("settings_language_title")
    scene.step_emg_max_flexor.label = scene._t("settings_stepper_emg_max_flexor")
    scene.step_emg_max_extensor.label = scene._t("settings_stepper_emg_max_extensor")
    scene.step_hand_start.label = scene._t("settings_stepper_hand_start_percent")
    scene.step_threshold.label = scene._t("settings_stepper_threshold_percent")
    scene.step_trigger_threshold.label = scene._t("settings_stepper_trigger_threshold_percent")
    scene.step_trigger_wait_seconds.label = scene._t("settings_stepper_trigger_wait_seconds")
    scene.step_relax_flexion.label = scene._t("settings_stepper_relax_flexion_percent")
    scene.step_relax_extension.label = scene._t("settings_stepper_relax_extension_percent")
    scene.step_countdown.label = scene._t("settings_stepper_countdown_seconds")
    scene.step_stars_to_collect.label = scene._t("settings_stepper_stars_to_collect")
    scene.step_training_duration_minutes.label = scene._t("settings_stepper_training_duration_minutes")
    scene.step_target_flexion.label = scene._t("settings_stepper_target_flexion_percent")
    scene.step_target_extension.label = scene._t("settings_stepper_target_extension_percent")
    scene.step_grip_step.label = scene._t("settings_stepper_grip_step_percent")
    scene.step_command_rate.label = scene._t("settings_stepper_command_rate_hz")
    scene.step_activation_hysteresis.label = scene._t("settings_stepper_activate_hysteresis_percent")
    scene.step_deactivation_hysteresis.label = scene._t("settings_stepper_release_hysteresis_percent")
    scene.step_forward_deadband.label = scene._t("settings_stepper_forward_deadband_percent")
    scene.step_reversal_deadband.label = scene._t("settings_stepper_reverse_deadband_percent")
    scene.step_background_blur.label = scene._t("settings_stepper_background_blur_percent")
    scene.step_sound_enabled.label = scene._t("settings_option_sound_enabled")
    scene.step_sound_effect_volume.label = scene._t("settings_stepper_sound_effect_volume_percent")
    scene.step_music_enabled.label = scene._t("settings_option_music_enabled")
    scene.step_music_volume.label = scene._t("settings_stepper_music_volume_percent")
    scene.step_theme_mode.label = scene._t("settings_theme_mode_label")
    scene._audio_enabled_options = [("on", scene._t("settings_state_on")), ("off", scene._t("settings_state_off"))]
    scene.step_sound_enabled.set_options(scene._audio_enabled_options)
    scene.step_sound_enabled.set_value(scene._sound_enabled, notify=False)
    scene.step_music_enabled.set_options(scene._audio_enabled_options)
    scene.step_music_enabled.set_value(scene._music_enabled, notify=False)
    scene.step_theme_mode.set_options(scene._theme_mode_options())
    scene.step_theme_mode.set_value(scene._theme_mode, notify=False)
    scene.step_dynamic_mvc_alpha_up.label = scene._t("settings_stepper_mvc_alpha_up")
    scene.step_dynamic_mvc_alpha_down.label = scene._t("settings_stepper_mvc_alpha_down")
    scene.step_dynamic_mvc_up_margin.label = scene._t("settings_stepper_mvc_up_margin")
    scene.step_dynamic_mvc_hold_activity.label = scene._t("settings_stepper_mvc_hold_ratio")
    scene.step_dynamic_mvc_decay_trigger.label = scene._t("settings_stepper_mvc_decay_trigger")
    scene.step_dynamic_mvc_decay_grace.label = scene._t("settings_stepper_mvc_decay_grace_seconds")
    scene._tabs = [
        ("welcome", scene._t("settings_tab_welcome")),
        ("game", scene._t("settings_tab_game")),
        ("emg", scene._t("settings_tab_emg_control")),
        ("exo", scene._t("settings_tab_exo_output")),
    ]
    scene._build_tab_buttons()
    scene._update_tab_button_states()
    scene._apply_theme_styles()
    scene._update_training_muscle_mode_buttons()
    scene._update_training_trigger_mode_buttons()
    scene._update_game_advanced_button_label()
    scene._update_emg_advanced_button_label()
    scene._update_exo_advanced_button_label()
    for stepper in scene._steppers:
        stepper._update_button_positions()
    scene._refresh_stepper_layout(reset_scroll=False)
    scene._build_device_buttons_from_bound()


def apply_stepper_scroll(scene):
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    scene._stepper_scroll_offset = max(0, min(scene._stepper_max_scroll, scene._stepper_scroll_offset))
    visible = scene._active_steppers()
    for stepper in visible:
        base_y = scene._active_stepper_base_y.get(stepper, stepper.y)
        stepper.set_y(base_y - scene._stepper_scroll_offset)
    if scene._active_tab == "emg" and scene._emg_advanced_toggle_base_y is not None:
        scene.emg_advanced_toggle_btn.rect.y = scene._emg_advanced_toggle_base_y - scene._stepper_scroll_offset
        scene.emg_advanced_toggle_btn.rect.x = scene._stepper_view_rect.x + s(10)
        scene.emg_advanced_toggle_btn.rect.w = max(s(120), scene._stepper_view_rect.w - s(28))
        scene.emg_advanced_toggle_btn.rect.h = max(s(32), scene._stepper_button_h)
    if scene._active_tab == "emg" and scene._training_trigger_toggle_base_y is not None:
        section_y = scene._training_trigger_toggle_base_y - scene._stepper_scroll_offset
        section_x = scene._stepper_view_rect.x + s(10)
        section_w = max(s(120), scene._stepper_view_rect.w - s(28))
        button_h = max(s(32), scene._stepper_button_h)
        button_gap = s(8)
        col_gap = s(10)
        col_w = max(s(100), (section_w - col_gap) // 2)
        for idx, button in enumerate(scene._training_trigger_mode_buttons):
            row = idx // 2
            col = idx % 2
            button.rect.x = section_x + col * (col_w + col_gap)
            button.rect.y = section_y + s(24) + row * (button_h + button_gap)
            button.rect.w = col_w
            button.rect.h = button_h
    if scene._active_tab == "game" and scene._training_muscle_toggle_base_y is not None:
        section_y = scene._training_muscle_toggle_base_y - scene._stepper_scroll_offset
        section_x = scene._stepper_view_rect.x + s(10)
        section_w = max(s(120), scene._stepper_view_rect.w - s(28))
        button_h = max(s(32), scene._stepper_button_h)
        button_gap = s(8)
        col_gap = s(10)
        col_w = max(s(100), (section_w - col_gap) // 2)
        for idx, button in enumerate(scene._training_muscle_mode_buttons):
            row = idx // 2
            col = idx % 2
            button.rect.x = section_x + col * (col_w + col_gap)
            button.rect.y = section_y + s(24) + row * (button_h + button_gap)
            button.rect.w = col_w
            button.rect.h = button_h
    if scene._active_tab == "game" and scene._game_advanced_toggle_base_y is not None:
        scene.game_advanced_toggle_btn.rect.y = scene._game_advanced_toggle_base_y - scene._stepper_scroll_offset
        scene.game_advanced_toggle_btn.rect.x = scene._stepper_view_rect.x + s(10)
        scene.game_advanced_toggle_btn.rect.w = max(s(120), scene._stepper_view_rect.w - s(28))
        scene.game_advanced_toggle_btn.rect.h = max(s(32), scene._stepper_button_h)
    if scene._active_tab == "exo" and scene._exo_advanced_toggle_base_y is not None:
        scene.exo_advanced_toggle_btn.rect.y = scene._exo_advanced_toggle_base_y - scene._stepper_scroll_offset
        scene.exo_advanced_toggle_btn.rect.x = scene._stepper_view_rect.x + s(10)
        scene.exo_advanced_toggle_btn.rect.w = max(s(120), scene._stepper_view_rect.w - s(28))
        scene.exo_advanced_toggle_btn.rect.h = max(s(32), scene._stepper_button_h)
    can_scroll = scene._stepper_max_scroll > 0
    scene._stepper_scroll_up_btn.disabled = (not can_scroll) or scene._stepper_scroll_offset <= 0
    scene._stepper_scroll_down_btn.disabled = (not can_scroll) or scene._stepper_scroll_offset >= scene._stepper_max_scroll


def get_display_devices(scene):
    def has_valid_name(dev) -> bool:
        name = (dev.name or "").strip()
        return bool(name) and name.lower() != "unknown"

    scanned = [d for d in scene.devices if has_valid_name(d)]
    bound_list = []
    for getter in (scene.get_bound_flexor_emg, scene.get_bound_extensor_emg, scene.get_bound_exo_hand):
        try:
            dev = getter()
        except Exception:
            dev = None
        if dev and has_valid_name(dev):
            bound_list.append(dev)

    seen = set()
    merged = []
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

    def sort_key(dev) -> tuple:
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


def build_device_buttons_from_bound(scene):
    s = lambda v: max(1, int(round(v * scene.ui_scale)))
    display_devices = scene._get_display_devices()
    if not display_devices:
        scene._device_buttons = []
        return

    scene._device_buttons = []
    x, y = scene._device_view_rect.x, scene._device_view_rect.y
    display_devices_scrolled = display_devices[scene._device_scroll_offset :]
    row_h = scene._device_row_height
    line_h = s(36)
    button_gap = s(8)
    label_w = max(s(220), scene._device_view_rect.w)
    role_btn_w = max(s(88), (label_w - 2 * button_gap) // 3)
    for d in display_devices_scrolled:
        device_label = d.name or "Unknown"
        max_heading_width = label_w - s(16)
        heading_tail = ""
        mac_suffix = scene._format_device_mac_suffix(d.address)
        heading_text = f"{device_label}{heading_tail}"
        if mac_suffix:
            heading_with_mac = f"{device_label}{heading_tail}{mac_suffix}"
            if scene.font.size(heading_with_mac)[0] <= max_heading_width:
                heading_text = heading_with_mac
            else:
                trimmed_name = device_label
                compact_with_mac = f"{trimmed_name}...{heading_tail}{mac_suffix}"
                while trimmed_name and scene.font.size(compact_with_mac)[0] > max_heading_width:
                    trimmed_name = trimmed_name[:-1]
                    compact_with_mac = f"{trimmed_name}...{heading_tail}{mac_suffix}"
                if trimmed_name:
                    heading_text = compact_with_mac

        if scene.font.size(heading_text)[0] > max_heading_width:
            trimmed_name = device_label
            compact_text = f"{trimmed_name}...{heading_tail}"
            while trimmed_name and scene.font.size(compact_text)[0] > max_heading_width:
                trimmed_name = trimmed_name[:-1]
                compact_text = f"{trimmed_name}...{heading_tail}"
            if trimmed_name:
                heading_text = compact_text
        label_btn = Button(pygame.Rect(x, y, label_w, line_h), heading_text, scene.font, on_click=lambda: None)
        label_btn.bg = scene._device_header_bg
        label_btn.hover_bg = scene._device_header_hover_bg
        label_btn.fg = scene._device_label_text_color
        label_btn.border_color_override = None if scene._is_dark_theme else (255, 255, 255)
        scene._device_buttons.append((label_btn, "label", d))

        rx = x
        bind_y = y + line_h + s(2)
        roles = [
            (scene._t("settings_role_flexor"), "bind_flexor", scene.on_bind_flexor_emg),
            (scene._t("settings_role_extensor"), "bind_extensor", scene.on_bind_extensor_emg),
            (scene._t("settings_role_exo_hand"), "bind_exo", scene.on_bind_exo_hand),
        ]
        for label_text, role_key, fn in roles:
            b = Button(
                pygame.Rect(rx, bind_y, role_btn_w, line_h),
                label_text,
                scene.font,
                on_click=scene._create_bind_click_handler(d, fn, role_key),
            )
            scene._device_buttons.append((b, role_key, d))
            rx += role_btn_w + button_gap
        y += row_h
        if len([b for b, role, _ in scene._device_buttons if role == "label"]) >= scene._device_list_max_visible:
            break

    scene._update_bind_button_states()
    scene._last_device_list_signature = scene._compute_device_list_signature()


def compute_device_list_signature(scene) -> tuple:
    display_devices = scene._get_display_devices()
    items = []
    for dev in display_devices:
        addr = (dev.address or "").upper()
        roles = tuple(scene._bound_roles_for_device(dev))
        connected = scene._is_device_connected(dev)
        items.append((addr, roles, connected))
    return tuple(items)
