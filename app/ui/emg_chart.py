from typing import Optional, Tuple

import pygame

Color = Tuple[int, int, int]


class EMGChart:
    def __init__(
        self,
        rect: pygame.Rect,
        max_samples: int = 500,  # Number of samples to display (for 10Hz refresh)
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
        if len(self.samples) > self.max_samples:
            self.samples = self.samples[-self.max_samples :]
        if self.samples:
            self.min_value = 0.0
            self.max_value = 65535.0
            value_range = self.max_value - self.min_value
            if value_range > 0:
                padding = value_range * 0.1
                self.min_value -= padding
                self.max_value += padding
            else:
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

        value_range = self.max_value - self.min_value
        if value_range == 0:
            return

        if len(self.samples) > 1:
            points = []
            draw_w = max(1, self.rect.w - 1)
            draw_h = max(1, self.rect.h - 1)
            x_step = draw_w / (len(self.samples) - 1) if len(self.samples) > 1 else 0

            for i, sample in enumerate(self.samples):
                normalized = (sample - self.min_value) / value_range
                y = self.rect.bottom - 1 - (normalized * draw_h)
                if self.reverse_direction:
                    x = self.rect.right - 1 - (i * x_step)
                else:
                    x = self.rect.left + (i * x_step)
                points.append((int(x), int(y)))

            if len(points) > 1:
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
