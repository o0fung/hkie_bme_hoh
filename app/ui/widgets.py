import math
import pygame
from typing import Callable, List, Optional, Tuple

Color = Tuple[int, int, int]
_STYLE_UNSET = object()


def _clamp_color(c: Color) -> Color:
    return (max(0, min(255, int(c[0]))), max(0, min(255, int(c[1]))), max(0, min(255, int(c[2]))))


def get_contrasting_color(color: Color) -> Color:
    """Return black for light colors, white for dark colors."""
    r, g, b = _clamp_color(color)
    # Perceived luminance (Rec. 709)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0) if luminance >= 140 else (255, 255, 255)


def draw_outlined_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: Color,
    pos: Tuple[int, int],
    outline_color: Optional[Color] = None,
    outline_width: int = 2,
):
    outline = outline_color if outline_color is not None else get_contrasting_color(color)
    outline = _clamp_color(outline)
    fill = _clamp_color(color)
    text_img = font.render(text, True, fill)
    x, y = pos
    if outline_width > 0:
        for ox, oy in (
            (-outline_width, 0),
            (outline_width, 0),
            (0, -outline_width),
            (0, outline_width),
            (-outline_width, -outline_width),
            (-outline_width, outline_width),
            (outline_width, -outline_width),
            (outline_width, outline_width),
        ):
            surface.blit(font.render(text, True, outline), (x + ox, y + oy))
    surface.blit(text_img, (x, y))


