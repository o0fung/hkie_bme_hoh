#!/usr/bin/env python3
"""
Direct test of SettingsScene._scan() method
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Mock pygame first
import pygame
pygame.init()
pygame.display.set_mode((800, 600))

from src.ble.ble_manager import BLEManager
from src.game.scenes import SettingsScene

def test_settings_scan():
    """Test the SettingsScene scan directly."""
    print("\n" + "=" * 70)
    print("TESTING SETTINGSSCENE._SCAN() DIRECTLY")
    print("=" * 70)
    
    screen = pygame.display.get_surface()
    screen_rect = screen.get_rect()
    
    # Create a BLEManager
    ble = BLEManager(simulation=False)
    
    # Create dummy callbacks
    def dummy_callback(*args, **kwargs):
        pass
    
    # Create SettingsScene
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
        init_values={},
    )
    
    print(f"SettingsScene created")
    print(f"Initial devices: {len(settings.devices)}")
    print(f"Initial device buttons: {len(settings._device_buttons)}")
    
    # Call the scan method
    print(f"\nCalling _scan()...")
    settings._scan()
    
    # Wait for the background thread to complete (max 15 seconds)
    print(f"Waiting for background scan thread to complete...")
    import time
    wait_count = 0
    max_wait = 150  # 15 seconds * 10 = 150 * 0.1s checks
    while settings._scan_thread and settings._scan_thread.is_alive() and wait_count < max_wait:
        time.sleep(0.1)
        wait_count += 1
    
    if wait_count >= max_wait:
        print(f"⚠️  WARNING: Background thread still running after 15 seconds!")
    else:
        print(f"✓ Background thread completed after {wait_count * 0.1:.1f}s")
    
    print(f"\nAfter _scan():")
    print(f"  Devices found: {len(settings.devices)}")
    print(f"  Device buttons created: {len(settings._device_buttons)}")
    
    # Show the devices
    if settings.devices:
        print(f"\nDevices list:")
        for i, d in enumerate(settings.devices, 1):
            print(f"  {i}. {d.name} ({d.address})")
    
    # Show device buttons
    if settings._device_buttons:
        print(f"\nDevice buttons created (first 20):")
        for i, (btn, role, dev) in enumerate(settings._device_buttons[:20], 1):
            print(f"  {i}. {role}: {dev.name}")
    
    ble.shutdown()
    
    print("\n" + "=" * 70)
    if len(settings._device_buttons) > 0:
        print("✅ SUCCESS: Device buttons were created!")
        return True
    else:
        print("❌ FAIL: No device buttons were created")
        return False


if __name__ == "__main__":
    try:
        success = test_settings_scan()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
