import math
import threading
import time
from typing import Callable, List, Optional, Set

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
        game_version: str = "0.0.0",
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

        self.font_big = pygame.font.SysFont("Arial", 48)
        self.font_small = pygame.font.SysFont("Arial", 24)
        self.font_tiny = pygame.font.SysFont("Arial", 18)

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
        self.scan_btn = Button(pygame.Rect(120, 150, 180, 40), "Scan BLE", self.font, on_click=self._scan)
        # Set simulation to OFF by default
        ble.simulation = False
        self.sim_toggle = Button(pygame.Rect(120, 200, 180, 40), f"Simulation: {'ON' if ble.simulation else 'OFF'}", self.font, on_click=self._toggle_sim)

        self.devices: List[BLEDeviceInfo] = []
        self._device_buttons: List[tuple[Button, str, BLEDeviceInfo]] = []  # button, role, dev
        self._scan_status = ""  # For debugging
        self._last_scan_time = 0.0
        self._scan_thread: Optional[threading.Thread] = None  # For background scanning
        self._scan_start_time = 0.0  # When scan started (for minimum display duration)
        self._devices_ready: List[BLEDeviceInfo] = []  # Devices found by scan (waiting for min display time)

        # Steppers
        x0, y0 = 120, 260
        self.step_emg_max = NumericStepper("EMG Max Range", (x0, y0), self.font, init_values.get("emg_max_range", 5000), 500, 1000, 5000, fmt="{:.0f}", on_change=set_emg_max)
        self.step_threshold = NumericStepper("Threshold %", (x0, y0+50), self.font, init_values.get("threshold_percent", 60), 5, 5, 100, fmt="{:.0f}%", on_change=set_threshold_percent)
        self.step_countdown = NumericStepper("Countdown s", (x0, y0+100), self.font, init_values.get("countdown_seconds", 3), 1, 1, 10, fmt="{:.0f}", on_change=set_countdown_seconds)
        self.step_target_close = NumericStepper("Target Close %", (x0, y0+150), self.font, init_values.get("target_close_percent", 90), 5, 50, 100, fmt="{:.0f}%", on_change=set_target_close_percent)

        self.on_bind_left_emg = on_bind_left_emg
        self.on_bind_right_emg = on_bind_right_emg
        self.on_bind_left_exo = on_bind_left_exo
        self.on_bind_right_exo = on_bind_right_exo
        self.get_bound_left_emg = get_bound_left_emg or (lambda: None)
        self.get_bound_right_emg = get_bound_right_emg or (lambda: None)
        self.get_bound_left_exo = get_bound_left_exo or (lambda: None)
        self.get_bound_right_exo = get_bound_right_exo or (lambda: None)
        # Debug: identify this SettingsScene instance
        print(f"[SETDBG] SettingsScene created id={id(self)} ble.simulation={self.ble.simulation}")
        
        # Build device buttons for bound devices immediately so they're visible before scanning
        self._build_device_buttons_from_bound()

    def _toggle_sim(self):
        self.ble.simulation = not self.ble.simulation
        self.sim_toggle.text = f"Simulation: {'ON' if self.ble.simulation else 'OFF'}"

    def _build_device_buttons_from_bound(self):
        """Build device buttons from bound devices if no buttons exist yet."""
        if self._device_buttons:
            return  # Already have buttons, don't rebuild
        
        # Get bound devices to display
        display_devices = self._get_display_devices()
        if not display_devices:
            return  # No devices to display
        
        # Build buttons for bound devices
        self._device_buttons = []
        x, y = 120, 500
        for d in display_devices:
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
                b = Button(pygame.Rect(rx, y, 120, 36), text, self.font, on_click=self._create_bind_click_handler(d, fn, text))
                self._device_buttons.append((b, text, d))
                rx += 130
            y += 46
        
        # Update button states after building
        self._update_bind_button_states()

    def _get_display_devices(self) -> List[BLEDeviceInfo]:
        """
        Build the device list to display:
        - Start from the latest scanned devices (self.devices), filtered by allowed_mac_addresses if present
        - Ensure currently bound devices are included even if not in the latest scan
        - De-duplicate by address while preserving order (scanned first, then any missing bound)
        """
        # Start with scanned devices, optionally filtered
        if self.allowed_mac_addresses:
            scanned = [
                d for d in self.devices
                if d.address and d.address.upper() in self.allowed_mac_addresses
            ]
        else:
            scanned = list(self.devices)

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

        # Optionally filter bound devices by allowed list as well (keeps UX consistent)
        if self.allowed_mac_addresses:
            bound_list = [
                d for d in bound_list
                if d.address and d.address.upper() in self.allowed_mac_addresses
            ]

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
            if role == "label":
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
                # Debug: indicate background thread found devices and which instance
                thread_id = threading.get_ident()
                print(f"[SCANDBG] id={id(self)} thread_id={thread_id} background set _devices_ready = {len(self._devices_ready)}")
                
                # Build four bind buttons per device row
                self._device_buttons = []
                x, y = 120, 500
                
                # Build display devices, ensuring bound devices are kept visible
                display_devices = self._get_display_devices()
                # print(f"[SCANDBG] display_devices: {display_devices}")
                
                for d in display_devices:
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
                        b = Button(pygame.Rect(rx, y, 120, 36), text, self.font, on_click=self._create_bind_click_handler(d, fn, text))
                        self._device_buttons.append((b, text, d))
                        rx += 130
                    y += 46
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
        for b, _, _ in self._device_buttons:
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

        self.step_emg_max.draw(surface)
        self.step_threshold.draw(surface)
        self.step_countdown.draw(surface)
        self.step_target_close.draw(surface)

        hint = self.font.render("Scan and bind devices; adjust EMG range/threshold and countdown.", True, WHITE)
        surface.blit(hint, (120, 470))
        
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
            surface.blit(scanning_text, (120, 450))
        elif self._devices_ready and elapsed < min_display_time:
            # Scan finished but minimum display time not yet reached
            # Still show "Scanning..." to maintain visibility
            animation_frame = int((time.time() * 2) % 4)
            dots = "." * (animation_frame + 1)
            scanning_text = self.font.render(f"[SCANNING{dots}] BLE scan complete, processing...", True, YELLOW)
            surface.blit(scanning_text, (120, 450))
        elif self._devices_ready and elapsed >= min_display_time:
            # Minimum time elapsed - now show results
            # Debug: note when draw consumes the ready devices (instance id, scan_start_time, thread)
            thread_alive = bool(self._scan_thread and self._scan_thread.is_alive())
            thread_id = id(self._scan_thread) if self._scan_thread else None
            print(f"[DRAWDBG] id={id(self)} consuming _devices_ready={len(self._devices_ready)} elapsed={elapsed:.1f} start={self._scan_start_time:.3f} thread_alive={thread_alive} thread_id={thread_id}")
            self.devices = self._devices_ready
            self._devices_ready = []
            self._scan_status = ""  # Clear status after scan completes
            # Re-enable scan button when scan is complete
            self.scan_btn.disabled = False
            
            # Build buttons if not already done
            if not self._device_buttons:
                self._device_buttons = []
                x, y = 120, 500
                # Build display devices, ensuring bound devices are kept visible
                display_devices = self._get_display_devices()
                for d in display_devices:
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
                        b = Button(pygame.Rect(rx, y, 120, 36), text, self.font, on_click=self._create_bind_click_handler(d, fn, text))
                        self._device_buttons.append((b, text, d))
                        rx += 130
                    y += 46
                # Update button states after building buttons
                self._update_bind_button_states()
        elif self._scan_status and "error" in self._scan_status.lower():
            # Only show error messages
            status_text = self.font.render(self._scan_status, True, RED)
            surface.blit(status_text, (120, 450))
            # Re-enable scan button on error
            self.scan_btn.disabled = False
        
        # Draw device count info
        if len(self.devices) > 0:
            info_text = self.font.render(f"Total discovered: {len(self.devices)} | Displaying: {len(self._device_buttons) // 5 if self._device_buttons else 0}", True, WHITE)
            surface.blit(info_text, (120, 845))

        for b, _, _ in self._device_buttons:
            b.draw(surface)
