from __future__ import annotations
from typing import Optional, Dict, Any, Callable, List

try:
    # Import type only; avoid hard dependency when reusing the helper standalone
    from .ble_manager import BLEManager, BLEDeviceInfo  # type: ignore
except Exception:  # pragma: no cover
    BLEManager = Any  # type: ignore  # noqa: F401
    BLEDeviceInfo = Any  # type: ignore  # noqa: F401

# Nordic UART Service (NUS) characteristics used by EMGS
NUS_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # RX on peripheral (write from central)
NUS_NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # TX on peripheral (notify to central)

# EMG modes per EMGS reference app
EMG_MODE_OFF = 0
EMG_MODE_RMS = 1
EMG_MODE_RAW = 2

# ICM/IMU channel names (index-based) from reference app
ICM_CHANNELS = [
    "ACC_RAW",   # 0
    "ACC_CAL",   # 1
    "ACC_LIN",   # 2
    "GYR_RAW",   # 3
    "GYR_CAL",   # 4
    "MAG_RAW",   # 5
    "MAG_CAL",   # 6
    "QUAT_VEC",  # 7
    "QUAT_MAG",  # 8
]


def build_set_emg_mode(mode: int) -> bytes:
    """Return command bytes to set EMG mode. 0=OFF, 1=RMS, 2=RAW."""
    mode = int(mode) & 0xFF
    return b"Aw" + bytes([mode])


def build_start_stream() -> bytes:
    """Return command bytes to start streaming."""
    return b"A5"


def build_stop_stream() -> bytes:
    """Return command bytes to stop streaming."""
    return b"A7"


def build_get_emg_mode() -> bytes:
    """Query current EMG mode (response via 'S' 'A' 'x' frame)."""
    return b"Ax"


def build_set_icm_mode(device_index: int, enable: bool) -> bytes:
    """Enable/disable one ICM (IMU) channel: 'AW' + <index:u8> + <enable:u8>."""
    idx = max(0, min(255, int(device_index)))
    return b"AW" + bytes([idx, 1 if enable else 0])


def build_get_icm_mode(device_index: int) -> bytes:
    """Query one ICM channel state (response via 'S' 'A' 'X' frame)."""
    idx = max(0, min(255, int(device_index)))
    return b"AX" + bytes([idx])


def build_time_sync(unix_ms: int) -> bytes:
    """
    Build time sync command. EMGS_v1 uses 'A9' + 8-byte little-endian timestamp (ms).
    """
    ts = int(unix_ms) & 0xFFFFFFFFFFFFFFFF
    return b"A9" + ts.to_bytes(8, "little", signed=False)


def build_set_name(name: str) -> bytes:
    """
    Build device name set command. Reference indicates 'AF' + ASCII name.
    Note: name length limits depend on firmware.
    """
    return b"AF" + name.encode("utf-8")


def build_set_connection_interval(interval_ms_min: int, interval_ms_max: int) -> bytes:
    """Set BLE connection interval (hinted as 'Am' + u16 ms)."""
    iv_min = max(6, min(3200, int(interval_ms_min)))  # 7.5ms..4000ms typical; clamp conservatively
    iv_max = max(6, min(3200, int(interval_ms_max)))  # 7.5ms..4000ms typical; clamp conservatively
    return b"Am" + iv_min.to_bytes(2, "little", signed=False) + iv_max.to_bytes(2, "little", signed=False)


def build_set_indicator_led(state: str) -> bytes:
    """
    Set EMGS RGB indicator LED via 'Ar' command.

    Known stable states from reference tools:
      - off, blue, yellow, purple
    We map red -> yellow as a close supported alternative for role coloring.
    """
    key = str(state or "").strip().lower()
    if key == "red":
        key = "yellow"
    rgb_code = {
        "off": 0x00,
        "blue": 0x09,
        "yellow": 0x11,
        "purple": 0x19,
    }
    # Fallback to off for unknown inputs
    code = rgb_code.get(key, 0x00)
    return b"Ar" + bytes([0, code])


def build_icm_control(device_index: int, enable: bool) -> bytes:
    """Backward-compatible alias for build_set_icm_mode()."""
    return build_set_icm_mode(device_index, enable)


