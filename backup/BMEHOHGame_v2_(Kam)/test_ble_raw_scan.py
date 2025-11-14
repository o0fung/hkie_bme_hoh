#!/usr/bin/env python3
"""
Advanced BLE scanning diagnostic to detect all nearby BLE devices,
including those not in any pairing list.
Run: python test_ble_raw_scan.py
"""

import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

try:
    from bleak import BleakScanner
except ImportError:
    print("ERROR: bleak not installed. Run: pip install bleak")
    sys.exit(1)


async def raw_scan():
    """Scan for ALL BLE devices without any filtering."""
    print("\n" + "=" * 70)
    print("RAW BLE SCAN - ALL NEARBY DEVICES")
    print("=" * 70)
    print("Scanning for 10 seconds... Please wait...\n")
    
    try:
        devices = await BleakScanner.discover(timeout=10.0)
        
        if not devices:
            print("❌ No devices found during 10-second scan.")
            print("\nPossible reasons:")
            print("  1. Bluetooth adapter disabled on this computer")
            print("  2. No BLE devices advertising in range")
            print("  3. Devices are in pairing/connected mode, not advertising mode")
            print("  4. Bluetooth driver issue on Windows")
            return
        
        print(f"✅ Found {len(devices)} BLE device(s):\n")
        
        for i, device in enumerate(devices, 1):
            print(f"{i}. Device: {device.name or 'Unknown'}")
            print(f"   MAC Address: {device.address}")
            print(f"   RSSI: {device.rssi} dBm")
            print(f"   Metadata: {device.metadata if hasattr(device, 'metadata') else 'N/A'}")
            print()
        
        # Check for your specific devices
        print("=" * 70)
        print("CHECKING FOR YOUR EMGS DEVICES")
        print("=" * 70)
        
        emgs_left_addr = "E2:15:14:6B:66:E9".lower()
        emgs_right_addr = "EA:5E:82:04:33:79".lower()
        
        found_left = False
        found_right = False
        
        for device in devices:
            dev_addr = device.address.lower()
            if dev_addr == emgs_left_addr:
                print(f"✅ Found EMG Left: {device.name} ({device.address}) RSSI: {device.rssi} dBm")
                found_left = True
            elif dev_addr == emgs_right_addr:
                print(f"✅ Found EMG Right: {device.name} ({device.address}) RSSI: {device.rssi} dBm")
                found_right = True
        
        if not found_left:
            print(f"❌ EMG Left NOT found (expected: {emgs_left_addr})")
        if not found_right:
            print(f"❌ EMG Right NOT found (expected: {emgs_right_addr})")
        
        if found_left and found_right:
            print("\n🎉 Both EMGS devices found! Ready to connect.")
        elif found_left or found_right:
            print("\n⚠️  Only one EMGS device found. Check the other device.")
        else:
            print("\n❌ Neither EMGS device found. See troubleshooting below.")
        
    except Exception as e:
        print(f"❌ Scan failed with error: {e}")
        import traceback
        traceback.print_exc()


def print_troubleshooting():
    """Print troubleshooting tips."""
    print("\n" + "=" * 70)
    print("TROUBLESHOOTING")
    print("=" * 70)
    
    print("""
1. DEVICE NOT ADVERTISING:
   - Ensure devices are powered ON
   - Check if they have a "Pairing Mode" button - press it to enter advertising mode
   - Some devices only advertise when not connected to another device
   - Check device manual for how to enter advertising/discoverable mode

2. DEVICE IN PAIRED/CONNECTED MODE:
   - If device is paired with another device (phone/computer), disconnect it first
   - The device must be in "advertising" or "discoverable" state, NOT connected
   - You may need to reset the device or unpair from other devices

3. RSSI TOO WEAK:
   - Devices are too far away (RSSI around -80 or weaker = out of range)
   - Move devices closer (within 1-2 meters)
   - Reduce Bluetooth interference (move away from WiFi router, microwaves)

4. WINDOWS BLUETOOTH ADAPTER ISSUE:
   - Check Device Manager > Bluetooth adapter status
   - Try disabling/re-enabling Bluetooth in Windows Settings
   - Update Bluetooth driver to latest version

5. VERIFY DEVICE ADDRESSING:
   - Check the actual MAC address label on your device
   - It may not be E2:15:14:6B:66:E9 and EA:5E:82:04:33:79
   - Update config/devices.sample.json with correct addresses if different

6. DEVICE NAME VERIFICATION:
   - Some devices advertise with specific names (e.g., "EMGS", "EMG-L", etc.)
   - Check what name appears in the scan results above
   - You may need to update the "name" field in config if different

7. FORCE DISCOVERY MODE ON DEVICE:
   - Hold power button for 3+ seconds to reset device state
   - Enter pairing/discovery mode per device manual
   - Some devices auto-advertise for only 60 seconds after power-on

8. TEST WITH WINDOWS SETTINGS:
   - Settings > Devices > Bluetooth & devices > "Add device" > "Bluetooth"
   - If your devices appear there, they're in advertising mode
   - If they DON'T appear in Windows scan, they're NOT advertising
""")


def main():
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "RAW BLE DEVICE DISCOVERY SCANNER" + " " * 21 + "║")
    print("╚" + "=" * 68 + "╝")
    
    print("\nThis scanner will find ALL BLE devices in range, not just paired ones.")
    print("It does NOT require Windows pairing or any configuration.\n")
    
    try:
        asyncio.run(raw_scan())
    except KeyboardInterrupt:
        print("\n\n⏹️  Scan interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print_troubleshooting()
    
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
1. Make sure both EMGS devices are powered ON
2. Put them in advertising/discovery mode (see manual or press pairing button)
3. Bring them within 1-2 meters of this computer
4. Run this scan again
5. If devices appear, update config/devices.sample.json with correct MAC addresses
6. Then run: python main.py
7. Click "Scan BLE" in the Settings panel - your devices should appear
""")


if __name__ == "__main__":
    main()
