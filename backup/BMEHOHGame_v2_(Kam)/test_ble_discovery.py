#!/usr/bin/env python3
"""
Diagnostic script to troubleshoot BLE device discovery issues.
Run: python test_ble_discovery.py
"""

import sys
import os
import asyncio
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from src.ble.ble_manager import BLEManager, BleakScanner

def test_bleak_available():
    """Check if bleak is installed and available."""
    print("=" * 60)
    print("1. Testing Bleak Installation")
    print("=" * 60)
    
    if BleakScanner is None:
        print("❌ FAIL: BleakScanner is None - bleak not installed or not supported")
        return False
    
    print(f"✅ PASS: BleakScanner available: {BleakScanner}")
    return True


def test_config_simulation():
    """Check if simulation mode is disabled in config."""
    print("\n" + "=" * 60)
    print("2. Testing Config Simulation Setting")
    print("=" * 60)
    
    config_path = Path(__file__).parent / "config" / "devices.sample.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    
    simulation = config.get("simulation", True)
    print(f"Config simulation setting: {simulation}")
    
    if simulation:
        print("❌ FAIL: Simulation is enabled in config - real scanning is disabled")
        return False
    
    print("✅ PASS: Simulation is disabled - real scanning should work")
    return True


def test_ble_manager_init():
    """Test BLEManager initialization in real mode."""
    print("\n" + "=" * 60)
    print("3. Testing BLEManager Initialization")
    print("=" * 60)
    
    ble = BLEManager(simulation=False)
    print(f"BLE simulation mode: {ble.simulation}")
    print(f"Event loop created: {ble._loop is not None}")
    print(f"Background thread started: {ble._thread is not None and ble._thread.is_alive()}")
    
    if ble.simulation:
        print("❌ FAIL: BLEManager is in simulation mode")
        return False
    
    if not ble._loop or not ble._thread:
        print("❌ FAIL: Event loop or thread not initialized")
        ble.shutdown()
        return False
    
    print("✅ PASS: BLEManager properly initialized in real mode")
    return ble


async def test_bleak_scanner_direct():
    """Test BleakScanner directly without BLEManager."""
    print("\n" + "=" * 60)
    print("4. Testing BleakScanner Directly (Direct Async)")
    print("=" * 60)
    
    if BleakScanner is None:
        print("❌ SKIP: BleakScanner not available")
        return []
    
    try:
        print("Scanning for 5 seconds (direct bleak call)...")
        devices = await BleakScanner.discover(timeout=5.0)
        print(f"✅ PASS: Found {len(devices)} device(s)")
        for d in devices:
            print(f"   - {d.name:30s} {d.address}")
        return devices
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return []


def test_ble_manager_scan(ble):
    """Test BLEManager.scan() method."""
    print("\n" + "=" * 60)
    print("5. Testing BLEManager.scan() Method")
    print("=" * 60)
    
    try:
        print("Scanning for 5 seconds (via BLEManager)...")
        devices = ble.scan(timeout=5.0)
        print(f"✅ PASS: Found {len(devices)} device(s)")
        for d in devices:
            print(f"   - {d.name:30s} {d.address}")
        return devices
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return []


def check_expected_devices(devices):
    """Check if expected EMGS devices were found."""
    print("\n" + "=" * 60)
    print("6. Checking for Expected EMGS Devices")
    print("=" * 60)
    
    config_path = Path(__file__).parent / "config" / "devices.sample.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    
    emg_left_addr = config.get("emg_left", {}).get("mac_address", "").upper()
    emg_right_addr = config.get("emg_right", {}).get("mac_address", "").upper()
    
    print(f"Expected EMG Left:  {emg_left_addr}")
    print(f"Expected EMG Right: {emg_right_addr}")
    
    found_addrs = {d.address.upper() for d in devices}
    
    if emg_left_addr in found_addrs:
        print(f"✅ Found EMG Left device")
    else:
        print(f"❌ EMG Left device NOT found")
    
    if emg_right_addr in found_addrs:
        print(f"✅ Found EMG Right device")
    else:
        print(f"❌ EMG Right device NOT found")


def main():
    """Run all diagnostic tests."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "BLE DEVICE DISCOVERY DIAGNOSTIC" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # Test 1: Bleak availability
    if not test_bleak_available():
        print("\n❌ Cannot proceed - Bleak not available. Install with: pip install bleak")
        return 1
    
    # Test 2: Config simulation setting
    if not test_config_simulation():
        print("\n❌ Cannot proceed - Simulation mode is enabled")
        return 1
    
    # Test 3: BLEManager init
    ble = test_ble_manager_init()
    if not ble:
        return 1
    
    # Test 4: Direct BleakScanner test
    print("\nRunning direct BleakScanner async test...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        devices_direct = loop.run_until_complete(test_bleak_scanner_direct())
        loop.close()
    except Exception as e:
        print(f"❌ Error running async test: {e}")
        devices_direct = []
    
    # Test 5: BLEManager scan test
    devices_ble = test_ble_manager_scan(ble)
    
    # Test 6: Check for expected devices
    all_devices = devices_direct if devices_direct else devices_ble
    if all_devices:
        check_expected_devices(all_devices)
    
    ble.shutdown()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_devices:
        print(f"✅ Device discovery working! Found {len(all_devices)} device(s)")
        return 0
    else:
        print("❌ No devices found. Troubleshooting tips:")
        print("   1. Ensure Bluetooth is enabled on this computer")
        print("   2. Power on the EMGS devices")
        print("   3. Bring devices closer (within 10 meters)")
        print("   4. Check device MAC addresses in config/devices.sample.json")
        print("   5. Try pairing devices with OS Bluetooth settings first")
        print("   6. On Windows: Check Device Manager for unknown Bluetooth devices")
        print("   7. On macOS: Grant Bluetooth permission in System Settings")
        print("   8. On Linux: Run 'bluetoothctl' and check 'scan on'")
        return 1


if __name__ == "__main__":
    sys.exit(main())
