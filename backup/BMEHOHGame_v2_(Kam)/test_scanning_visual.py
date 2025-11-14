#!/usr/bin/env python3
"""Test to visually confirm the scanning message is displayed and animated."""

import pygame
import time
from src.game.scenes import SettingsScene
from src.ble.ble_manager import BLEManager

pygame.init()
pygame.display.set_mode((1280, 800))
screen = pygame.display.get_surface()
clock = pygame.time.Clock()

# Create scene
ble = BLEManager(simulation=False)
settings = SettingsScene(
    screen_rect=pygame.Rect(0, 0, 1280, 800),
    ble=ble,
    on_close=lambda: print("[TEST] Close clicked"),
    set_emg_max=lambda x: None,
    set_threshold_percent=lambda x: None,
    set_countdown_seconds=lambda x: None,
    set_target_close_percent=lambda x: None,
    on_bind_left_emg=lambda x: None,
    on_bind_right_emg=lambda x: None,
    on_bind_left_exo=lambda x: None,
    on_bind_right_exo=lambda x: None,
    init_values={},
)

print("[TEST] Starting scan...")
settings._scan()  # Trigger scan

# Run game loop for 6 seconds to show the full scan + minimum display time
start_time = time.time()
frame_count = 0
last_print = 0

try:
    while time.time() - start_time < 6.0:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt()
        
        frame_count += 1
        settings.update(0.016)
        
        # Clear and draw
        screen.fill((20, 20, 20))
        settings.draw(screen)
        
        # Print status every 1 second
        elapsed = time.time() - start_time
        if int(elapsed) > last_print:
            last_print = int(elapsed)
            is_scanning = settings._scan_thread and settings._scan_thread.is_alive()
            print(f"[TEST] t={elapsed:.1f}s | is_scanning={is_scanning} | devices={len(settings.devices)}")
        
        pygame.display.flip()
        clock.tick(60)
        
except KeyboardInterrupt:
    pass

print(f"[TEST] Final: Found {len(settings.devices)} devices, rendered {frame_count} frames")
print(f"[TEST] Buttons created: {len(settings._device_buttons)}")
pygame.quit()
