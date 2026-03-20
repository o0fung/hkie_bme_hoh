from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    code = rgb_code.get(key, 0x00)
    return b"Ar" + bytes([0, code])


def build_icm_control(device_index: int, enable: bool) -> bytes:
    """Alias for build_set_icm_mode()."""
    return build_set_icm_mode(device_index, enable)


def parse_notification(payload: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse a single EMGS notification to a structured payload.

    This module is the protocol boundary between BLE byte streams and higher-level
    app logic, so parsing is intentionally defensive against firmware variants.
    """
    if not payload or len(payload) < 2:
        return None

    # Fallback path for non-framed firmware: treat payload as big-endian u16 stream.
    if payload[0:1] != b"S":
        if len(payload) >= 4 and len(payload) % 2 == 0:
            emg_codes: List[int] = []
            for i in range(0, len(payload), 2):
                emg_codes.append(int.from_bytes(payload[i : i + 2], "big", signed=False))
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
            out["charging"] = payload[2] == 1
        return out

    if pkt_type == "A":  # app helper
        if len(payload) >= 3:
            out["cmd"] = chr(payload[2])
        return out

    if pkt_type == "E":  # EMG data (rich format per EMGS_v1)
        data = payload
        n = len(data)
        if n >= 19:
            batt = data[3]
            charge_state = data[4] == 1
            packet_id = int.from_bytes(data[5:7], "little", signed=False)
            timestamp_ms = int.from_bytes(data[7:15], "little", signed=False)
            mode_pos = data[15]
            snr = data[16]
            rms_raw = int.from_bytes(data[17:19], "big", signed=False)
            emg_codes: List[int] = []
            for i in range(19, n - ((n - 19) % 2), 2):
                emg_codes.append(int.from_bytes(data[i : i + 2], "big", signed=False))
            emg_mv: List[float] = [((c / 65535.0 * 3.0 - 1.5) / 1200.0) * 1000.0 for c in emg_codes]
            out.update(
                {
                    "battery_raw": batt,
                    "charging": charge_state,
                    "packet_id": packet_id,
                    "timestamp_ms": timestamp_ms,
                    "mode_pos": mode_pos,
                    "snr": snr,
                    "rms_raw": rms_raw,
                    "emg_codes": emg_codes,
                    "emg_mv": emg_mv,
                }
            )
            if emg_codes:
                out["emg_value"] = emg_codes[0]
                out["emg_samples"] = emg_codes
        return out

    if pkt_type == "I":  # IMU data
        data = payload
        n = len(data)
        if n >= 15:
            packet_id = int.from_bytes(data[3:5], "little", signed=False)
            sensor_type = data[5]
            timestamp_ms = int.from_bytes(data[6:14], "little", signed=False)
            sampling_freq = data[14]
            payload_floats_len = n - 15
            readings: List[float] = []
            for i in range(0, payload_floats_len - (payload_floats_len % 4), 4):
                b = data[15 + i : 15 + i + 4]
                import struct as _struct

                readings.append(_struct.unpack("<f", b)[0])
            out.update(
                {
                    "packet_id": packet_id,
                    "timestamp_ms": timestamp_ms,
                    "sensor_type": sensor_type,
                    "sampling_freq": sampling_freq,
                    "imu_readings": readings,
                }
            )
        return out

    return out
