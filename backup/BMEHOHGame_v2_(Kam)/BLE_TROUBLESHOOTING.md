# BLE Device Discovery Troubleshooting

## Status: ✅ Event Loop Fixed
The BLE manager is now properly initialized with the event loop running.

## Issue: ❌ No Devices Found
Even though scanning works, your two EMGS devices are not being discovered. Here are Windows-specific troubleshooting steps:

---

## 1. Check Bluetooth is Enabled on Your Computer

### Windows Settings:
```
Settings > Devices > Bluetooth & devices > Bluetooth > ON
```

Make sure the toggle is **ON** and shows "Bluetooth is on"

---

## 2. Check Device Manager for Bluetooth Devices

### Steps:
1. Press `Win + X` → Device Manager
2. Expand **"Bluetooth"** section
3. Your EMGS devices should appear here when powered on
4. Look for unknown devices or warnings (yellow exclamation marks)

### What to look for:
- Device name like "EMGS" or similar
- MAC address matching your config (E2:15:14:6B:66:E9, EA:5E:82:04:33:79)
- Status should be "Connected" or "Paired" ideally

---

## 3. Power Cycle EMGS Devices

1. **Power OFF** the EMGS devices
2. Wait 5 seconds
3. **Power ON** the EMGS devices
4. Wait for them to advertise (usually 2-3 seconds)
5. Run the scan again

---

## 4. Bring Devices Closer

- Bring devices within **1-2 meters** of the computer
- Remove any obstacles between devices and computer
- Avoid interference from:
  - WiFi routers
  - Microwaves
  - USB 3.0 devices (can interfere with 2.4GHz Bluetooth)

---

## 5. Check Device Bluetooth Mode

Your EMGS devices should be in **"advertising" or "discoverable" mode**, NOT in "paired/connected" mode.

If they were previously paired with another device:
1. Unpair them from the other device first
2. Or reset them to factory defaults (check your device manual)

---

## 6. Check Bluetooth Driver on Windows

Sometimes the Bluetooth driver needs updating:

1. Go to **Device Manager** (Win + X)
2. Expand **"Bluetooth"**
3. Right-click your Bluetooth adapter
4. Select **"Update driver"**
5. Choose **"Search automatically for updated driver software"**

---

## 7. Test with Windows Settings

Try pairing with Windows Bluetooth settings first to verify devices are discoverable:

1. Open **Settings** > **Devices** > **Bluetooth & devices**
2. Click **"Add device"** > **"Bluetooth"**
3. Wait for device list to appear
4. Your EMGS devices should show up in the list

If they appear here, the devices are working and in advertising mode.

---

## 8. Check MAC Addresses in Config

Verify the MAC addresses in `config/devices.sample.json` match your actual devices:

```json
"emg_left": {
  "name": "EMGS",
  "mac_address": "E2:15:14:6B:66:E9",
  ...
},
"emg_right": {
  "name": "EMGS",
  "mac_address": "EA:5E:82:04:33:79",
  ...
}
```

You can find the actual MAC address on your device or by checking **Device Manager** > **Bluetooth** > right-click device > **Properties** > **Details** tab.

---

## 9. Run the Diagnostic Again

Once you've tried the above steps, run:

```powershell
python test_ble_discovery.py
```

This will tell you if devices are now discoverable.

---

## 10. Check for Bluetooth Interference

Windows may have multiple Bluetooth adapters or may be scanning different frequencies. Try:

1. Disable WiFi temporarily (to avoid 2.4GHz interference)
2. Run the scan again
3. Re-enable WiFi

---

## Advanced: Enable Bluetooth Verbose Logging

If still not working, enable Windows Bluetooth logging:

```powershell
# Run as Administrator
Get-NetAdapter -Physical | Where-Object { $_.PhysicalMediaType -eq "Native 802.11" }
```

Or check **Event Viewer**:
1. Press `Win + R` → type `eventvwr.msc`
2. Navigate to **Windows Logs** > **System**
3. Look for Bluetooth-related errors

---

## If Devices Still Don't Appear

Please provide:
1. Output of `python test_ble_discovery.py`
2. Device Manager screenshot showing Bluetooth devices
3. Actual MAC addresses of your EMGS devices
4. Whether devices appear in Windows "Add device" dialog

This will help diagnose if it's a hardware issue or configuration problem.
