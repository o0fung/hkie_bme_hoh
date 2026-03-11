import math
import pygame
from typing import Callable, Optional, Tuple

Color = Tuple[int, int, int]


class Label:
    def __init__(self, text: str, pos: Tuple[int, int], font: pygame.font.Font, color: Color = (255, 255, 255)):
        self.text = text
        self.pos = pos
        self.font = font
        self.color = color

    def draw(self, surface: pygame.Surface):
        img = self.font.render(self.text, True, self.color)
        surface.blit(img, self.pos)


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        font: pygame.font.Font,
        on_click: Callable[[], None],
        bg: Color = (30, 30, 30),
        fg: Color = (255, 255, 255),
        hover_bg: Color = (60, 60, 60),
    ):
        self.rect = rect
        self.text = text
        self.font = font
        self.on_click = on_click
        self.bg = bg
        self.fg = fg
        self.hover_bg = hover_bg
        self._pressed = False
        self.disabled = False

    def handle_event(self, event: pygame.event.Event):
        if self.disabled:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1,):
            if self.rect.collidepoint(event.pos):
                self._pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (1,):
            if self._pressed and self.rect.collidepoint(event.pos):
                self.on_click()
            self._pressed = False

    def draw(self, surface: pygame.Surface):
        if self.disabled:
            # Disabled appearance: darker background, grayed out text
            bg = (15, 15, 15)
            fg = (100, 100, 100)
            border_color = (80, 80, 80)
        else:
            mouse_pos = pygame.mouse.get_pos()
            bg = self.hover_bg if self.rect.collidepoint(mouse_pos) else self.bg
            fg = self.fg
            # Use green border for green buttons, white border for others
            if self.bg[1] > 100:  # Green button (green channel is high)
                border_color = (100, 200, 100)  # Green border
            else:
                border_color = (200, 200, 200)  # White border
        
        border_radius = max(6, min(18, int(min(self.rect.w, self.rect.h) * 0.15)))
        border_width = max(2, min(4, int(min(self.rect.w, self.rect.h) * 0.04)))
        pygame.draw.rect(surface, bg, self.rect, border_radius=border_radius)
        pygame.draw.rect(surface, border_color, self.rect, width=border_width, border_radius=border_radius)
        label_img = self.font.render(self.text, True, fg)
        lx = self.rect.x + (self.rect.w - label_img.get_width()) // 2
        ly = self.rect.y + (self.rect.h - label_img.get_height()) // 2
        surface.blit(label_img, (lx, ly))


class Panel:
    def __init__(self, rect: pygame.Rect, bg: Color = (0, 0, 0), alpha: int = 180):
        self.rect = rect
        self.bg = bg
        self.alpha = alpha

    def draw(self, surface: pygame.Surface):
        panel = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        panel.fill((*self.bg, self.alpha))
        surface.blit(panel, (self.rect.x, self.rect.y))


class BarGauge:
    def __init__(self, rect: pygame.Rect, max_color: Color = (80, 200, 120), bg: Color = (40, 40, 40)):
        self.rect = rect
        self.max_color = max_color
        self.bg = bg
        self.value = 0.0
        self.threshold = 0.6

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))

    def set_threshold(self, t: float):
        self.threshold = max(0.0, min(1.0, t))

    def draw(self, surface: pygame.Surface):
        border_radius = max(6, min(18, int(min(self.rect.w, self.rect.h) * 0.15)))
        # background
        pygame.draw.rect(surface, self.bg, self.rect, border_radius=border_radius)
        # fill based on value (vertical bar)
        h = int(self.rect.h * self.value)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.h - h, self.rect.w, h)
        pygame.draw.rect(surface, self.max_color, fill_rect, border_radius=border_radius)
        # threshold marker
        th = int(self.rect.h * (1.0 - self.threshold))
        y = self.rect.y + th
        marker_width = max(2, min(6, int(self.rect.w * 0.05)))
        pygame.draw.line(surface, (250, 230, 90), (self.rect.x, y), (self.rect.right, y), width=marker_width)


