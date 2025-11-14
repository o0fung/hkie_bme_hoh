from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple

HEADER = 0xFF
N_FINGERS = 5

# Helper: packet builder/validator

def build_packet(cmd: str, payload: bytes = b"") -> bytes:
    """
    Encode a command packet following COMM.cpp:
    [0]=0xFF, [1]=L, [2]=cmd, [3..]=payload, [L]=checksum(~sum of [1..L-1])
    Where total length = L + 1 (including header).
    """
    if not isinstance(cmd, (bytes, bytearray)):
        if not cmd or len(cmd) != 1:
            raise ValueError("cmd must be single ASCII char")
        cmd_b = cmd.encode("ascii")
    else:
        if len(cmd) != 1:
            raise ValueError("cmd must be single byte")
        cmd_b = bytes(cmd)
    payload = payload or b""
    # total length N = 1(header) + 1(L) + 1(cmd) + len(payload) + 1(checksum)
    L = 3 + len(payload)
    out = bytearray(2 + 1 + len(payload) + 1)  # header + L + cmd + payload + checksum
    out[0] = HEADER
    out[1] = L
    out[2] = cmd_b[0]
    if payload:
        out[3:3 + len(payload)] = payload
    # compute checksum over [1..L-1] (length, cmd, payload)
    checksum = 0
    for i in range(1, L):
        checksum += out[i]
    out[L] = (~checksum) & 0xFF
    return bytes(out)


def verify_and_parse(payload: bytes) -> Optional[Dict[str, Any]]:
    """
    Validate a packet and return a parsed dict with keys type and fields.
    Returns None if invalid.
    """
    if not payload or len(payload) < 4:
        return None
    if payload[0] != HEADER:
        return None
    L = payload[1]
    if L != len(payload) - 1:
        return None
    # checksum over [1..L-1]
    checksum = 0
    for i in range(1, L):
        checksum += payload[i]
    if payload[L] != ((~checksum) & 0xFF):
        return None
    cmd = chr(payload[2])
    out: Dict[str, Any] = {"type": cmd, "raw": payload}
    if cmd == 'm' and L >= 11:
        # Status frame
        status1 = payload[3]
        status2 = payload[4]
        status3 = payload[5]
        moving_mask = status1 & 0x1F
        motor_state = (status1 >> 5) & 0x07
        flexing_mask = status2 & 0x1F
        sys_flags = (status2 >> 5) & 0x07
        side_right = (sys_flags & 0x01) == 1
        brace_connected = ((sys_flags >> 1) & 0x01) == 1
        cable_connected = ((sys_flags >> 2) & 0x01) == 1
        cpm_state = (status3 >> 4) & 0x0F
        fingers: List[Dict[str, Any]] = []
        positions: List[int] = []
        currents: List[bool] = []
        for i in range(N_FINGERS):
            b = payload[6 + i]
            pos = b & 0x7F
            cur = ((b >> 7) & 0x01) == 1
            positions.append(pos)
            currents.append(cur)
            fingers.append({"index": i, "position": pos, "has_current": cur})
        out.update({
            "motor_state": motor_state,
            "moving_mask": moving_mask,
            "flexing_mask": flexing_mask,
            "side_right": side_right,
            "brace_connected": brace_connected,
            "cable_connected": cable_connected,
            "cpm_state": cpm_state,
            "finger_positions": positions,
            "finger_currents": currents,
            "fingers": fingers,
        })
    elif cmd in ('v', 'V'):
        # Version strings
        # length byte includes length+cmd+checksum; string from [3..L-1]
        out["text"] = payload[3:L]
        try:
            out["text_str"] = out["text"].decode('utf-8', errors='ignore')
        except Exception:
            pass
    elif cmd == 'd':
        # Data frame with floats; expose raw
        out["data"] = payload[3:L]
    elif cmd == 's':
        out["settings"] = payload[3:L]
    return out


