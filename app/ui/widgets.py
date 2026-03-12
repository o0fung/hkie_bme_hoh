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
        self.flexion_color: Color = (90, 180, 255)
        self.extension_color: Color = (255, 140, 140)
        self.partition = 0.7  # Hand start percent mapped to 0..1
        self.target_flexion = max(0.0, min(1.0, target))
        self.target_extension = 0.3

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))

    def set_target(self, t: float):
        # Backward-compatible helper: legacy single-target callers map to flexion target.
        clamped = max(0.0, min(1.0, t))
        self.target = clamped
        self.target_flexion = clamped

    def set_partition(self, p: float):
        self.partition = max(0.0, min(1.0, p))

    def set_targets(self, flexion: float, extension: float):
        self.target_flexion = max(0.0, min(1.0, flexion))
        self.target_extension = max(0.0, min(1.0, extension))

    def _percent_to_angle(self, p: float) -> float:
        # 0% flexion (full extension) is right side, 100% flexion is left side.
        return max(0.0, min(1.0, p)) * math.pi

    def _point_on_arc(self, angle: float, radius: float) -> tuple[int, int]:
        cx, cy = self.center
        x = cx + radius * math.cos(angle)
        y = cy - radius * math.sin(angle)
        return int(x), int(y)

    def _draw_arc_segment(self, surface: pygame.Surface, angle_start: float, angle_end: float, color: Color):
        if angle_end <= angle_start:
            return
        span = angle_end - angle_start
        steps = max(8, int((span / math.pi) * 64))
        points = []
        for i in range(steps + 1):
            t = i / steps
            a = angle_start + span * t
            points.append(self._point_on_arc(a, self.radius))
        if len(points) >= 2:
            pygame.draw.lines(surface, color, False, points, width=self.line_width)

    def _draw_marker(self, surface: pygame.Surface, percent: float, color: Color):
        angle = self._percent_to_angle(percent)
        inner = self._point_on_arc(angle, self.radius - max(8, self.line_width // 2))
        outer = self._point_on_arc(angle, self.radius + max(14, self.line_width))
        pygame.draw.line(surface, color, inner, outer, width=max(2, self.line_width // 2))
        pygame.draw.circle(surface, color, outer, max(3, self.line_width // 3))

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        cx, cy = self.center
        split_angle = self._percent_to_angle(self.partition)
        value_angle = self._percent_to_angle(self.value)

        # Base arc then two partitions.
        self._draw_arc_segment(surface, 0.0, math.pi, self.bg_color)
        self._draw_arc_segment(surface, 0.0, split_angle, self.extension_color)
        self._draw_arc_segment(surface, split_angle, math.pi, self.flexion_color)

        # Partition indicator at hand start point.
        self._draw_marker(surface, self.partition, self.target_color)

        # Threshold markers.
        self._draw_marker(surface, self.target_flexion, self.flexion_color)
        self._draw_marker(surface, self.target_extension, self.extension_color)

        # Pointer for current hand position.
        pointer_end = self._point_on_arc(value_angle, self.radius + max(6, self.line_width // 2))
        pygame.draw.line(surface, (255, 255, 255), (cx, cy), pointer_end, width=max(2, self.line_width // 3))
        pygame.draw.circle(surface, (255, 255, 255), pointer_end, max(4, self.line_width // 2))
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), max(4, self.line_width // 2))

        # Labels.
        flex_img = font.render("Flexion", True, self.flexion_color)
        ext_img = font.render("Extension", True, self.extension_color)
        surface.blit(flex_img, (cx - self.radius - flex_img.get_width() - 14, cy - flex_img.get_height() // 2))
        surface.blit(ext_img, (cx + self.radius + 14, cy - ext_img.get_height() // 2))

        # Percentage text in center.
        percent_text = f"{int(self.value * 100)}%"
        text_img = font.render(percent_text, True, (255, 255, 255))
        text_x = cx - text_img.get_width() // 2
        text_y = cy - text_img.get_height() // 2 + max(8, self.line_width)
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
