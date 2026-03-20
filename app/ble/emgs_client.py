from __future__ import annotations
from typing import Optional, Dict, Any, Callable, List

try:
    # Import type only; avoid hard dependency when reusing the helper standalone
    from .ble_manager import BLEManager, BLEDeviceInfo  # type: ignore
except Exception:  # pragma: no cover
    BLEManager = Any  # type: ignore  # noqa: F401
    BLEDeviceInfo = Any  # type: ignore  # noqa: F401

from .emgs_protocol import (
    EMG_MODE_OFF,
    EMG_MODE_RAW,
    EMG_MODE_RMS,
    ICM_CHANNELS,
    build_get_emg_mode,
    build_get_icm_mode,
    build_icm_control,
    build_set_connection_interval,
    build_set_emg_mode,
    build_set_indicator_led,
    build_set_icm_mode,
    build_set_name,
    build_start_stream,
    build_stop_stream,
    build_time_sync,
    parse_notification,
)

# Nordic UART Service (NUS) characteristics used by EMGS
NUS_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # RX on peripheral (write from central)
NUS_NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # TX on peripheral (notify to central)

__all__ = [
    "NUS_WRITE_UUID",
    "NUS_NOTIFY_UUID",
    "EMG_MODE_OFF",
    "EMG_MODE_RMS",
    "EMG_MODE_RAW",
    "ICM_CHANNELS",
    "build_set_emg_mode",
    "build_start_stream",
    "build_stop_stream",
    "build_get_emg_mode",
    "build_set_icm_mode",
    "build_get_icm_mode",
    "build_time_sync",
    "build_set_name",
    "build_set_connection_interval",
    "build_set_indicator_led",
    "build_icm_control",
    "parse_notification",
    "EMGSClient",
]


