#!/usr/bin/env python3
"""
Debug script to test the game app's BLE scan directly.
This mimics what happens in the Settings scene.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.ble.ble_manager import BLEManager

def test_app_ble_scan():
    """Test the exact scan that the app uses."""
    print("\n" + "=" * 70)
    print("TESTING APP'S BLE SCAN (Like Settings scene does)")
    print("=" * 70)
    
    # Initialize BLEManager the same way the app does
    print("\n1. Initializing BLEManager with simulation=False...")
    ble = BLEManager(simulation=False)
    print(f"   ✓ BLE Manager created")
    print(f"   - Simulation mode: {ble.simulation}")
    print(f"   - Event loop: {ble._loop is not None}")
    print(f"   - Background thread: {ble._thread is not None}")
    
    # Test with 4 second timeout (original)
    print("\n2. Scanning with 4 second timeout (original)...")
    try:
        devices_4s = ble.scan(timeout=4.0)
        print(f"   ✓ Scan completed")
        print(f"   - Devices found: {len(devices_4s)}")
        for d in devices_4s:
            print(f"     • {d.name} ({d.address})")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        devices_4s = []
    
    # Test with 10 second timeout (updated)
    print("\n3. Scanning with 10 second timeout (updated)...")
    try:
        devices_10s = ble.scan(timeout=10.0)
        print(f"   ✓ Scan completed")
        print(f"   - Devices found: {len(devices_10s)}")
        for d in devices_10s:
            print(f"     • {d.name} ({d.address})")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        devices_10s = []
    
    ble.shutdown()
    
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    
    if len(devices_4s) == 0 and len(devices_10s) == 0:
        print("❌ PROBLEM: No devices found with either timeout")
        print("   This suggests the BLEManager.scan() method is not working correctly")
        return False
    elif len(devices_4s) == 0 and len(devices_10s) > 0:
        print("✓ ISSUE FIXED: 10s timeout now finds devices (was 4s)")
        return True
    elif len(devices_4s) > 0:
        print("✓ Devices found with both timeouts")
        return True


if __name__ == "__main__":
    success = test_app_ble_scan()
    sys.exit(0 if success else 1)
