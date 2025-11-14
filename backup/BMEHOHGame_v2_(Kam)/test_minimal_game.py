#!/usr/bin/env python3
"""
Minimal game test that opens the Settings scene immediately to debug device discovery.
"""

import json
import os
import sys
import time

import pygame

from src.ble.ble_manager import BLEManager
from src.game.scenes import SettingsScene

pygame.init()
screen = pygame.display.set_mode((1200, 800))
pygame.display.set_caption("Game Minimal Test - Settings Scene")
clock = pygame.time.Clock()

# Load config exactly like main.py does
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "devices.json")
SAMPLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "devices.sample.json")

print("=" * 70)
print("MINIMAL GAME TEST - Settings Scene")
print("=" * 70)

# Load config
if not os.path.exists(CONFIG_PATH):
    print(f"[INIT] Creating {CONFIG_PATH} from sample...")
    with open(SAMPLE_CONFIG_PATH, "r") as f:
        sample = json.load(f)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(sample, f, indent=2)

with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)

simulation = bool(cfg.get("simulation", True))
print(f"[INIT] Config loaded: simulation={simulation}")

# Create BLEManager exactly like main.py does
ble = BLEManager(simulation=simulation)
print(f"[INIT] BLEManager created: simulation={ble.simulation}")

# Create Settings scene exactly like main.py does
screen_rect = screen.get_rect()

settings = SettingsScene(
    screen_rect=screen_rect,
    ble=ble,
    on_close=lambda: None,
    set_emg_max=lambda x: None,
    set_threshold_percent=lambda x: None,
    set_countdown_seconds=lambda x: None,
    set_target_close_percent=lambda x: None,
    on_bind_left_emg=lambda x: None,
    on_bind_right_emg=lambda x: None,
    on_bind_left_exo=lambda x: None,
    on_bind_right_exo=lambda x: None,
    init_values=cfg.get("settings", {}),
)

print(f"[INIT] SettingsScene created: ble.simulation={settings.ble.simulation}")

# Automatically trigger scan after 0.5 seconds
print(f"\n[TEST] Opening game window...")
print(f"[TEST] Will auto-trigger scan in 0.5 seconds")
print(f"[TEST] Close window or press ESC to exit\n")

scan_triggered = False
scan_time = 0.5
elapsed = 0

running = True
while running:
    dt = clock.tick(60) / 1000.0
    elapsed += dt
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        
        settings.handle_event(event)
    
    # Auto-trigger scan
    if not scan_triggered and elapsed > scan_time:
        print(f"[AUTO] Triggering scan at t={elapsed:.2f}s")
        settings._scan()
        scan_triggered = True
    
    settings.update(dt)
    
    # Draw
    screen.fill((10, 20, 30))
    settings.draw(screen)
    
    # Draw status overlay
    font = pygame.font.SysFont("Arial", 20)
    status_lines = [
        f"Elapsed: {elapsed:.2f}s",
        f"Scan status: {settings._scan_status}",
        f"Devices found: {len(settings.devices)}",
        f"UI buttons: {len(settings._device_buttons)}",
        f"Scanning: {settings._scan_thread is not None and settings._scan_thread.is_alive()}",
    ]
    
    for i, line in enumerate(status_lines):
        text = font.render(line, True, (200, 200, 200))
        screen.blit(text, (20, 20 + i * 25))
    
    pygame.display.flip()

pygame.quit()
print(f"\n[DONE] Test complete")
print(f"[RESULT] Final scan status: {settings._scan_status}")
print(f"[RESULT] Devices found: {len(settings.devices)}")
