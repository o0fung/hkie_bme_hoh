from typing import Optional
import pygame


class Scene:
    def handle_event(self, event: pygame.event.Event):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        pass


class SceneManager:
    def __init__(self):
        self._scene: Optional[Scene] = None

    def set_scene(self, scene: Scene):
        self._scene = scene

    def handle_event(self, event: pygame.event.Event):
        if self._scene:
            self._scene.handle_event(event)

    def update(self, dt: float):
        if self._scene:
            self._scene.update(dt)

    def draw(self, surface: pygame.Surface):
        if self._scene:
            self._scene.draw(surface)