# High-level client
class ExoClient:
    def __init__(
        self,
        manager: Any,
        device: Any,
        *,
        write_uuid: str,
        notify_uuid: Optional[str] = None,
        on_status: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_notify: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.manager = manager
        self.device = device
        self.address: str = device.address
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid

        self._on_status = on_status
        self._on_notify = on_notify

        # Last known positions 0..100
        self.finger_positions: List[int] = [0] * N_FINGERS
        self.avg_position: float = 0.0  # 0..100
        self.motor_state: Optional[int] = None

        self._subscribed = False

    # Subscribe/unsubscribe
    def subscribe(self) -> bool:
        if not self.notify_uuid:
            return False
        ok = self.manager.start_notifications(self.address, self.notify_uuid, self._handle_notify)
        self._subscribed = bool(ok)
        return self._subscribed

    def unsubscribe(self) -> None:
        self._subscribed = False

    # Packet send helpers
    def send(self, cmd: str, payload: bytes = b"", *, response: bool = False) -> bool:
        if not self.write_uuid:
            return False
        pkt = build_packet(cmd, payload)
        return bool(self.manager.write_characteristic(self.address, self.write_uuid, pkt, response=response))

    # User-level controls
    def stop(self) -> bool:
        return self.send('x')

    def reset_extension(self) -> bool:
        return self.send('e')

    def reset_flexion(self) -> bool:
        return self.send('f')

    def calibration(self) -> bool:
        return self.send('c')

    def cpm(self, skip_mask: int = 0) -> bool:
        return self.send('p', bytes([skip_mask & 0x1F]))

    def cpm_seq(self, skip_mask: int = 0, reverse: bool = False) -> bool:
        return self.send('r' if reverse else 's', bytes([skip_mask & 0x1F]))

    def cpm_pause(self) -> bool:
        return self.send('Z')

    def cpm_resume(self) -> bool:
        return self.send('z')

    def cpm_one_cycle(self) -> bool:
        return self.send('o')

    def set_limits_extension(self, values: List[int]) -> bool:
        return self._send_5('l', values)

    def set_limits_flexion(self, values: List[int]) -> bool:
        return self._send_5('L', values)

    def set_wait_time_ext(self, micros: int) -> bool:
        return self._send_u32('t', micros)

    def set_wait_time_flex(self, micros: int) -> bool:
        return self._send_u32('T', micros)

    def enable_version_stream(self, enable: bool = True) -> bool:
        return self.send('v' if enable else 'V')

    def enable_data_stream(self, enable: bool = True) -> bool:
        return self.send('D' if enable else 'd')

    def enable_status_stream(self, enable: bool = True) -> bool:
        return self.send('G' if enable else 'g')

    def request_info(self) -> bool:
        return self.send('i')

    def request_debug_info(self) -> bool:
        return self.send('I')

    def move_uniform(self, percent: int, limit_flags: Optional[List[bool]] = None) -> bool:
        """Move all 5 fingers to same percent (0..100). limit_flags optionally applies ROM limit bits per finger."""
        p = max(0, min(100, int(percent)))
        vals = [p] * N_FINGERS
        if limit_flags is None:
            b = bytes([v & 0x7F for v in vals])
        else:
            b = bytes([ (v & 0x7F) | ((1 if limit_flags[i] else 0) << 7) for i, v in enumerate(vals) ])
        return self.send('m', b)

    def move_each(self, percents: List[int], limit_flags: Optional[List[bool]] = None) -> bool:
        if len(percents) != N_FINGERS:
            raise ValueError("percents must have length 5")
        vals = [max(0, min(100, int(v))) for v in percents]
        if limit_flags is None:
            b = bytes([v & 0x7F for v in vals])
        else:
            if len(limit_flags) != N_FINGERS:
                raise ValueError("limit_flags must have length 5")
            b = bytes([ (v & 0x7F) | ((1 if limit_flags[i] else 0) << 7) for i, v in enumerate(vals) ])
        return self.send('m', b)

    # Internal encoders
    def _send_5(self, cmd: str, values: List[int]) -> bool:
        if len(values) != N_FINGERS:
            raise ValueError("values must have length 5")
        b = bytes([max(0, min(100, int(v))) & 0x7F for v in values])
        return self.send(cmd, b)

    def _send_u32(self, cmd: str, value: int) -> bool:
        v = int(value) & 0xFFFFFFFF
        b = bytes([ (v >> (8*i)) & 0xFF for i in range(4) ])  # little-endian
        return self.send(cmd, b)

    # Notify handler
    def _handle_notify(self, payload: bytes) -> None:
        parsed = verify_and_parse(payload)
        if not parsed:
            return
        if parsed.get("type") == 'm' and 'finger_positions' in parsed:
            self.finger_positions = list(parsed['finger_positions'])
            self.avg_position = sum(self.finger_positions) / float(N_FINGERS)
            self.motor_state = parsed.get('motor_state')
            if self._on_status:
                try:
                    self._on_status(parsed)
                except Exception:
                    pass
        if self._on_notify:
            try:
                self._on_notify(parsed)
            except Exception:
                pass
