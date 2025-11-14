#!/usr/bin/env python3
"""
Check what the actual EMGS device names are in the raw scan
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

from bleak import BleakScanner

async def check_device_names():
    """Find devices and show their actual names."""
    print("Scanning for 10 seconds to find your EMGS devices...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    target_addrs = [
        "E2:15:14:6B:66:E9",
        "EA:5E:82:04:33:79"
    ]
    
    print("\nLooking for your EMGS devices:\n")
    for addr in target_addrs:
        matching = [d for d in devices if d.address.upper() == addr.upper()]
        if matching:
            d = matching[0]
            print(f"✅ Found {addr}")
            print(f"   Name: {d.name}")
            print(f"   Name repr: {repr(d.name)}")
            print(f"   Name is None: {d.name is None}")
            print(f"   Name type: {type(d.name)}")
        else:
            print(f"❌ NOT found {addr}")
    
    print(f"\n\nAll devices with their names:")
    for d in devices:
        if d.name:
            print(f"  {d.name:40s} {d.address}")

if __name__ == "__main__":
    asyncio.run(check_device_names())
