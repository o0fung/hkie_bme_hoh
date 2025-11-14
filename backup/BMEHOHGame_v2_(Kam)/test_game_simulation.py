#!/usr/bin/env python3
"""
Simulate the exact game initialization and Settings opening.
This mimics what happens when you run: python main.py -> click Settings -> click Scan BLE
"""

import sys
import os
import json
import time

# Mock pygame first
import pygame
pygame.init()
pygame.display.set_mode((800, 600))

from src.ble.ble_manager import BLEManager
from src.game.scenes import SettingsScene

print("=" * 70)
print("SIMULATING GAME INITIALIZATION")
print("=" * 70)

# Step 1: Load config like main.py does
print("\n[STEP 1] Loading configuration")
CONFIG_PATH = "config/devices.json"
SAMPLE_CONFIG_PATH = "config/devices.sample.json"

# Check if devices.json exists
if not os.path.exists(CONFIG_PATH):
    print(f"  {CONFIG_PATH} does not exist, copying from sample...")
    try:
        with open(SAMPLE_CONFIG_PATH, "r") as f:
            sample = json.load(f)
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(sample, f, indent=2)
        print(f"  ✓ Created {CONFIG_PATH}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
        sys.exit(1)

# Load the config
try:
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    simulation = bool(cfg.get("simulation", True))
    print(f"  ✓ Config loaded")
    print(f"    - simulation: {simulation}")
except Exception as e:
    print(f"  ❌ Error loading config: {e}")
    sys.exit(1)

# Step 2: Create BLEManager like main.py does
print("\n[STEP 2] Creating BLEManager")
ble = BLEManager(simulation=simulation)
print(f"  ✓ BLEManager created")
print(f"    - simulation={ble.simulation}")

# Step 3: Create SettingsScene like main.py does
print("\n[STEP 3] Creating SettingsScene")

screen = pygame.display.get_surface()
screen_rect = screen.get_rect()

def dummy_callback(*args, **kwargs):
    pass

settings = SettingsScene(
    screen_rect=screen_rect,
    ble=ble,
    on_close=dummy_callback,
    set_emg_max=dummy_callback,
    set_threshold_percent=dummy_callback,
    set_countdown_seconds=dummy_callback,
    set_target_close_percent=dummy_callback,
    on_bind_left_emg=dummy_callback,
    on_bind_right_emg=dummy_callback,
    on_bind_left_exo=dummy_callback,
    on_bind_right_exo=dummy_callback,
    init_values=cfg.get("settings", {}),
)

print(f"  ✓ SettingsScene created")
print(f"    - ble.simulation={settings.ble.simulation}")

# Step 4: Call _scan() like user does
print("\n[STEP 4] Calling _scan()")
settings._scan()

# Step 5: Wait for scan to complete
print("\n[STEP 5] Waiting for scan thread")
wait_time = 0
max_wait = 150
while settings._scan_thread and settings._scan_thread.is_alive() and wait_time < max_wait:
    time.sleep(0.1)
    wait_time += 1

print(f"  ✓ Scan completed after {wait_time * 0.1:.1f}s")

# Step 6: Check results
print("\n[STEP 6] Results")
print(f"  Devices found: {len(settings.devices)}")
print(f"  UI buttons created: {len(settings._device_buttons)}")
print(f"  Scan status: {settings._scan_status}")

emgs_count = len([d for d in settings.devices if d.name and 'EMGS' in d.name])
print(f"  EMGS devices: {emgs_count}")

if emgs_count == 2 and len(settings._device_buttons) == 10:
    print("\n✅ SUCCESS: Game simulation works correctly!")
    sys.exit(0)
else:
    print(f"\n❌ FAILURE: Expected 2 EMGS devices and 10 buttons")
    sys.exit(1)