class Label:
    def __init__(self, text: str, pos: Tuple[int, int], font: pygame.font.Font, color: Color = (255, 255, 255)):
        self.text = text
        self.pos = pos
        self.font = font
        self.color = color

    def draw(self, surface: pygame.Surface):
        draw_outlined_text(surface, self.font, self.text, self.color, self.pos)


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
        self.border_color_override: Optional[Color] = None

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
            # Disabled appearance follows current theme brightness.
            base_bg = self.bg
            luminance = 0.2126 * base_bg[0] + 0.7152 * base_bg[1] + 0.0722 * base_bg[2]
            if luminance >= 140:
                bg = (205, 205, 205)
                fg = (120, 120, 120)
                border_color = self.border_color_override if self.border_color_override is not None else (245, 245, 245)
            else:
                bg = (15, 15, 15)
                fg = (100, 100, 100)
                border_color = (80, 80, 80)
        else:
            mouse_pos = pygame.mouse.get_pos()
            bg = self.hover_bg if self.rect.collidepoint(mouse_pos) else self.bg
            fg = self.fg
            # Use green border for green buttons, white border for others
            border_color = self.border_color_override if self.border_color_override is not None else get_contrasting_color(bg)
        
        border_radius = max(6, min(18, int(min(self.rect.w, self.rect.h) * 0.15)))
        border_width = max(2, min(4, int(min(self.rect.w, self.rect.h) * 0.04)))
        pygame.draw.rect(surface, bg, self.rect, border_radius=border_radius)
        pygame.draw.rect(surface, border_color, self.rect, width=border_width, border_radius=border_radius)
        label_img = self.font.render(self.text, True, fg)
        lx = self.rect.x + (self.rect.w - label_img.get_width()) // 2
        ly = self.rect.y + (self.rect.h - label_img.get_height()) // 2
        draw_outlined_text(surface, self.font, self.text, fg, (lx, ly))


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
        self.threshold_color: Color = (250, 230, 90)
        self.border_color_override: Optional[Color] = None
        self.value = 0.0
        self.threshold = 0.6
        self.activate_threshold: Optional[float] = None
        self.deactivate_threshold: Optional[float] = None

    def set_value(self, v: float):
        self.value = max(0.0, min(1.0, v))

    def set_threshold(self, t: float):
        self.threshold = max(0.0, min(1.0, t))
        self.activate_threshold = None
        self.deactivate_threshold = None

    def set_threshold_band(self, threshold: float, activate: float, deactivate: float):
        self.threshold = max(0.0, min(1.0, threshold))
        self.activate_threshold = max(0.0, min(1.0, activate))
        self.deactivate_threshold = max(0.0, min(1.0, deactivate))

    def _threshold_y(self, threshold: float) -> int:
        th = int(self.rect.h * (1.0 - threshold))
        return self.rect.y + th

    def draw(self, surface: pygame.Surface, font: Optional[pygame.font.Font] = None):
        border_radius = max(6, min(18, int(min(self.rect.w, self.rect.h) * 0.15)))
        # background
        pygame.draw.rect(surface, self.bg, self.rect, border_radius=border_radius)
        # fill based on value (vertical bar)
        h = int(self.rect.h * self.value)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.h - h, self.rect.w, h)
        pygame.draw.rect(surface, self.max_color, fill_rect, border_radius=border_radius)
        # threshold marker (base threshold only)
        marker_width = max(2, min(6, int(self.rect.w * 0.05)))
        y_base = self._threshold_y(self.threshold)
        pygame.draw.line(surface, self.threshold_color, (self.rect.x, y_base), (self.rect.right, y_base), width=marker_width)
        # Contrasting outer border to keep bar readable on photo backgrounds.
        border_color = self.border_color_override if self.border_color_override is not None else get_contrasting_color(self.max_color)
        pygame.draw.rect(surface, border_color, self.rect, width=max(2, marker_width), border_radius=border_radius)


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
        self.mirrored = False
        self.pointer_color: Color = (255, 255, 255)
        self.center_text_color: Color = (255, 255, 255)
        self.text_outline_color: Optional[Color] = None
        self.flexion_label = "Flexion"
        self.extension_label = "Extension"
        self.show_flexion_segment = True
        self.show_extension_segment = True
        self.show_partition_marker = True
        self.show_flexion_target = True
        self.show_extension_target = True

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

    def set_mirrored(self, mirrored: bool):
        self.mirrored = bool(mirrored)

    def set_labels(self, flexion_label: str, extension_label: str):
        self.flexion_label = str(flexion_label)
        self.extension_label = str(extension_label)

    def set_channel_visibility(self, show_flexion: bool, show_extension: bool):
        self.show_flexion_segment = bool(show_flexion)
        self.show_extension_segment = bool(show_extension)

    def set_marker_visibility(self, show_partition: bool, show_flexion_target: bool, show_extension_target: bool):
        self.show_partition_marker = bool(show_partition)
        self.show_flexion_target = bool(show_flexion_target)
        self.show_extension_target = bool(show_extension_target)

    def _percent_to_angle(self, p: float) -> float:
        clamped = max(0.0, min(1.0, p))
        # Default: 0% flexion (full extension) at right, 100% at left.
        # Mirrored: swap sides so 0% is left and 100% is right.
        if self.mirrored:
            return (1.0 - clamped) * math.pi
        return clamped * math.pi

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
        if self.show_flexion_segment and self.show_extension_segment:
            if self.mirrored:
                self._draw_arc_segment(surface, 0.0, split_angle, self.flexion_color)
                self._draw_arc_segment(surface, split_angle, math.pi, self.extension_color)
            else:
                self._draw_arc_segment(surface, 0.0, split_angle, self.extension_color)
                self._draw_arc_segment(surface, split_angle, math.pi, self.flexion_color)
        elif self.show_flexion_segment:
            self._draw_arc_segment(surface, 0.0, math.pi, self.flexion_color)
        elif self.show_extension_segment:
            self._draw_arc_segment(surface, 0.0, math.pi, self.extension_color)
        else:
            # Neither segment visible: leave base arc only.
            pass

        # Partition indicator at hand start point.
        if self.show_partition_marker:
            self._draw_marker(surface, self.partition, self.target_color)

        # Threshold markers.
        if self.show_flexion_target:
            self._draw_marker(surface, self.target_flexion, self.flexion_color)
        if self.show_extension_target:
            self._draw_marker(surface, self.target_extension, self.extension_color)

        # Pointer for current hand position.
        pointer_end = self._point_on_arc(value_angle, self.radius + max(6, self.line_width // 2))
        pygame.draw.line(surface, self.pointer_color, (cx, cy), pointer_end, width=max(2, self.line_width // 3))
        pygame.draw.circle(surface, self.pointer_color, pointer_end, max(4, self.line_width // 2))
        pygame.draw.circle(surface, self.pointer_color, (cx, cy), max(4, self.line_width // 2))

        # Labels.
        flex_img = font.render(self.flexion_label, True, self.flexion_color)
        ext_img = font.render(self.extension_label, True, self.extension_color)
        if self.mirrored:
            ext_pos = (cx - self.radius - ext_img.get_width() - 14, cy - ext_img.get_height() // 2)
            flex_pos = (cx + self.radius + 14, cy - flex_img.get_height() // 2)
            draw_outlined_text(surface, font, self.extension_label, self.extension_color, ext_pos)
            draw_outlined_text(surface, font, self.flexion_label, self.flexion_color, flex_pos)
        else:
            flex_pos = (cx - self.radius - flex_img.get_width() - 14, cy - flex_img.get_height() // 2)
            ext_pos = (cx + self.radius + 14, cy - ext_img.get_height() // 2)
            draw_outlined_text(surface, font, self.flexion_label, self.flexion_color, flex_pos)
            draw_outlined_text(surface, font, self.extension_label, self.extension_color, ext_pos)

        # Percentage text in center.
        percent_text = f"{int(self.value * 100)}%"
        text_img = font.render(percent_text, True, self.center_text_color)
        text_x = cx - text_img.get_width() // 2
        text_y = cy - text_img.get_height() // 2 + max(8, self.line_width)
        draw_outlined_text(surface, font, percent_text, self.center_text_color, (text_x, text_y), outline_color=self.text_outline_color)


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
        self.fade_width_ratio = 0.6
        self.fade_max_alpha = 255
        self.fade_min_alpha = 40
        self.background_alpha = 0
        self.border_color: Optional[Color] = None

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
        if self.background_alpha > 0:
            layer = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
            layer.fill((*self.bg_color, max(0, min(255, int(self.background_alpha)))))
            surface.blit(layer, self.rect.topleft)
        if self.border_color is not None:
            border_radius = max(4, min(14, int(min(self.rect.w, self.rect.h) * 0.1)))
            pygame.draw.rect(surface, self.border_color, self.rect, width=2, border_radius=border_radius)
        if not self.samples:
            return
        
        # Calculate scaling
        value_range = self.max_value - self.min_value
        if value_range == 0:
            return
        
        # Draw data line
        if len(self.samples) > 1:
            points = []
            draw_w = max(1, self.rect.w - 1)
            draw_h = max(1, self.rect.h - 1)
            x_step = draw_w / (len(self.samples) - 1) if len(self.samples) > 1 else 0
            
            for i, sample in enumerate(self.samples):
                # Normalize sample to 0-1 range
                normalized = (sample - self.min_value) / value_range
                # Flip Y coordinate (pygame has origin at top-left)
                y = self.rect.bottom - 1 - (normalized * draw_h)
                # Calculate x position based on direction
                if self.reverse_direction:
                    # Mirror mode: draw toward the left, staying fully inside chart rect.
                    x = self.rect.right - 1 - (i * x_step)
                else:
                    # Default mode: draw toward the right, staying fully inside chart rect.
                    x = self.rect.left + (i * x_step)
                points.append((int(x), int(y)))
            
            if len(points) > 1:
                # Transparent background: apply gradient by changing curve alpha only.
                toward_center_is_right = self.rect.centerx < surface.get_rect().centerx
                fade_width = max(1, int(self.rect.w * self.fade_width_ratio))
                chart_layer = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)

                for i in range(len(points) - 1):
                    x0, y0 = points[i]
                    x1, y1 = points[i + 1]
                    local_x0 = x0 - self.rect.x
                    local_y0 = y0 - self.rect.y
                    local_x1 = x1 - self.rect.x
                    local_y1 = y1 - self.rect.y
                    mid_x = (local_x0 + local_x1) * 0.5
                    if toward_center_is_right:
                        dist_from_center_edge = (self.rect.w - 1) - mid_x
                    else:
                        dist_from_center_edge = mid_x
                    t = max(0.0, min(1.0, 1.0 - (dist_from_center_edge / fade_width)))
                    alpha = int(self.fade_max_alpha - ((self.fade_max_alpha - self.fade_min_alpha) * t))
                    seg_color = (*self.line_color, max(self.fade_min_alpha, min(self.fade_max_alpha, alpha)))
                    pygame.draw.line(chart_layer, seg_color, (local_x0, local_y0), (local_x1, local_y1), width=2)

                surface.blit(chart_layer, self.rect.topleft)


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
        self.text_color: Color = (255, 255, 255)
        self.text_outline_color: Optional[Color] = (0, 0, 0)
        self._button_bg: Color = (30, 30, 30)
        self._button_hover_bg: Color = (60, 60, 60)
        self._button_fg: Color = (255, 255, 255)
        self._button_border_color: Optional[Color] = None
        self._slider_right_x: Optional[int] = None
        self._slider_min_width = 72
        self._slider_gap = 10
        self._slider_track_rect = pygame.Rect(0, 0, 0, 0)
        self._slider_knob_radius = max(6, int(self.button_h * 0.3))
        self._slider_dragging = False
        # Ensure initial value is always valid for this stepper's range.
        self.value = self._clamp_value(self.value)
        # Calculate button positions based on text width to prevent overlap
        self._update_button_positions()
        # Keep caller state consistent if persisted/default value was out of range.
        if self.on_change and self.value != value:
            self.on_change(self.value)

    def _clamp_value(self, v: float) -> float:
        return max(self.min_v, min(self.max_v, v))

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
        self._update_slider_geometry()
        self._apply_button_style()

    def _update_slider_geometry(self):
        self._slider_track_rect = pygame.Rect(0, 0, 0, 0)
        if self._slider_right_x is None:
            return
        slider_start_x = self.btn_plus.rect.right + self._slider_gap
        slider_end_x = int(self._slider_right_x)
        slider_w = slider_end_x - slider_start_x
        if slider_w < self._slider_min_width:
            return
        track_h = max(6, int(self.button_h * 0.2))
        track_y = self.y + (self.button_h - track_h) // 2
        self._slider_track_rect = pygame.Rect(slider_start_x, track_y, slider_w, track_h)

    def _apply_button_style(self):
        for btn in (self.btn_minus, self.btn_plus):
            btn.bg = self._button_bg
            btn.hover_bg = self._button_hover_bg
            btn.fg = self._button_fg
            btn.border_color_override = self._button_border_color

    def _notify(self):
        self.value = self._clamp_value(self.value)
        if self.on_change:
            self.on_change(self.value)
        # Update button positions when value changes (text width may change)
        self._update_button_positions()

    def _set_value_from_slider_x(self, mouse_x: int):
        if self._slider_track_rect.w <= 0:
            return
        ratio = (mouse_x - self._slider_track_rect.left) / max(1, self._slider_track_rect.w)
        ratio = max(0.0, min(1.0, ratio))
        raw_value = self.min_v + ratio * (self.max_v - self.min_v)
        if self.step > 0:
            steps = round((raw_value - self.min_v) / self.step)
            raw_value = self.min_v + steps * self.step
        self.value = self._clamp_value(raw_value)
        self._notify()

    def set_slider_right_x(self, slider_right_x: Optional[int], min_width: int = 72):
        self._slider_right_x = int(slider_right_x) if slider_right_x is not None else None
        self._slider_min_width = max(24, int(min_width))
        self._update_button_positions()

    def _dec(self):
        self.value = self._clamp_value(self.value - self.step)
        self._notify()

    def _inc(self):
        self.value = self._clamp_value(self.value + self.step)
        self._notify()

    def set_value(self, value: float, notify: bool = False):
        self.value = self._clamp_value(float(value))
        if notify and self.on_change:
            self.on_change(self.value)
        self._update_button_positions()

    def set_y(self, y: int):
        """Move stepper vertically and keep +/- buttons aligned."""
        self.y = int(y)
        self._update_button_positions()

    def set_style(
        self,
        text_color: Optional[Color] = None,
        text_outline_color: Optional[Color] = None,
        button_bg=_STYLE_UNSET,
        button_hover_bg=_STYLE_UNSET,
        button_fg=_STYLE_UNSET,
        button_border_color=_STYLE_UNSET,
    ):
        if text_color is not None:
            self.text_color = text_color
        self.text_outline_color = text_outline_color
        if button_bg is not _STYLE_UNSET:
            self._button_bg = button_bg
        if button_hover_bg is not _STYLE_UNSET:
            self._button_hover_bg = button_hover_bg
        if button_fg is not _STYLE_UNSET:
            self._button_fg = button_fg
        if button_border_color is not _STYLE_UNSET:
            self._button_border_color = button_border_color
        self._apply_button_style()

    def draw(self, surface: pygame.Surface):
        draw_outlined_text(
            surface,
            self.font,
            f"{self.label}: {self.fmt.format(self.value)}",
            self.text_color,
            (self.x, self.y),
            outline_color=self.text_outline_color,
        )
        self.btn_minus.draw(surface)
        self.btn_plus.draw(surface)
        if self._slider_track_rect.w > 0:
            track_color = (120, 120, 120) if self._button_border_color is None else self._button_border_color
            fill_color = self._button_fg
            knob_color = self._button_fg
            pygame.draw.rect(surface, (45, 45, 45), self._slider_track_rect, border_radius=max(3, self._slider_track_rect.h // 2))
            ratio = 0.0 if self.max_v <= self.min_v else (self.value - self.min_v) / (self.max_v - self.min_v)
            ratio = max(0.0, min(1.0, ratio))
            fill_w = int(round(self._slider_track_rect.w * ratio))
            if fill_w > 0:
                fill_rect = pygame.Rect(
                    self._slider_track_rect.x,
                    self._slider_track_rect.y,
                    fill_w,
                    self._slider_track_rect.h,
                )
                pygame.draw.rect(surface, fill_color, fill_rect, border_radius=max(3, self._slider_track_rect.h // 2))
            pygame.draw.rect(
                surface,
                track_color,
                self._slider_track_rect,
                width=2,
                border_radius=max(3, self._slider_track_rect.h // 2),
            )
            knob_x = self._slider_track_rect.x + int(round(self._slider_track_rect.w * ratio))
            knob_x = max(self._slider_track_rect.left, min(self._slider_track_rect.right, knob_x))
            knob_y = self._slider_track_rect.centery
            pygame.draw.circle(surface, knob_color, (knob_x, knob_y), self._slider_knob_radius)

    def handle_event(self, event: pygame.event.Event):
        self.btn_minus.handle_event(event)
        self.btn_plus.handle_event(event)
        if self._slider_track_rect.w <= 0:
            self._slider_dragging = False
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            knob_ratio = 0.0 if self.max_v <= self.min_v else (self.value - self.min_v) / (self.max_v - self.min_v)
            knob_ratio = max(0.0, min(1.0, knob_ratio))
            knob_x = self._slider_track_rect.x + int(round(self._slider_track_rect.w * knob_ratio))
            knob_y = self._slider_track_rect.centery
            knob_rect = pygame.Rect(0, 0, self._slider_knob_radius * 2 + 8, self._slider_knob_radius * 2 + 8)
            knob_rect.center = (knob_x, knob_y)
            if self._slider_track_rect.collidepoint(event.pos) or knob_rect.collidepoint(event.pos):
                self._slider_dragging = True
                self._set_value_from_slider_x(event.pos[0])
        elif event.type == pygame.MOUSEMOTION and self._slider_dragging:
            self._set_value_from_slider_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._slider_dragging = False


class OptionStepper:
    def __init__(
        self,
        label: str,
        pos: Tuple[int, int],
        font: pygame.font.Font,
        options: List[Tuple[str, str]],
        value: str,
        on_change: Optional[Callable[[str], None]] = None,
        button_x: Optional[int] = None,
        button_w: int = 40,
        button_h: int = 36,
        button_gap: int = 10,
        text_button_gap: int = 20,
    ):
        self.label = label
        self.x, self.y = pos
        self.font = font
        self.options = list(options)
        self.on_change = on_change
        self.button_x = button_x
        self.button_w = button_w
        self.button_h = button_h
        self.button_gap = button_gap
        self.text_button_gap = text_button_gap
        self.text_color: Color = (255, 255, 255)
        self.text_outline_color: Optional[Color] = (0, 0, 0)
        self._button_bg: Color = (30, 30, 30)
        self._button_hover_bg: Color = (60, 60, 60)
        self._button_fg: Color = (255, 255, 255)
        self._button_border_color: Optional[Color] = None
        self.value = self._sanitize_value(value)
        self._update_button_positions()

    def _sanitize_value(self, value: str) -> str:
        option_keys = [key for key, _ in self.options]
        if not option_keys:
            return ""
        return value if value in option_keys else option_keys[0]

    def _current_option_label(self) -> str:
        for key, display in self.options:
            if key == self.value:
                return display
        return self.value

    def _update_button_positions(self):
        if self.button_x is not None:
            button_start_x = self.button_x
        else:
            label_text = f"{self.label}: {self._current_option_label()}"
            label_img = self.font.render(label_text, True, (255, 255, 255))
            button_start_x = self.x + label_img.get_width() + self.text_button_gap
        self.btn_prev = Button(
            pygame.Rect(button_start_x, self.y, self.button_w, self.button_h),
            "<",
            self.font,
            on_click=self._prev,
        )
        self.btn_next = Button(
            pygame.Rect(button_start_x + self.button_w + self.button_gap, self.y, self.button_w, self.button_h),
            ">",
            self.font,
            on_click=self._next,
        )
        self._apply_button_style()

    def _apply_button_style(self):
        for btn in (self.btn_prev, self.btn_next):
            btn.bg = self._button_bg
            btn.hover_bg = self._button_hover_bg
            btn.fg = self._button_fg
            btn.border_color_override = self._button_border_color

    def _notify(self):
        self.value = self._sanitize_value(self.value)
        if self.on_change:
            self.on_change(self.value)
        self._update_button_positions()

    def _move(self, delta: int):
        if not self.options:
            return
        keys = [key for key, _ in self.options]
        try:
            idx = keys.index(self.value)
        except ValueError:
            idx = 0
        self.value = keys[(idx + delta) % len(keys)]
        self._notify()

    def _prev(self):
        self._move(-1)

    def _next(self):
        self._move(1)

    def set_options(self, options: List[Tuple[str, str]]):
        self.options = list(options)
        self.value = self._sanitize_value(self.value)
        self._update_button_positions()

    def set_value(self, value: str, notify: bool = False):
        self.value = self._sanitize_value(value)
        if notify and self.on_change:
            self.on_change(self.value)
        self._update_button_positions()

    def set_y(self, y: int):
        self.y = int(y)
        self._update_button_positions()

    def set_style(
        self,
        text_color: Optional[Color] = None,
        text_outline_color: Optional[Color] = None,
        button_bg=_STYLE_UNSET,
        button_hover_bg=_STYLE_UNSET,
        button_fg=_STYLE_UNSET,
        button_border_color=_STYLE_UNSET,
    ):
        if text_color is not None:
            self.text_color = text_color
        self.text_outline_color = text_outline_color
        if button_bg is not _STYLE_UNSET:
            self._button_bg = button_bg
        if button_hover_bg is not _STYLE_UNSET:
            self._button_hover_bg = button_hover_bg
        if button_fg is not _STYLE_UNSET:
            self._button_fg = button_fg
        if button_border_color is not _STYLE_UNSET:
            self._button_border_color = button_border_color
        self._apply_button_style()

    def draw(self, surface: pygame.Surface):
        draw_outlined_text(
            surface,
            self.font,
            f"{self.label}: {self._current_option_label()}",
            self.text_color,
            (self.x, self.y),
            outline_color=self.text_outline_color,
        )
        self.btn_prev.draw(surface)
        self.btn_next.draw(surface)

    def handle_event(self, event: pygame.event.Event):
        self.btn_prev.handle_event(event)
        self.btn_next.handle_event(event)
