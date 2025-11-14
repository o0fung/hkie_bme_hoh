#!/usr/bin/env python3
"""
Comprehensive diagnostic to check BLE setup and identify why scan might find 0 devices.
"""

import sys
import os
import json

# Force UTF-8 output for Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 80)
print("BLE DEVICE DISCOVERY DIAGNOSTIC")
print("=" * 80)

# Check 1: Configuration
print("\n[CHECK 1] Configuration Files")
print("-" * 80)

configs_to_check = ["config/devices.json", "config/devices.sample.json"]
for cfg_file in configs_to_check:
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file) as f:
                cfg = json.load(f)
            sim = cfg.get("simulation", "NOT SET")
            print(f"✓ {cfg_file} exists")
            print(f"  - simulation: {sim}")
            if not sim:
                emg_l = cfg.get("emg_left", {}).get("mac_address", "NOT SET")
                emg_r = cfg.get("emg_right", {}).get("mac_address", "NOT SET")
                print(f"  - EMG Left MAC: {emg_l}")
                print(f"  - EMG Right MAC: {emg_r}")
        except Exception as e:
            print(f"✗ {cfg_file}: Error reading - {e}")
    else:
        print(f"✗ {cfg_file} does NOT exist")

# Check 2: Python environment
print("\n[CHECK 2] Python Environment")
print("-" * 80)

try:
    import bleak
    print(f"✓ Bleak is installed")
except ImportError as e:
    print(f"✗ Bleak NOT installed: {e}")
    print(f"  Run: pip install bleak")

try:
    import pygame
    print(f"✓ Pygame is installed: {pygame.version.ver}")
except ImportError as e:
    print(f"✗ Pygame NOT installed: {e}")

# Check 3: BLEManager initialization
print("\n[CHECK 3] BLEManager Initialization")
print("-" * 80)

try:
    from src.ble.ble_manager import BLEManager, BLEAK_AVAILABLE
    
    print(f"✓ BLEManager imported successfully")
    print(f"  - BLEAK_AVAILABLE: {BLEAK_AVAILABLE}")
    
    # Create manager with simulation OFF
    ble = BLEManager(simulation=False)
    print(f"✓ BLEManager created (simulation=False)")
    print(f"  - Event loop running: {ble._loop is not None}")
    print(f"  - Simulation mode: {ble.simulation}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check 4: Quick scan test
print("\n[CHECK 4] BLE Scan Test (5 second timeout)")
print("-" * 80)

try:
    devices = ble.scan(timeout=5.0)
    print(f"✓ Scan completed")
    print(f"  - Total devices found: {len(devices)}")
    
    # Count EMGS devices
    emgs_devices = [d for d in devices if d.name and 'EMGS' in d.name]
    print(f"  - EMGS devices found: {len(emgs_devices)}")
    
    if len(emgs_devices) > 0:
        print(f"\n  EMGS Devices:")
        for d in emgs_devices:
            print(f"    • {d.name} ({d.address})")
    else:
        print(f"\n  ⚠️  No EMGS devices found!")
        print(f"  First 5 devices found:")
        for i, d in enumerate(devices[:5], 1):
            print(f"    {i}. {d.name} ({d.address})")
    
    if len(devices) == 0:
        print(f"\n  ⚠️  SCAN RETURNED 0 DEVICES!")
        print(f"  This could mean:")
        print(f"    1. Windows Bluetooth is disabled")
        print(f"    2. No BLE devices are advertising")
        print(f"    3. EMGS devices are powered off")
        print(f"    4. Windows driver issues")
        print(f"\n  Troubleshooting:")
        print(f"    - Check Settings > Bluetooth > is it ON?")
        print(f"    - Power cycle the EMGS devices")
        print(f"    - Check Device Manager for Bluetooth issues")
        print(f"    - Try: python -m bleak.backends.winrt")
    
except Exception as e:
    print(f"✗ Scan failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check 5: SettingsScene test
print("\n[CHECK 5] SettingsScene Integration")
print("-" * 80)

try:
    import pygame
    pygame.init()
    pygame.display.set_mode((800, 600))
    
    from src.game.scenes import SettingsScene
    
    screen = pygame.display.get_surface()
    screen_rect = screen.get_rect()
    
    def dummy(*args, **kwargs):
        pass
    
    settings = SettingsScene(
        screen_rect=screen_rect,
        ble=ble,
        on_close=dummy,
        set_emg_max=dummy,
        set_threshold_percent=dummy,
        set_countdown_seconds=dummy,
        set_target_close_percent=dummy,
        on_bind_left_emg=dummy,
        on_bind_right_emg=dummy,
        on_bind_left_exo=dummy,
        on_bind_right_exo=dummy,
        init_values={},
    )
    
    print(f"✓ SettingsScene created")
    print(f"  - ble.simulation: {settings.ble.simulation}")
    
except Exception as e:
    print(f"✗ SettingsScene creation failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
ble.shutdown()

# Summary
print("\n" + "=" * 80)
print("DIAGNOSTIC SUMMARY")
print("=" * 80)

if len(devices) == 0:
    print("\n⚠️  ISSUE IDENTIFIED: Scan returned 0 devices")
    print("\nLikely causes:")
    print("  1. Windows Bluetooth disabled - Enable in Settings")
    print("  2. EMGS devices not powered on - Turn them on")
    print("  3. EMGS devices out of range - Move closer")
    print("  4. Windows driver issue - Check Device Manager")
    print("\nNext steps:")
    print("  1. Verify Settings > Bluetooth > Status is ON")
    print("  2. Power cycle the EMGS devices")
    print("  3. Run this diagnostic again")
    print("  4. If still 0 devices, check Windows Event Viewer for Bluetooth errors")
elif len(emgs_devices) == 0:
    print("\n⚠️  ISSUE IDENTIFIED: BLE scan works, but no EMGS devices found")
    print(f"\nFound {len(devices)} other devices, which means Bluetooth is working.")
    print("The EMGS devices may not be advertising correctly.")
    print("\nNext steps:")
    print("  1. Check EMGS device power and status")
    print("  2. Check EMGS device firmware version")
    print("  3. Try manually scanning with: nrfConnect or similar BLE scanner")
    print("  4. Verify EMGS devices are in pairing mode if needed")
else:
    print("\n✅ EVERYTHING LOOKS GOOD!")
    print(f"\n✓ Found {len(emgs_devices)} EMGS device(s) out of {len(devices)} total devices")
    print(f"✓ BLE scanning is working correctly")
    print(f"✓ Ready to run: python main.py")
