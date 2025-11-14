import math
import threading
import time
from typing import Callable, List, Optional, Set

import pygame

from src.ui.widgets import Button, Label, Panel, BarGauge, NumericStepper, CircularGauge, EMGChart
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
        game_version: str = "0.0.0",
        emg_left_raw_provider: Optional[Callable[[], list[float]]] = None,
        emg_right_raw_provider: Optional[Callable[[], list[float]]] = None,
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
        self.game_version = game_version

        self.font_big = pygame.font.SysFont("Arial", 80)
        self.font_small = pygame.font.SysFont("Arial", 40)
        self.font_tiny = pygame.font.SysFont("Arial", 24)

        # Stars configuration - calculate star vertical center first for alignment
        self.stars_collected = 0
        self.max_stars = 3
        # Calculate star vertical center for alignment with top widgets
        # Stars dimensions and positioning (matches _draw_stars)
        star_margin_top = 40
        star_r_outer = 54
        star_height = 2 * star_r_outer  # 108 pixels
        self._stars_center_y = star_margin_top + star_height // 2  # 94 pixels from top

        # Top-left controls - larger buttons to match larger fonts
        # Calculate button positions to align with stars (centered vertically)
        button_height = 60
        button_y = self._stars_center_y - button_height // 2  # Center buttons vertically with stars
        button_spacing = 10  # Spacing between buttons
        button_x = 20
        self.settings_button = Button(pygame.Rect(button_x, button_y, 200, button_height), "Settings", self.font_small, on_click=self.open_settings)
        button_x += 200 + button_spacing  # Move past Settings button
        self.reset_button = Button(pygame.Rect(button_x, button_y, 160, button_height), "Reset", self.font_small, on_click=self._reset)
        button_x += 160 + button_spacing  # Move past Reset button
        self.exit_button = Button(pygame.Rect(button_x, button_y, 140, button_height), "Exit", self.font_small, on_click=self._exit)

        # Bars - larger for better visibility
        bar_w = 80
        bar_h = int(self.screen_rect.h * 0.6)
        top = (self.screen_rect.h - bar_h) // 2
        self.left_bar = BarGauge(pygame.Rect(120, top, bar_w, bar_h), max_color=(90, 180, 255))
        self.right_bar = BarGauge(pygame.Rect(self.screen_rect.w - 120 - bar_w, top, bar_w, bar_h), max_color=(255, 140, 140))
        
        # Circular gauges for exo hand positions - placed next to top of EMG bars
        gauge_radius = 120
        gauge_y = top + 100  # Position above the bars with some spacing
        self.left_gauge = CircularGauge(
            center=(120 + bar_w // 2 + 250, gauge_y),
            radius=gauge_radius,
            value_color=(90, 180, 255),
            target_color=(250, 230, 90),
        )
        self.right_gauge = CircularGauge(
            center=(self.screen_rect.w - 120 - bar_w // 2 - 250, gauge_y),
            radius=gauge_radius,
            value_color=(255, 140, 140),
            target_color=(250, 230, 90),
        )
        
        # EMG charts - positioned near bottom of EMG bars
        chart_height = 450
        chart_width = bar_w + 500  # Slightly wider than bar
        chart_y = top + bar_h - chart_height - 10  # Just above the bottom of bars
        self.left_chart = EMGChart(
            pygame.Rect(120 + 100, chart_y + 100, chart_width, chart_height),
            max_samples=500,
            line_color=(90, 180, 255),
            reverse_direction=True,  # Mirror mode: draw from right to left
        )
        self.right_chart = EMGChart(
            pygame.Rect(self.screen_rect.w - 120 - chart_width - 100, chart_y + 100, chart_width, chart_height),
            max_samples=500,
            line_color=(255, 140, 140),
            reverse_direction=False,  # Mirror mode: draw from left to right
        )
        
        # Labels for hands - positioned under the bars, centered horizontally
        label_y = top + bar_h + 20
        # Calculate label positions (centered under each bar)
        left_label_x = 120 + bar_w // 2 - self.font_small.size("Left Hand")[0] // 2
        right_label_x = self.screen_rect.w - 120 - bar_w // 2 - self.font_small.size("Right Hand")[0] // 2
        self.left_hand_label = Label("Left Hand", (left_label_x, label_y), self.font_small, color=(255, 255, 255))
        self.right_hand_label = Label("Right Hand", (right_label_x, label_y), self.font_small, color=(255, 255, 255))
        
        # Store raw EMG providers
        self.emg_left_raw_provider = emg_left_raw_provider or (lambda: [])
        self.emg_right_raw_provider = emg_right_raw_provider or (lambda: [])

        # Countdown
        self.countdown_timer = 0.0
        # Require the player to relax (open both hands) after earning a star
        self.require_open_reset = False
        
    def reset(self):
        """
        Public reset method used by the App to reset the game state.
        This intentionally does not call the App-level callback to avoid recursion.
        """
        self.stars_collected = 0
        self.countdown_timer = 0.0
        self.require_open_reset = False

    def _reset(self):
        """
        Internal handler for the Reset button.
        Resets local game state and then notifies the App via the callback.
        """
        self.reset()
        self.reset_game_cb()
    
    def _exit(self):
        """Safely exit the program by posting a QUIT event."""
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        pygame.event.pump()

    def handle_event(self, event: pygame.event.Event):
        self.settings_button.handle_event(event)
        self.reset_button.handle_event(event)
        self.exit_button.handle_event(event)

    def update(self, dt: float):
        # Update bars
        emg_l = self.emg_left_provider()
        emg_r = self.emg_right_provider()
        thr = self.get_threshold_percent() / 100.0
        self.left_bar.set_value(emg_l)
        self.right_bar.set_value(emg_r)
        self.left_bar.set_threshold(thr)
        self.right_bar.set_threshold(thr)
        
        # Update EMG charts at 10Hz (every 100ms)
        current_time = time.time()
        if self.left_chart.should_update(current_time):
            left_raw = self.emg_left_raw_provider()
            if left_raw:
                self.left_chart.add_samples(left_raw)
        if self.right_chart.should_update(current_time):
            right_raw = self.emg_right_raw_provider()
            if right_raw:
                self.right_chart.add_samples(right_raw)

        # Control exo target based on threshold
        target_l = 1.0 if emg_l >= thr else 0.0
        target_r = 1.0 if emg_r >= thr else 0.0
        self.send_left_grip(target_l)
        self.send_right_grip(target_r)

        # Check both hands at target close
        pos_l = self.left_pos_provider()
        pos_r = self.right_pos_provider()
        target_close = self.get_target_close_percent() / 100.0
        
        # Update circular gauges with current positions and target
        self.left_gauge.set_value(pos_l)
        self.left_gauge.set_target(target_close)
        self.right_gauge.set_value(pos_r)
        self.right_gauge.set_target(target_close)
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
        """
        Draw stars in the top right corner with proper dimensions and spacing.
        Each star dimensions: width = 2 * r_outer, height = 2 * r_outer
        """
        # Star dimensions (3x original size)
        r_outer = 54
        r_inner = 24
        star_width = 2 * r_outer  # 108 pixels
        star_height = 2 * r_outer  # 108 pixels
        
        # Margins and spacing
        margin_right = 40  # Margin from right edge of screen
        margin_top = 40  # Margin from top edge of screen
        star_spacing = 20  # Spacing between stars
        
        # Calculate total width needed for all stars
        total_stars_width = self.max_stars * star_width + (self.max_stars - 1) * star_spacing
        
        # Start position from right edge (accounting for margin and total width)
        start_x = self.screen_rect.w - margin_right - total_stars_width
        # Start position from top (accounting for margin and half star height for centering)
        start_y = margin_top + star_height // 2
        
        for i in range(self.max_stars):
            color = YELLOW if i < self.stars_collected else GRAY
            points = []
            
            # Calculate center position for this star
            ox = start_x + star_width // 2 + i * (star_width + star_spacing)
            oy = start_y
            
            # Generate 5-point star shape
            for k in range(10):
                ang = math.pi/2 + k * math.pi/5
                r = r_outer if k % 2 == 0 else r_inner
                x = int(ox + r * math.cos(ang))
                y = int(oy - r * math.sin(ang))
                points.append((x, y))
            
            # Draw star
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (30, 30, 30), points, width=3)

    def draw(self, surface: pygame.Surface):
        surface.fill((10, 20, 30))
        # Title - aligned vertically with stars
        title = self.font_big.render("Dual Grip Hold", True, WHITE)
        title_y = self._stars_center_y - title.get_height() // 2  # Center title vertically with stars
        surface.blit(title, (self.screen_rect.centerx - title.get_width()//2, title_y))

        # Buttons
        self.settings_button.draw(surface)
        self.reset_button.draw(surface)
        self.exit_button.draw(surface)

        # Stars
        self._draw_stars(surface)

        # Circular gauges (drawn before bars so they appear on top)
        self.left_gauge.draw(surface, self.font_small)
        self.right_gauge.draw(surface, self.font_small)
        
        # Bars
        self.left_bar.draw(surface)
        self.right_bar.draw(surface)
        
        # EMG charts (drawn on top of bars, near bottom)
        self.left_chart.draw(surface)
        self.right_chart.draw(surface)
        
        # Hand labels (under the bars)
        self.left_hand_label.draw(surface)
        self.right_hand_label.draw(surface)

        # Center instructions and countdown
        msg = "Hold BOTH hands closed!"
        msg_img = self.font_small.render(msg, True, WHITE)
        surface.blit(msg_img, (self.screen_rect.centerx - msg_img.get_width()//2, self.screen_rect.centery - 80))

        if self.countdown_timer > 0.0:
            cd = int(self.countdown_timer) + (1 if self.countdown_timer - int(self.countdown_timer) > 0 else 0)
            # Make countdown 1.5x larger and move it down to avoid overlap with instruction text
            countdown_font = pygame.font.SysFont("Arial", int(self.font_big.get_height() * 1.5))
            cd_img = countdown_font.render(str(cd), True, YELLOW)
            # Move down by adding offset to avoid overlap with instruction text
            countdown_y = self.screen_rect.centery - cd_img.get_height()//2 + 60  # Move down 60px
            surface.blit(cd_img, (self.screen_rect.centerx - cd_img.get_width()//2, countdown_y))

        if self.stars_collected >= self.max_stars:
            win = self.font_big.render("You Win!", True, GREEN)
            surface.blit(win, (self.screen_rect.centerx - win.get_width()//2, self.screen_rect.centery + 60))
        elif self.require_open_reset:
            hint = self.font_small.render("Relax and open both hands to start next star", True, WHITE)
            surface.blit(hint, (self.screen_rect.centerx - hint.get_width()//2, self.screen_rect.centery + 20))
        
        # Display game version in bottom right corner
        version_text = f"v{self.game_version}"
        version_img = self.font_tiny.render(version_text, True, GRAY)
        version_x = self.screen_rect.w - version_img.get_width() - 20
        version_y = self.screen_rect.h - version_img.get_height() - 20
        surface.blit(version_img, (version_x, version_y))


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
        allowed_mac_addresses: Optional[Set[str]] = None,
        get_bound_left_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_right_emg: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_left_exo: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
        get_bound_right_exo: Optional[Callable[[], Optional[BLEDeviceInfo]]] = None,
    ):
        self.screen_rect = screen_rect
        self.ble = ble
        self.on_close = on_close
        self.font_title = pygame.font.SysFont("Arial", 36)
        self.font = pygame.font.SysFont("Arial", 24)
        self.allowed_mac_addresses = allowed_mac_addresses or set()

        self.panel = Panel(pygame.Rect(80, 80, screen_rect.w - 160, screen_rect.h - 160), bg=(0, 0, 0), alpha=210)
        self.close_btn = Button(pygame.Rect(screen_rect.w - 80 - 140, 100, 120, 40), "Close", self.font, on_click=on_close)
        # Use more screen space - move buttons and settings more to the right
        button_x = 200  # Start further right
        self.scan_btn = Button(pygame.Rect(button_x, 150, 180, 40), "Scan BLE", self.font, on_click=self._scan)
        # Simulation button reflects current BLE manager simulation state
        # (do not override ble.simulation here; it is controlled by config and the toggle)
        sim_text = f"Simulation: {'ON' if ble.simulation else 'OFF'}"
        sim_text_width = self.font.size(sim_text)[0]
        sim_btn_width = max(220, sim_text_width + 40)  # At least 220px, or text width + padding
        self.sim_toggle = Button(pygame.Rect(button_x, 200, sim_btn_width, 40), sim_text, self.font, on_click=self._toggle_sim)

        self.devices: List[BLEDeviceInfo] = []
        self._device_buttons: List[tuple[Button, str, BLEDeviceInfo]] = []  # button, role, dev
        self._scan_status = ""  # For debugging
        self._last_scan_time = 0.0
        self._scan_thread: Optional[threading.Thread] = None  # For background scanning
        self._scan_start_time = 0.0  # When scan started (for minimum display duration)
        self._devices_ready: List[BLEDeviceInfo] = []  # Devices found by scan (waiting for min display time)
        # Scrolling support for device list
        self._device_scroll_offset = 0
        self._device_list_start_y = 560  # Moved down to accommodate instruction label
        self._device_list_max_visible = 10  # Maximum number of devices visible at once
        # Touch scrolling support
        self._scrollbar_dragging = False
        self._last_scroll_y = 0

        # Steppers - use more screen space (move right)
        # Calculate max label width to align all +/- buttons
        # Moved down to avoid overlap with instruction label (which is at y=250)
        x0, y0 = 200, 300
        stepper_labels = [
            ("EMG Max Range", "{:.0f}", init_values.get("emg_max_range", 5000)),
            ("Threshold %", "{:.0f}%", init_values.get("threshold_percent", 60)),
            ("Countdown s", "{:.0f}", init_values.get("countdown_seconds", 3)),
            ("Target Close %", "{:.0f}%", init_values.get("target_close_percent", 90)),
        ]
        max_label_width = 0
        for label, fmt, val in stepper_labels:
            label_text = f"{label}: {fmt.format(val)}"
            text_width = self.font.size(label_text)[0]
            max_label_width = max(max_label_width, text_width)
        # Fixed button x position - all buttons align to this position
        button_x = x0 + max_label_width + 20
        
        self.step_emg_max = NumericStepper("EMG Max Range", (x0, y0), self.font, init_values.get("emg_max_range", 5000), 500, 1000, 5000, fmt="{:.0f}", on_change=set_emg_max, button_x=button_x)
        self.step_threshold = NumericStepper("Threshold %", (x0, y0+50), self.font, init_values.get("threshold_percent", 60), 5, 5, 100, fmt="{:.0f}%", on_change=set_threshold_percent, button_x=button_x)
        self.step_countdown = NumericStepper("Countdown s", (x0, y0+100), self.font, init_values.get("countdown_seconds", 3), 1, 1, 10, fmt="{:.0f}", on_change=set_countdown_seconds, button_x=button_x)
        self.step_target_close = NumericStepper("Target Close %", (x0, y0+150), self.font, init_values.get("target_close_percent", 90), 5, 50, 100, fmt="{:.0f}%", on_change=set_target_close_percent, button_x=button_x)

        self.on_bind_left_emg = on_bind_left_emg
        self.on_bind_right_emg = on_bind_right_emg
        self.on_bind_left_exo = on_bind_left_exo
        self.on_bind_right_exo = on_bind_right_exo
        self.get_bound_left_emg = get_bound_left_emg or (lambda: None)
        self.get_bound_right_emg = get_bound_right_emg or (lambda: None)
        self.get_bound_left_exo = get_bound_left_exo or (lambda: None)
        self.get_bound_right_exo = get_bound_right_exo or (lambda: None)
        
        # Build device buttons for bound devices immediately so they're visible before scanning
        self._build_device_buttons_from_bound()

    def _toggle_sim(self):
        self.ble.simulation = not self.ble.simulation
        sim_text = f"Simulation: {'ON' if self.ble.simulation else 'OFF'}"
        self.sim_toggle.text = sim_text
        # Update button width if needed
        sim_text_width = self.font.size(sim_text)[0]
        new_width = max(220, sim_text_width + 40)
        if new_width != self.sim_toggle.rect.w:
            self.sim_toggle.rect.w = new_width

    def _build_device_buttons_from_bound(self):
        """Build device buttons from bound devices and scanned devices, respecting scroll offset."""
        # Get bound devices to display
        display_devices = self._get_display_devices()
        if not display_devices:
            self._device_buttons = []
            return  # No devices to display
        
        # Build buttons for devices
        self._device_buttons = []
        x, y = 200, self._device_list_start_y
        
        # Apply scroll offset
        display_devices_scrolled = display_devices[self._device_scroll_offset:]
        for d in display_devices_scrolled:
            # Show device name - calculate width based on text length
            device_label = d.name or "Unknown"
            device_name_width = max(300, self.font.size(device_label)[0] + 20)  # At least 300px, or text width + padding
            label_btn = Button(pygame.Rect(x, y, device_name_width, 36), device_label, self.font, on_click=lambda: None)
            self._device_buttons.append((label_btn, "label", d))
            # MAC address label (smaller, to the right of device name button)
            mac_text = f"[{d.address}]"
            mac_label = Label(mac_text, (x + device_name_width + 10, y + 6), self.font, color=(180, 180, 180))
            self._device_buttons.append((mac_label, "mac_label", d))
            # Calculate where bind buttons start (after device name + MAC address with spacing)
            mac_text_width = self.font.size(mac_text)[0]
            rx = x + device_name_width + 10 + mac_text_width + 20  # Start bind buttons after MAC address with spacing
            
            roles = [
                ("Bind EMG L", self.on_bind_left_emg),
                ("Bind EMG R", self.on_bind_right_emg),
                ("Bind Exo L", self.on_bind_left_exo),
                ("Bind Exo R", self.on_bind_right_exo),
            ]
            for text, fn in roles:
                # Calculate button width based on text
                text_width = self.font.size(text)[0]
                btn_width = max(130, text_width + 30)  # At least 130px, or text width + padding
                b = Button(pygame.Rect(rx, y, btn_width, 36), text, self.font, on_click=self._create_bind_click_handler(d, fn, text))
                self._device_buttons.append((b, text, d))
                rx += btn_width + 10  # 10px spacing between buttons
            y += 46
            # Stop if we've displayed max visible devices
            if len([b for b, role, _ in self._device_buttons if role == "label"]) >= self._device_list_max_visible:
                break
        
        # Update button states after building
        self._update_bind_button_states()

    def _get_display_devices(self) -> List[BLEDeviceInfo]:
        """
        Build the device list to display:
        - Filter to only show devices with name not None
        - Sort devices: RR_HOH and EMGS prefixes first, then others
        - Include currently bound devices even if not in scan
        - De-duplicate by address while preserving order
        """
        # Filter scanned devices to only those with names
        scanned = [d for d in self.devices if d.name is not None]

        # Collect currently bound devices
        bound_list: List[BLEDeviceInfo] = []
        for getter in (self.get_bound_left_emg, self.get_bound_right_emg, self.get_bound_left_exo, self.get_bound_right_exo):
            dev = None
            try:
                dev = getter()
            except Exception:
                dev = None
            if dev:
                bound_list.append(dev)

        # Merge: scanned first, then add any bound device not present
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

        # Sort: devices with names starting with "RR_HOH" or "EMGS" first
        def sort_key(dev: BLEDeviceInfo) -> tuple:
            name = dev.name or ""
            if name.startswith("RR_HOH"):
                return (0, name)  # First priority
            elif name.startswith("EMGS"):
                return (1, name)  # Second priority
            else:
                return (2, name)  # Others after

        merged.sort(key=sort_key)
        return merged

    def _create_bind_click_handler(self, dev: BLEDeviceInfo, f: Callable, role_text: str):
        """Create a click handler for a bind button."""
        def click_handler():
            # Check current bindings
            bound_left_emg = self.get_bound_left_emg()
            bound_right_emg = self.get_bound_right_emg()
            bound_left_exo = self.get_bound_left_exo()
            bound_right_exo = self.get_bound_right_exo()
            
            # Check if this device is already bound to this specific role (toggle unbind)
            is_already_bound_to_this_role = False
            if role_text == "Bind EMG L" and bound_left_emg and bound_left_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_text == "Bind EMG R" and bound_right_emg and bound_right_emg.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_text == "Bind Exo L" and bound_left_exo and bound_left_exo.address == dev.address:
                is_already_bound_to_this_role = True
            elif role_text == "Bind Exo R" and bound_right_exo and bound_right_exo.address == dev.address:
                is_already_bound_to_this_role = True
            
            # If already bound to this role, unbind it (toggle behavior)
            if is_already_bound_to_this_role:
                f(None)
                self._update_bind_button_states()
                return
            
            # Unbind from old role if already bound to a different role
            if bound_left_emg and bound_left_emg.address == dev.address and role_text != "Bind EMG L":
                self.on_bind_left_emg(None)
            if bound_right_emg and bound_right_emg.address == dev.address and role_text != "Bind EMG R":
                self.on_bind_right_emg(None)
            if bound_left_exo and bound_left_exo.address == dev.address and role_text != "Bind Exo L":
                self.on_bind_left_exo(None)
            if bound_right_exo and bound_right_exo.address == dev.address and role_text != "Bind Exo R":
                self.on_bind_right_exo(None)
            
            # Check if device is already connected via BLE
            is_connected = self.ble.is_connected(dev.address)
            
            # Connect if not already connected
            if not is_connected:
                if not self.ble.connect(dev.address):
                    # Connection failed, don't bind
                    return
            
            # Bind the device to the new role
            f(dev)
            # Update button states after binding
            self._update_bind_button_states()
        return click_handler

    def _update_bind_button_states(self):        
        bound_left_emg = self.get_bound_left_emg()
        bound_right_emg = self.get_bound_right_emg()
        bound_left_exo = self.get_bound_left_exo()
        bound_right_exo = self.get_bound_right_exo()
        
        for button, role, device in self._device_buttons:
            if role == "label" or role == "mac_label":
                continue
            
            # Reset button to default state (not disabled, default colors)
            button.disabled = False
            
            # Check if this device is bound to this role and set green color if so
            is_bound = False
            if role == "Bind EMG L":
                is_bound = bound_left_emg is not None and bound_left_emg.address == device.address
            elif role == "Bind EMG R":
                is_bound = bound_right_emg is not None and bound_right_emg.address == device.address
            elif role == "Bind Exo L":
                is_bound = bound_left_exo is not None and bound_left_exo.address == device.address
            elif role == "Bind Exo R":
                is_bound = bound_right_exo is not None and bound_right_exo.address == device.address
            
            # Set button colors: green if bound, default otherwise
            if is_bound:
                # Green color for bound devices
                button.bg = (40, 120, 40)  # Dark green background
                button.hover_bg = (60, 160, 60)  # Lighter green on hover
                button.fg = (255, 255, 255)  # White text
            else:
                # Default colors
                button.bg = (30, 30, 30)  # Dark gray background
                button.hover_bg = (60, 60, 60)  # Lighter gray on hover
                button.fg = (255, 255, 255)  # White text

    def _scan(self):
        """Scan for BLE devices in a background thread so UI doesn't freeze."""
        # Don't start a new scan if one is already running
        if self._scan_thread and self._scan_thread.is_alive():
            return
        
        # Disable scan button while scanning
        self.scan_btn.disabled = True
        
        # Reset device list and buttons when starting a new scan
        self.devices = []
        self._device_buttons = []
        self._devices_ready = []
        
        self._scan_status = "Scanning..."
        self._scan_start_time = time.time()  # Track when scan started for minimum display time
        
        def do_scan():
            """Background thread function to perform the scan."""
            try:
                self.devices = self.ble.scan(timeout=10.0)
                # Store results but don't update status yet - draw() will enforce minimum display time
                self._devices_ready = self.devices
                
                # Build four bind buttons per device row
                self._device_buttons = []
                x, y = 200, self._device_list_start_y
                
                # Build display devices, ensuring bound devices are kept visible
                display_devices = self._get_display_devices()
                
                # Reset scroll offset when new scan completes
                self._device_scroll_offset = 0
                
                # Apply scroll offset
                display_devices_scrolled = display_devices[self._device_scroll_offset:]
                for d in display_devices_scrolled:
                    # Show device name - calculate width based on text length
                    device_label = d.name or "Unknown"
                    device_name_width = max(300, self.font.size(device_label)[0] + 20)  # At least 300px, or text width + padding
                    label_btn = Button(pygame.Rect(x, y, device_name_width, 36), device_label, self.font, on_click=lambda: None)
                    self._device_buttons.append((label_btn, "label", d))
                    # MAC address label (smaller, to the right of device name button)
                    mac_text = f"[{d.address}]"
                    mac_label = Label(mac_text, (x + device_name_width + 10, y + 6), self.font, color=(180, 180, 180))
                    self._device_buttons.append((mac_label, "mac_label", d))
                    # Calculate where bind buttons start (after device name + MAC address with spacing)
                    mac_text_width = self.font.size(mac_text)[0]
                    rx = x + device_name_width + 10 + mac_text_width + 20  # Start bind buttons after MAC address with spacing
                    
                    roles = [
                        ("Bind EMG L", self.on_bind_left_emg),
                        ("Bind EMG R", self.on_bind_right_emg),
                        ("Bind Exo L", self.on_bind_left_exo),
                        ("Bind Exo R", self.on_bind_right_exo),
                    ]
                    for text, fn in roles:
                        # Calculate button width based on text
                        text_width = self.font.size(text)[0]
                        btn_width = max(130, text_width + 30)  # At least 130px, or text width + padding
                        b = Button(pygame.Rect(rx, y, btn_width, 36), text, self.font, on_click=self._create_bind_click_handler(d, fn, text))
                        self._device_buttons.append((b, text, d))
                        rx += btn_width + 10  # 10px spacing between buttons
                    y += 46
                    # Stop if we've displayed max visible devices
                    if len([b for b, role, _ in self._device_buttons if role == "label"]) >= self._device_list_max_visible:
                        break
            except Exception as e:
                self._scan_status = f"Scan error: {e}"
        
        # Start scan in background thread
        self._scan_thread = threading.Thread(target=do_scan, daemon=True)
        self._scan_thread.start()

    def handle_event(self, event: pygame.event.Event):
        self.close_btn.handle_event(event)
        self.scan_btn.handle_event(event)
        self.sim_toggle.handle_event(event)
        self.step_emg_max.handle_event(event)
        self.step_threshold.handle_event(event)
        self.step_countdown.handle_event(event)
        self.step_target_close.handle_event(event)
        
        # Handle scrolling for device list
        display_devices = self._get_display_devices()
        total_devices = len(display_devices)
        
        # Check if scrollbar area exists
        scrollbar_x = self.screen_rect.w - 100
        scrollbar_y = self._device_list_start_y
        scrollbar_height = self._device_list_max_visible * 46
        scrollbar_width = 20
        scrollbar_rect = pygame.Rect(scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height)
        
        # Handle mouse wheel scrolling
        if event.type == pygame.MOUSEWHEEL:
            if total_devices > self._device_list_max_visible:
                max_scroll = total_devices - self._device_list_max_visible
                self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset - event.y))
                # Rebuild device buttons with new scroll offset
                self._device_buttons = []
                self._build_device_buttons_from_bound()
        
        # Handle touch scrolling on scrollbar (for touch screens)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if total_devices > self._device_list_max_visible and scrollbar_rect.collidepoint(event.pos):
                self._scrollbar_dragging = True
                self._last_scroll_y = event.pos[1]
                # Calculate initial scroll offset based on touch position
                rel_y = event.pos[1] - scrollbar_y
                scroll_ratio = rel_y / scrollbar_height
                max_scroll = total_devices - self._device_list_max_visible
                self._device_scroll_offset = int(scroll_ratio * max_scroll)
                self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset))
                self._device_buttons = []
                self._build_device_buttons_from_bound()
        
        elif event.type == pygame.MOUSEMOTION:
            if self._scrollbar_dragging and total_devices > self._device_list_max_visible:
                # Calculate scroll based on drag distance
                dy = event.pos[1] - self._last_scroll_y
                # Convert pixel movement to scroll units (roughly 1 device per 46 pixels)
                scroll_delta = int(dy / 46)
                if scroll_delta != 0:
                    max_scroll = total_devices - self._device_list_max_visible
                    self._device_scroll_offset = max(0, min(max_scroll, self._device_scroll_offset + scroll_delta))
                    self._last_scroll_y = event.pos[1]
                    # Rebuild device buttons with new scroll offset
                    self._device_buttons = []
                    self._build_device_buttons_from_bound()
        
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._scrollbar_dragging = False
        
        # Handle device button events (only buttons, not labels)
        for b, role, _ in self._device_buttons:
            if role != "label" and role != "mac_label":
                b.handle_event(event)

    def update(self, dt: float):
        # Build device buttons from bound devices if needed (e.g., when scene is first shown)
        if not self._device_buttons:
            self._build_device_buttons_from_bound()
        # Update button states based on current bindings
        self._update_bind_button_states()

    def draw(self, surface: pygame.Surface):
        self.panel.draw(surface)
        title = self.font_title.render("Settings", True, WHITE)
        surface.blit(title, (100, 100))
        self.close_btn.draw(surface)
        self.scan_btn.draw(surface)
        self.sim_toggle.draw(surface)

        # Instruction label at the top (under Simulation button)
        hint = self.font.render("Scan and bind devices; adjust EMG range/threshold and countdown.", True, WHITE)
        surface.blit(hint, (200, 250))

        self.step_emg_max.draw(surface)
        self.step_threshold.draw(surface)
        self.step_countdown.draw(surface)
        self.step_target_close.draw(surface)
        
        # Draw scan status - prominently displayed
        is_scanning = self._scan_thread and self._scan_thread.is_alive()
        
        # Check if minimum display time has elapsed (3 seconds minimum for visibility)
        elapsed = time.time() - self._scan_start_time if self._scan_start_time else 0
        min_display_time = 3.0  # Minimum 3 seconds to show "Scanning..."
        
        # Re-enable button if scan thread finished but no devices were found
        if not is_scanning and self._scan_start_time > 0 and elapsed >= min_display_time and not self._devices_ready and not self._scan_status:
            self.scan_btn.disabled = False
        
        if is_scanning:
            # Scanning in progress - show animated indicator
            # Animated dots that cycle every 1 second
            animation_frame = int((time.time() * 2) % 4)  # 0,1,2,3,0,1,2,3... (every 0.5s change)
            dots = "." * (animation_frame + 1)
            scanning_text = self.font.render(f"[SCANNING{dots}] BLE scan in progress, please wait...", True, YELLOW)
            surface.blit(scanning_text, (200, 540))  # Moved down to avoid overlap with config rows
        elif self._devices_ready and elapsed < min_display_time:
            # Scan finished but minimum display time not yet reached
            # Still show "Scanning..." to maintain visibility
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self.font.render(f"[SCANNING{dots}] BLE scan complete, processing...", True, YELLOW)
            surface.blit(scanning_text, (200, 540))  # Moved down to avoid overlap with config rows
        elif self._devices_ready and elapsed >= min_display_time:
            # Minimum time elapsed - now show results
            self.devices = self._devices_ready
            self._devices_ready = []
            self._scan_status = ""  # Clear status after scan completes
            # Re-enable scan button when scan is complete
            self.scan_btn.disabled = False
            
            # Build buttons if not already done
            if not self._device_buttons:
                # Reset scroll offset when new scan completes
                self._device_scroll_offset = 0
                # Rebuild device buttons (will use current scroll offset)
                self._build_device_buttons_from_bound()
        elif self._scan_status and "error" in self._scan_status.lower():
            # Only show error messages
            status_text = self.font.render(self._scan_status, True, RED)
            surface.blit(status_text, (200, 540))  # Moved down to avoid overlap
            # Re-enable scan button on error
            self.scan_btn.disabled = False
        
        # Draw device list with scrollbar if needed
        display_devices = self._get_display_devices()
        total_devices = len(display_devices)
        visible_devices = len([b for b, role, _ in self._device_buttons if role == "label"])
        
        # Draw scrollbar if there are more devices than visible
        if total_devices > self._device_list_max_visible:
            scrollbar_x = self.screen_rect.w - 100
            scrollbar_y = self._device_list_start_y
            scrollbar_height = self._device_list_max_visible * 46
            scrollbar_width = 20
            
            # Draw scrollbar track
            pygame.draw.rect(surface, (60, 60, 60), (scrollbar_x, scrollbar_y, scrollbar_width, scrollbar_height), border_radius=4)
            
            # Calculate scrollbar thumb position and size
            thumb_height = max(20, int((self._device_list_max_visible / total_devices) * scrollbar_height))
            max_thumb_y = scrollbar_y + scrollbar_height - thumb_height
            scroll_ratio = self._device_scroll_offset / max(1, total_devices - self._device_list_max_visible)
            thumb_y = scrollbar_y + int(scroll_ratio * (max_thumb_y - scrollbar_y))
            
            # Draw scrollbar thumb
            pygame.draw.rect(surface, (150, 150, 150), (scrollbar_x, thumb_y, scrollbar_width, thumb_height), border_radius=4)
        
        # Draw device count and scroll info
        if total_devices > 0:
            scroll_info = ""
            if total_devices > self._device_list_max_visible:
                scroll_info = f" | Scroll: {self._device_scroll_offset + 1}-{min(self._device_scroll_offset + visible_devices, total_devices)}/{total_devices} (Use mouse wheel)"
            info_text = self.font.render(f"Total discovered: {total_devices} | Displaying: {visible_devices}{scroll_info}", True, WHITE)
            surface.blit(info_text, (200, self.screen_rect.h - 100))

        # Draw device buttons and labels
        for b, role, _ in self._device_buttons:
            if hasattr(b, 'draw'):
                b.draw(surface)
