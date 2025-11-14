#!/usr/bin/env python3
"""
Comprehensive test showing the full BLE scanning pipeline:
1. BLEManager scans for raw devices
2. SettingsScene filters and creates UI
3. Both EMGS devices appear in final UI
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
import time

def main():
    print("\n" + "=" * 80)
    print("COMPREHENSIVE BLE DEVICE DISCOVERY TEST")
    print("=" * 80)
    
    screen = pygame.display.get_surface()
    screen_rect = screen.get_rect()
    
    # =========================================================================
    # STEP 1: Test BLEManager.scan()
    # =========================================================================
    print("\n[STEP 1] Testing BLEManager.scan() with real devices")
    print("-" * 80)
    
    ble = BLEManager(simulation=False)
    print(f"✓ Created BLEManager (simulation={'OFF' if not ble.simulation else 'ON'})")
    
    print(f"  Scanning for devices (timeout 10s)...")
    start_time = time.time()
    all_devices = ble.scan(timeout=10.0)
    elapsed = time.time() - start_time
    
    print(f"✓ Scan completed in {elapsed:.1f}s")
    print(f"  Total devices found: {len(all_devices)}")
    
    # Find EMGS devices
    emgs_in_scan = [d for d in all_devices if d.name and 'EMGS' in d.name]
    print(f"  EMGS devices in scan: {len(emgs_in_scan)}")
    for d in emgs_in_scan:
        print(f"    • {d.name} ({d.address})")
    
    # =========================================================================
    # STEP 2: Test SettingsScene._scan()
    # =========================================================================
    print("\n[STEP 2] Testing SettingsScene scanning and UI button creation")
    print("-" * 80)
    
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
        init_values={},
    )
    
    print(f"✓ Created SettingsScene")
    print(f"  Before scan: {len(settings.devices)} devices, {len(settings._device_buttons)} buttons")
    
    # Trigger the scan
    print(f"  Starting background scan...")
    settings._scan()
    
    # Wait for thread
    print(f"  Waiting for scan thread (max 15s)...")
    wait_time = 0
    max_wait = 150
    while settings._scan_thread and settings._scan_thread.is_alive() and wait_time < max_wait:
        time.sleep(0.1)
        wait_time += 1
    
    print(f"✓ Scan thread completed after {wait_time * 0.1:.1f}s")
    print(f"  After scan: {len(settings.devices)} devices, {len(settings._device_buttons)} buttons")
    
    # =========================================================================
    # STEP 3: Verify EMGS devices in UI
    # =========================================================================
    print("\n[STEP 3] Verifying EMGS devices in UI")
    print("-" * 80)
    
    emgs_in_ui = [d for d in settings.devices if d.name and 'EMGS' in d.name]
    print(f"  EMGS devices found by SettingsScene: {len(emgs_in_ui)}")
    for d in emgs_in_ui:
        print(f"    • {d.name} ({d.address})")
    
    # Show what UI buttons were created for EMGS
    emgs_buttons = [(btn, role, dev) for btn, role, dev in settings._device_buttons if dev.name and 'EMGS' in dev.name]
    print(f"\n  UI buttons created for EMGS devices: {len(emgs_buttons)}")
    
    # Group by device
    emgs_button_counts = {}
    for btn, role, dev in emgs_buttons:
        if dev.address not in emgs_button_counts:
            emgs_button_counts[dev.address] = []
        emgs_button_counts[dev.address].append(role)
    
    for addr, roles in emgs_button_counts.items():
        print(f"    • {addr}:")
        for role in roles:
            print(f"      - {role}")
    
    # =========================================================================
    # STEP 4: Final verification
    # =========================================================================
    print("\n[STEP 4] Final verification")
    print("-" * 80)
    
    expected_emgs_count = 2
    actual_emgs_count = len(emgs_in_ui)
    buttons_per_device = 5  # 1 label + 4 bind buttons
    expected_buttons = expected_emgs_count * buttons_per_device
    actual_buttons = len(emgs_buttons)
    
    tests_passed = 0
    tests_total = 3
    
    # Test 1: EMGS devices found
    if actual_emgs_count == expected_emgs_count:
        print(f"✅ Test 1: EMGS devices found")
        print(f"   Expected: {expected_emgs_count}, Actual: {actual_emgs_count}")
        tests_passed += 1
    else:
        print(f"❌ Test 1: EMGS devices mismatch")
        print(f"   Expected: {expected_emgs_count}, Actual: {actual_emgs_count}")
    
    # Test 2: Buttons created
    if actual_buttons == expected_buttons:
        print(f"✅ Test 2: UI buttons created correctly")
        print(f"   Expected: {expected_buttons}, Actual: {actual_buttons}")
        tests_passed += 1
    else:
        print(f"❌ Test 2: Button count mismatch")
        print(f"   Expected: {expected_buttons}, Actual: {actual_buttons}")
    
    # Test 3: Settings status message
    if "Found" in settings._scan_status:
        print(f"✅ Test 3: Scan status message")
        print(f"   Status: '{settings._scan_status}'")
        tests_passed += 1
    else:
        print(f"❌ Test 3: Scan status not set correctly")
        print(f"   Status: '{settings._scan_status}'")
    
    # Cleanup
    ble.shutdown()
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print(f"TEST SUMMARY: {tests_passed}/{tests_total} tests passed")
    print("=" * 80)
    
    if tests_passed == tests_total:
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe Settings scene now correctly:")
        print("  1. Scans for BLE devices in background thread")
        print("  2. Finds both EMGS devices (E2:15:14:6B:66:E9 & EA:5E:82:04:33:79)")
        print("  3. Creates UI buttons for device binding")
        print("  4. Displays scan status and device count")
        print("\nYou should now see EMGS devices in the game Settings panel!")
        return 0
    else:
        print(f"\n⚠️  {tests_total - tests_passed} test(s) failed")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
