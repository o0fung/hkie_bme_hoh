#!/usr/bin/env python3
"""
Quick validation that main.py will initialize correctly with the BLE fixes.
"""

import sys
import os

print("=" * 70)
print("VALIDATING main.py INITIALIZATION")
print("=" * 70)

# Check configuration
print("\n1. Checking config/devices.sample.json...")
import json

config_path = "config/devices.sample.json"
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    simulation = config.get("simulation", False)
    emg_left = config.get("emg_left", {})
    emg_right = config.get("emg_right", {})
    
    print(f"   ✓ Config loaded")
    print(f"     - Simulation: {'ON' if simulation else 'OFF'}")
    print(f"     - EMG Left MAC: {emg_left.get('mac_address', 'NOT SET')}")
    print(f"     - EMG Right MAC: {emg_right.get('mac_address', 'NOT SET')}")
    
    if not simulation:
        print(f"   ✅ Simulation DISABLED - will use real devices")
    else:
        print(f"   ⚠️  Simulation ENABLED - set to false to use real devices")
        
except Exception as e:
    print(f"   ❌ Error loading config: {e}")
    sys.exit(1)

# Check BLE manager
print("\n2. Checking BLEManager...")
try:
    from src.ble.ble_manager import BLEManager
    
    # Create manager with simulation disabled
    ble = BLEManager(simulation=False)
    print(f"   ✓ BLEManager created")
    print(f"     - Event loop running: {ble._loop is not None}")
    print(f"     - Simulation mode: {ble.simulation}")
    
    # Quick test scan
    print(f"\n3. Testing scan() method...")
    print(f"   Scanning for devices (timeout 5s)...")
    devices = ble.scan(timeout=5.0)
    print(f"   ✓ Scan completed")
    print(f"     - Total devices: {len(devices)}")
    
    emgs_count = len([d for d in devices if d.name and 'EMGS' in d.name])
    print(f"     - EMGS devices: {emgs_count}")
    
    if emgs_count >= 2:
        print(f"   ✅ Both EMGS devices found!")
    elif emgs_count == 1:
        print(f"   ⚠️  Only 1 EMGS device found (expecting 2)")
    else:
        print(f"   ⚠️  No EMGS devices found (check if they're powered on)")
    
    # Cleanup
    ble.shutdown()
    print(f"   ✓ BLEManager shutdown")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check pygame imports
print("\n4. Checking pygame and game imports...")
try:
    import pygame
    from src.game.scenes import SettingsScene, GameScene
    from src.ui.widgets import Button
    
    print(f"   ✓ All imports successful")
    print(f"     - pygame version: {pygame.version.ver}")
    
except Exception as e:
    print(f"   ❌ Import error: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ ALL CHECKS PASSED - Ready to run main.py")
print("=" * 70)
print("\nTo start the game:")
print("  python main.py")
print("\nThen:")
print("  1. Click 'Settings' button")
print("  2. Click 'Scan BLE'")
print("  3. Wait ~10 seconds")
print("  4. You should see both EMGS devices appear")