class EMGSClient:
    """
    High-level EMGS client wrapper for Nordic UART Service devices.

    - Stores device info and characteristic UUIDs
    - Manages notify subscription and command writes
    - Parses notifications and routes to callbacks

    Intended to be reused across projects and support multiple EMGS devices simultaneously.
    Safe to instantiate one EMGSClient per device using a shared BLEManager.
    """

    def __init__(
        self,
        manager: Any,
        device: Any,
        *,
        write_uuid: str = NUS_WRITE_UUID,
        notify_uuid: str = NUS_NOTIFY_UUID,
        on_emg: Optional[Callable[[int, List[int]], None]] = None,
        on_status: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_notify: Optional[Callable[[Dict[str, Any]], None]] = None,
        battery_low_voltage: Optional[float] = None,
        battery_high_voltage: Optional[float] = None,
    ) -> None:
        self.manager = manager
        self.device = device
        self.address: str = device.address
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid

        # State
        self.streaming: bool = False
        self.emg_mode: Optional[int] = None
        self.last_emg_value: Optional[int] = None
        self.is_connect: bool = False
        self.is_charging: bool = False

        # Parameters
        self.name: Optional[str] = getattr(device, "name", None)
        self.status_text: str = "Disconnected"
        self.timestamp_text: Optional[str] = None
        self.battery_percent: Optional[float] = None
        self.battery_raw: Optional[int] = None
        self.firmware_version: Optional[str] = None
        self.hardware_version: Optional[str] = None
        self.dsp_version: Optional[str] = None
        self.conn_interval_min: Optional[int] = None
        self.conn_interval_max: Optional[int] = None

        # Battery calibration
        self._batt_lo = battery_low_voltage
        self._batt_hi = battery_high_voltage

        # Callbacks
        self._on_emg = on_emg
        self._on_status = on_status
        self._on_notify = on_notify

        self._subscribed: bool = False

        # ICM channel states
        self.icm_mode: List[Dict[str, Any]] = [
            {"channel": ch, "state": False} for ch in ICM_CHANNELS
        ]

    # ---------- Control ----------
    def subscribe(self) -> bool:
        """Start notifications and route to this instance handler."""
        if not self.notify_uuid:
            return False
        ok = self.manager.start_notifications(self.address, self.notify_uuid, self._handle_notify)
        self._subscribed = bool(ok)
        if self._subscribed:
            self.is_connect = True
            self.status_text = "Connected"
            self._emit_status()
        return self._subscribed

    def unsubscribe(self) -> None:
        # BLEManager may not have an explicit stop; re-connect cycles usually reset
        self._subscribed = False
        self.is_connect = False
        self.status_text = "Disconnected"
        self._emit_status()

    def set_emg_mode(self, mode: int) -> bool:
        return self._write(build_set_emg_mode(mode))

    def get_emg_mode(self) -> bool:
        return self._write(build_get_emg_mode())

    def start_stream(self) -> bool:
        self.streaming = True
        return self._write(build_start_stream())

    def stop_stream(self) -> bool:
        self.streaming = False
        return self._write(build_stop_stream())

    def time_sync(self, unix_ms: int) -> bool:
        return self._write(build_time_sync(unix_ms))

    def set_name(self, name: str) -> bool:
        return self._write(build_set_name(name))

    def set_connection_interval(self, interval_ms_min: int, interval_ms_max: int) -> bool:
        return self._write(build_set_connection_interval(interval_ms_min, interval_ms_max))

    def set_icm_enabled(self, device: int, enable: bool) -> bool:
        """Enable/disable a specific ICM channel by index."""
        return self._write(build_icm_control(device, enable))

    def set_icm_mode(self, device_index: int, enable: bool) -> bool:
        return self._write(build_set_icm_mode(device_index, enable))

    def get_icm_mode(self, device_index: int) -> bool:
        return self._write(build_get_icm_mode(device_index))

    def send_raw(self, data: bytes, *, response: bool = False) -> bool:
        """Send raw bytes to the device write characteristic."""
        return self._write(data, response=response)

    # ---------- Info queries (responses via 'A' frames) ----------
    def query_device_info_all(self) -> None:
        """Query various device info pages. Responses will arrive via status callback."""
        for cmd in (b"A0", b"Aa", b"AG", b"AK", b"An"):
            self._write(cmd)

    # ---------- Internal ----------
    def _write(self, data: bytes, *, response: bool = False) -> bool:
        if not self.write_uuid:
            return False
        return bool(self.manager.write_characteristic(self.address, self.write_uuid, data, response=response))

    def _handle_notify(self, payload: bytes) -> None:
        # Runtime dispatch point:
        # - EMG ('E'): forward parsed sample batch to app callback
        # - App helper ('A'): refresh status/metadata fields
        parsed = parse_notification(payload)
        if not parsed:
            return
        pkt_type = parsed.get("type")
        if pkt_type == "E":
            val = int(parsed.get("emg_value", 0))
            self.last_emg_value = val
            samples = parsed.get("emg_samples") or []
            if self._on_emg:
                try:
                    self._on_emg(val, samples)  # first value and full sample list
                except Exception:
                    pass
        elif pkt_type == "A":
            # Decode 'A' app helper response frames
            raw = parsed.get("raw", b"")
            cmd = parsed.get("cmd")
            if not isinstance(raw, (bytes, bytearray)):
                raw = b""

            if cmd == "0":
                self._update_battery_and_charging(raw)
                self._update_fw_hw(raw)
                self._emit_status()
            elif cmd == "3":
                self._update_battery_and_charging(raw)
                self._update_time_sync(raw, offset=5)
                self._emit_status()
            elif cmd == "5":
                self._update_battery_and_charging(raw)
                self.streaming = True
                self._emit_status()
            elif cmd == "7":
                self._update_battery_and_charging(raw)
                self.streaming = False
                self._emit_status()
            elif cmd == "a":
                self._update_battery_and_charging(raw)
                self._update_dsp(raw)
                self._emit_status()
            elif cmd == "G":
                self._update_timestamp(raw, start=3)
                self._emit_status()
            elif cmd == "X":
                if len(raw) >= 5:
                    idx = raw[3]
                    state = (raw[4] == 1)
                    if 0 <= idx < len(self.icm_mode):
                        self.icm_mode[idx]["state"] = state
                self._emit_status()
            elif cmd == "x":
                if len(raw) >= 4:
                    self.emg_mode = raw[3]
                self._emit_status()
            elif cmd == "K":
                name = self._parse_c_string(raw, 3, 15)
                if name:
                    self.name = name
                self._emit_status()
            elif cmd == "n":
                if len(raw) >= 7:
                    self.conn_interval_min = int.from_bytes(raw[3:5], "little", signed=False)
                    self.conn_interval_max = int.from_bytes(raw[5:7], "little", signed=False)
                self._emit_status()
            else:
                self._emit_status()
        # Always fire generic notify if provided
        if self._on_notify:
            try:
                self._on_notify(parsed)
            except Exception:
                pass

        if pkt_type == "C":
            raw = parsed.get("raw", b"")
            if isinstance(raw, (bytes, bytearray)) and len(raw) >= 3:
                self.is_charging = (raw[2] == 1)
                self._emit_status()

    # ---------- Internal helpers for decoding ----------
    def _update_battery_and_charging(self, raw: bytes) -> None:
        if len(raw) >= 5:
            self.battery_raw = int(raw[3])
            if self._batt_lo is not None and self._batt_hi is not None and self._batt_hi > self._batt_lo:
                val = (float(self.battery_raw) - float(self._batt_lo)) / (float(self._batt_hi) - float(self._batt_lo)) * 100.0
                self.battery_percent = max(0.0, min(100.0, val))
            self.is_charging = (raw[4] == 1)

    def _update_fw_hw(self, raw: bytes) -> None:
        if len(raw) >= 9:
            self.firmware_version = f"{raw[5]}.{raw[6]}"
            self.hardware_version = f"{raw[7]}.{raw[8]}"

    def _update_time_sync(self, raw: bytes, offset: int) -> None:
        if len(raw) >= offset + 8:
            ts = int.from_bytes(raw[offset:offset+8], "little", signed=False)
            self.timestamp_text = self._format_ts(ts)

    def _update_dsp(self, raw: bytes) -> None:
        if len(raw) >= 8:
            self.dsp_version = f"{raw[5]}.{raw[6]}.{raw[7]}"

    def _update_timestamp(self, raw: bytes, start: int) -> None:
        if len(raw) >= start + 8:
            ts = int.from_bytes(raw[start:start+8], "little", signed=False)
            self.timestamp_text = self._format_ts(ts)

    def _format_ts(self, ts_ms: int) -> str:
        try:
            import time as _time
            return _time.strftime('%Y-%m-%d %H:%M:%S', _time.localtime(ts_ms / 1000.0))
        except Exception:
            return str(ts_ms)

    def _parse_c_string(self, raw: bytes, start: int, end: int) -> str:
        end = min(len(raw), end)
        out = bytearray()
        for b in raw[start:end]:
            if b == 0:
                break
            out.append(b)
        try:
            return out.decode('utf-8', errors='ignore')
        except Exception:
            return ''

    def _emit_status(self) -> None:
        if not self._on_status:
            return
        snapshot = self.get_status_snapshot()
        try:
            self._on_status(snapshot)
        except Exception:
            pass

    # ---------- Public snapshot ----------
    def get_status_snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "status": self.status_text,
            "timestamp": self.timestamp_text,
            "battery_percent": self.battery_percent,
            "battery_raw": self.battery_raw,
            "firmware_version": self.firmware_version,
            "hardware_version": self.hardware_version,
            "dsp_version": self.dsp_version,
            "conn_interval_min": self.conn_interval_min,
            "conn_interval_max": self.conn_interval_max,
            "is_connect": self.is_connect,
            "is_stream": self.streaming,
            "is_charging": self.is_charging,
            "emg_mode": self.emg_mode,
            "icm_mode": [dict(m) for m in self.icm_mode],
        }
