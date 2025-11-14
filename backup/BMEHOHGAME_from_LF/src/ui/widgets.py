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

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1,):
            if self.rect.collidepoint(event.pos):
                self._pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (1,):
            if self._pressed and self.rect.collidepoint(event.pos):
                self.on_click()
            self._pressed = False

    def draw(self, surface: pygame.Surface):
        mouse_pos = pygame.mouse.get_pos()
        bg = self.hover_bg if self.rect.collidepoint(mouse_pos) else self.bg
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, (200, 200, 200), self.rect, width=2, border_radius=8)
        label_img = self.font.render(self.text, True, self.fg)
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
        # background
        pygame.draw.rect(surface, self.bg, self.rect, border_radius=8)
        # fill based on value (vertical bar)
        h = int(self.rect.h * self.value)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.h - h, self.rect.w, h)
        pygame.draw.rect(surface, self.max_color, fill_rect, border_radius=8)
        # threshold marker
        th = int(self.rect.h * (1.0 - self.threshold))
        y = self.rect.y + th
        pygame.draw.line(surface, (250, 230, 90), (self.rect.x, y), (self.rect.right, y), width=3)


class NumericStepper:
    def __init__(self, label: str, pos: Tuple[int, int], font: pygame.font.Font, value: float, step: float, min_v: float, max_v: float, fmt: str = "{:.0f}", on_change: Optional[Callable[[float], None]] = None):
        self.label = label
        self.x, self.y = pos
        self.font = font
        self.value = value
        self.step = step
        self.min_v = min_v
        self.max_v = max_v
        self.fmt = fmt
        self.on_change = on_change
        self.btn_minus = Button(pygame.Rect(self.x + 240, self.y, 40, 36), "-", font, on_click=self._dec)
        self.btn_plus = Button(pygame.Rect(self.x + 290, self.y, 40, 36), "+", font, on_click=self._inc)

    def _notify(self):
        if self.on_change:
            self.on_change(self.value)

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
