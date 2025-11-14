#!/usr/bin/env python3
"""
Check what BLEDeviceInfo objects are created in the app
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.ble.ble_manager import BLEManager

def test_ble_device_info():
    """Check BLEDeviceInfo objects returned by BLEManager.scan()"""
    print("=" * 70)
    print("TESTING BLEDeviceInfo CREATION")
    print("=" * 70)
    
    ble = BLEManager(simulation=False)
    
    print("\nScanning...")
    devices = ble.scan(timeout=10.0)
    print(f"Found {len(devices)} devices\n")
    
    # Show all devices
    print("Device names and addresses:")
    for i, d in enumerate(devices, 1):
        print(f"{i:2d}. Name: '{d.name}' | Address: {d.address}")
    
    # Filter EMGS
    emgs = [d for d in devices if d.name and 'EMGS' in d.name]
    print(f"\nEMGS devices (filtered): {len(emgs)}")
    for d in emgs:
        print(f"   {d.name} ({d.address})")
    
    # Check if your addresses are in the list
    your_addrs = {"E2:15:14:6B:66:E9", "EA:5E:82:04:33:79"}
    found = []
    for d in devices:
        if d.address.upper() in {a.upper() for a in your_addrs}:
            found.append(d)
    
    print(f"\nYour devices (by address): {len(found)}")
    for d in found:
        print(f"   {d.name} ({d.address})")
    
    ble.shutdown()

if __name__ == "__main__":
    test_ble_device_info()