def parse_notification(payload: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse a single EMGS notification.
    Expected framing (per EMGS app):
      - payload[0] == ord('S') header
      - payload[1] == packet type: 'A','C','E','I', etc.
    Returns a dict like { 'type': 'A'|'C'|'E'|'I', ... } or None if unrecognized.

    NOTE: The exact EMG ('E') packet format isn't defined here; we provide a pragmatic fallback:
      - If len>=4, interpret payload[2:4] as little-endian uint16 'value'.
      - Caller can scale/normalize as needed.
    """
    if not payload or len(payload) < 2:
        return None

    # Fallback: some firmware variants send raw EMG u16 stream without the 'S' framing.
    # Interpret compact even-length payloads as big-endian sample codes.
    if payload[0:1] != b"S":
        if len(payload) >= 4 and len(payload) % 2 == 0:
            emg_codes: List[int] = []
            for i in range(0, len(payload), 2):
                emg_codes.append(int.from_bytes(payload[i:i+2], "big", signed=False))
            if emg_codes:
                return {
                    "type": "E",
                    "raw": payload,
                    "emg_value": emg_codes[0],
                    "emg_samples": emg_codes,
                    "emg_codes": emg_codes,
                }
        return None

    pkt_type = chr(payload[1])
    out: Dict[str, Any] = {"type": pkt_type, "raw": payload}

    if pkt_type == "C":  # charging status
        if len(payload) >= 3:
            out["charging"] = (payload[2] == 1)
        return out

    if pkt_type == "A":  # app helper
        if len(payload) >= 3:
            out["cmd"] = chr(payload[2])
        # Additional fields can be decoded on demand
        return out

    if pkt_type == "E":  # EMG data (rich format per EMGS_v1)
        # Expected layout (indexes from EMGS_v1 app.py):
        # [2]=len, [3]=battery, [4]=charge, [5:7]=packet_id(le), [7:15]=timestamp(le,u64),
        # [15]=mode/freq, [16]=snr, [17:19]=rms(be,u16), [19:]=samples(be,u16...)
        data = payload
        n = len(data)
        if n >= 19:
            datalen = data[2]
            batt = data[3]
            charge_state = (data[4] == 1)
            packet_id = int.from_bytes(data[5:7], "little", signed=False)
            timestamp_ms = int.from_bytes(data[7:15], "little", signed=False)
            mode_pos = data[15]
            snr = data[16]
            rms_raw = int.from_bytes(data[17:19], "big", signed=False)
            # Remaining samples are big-endian u16 codes
            emg_codes: List[int] = []
            for i in range(19, n - ((n - 19) % 2), 2):
                emg_codes.append(int.from_bytes(data[i:i+2], "big", signed=False))
            # Scale to mV (per EMGS_v1): ((code/65535*3.0 - 1.5)/1200.0) * 1000
            emg_mv: List[float] = [((c / 65535.0 * 3.0 - 1.5) / 1200.0) * 1000.0 for c in emg_codes]
            out.update({
                "battery_raw": batt,
                "charging": charge_state,
                "packet_id": packet_id,
                "timestamp_ms": timestamp_ms,
                "mode_pos": mode_pos,
                "snr": snr,
                "rms_raw": rms_raw,
                "emg_codes": emg_codes,
                "emg_mv": emg_mv,
            })
            if emg_codes:
                out["emg_value"] = emg_codes[0]
                out["emg_samples"] = emg_codes
        return out

    if pkt_type == "I":  # IMU data
        # [2]=len, [3:5]=packet_id(le,u16), [5]=sensor_type, [6:14]=timestamp(le,u64), [14]=fs,
        # [15:]=float32 little-endian values (x,y,z repeating)
        data = payload
        n = len(data)
        if n >= 15:
            datalen = data[2]
            packet_id = int.from_bytes(data[3:5], "little", signed=False)
            sensor_type = data[5]
            timestamp_ms = int.from_bytes(data[6:14], "little", signed=False)
            sampling_freq = data[14]
            # Remaining floats
            payload_floats_len = n - 15
            readings: List[float] = []
            # 4 bytes per float, little-endian
            for i in range(0, payload_floats_len - (payload_floats_len % 4), 4):
                b = data[15 + i: 15 + i + 4]
                # manual little-endian float decode to avoid struct import overhead
                import struct as _struct
                readings.append(_struct.unpack('<f', b)[0])
            out.update({
                "packet_id": packet_id,
                "timestamp_ms": timestamp_ms,
                "sensor_type": sensor_type,  # 1=ACC,4=GYR,6=MAG
                "sampling_freq": sampling_freq,
                "imu_readings": readings,
            })
        return out

    # Others: return minimal info
    return out


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