class CircularGauge:
    def __init__(
        self,
        center: Tuple[int, int],
        radius: int,
        value: float = 0.0,
        target: float = 0.9,
        value_color: Color = (80, 200, 120),
        bg_color: Color = (40, 40, 40),
        target_color: Color = (250, 230, 90),
        line_width: int = 8,
    ):
        self.center = center
        self.radius = radius
        self.value = max(0.0, min(1.0, value))
        self.target = max(0.0, min(1.0, target))
        self.value_color = value_color
        self.bg_color = bg_color
        self.target_color = target_color
        self.line_width = line_width

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))

    def set_target(self, t: float):
        self.target = max(0.0, min(1.0, t))

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        cx, cy = self.center
        
        # Simple circular gauge: 0% at top, fills clockwise as percentage increases
        # Top is at -90 degrees (or 270° when normalized)
        start_angle = -math.pi / 2  # Top: -90° = 3π/2 (270°)
        
        # Draw background circle outline (full 360 degrees)
        # Use multiple arcs to create thick line effect
        for i in range(self.line_width):
            r_offset = i - self.line_width // 2
            r = self.radius + r_offset
            arc_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            pygame.draw.arc(surface, self.bg_color, arc_rect, 0, math.pi * 2)
        
        # Draw value arc (progress from 0% to current value)
        # At 0%: no arc (start == end)
        # At 50%: half circle
        # At 100%: full circle
        if self.value > 0.0:
            # Calculate how much to sweep (0 to 2π radians)
            sweep_angle = self.value * (math.pi * 2)
            end_angle = start_angle + sweep_angle
            
            # Draw arc with thick line
            for i in range(self.line_width):
                r_offset = i - self.line_width // 2
                r = self.radius + r_offset
                arc_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
                pygame.draw.arc(surface, self.value_color, arc_rect, start_angle, end_angle)
        
        # Draw target marker (shows threshold, e.g. 90%)
        # Position target marker at the threshold percentage around the circle
        target_angle = start_angle + (1 - self.target) * (math.pi * 2) + math.pi 
        target_x = cx + (self.radius + 8) * math.cos(target_angle)
        target_y = cy + (self.radius + 8) * math.sin(target_angle)
        pygame.draw.circle(surface, self.target_color, (int(target_x), int(target_y)), 8)
        
        # Draw percentage text in center
        percent_text = f"{int(self.value * 100)}%"
        text_img = font.render(percent_text, True, (255, 255, 255))
        text_x = cx - text_img.get_width() // 2
        text_y = cy - text_img.get_height() // 2
        surface.blit(text_img, (text_x, text_y))


class EMGChart:
    def __init__(
        self,
        rect: pygame.Rect,
        max_samples: int = 500,  # Number of samples to display (for 10Hz refresh, 500 = 50 seconds of data at 1kHz)
        line_color: Color = (80, 200, 120),
        bg_color: Color = (20, 20, 20),
        reverse_direction: bool = False,  # If True, draw from right to left (mirror mode)
    ):
        self.rect = rect
        self.max_samples = max_samples
        self.line_color = line_color
        self.bg_color = bg_color
        self.reverse_direction = reverse_direction
        self.samples: list[float] = []  # Buffer of raw EMG samples
        self.last_update_time = 0.0
        self.update_interval = 0.1  # Update at 10Hz (100ms)
        self.min_value = 0.0
        self.max_value = 65535.0  # Default max for raw EMG codes (u16)

    def add_samples(self, new_samples: list[float]):
        """Add new raw EMG samples to the buffer."""
        self.samples.extend(new_samples)
        # Keep only the most recent samples
        if len(self.samples) > self.max_samples:
            self.samples = self.samples[-self.max_samples:]
        # Update min/max for scaling
        if self.samples:
            # self.min_value = min(self.samples)
            # self.max_value = max(self.samples)
            self.min_value = 0.0
            self.max_value = 65535.0
            # Add some padding
            value_range = self.max_value - self.min_value
            if value_range > 0:
                padding = value_range * 0.1
                self.min_value -= padding
                self.max_value += padding
            else:
                # If all values are same, add some range
                self.min_value = max(0.0, self.min_value - 1000)
                self.max_value = self.max_value + 1000

    def should_update(self, current_time: float) -> bool:
        """Check if it's time to update the chart (10Hz refresh)."""
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            return True
        return False

    def draw(self, surface: pygame.Surface):
        """Draw the EMG chart with current samples."""
        if not self.samples:
            return
        
        # Draw background
        pygame.draw.rect(surface, self.bg_color, self.rect)
        
        # Calculate scaling
        value_range = self.max_value - self.min_value
        if value_range == 0:
            return
        
        # Draw data line
        if len(self.samples) > 1:
            points = []
            x_step = self.rect.w / (len(self.samples) - 1) if len(self.samples) > 1 else 0
            
            for i, sample in enumerate(self.samples):
                # Normalize sample to 0-1 range
                normalized = (sample - self.min_value) / value_range
                # Flip Y coordinate (pygame has origin at top-left)
                y = self.rect.bottom - (normalized * self.rect.h)
                # Calculate x position based on direction
                if self.reverse_direction:
                    # Right to left: newest data on right, oldest on left
                    # i=0 (oldest) should be on left, i=last (newest) should be on right
                    x = self.rect.right - (i * x_step)
                else:
                    # Left to right: newest data on right, oldest on left
                    x = self.rect.left + (i * x_step)
                points.append((int(x), int(y)))
            
            # Draw line connecting all points
            if len(points) > 1:
                pygame.draw.lines(surface, self.line_color, False, points, width=2)


