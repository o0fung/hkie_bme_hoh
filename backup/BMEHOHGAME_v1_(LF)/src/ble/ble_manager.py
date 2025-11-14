import asyncio
import threading
from typing import Any, Callable, Dict, List, Optional

try:
    from bleak import BleakScanner, BleakClient  # type: ignore
except Exception:  # Bleak might not be installed or supported
    BleakScanner = None
    BleakClient = None  # type: ignore

# Fallback-friendly client type for annotations
BleakClientType = Any


class BLEDeviceInfo:
    def __init__(self, name: str, address: str):
        self.name = name or "Unknown"
        self.address = address

    def to_dict(self):
        return {"name": self.name, "address": self.address}


class BLEManager:
    """
    Cross-platform BLE manager using bleak, running its own asyncio loop in a background thread.
    Provides simple scan/connect/notify interface and a simulation fallback.
    """

    def __init__(self, simulation: bool = False):
        self.simulation = simulation or (BleakScanner is None)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._clients: Dict[str, BleakClientType] = {}
        self._lock = threading.Lock()

        if not self.simulation:
            self._start_loop_thread()

    # ---------- Async loop management ----------
    def _start_loop_thread(self):
        def _runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()

    def _run_coro(self, coro):
        if self.simulation:
            return None
        if not self._loop:
            return None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ---------- API ----------
    def scan(self, timeout: float = 5.0) -> List[BLEDeviceInfo]:
        if self.simulation:
            # Return some fake devices for UI testing
            return [
                BLEDeviceInfo("EMG Sensor A", "FA:KE:EM:GA:AA:01"),
                BLEDeviceInfo("EMG Sensor B", "FA:KE:EM:GB:BB:02"),
                BLEDeviceInfo("Exo-Hand", "FA:KE:EX:OH:AN:D1"),
            ]

        if BleakScanner is None:
            return []

        devices: List[BLEDeviceInfo] = []

        async def _scan():
            found = await BleakScanner.discover(timeout=timeout)
            for d in found:
                devices.append(BLEDeviceInfo(d.name, d.address))

        fut = self._run_coro(_scan())
        if fut:
            fut.result(timeout + 2)
        return devices

    def connect(self, address: str) -> bool:
        if self.simulation:
            with self._lock:
                self._clients[address] = None  # type: ignore
            return True

        if BleakClient is None:
            return False

        async def _connect():
            client = BleakClient(address)
            await client.connect()
            return client

        fut = self._run_coro(_connect())
        if not fut:
            return False
        try:
            client = fut.result(10)
            with self._lock:
                self._clients[address] = client
            return True
        except Exception:
            return False

    def disconnect(self, address: str):
        if self.simulation:
            with self._lock:
                self._clients.pop(address, None)
            return

        async def _disconnect():
            with self._lock:
                client = self._clients.pop(address, None)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        fut = self._run_coro(_disconnect())
        if fut:
            try:
                fut.result(10)
            except Exception:
                pass

    def start_notifications(
        self,
        address: str,
        characteristic_uuid: str,
        callback: Callable[[bytes], None],
    ) -> bool:
        if self.simulation:
            # Nothing to wire; UI can push synthetic values
            return True

        async def _start():
            with self._lock:
                client = self._clients.get(address)
            if not client:
                return False

            def _cb(_sender, data: bytearray):
                try:
                    callback(bytes(data))
                except Exception:
                    pass

            await client.start_notify(characteristic_uuid, _cb)
            return True

        fut = self._run_coro(_start())
        if not fut:
            return False
        try:
            return fut.result(10)
        except Exception:
            return False

    def write_characteristic(
        self,
        address: str,
        characteristic_uuid: str,
        data: bytes,
        response: bool = False,
    ) -> bool:
        if self.simulation:
            # Pretend success
            return True

        async def _write():
            with self._lock:
                client = self._clients.get(address)
            if not client:
                return False
            await client.write_gatt_char(characteristic_uuid, data, response=response)
            return True

        fut = self._run_coro(_write())
        if not fut:
            return False
        try:
            return fut.result(10)
        except Exception:
            return False

    def shutdown(self):
        # Disconnect all and stop loop
        try:
            for addr in list(self._clients.keys()):
                self.disconnect(addr)
        finally:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=2)
