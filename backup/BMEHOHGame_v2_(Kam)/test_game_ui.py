#!/usr/bin/env python3
"""
Test the game with real devices to verify Settings panel shows found devices.
Run with: python test_game_ui.py
Then click Settings -> Scan BLE and wait ~12 seconds.
"""

import pygame
import time
import sys
from src.ble.ble_manager import BLEManager
from src.game.scenes import SettingsScene

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((1200, 800))
pygame.display.set_caption("Game UI Test - Settings Panel")
clock = pygame.time.Clock()

# Create BLE manager (non-simulation)
ble = BLEManager(simulation=False)
print("[TEST] BLEManager created (simulation=False)")

# Create Settings scene with dummy callbacks
screen_rect = screen.get_rect()

def dummy_callback(*args, **kwargs):
    pass

settings = SettingsScene(
    screen_rect=screen_rect,
    ble=ble,
    on_close=lambda: None,
    set_emg_max=dummy_callback,
    set_threshold_percent=dummy_callback,
    set_countdown_seconds=dummy_callback,
    set_target_close_percent=dummy_callback,
    on_bind_left_emg=dummy_callback,
    on_bind_right_emg=dummy_callback,
    on_bind_left_exo=dummy_callback,
    on_bind_right_exo=dummy_callback,
    init_values={},
)

# Pre-populate some devices from a scan
print("\n[TEST] Scanning for devices once to populate the list...")
devices = ble.scan(timeout=5.0)
print(f"[TEST] Found {len(devices)} devices in initial scan")

# Now use the Settings scene to show them
settings.devices = devices
emgs_devices = [d for d in devices if d.name and 'EMGS' in d.name]
print(f"[TEST] EMGS devices found: {len(emgs_devices)}")
for d in emgs_devices:
    print(f"       - {d.name} ({d.address})")

print("\n[TEST] Starting game loop - click Scan BLE to scan again")
print("[TEST] Press ESC to exit")
print("-" * 60)

running = True
while running:
    dt = clock.tick(60) / 1000.0
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        
        settings.handle_event(event)
    
    settings.update(dt)
    
    # Clear and draw
    screen.fill((10, 20, 30))
    settings.draw(screen)
    
    # Draw scan status info
    font_small = pygame.font.SysFont("Arial", 20)
    status_lines = [
        f"Devices in list: {len(settings.devices)}",
        f"UI buttons created: {len(settings._device_buttons)}",
        f"Scan status: {settings._scan_status}",
    ]
    for i, line in enumerate(status_lines):
        text = font_small.render(line, True, (200, 200, 200))
        screen.blit(text, (20, 20 + i * 25))
    
    # Show EMGS devices
    emgs_text = font_small.render("EMGS Devices Found:", True, (100, 200, 100))
    screen.blit(emgs_text, (20, screen_rect.h - 120))
    
    emgs_in_list = [d for d in settings.devices if d.name and 'EMGS' in d.name]
    for i, d in enumerate(emgs_in_list[:3]):  # Show first 3
        text = font_small.render(f"  {i+1}. {d.name} ({d.address})", True, (100, 200, 100))
        screen.blit(text, (20, screen_rect.h - 95 + i * 20))
    
    pygame.display.flip()

pygame.quit()
print("\n[TEST] Game loop ended - test complete")