class NumericStepper:
    def __init__(
        self,
        label: str,
        pos: Tuple[int, int],
        font: pygame.font.Font,
        value: float,
        step: float,
        min_v: float,
        max_v: float,
        fmt: str = "{:.0f}",
        on_change: Optional[Callable[[float], None]] = None,
        button_x: Optional[int] = None,
        button_w: int = 40,
        button_h: int = 36,
        button_gap: int = 10,
        text_button_gap: int = 20,
    ):
        self.label = label
        self.x, self.y = pos
        self.font = font
        self.value = value
        self.step = step
        self.min_v = min_v
        self.max_v = max_v
        self.fmt = fmt
        self.on_change = on_change
        self.button_x = button_x  # Optional fixed x position for button alignment
        self.button_w = button_w
        self.button_h = button_h
        self.button_gap = button_gap
        self.text_button_gap = text_button_gap
        # Calculate button positions based on text width to prevent overlap
        self._update_button_positions()

    def _update_button_positions(self):
        """Update button positions based on current label text width or fixed button_x."""
        if self.button_x is not None:
            # Use fixed x position for alignment (grid layout)
            button_start_x = self.button_x
        else:
            # Calculate based on text width (dynamic positioning)
            label_text = f"{self.label}: {self.fmt.format(self.value)}"
            label_img = self.font.render(label_text, True, (255, 255, 255))
            text_width = label_img.get_width()
            # Position buttons with padding after text (20px gap)
            button_start_x = self.x + text_width + self.text_button_gap
        self.btn_minus = Button(pygame.Rect(button_start_x, self.y, self.button_w, self.button_h), "-", self.font, on_click=self._dec)
        self.btn_plus = Button(
            pygame.Rect(button_start_x + self.button_w + self.button_gap, self.y, self.button_w, self.button_h),
            "+",
            self.font,
            on_click=self._inc,
        )

    def _notify(self):
        if self.on_change:
            self.on_change(self.value)
        # Update button positions when value changes (text width may change)
        self._update_button_positions()

    def _dec(self):
        self.value = max(self.min_v, self.value - self.step)
        self._notify()

    def _inc(self):
        self.value = min(self.max_v, self.value + self.step)
        self._notify()

    def draw(self, surface: pygame.Surface):
        label_img = self.font.render(f"{self.label}: {self.fmt.format(self.value)}", True, (255, 255, 255))
        surface.blit(label_img, (self.x, self.y))
        self.btn_minus.draw(surface)
        self.btn_plus.draw(surface)

    def handle_event(self, event: pygame.event.Event):
        self.btn_minus.handle_event(event)
        self.btn_plus.handle_event(event)
