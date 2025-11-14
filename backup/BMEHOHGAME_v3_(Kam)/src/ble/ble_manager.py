import asyncio
import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:
    from bleak import BleakScanner, BleakClient  # type: ignore
    BLEAK_AVAILABLE = True
except Exception as e:  # Bleak might not be installed or supported
    BleakScanner = None
    BleakClient = None  # type: ignore
    BLEAK_AVAILABLE = False

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

    def __init__(self, simulation: bool = False, on_disconnect: Optional[Callable[[str], None]] = None):
        self.simulation = simulation or (BleakScanner is None)
        print(f"[BLEDBG] BLEManager initialized with simulation={self.simulation}")
        print(f"[BLEDBG] BleakScanner is None: {BleakScanner is None}")
        #self.simulation = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._clients: Dict[str, BleakClientType] = {}
        self._lock = threading.Lock()
        self._on_disconnect: Optional[Callable[[str], None]] = on_disconnect

        if not self.simulation:
            self._start_loop_thread()

    # ---------- Async loop management ----------
    def _start_loop_thread(self):
        def _runner():
            print("[BLEDBG] _start_loop_thread: Initializing event loop")  # Debug: Event loop initialization
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()
        
        # Wait a bit for the loop to be initialized
        for _ in range(100):
            if self._loop is not None:
                print("[BLEDBG] _start_loop_thread: Event loop initialized")  # Debug: Event loop initialized
                break
            time.sleep(0.01)  # 10ms * 100 = max 1 second wait

    def _run_coro(self, coro):
        """Schedule a coroutine on the background event loop.

        Accept either a coroutine object or a zero-argument callable that
        returns a coroutine. We purposely avoid *creating* the coroutine
        object unless we're actually going to schedule it. That prevents
        "coroutine was never awaited" warnings when the manager is in
        simulation mode or when the loop hasn't been started.
        """
        if self.simulation:
            return None
        if not self._loop:
            return None

        # print("[BLEDBG] _run_coro called")  # Debug: Confirm _run_coro is invoked

        # If a callable (factory) was passed, call it now to create the
        # coroutine object; otherwise assume a coroutine object was passed.
        coro_obj = coro() if callable(coro) else coro
        return asyncio.run_coroutine_threadsafe(coro_obj, self._loop)

    # ---------- API ----------
    def scan(self, timeout: float = 5.0) -> List[BLEDeviceInfo]:
        print("[BLEDBG] scan() method called")  # Debug: Confirm scan method is invoked
        if self.simulation:
            # Return some fake devices for UI testing
            return [
                BLEDeviceInfo("EMG Sensor A", "FA:KE:EM:GA:AA:01"),
                BLEDeviceInfo("EMG Sensor B", "FA:KE:EM:GB:BB:02"),
                BLEDeviceInfo("Exo-Hand", "FA:KE:EX:OH:AN:D1"),
            ]

        if BleakScanner is None:
            print("[BLEDBG] Bleak Scanner is None")  # Debug: Bleak Scanner is None
            return []
        
        async def _scan() -> List[BLEDeviceInfo]:
            """Async scan function that returns devices."""
            try:
                print("[BLEDBG] _scan() method called")  # Debug: Confirm _scan method is invoked
                found = await BleakScanner.discover(timeout=timeout)
                # Debug: show what bleak discovered when called from app
                try:
                    print(f"[BLEDBG] BleakScanner.discover returned {len(found)} devices")
                    for i, dev in enumerate(found[:8]):
                        print(f"[BLEDBG]   {i}: name={getattr(dev,'name',None)} addr={getattr(dev,'address',None)} rssi={getattr(dev,'rssi',None)}")
                except Exception:
                    pass
                result = []
                for d in found:
                    result.append(BLEDeviceInfo(d.name, d.address))
                return result
            except Exception as e:
                print(f"[ERROR] BLE scan failed: {e}")
                import traceback
                traceback.print_exc()
                return []

        # Pass the callable, not the created coroutine, so we don't create
        # the coroutine when running in simulation mode (which would leave
        # an unawaited coroutine object).
        fut = self._run_coro(_scan)
        if fut:
            try:
                devices = fut.result(timeout + 2)
                # Debug: report devices length as seen by the caller
                try:
                    print(f"[BLEDBG] scan() future returned {len(devices)} devices to caller")
                except Exception:
                    pass
                return devices
            except Exception as e:
                print(f"[ERROR] BLE scan coroutine failed: {e}")
                import traceback
                traceback.print_exc()
                return []
        return []

    def connect(self, address: str) -> bool:
        if self.simulation:
            with self._lock:
                self._clients[address] = None  # type: ignore
            return True

        if BleakClient is None:
            return False

        async def _connect():
            def disconnected_callback(client):
                """Called when device disconnects unexpectedly."""
                # Remove from clients dict
                with self._lock:
                    self._clients.pop(address, None)
                # Notify callback if registered
                if self._on_disconnect:
                    try:
                        self._on_disconnect(address)
                    except Exception:
                        pass
            
            client = BleakClient(address, disconnected_callback=disconnected_callback)
            await client.connect()
            return client

        fut = self._run_coro(_connect)
        if not fut:
            return False
        try:
            client = fut.result(10)
            with self._lock:
                self._clients[address] = client
            return True
        except Exception:
            return False

    def is_connected(self, address: str) -> bool:
        """Check if a device is currently connected."""
        if self.simulation:
            with self._lock:
                return address in self._clients
        with self._lock:
            return address in self._clients

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

        fut = self._run_coro(_disconnect)
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

        fut = self._run_coro(_start)
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

        fut = self._run_coro(_write)
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
