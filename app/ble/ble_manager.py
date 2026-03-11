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
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()
        
        # Wait for the loop to be initialized
        for _ in range(100):
            if self._loop is not None:
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

        # If a callable (factory) was passed, call it now to create the
        # coroutine object; otherwise assume a coroutine object was passed.
        coro_obj = coro() if callable(coro) else coro
        return asyncio.run_coroutine_threadsafe(coro_obj, self._loop)

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
        
        async def _scan() -> List[BLEDeviceInfo]:
            """Async scan function that returns devices."""
            try:
                found = await BleakScanner.discover(timeout=timeout)
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
                    # Use shorter timeout to avoid blocking
                    await asyncio.wait_for(client.disconnect(), timeout=2.0)
                except (asyncio.TimeoutError, Exception):
                    pass

        fut = self._run_coro(_disconnect)
        if fut:
            try:
                fut.result(3.0)  # Reduced from 10 to 3 seconds
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
        # Stop notifications and disconnect all clients with shorter timeout
        if not self.simulation and self._loop:
            async def _shutdown_all():
                clients_to_disconnect = []
                with self._lock:
                    # Copy the clients dict to avoid modification during iteration
                    clients_to_disconnect = list(self._clients.items())
                
                # Disconnect all clients with short timeout
                for addr, client in clients_to_disconnect:
                    if client:
                        try:
                            # Try to stop notifications first (if supported)
                            # Note: Some clients may not support this, so we catch exceptions
                            try:
                                await asyncio.wait_for(client.disconnect(), timeout=1.0)
                            except (asyncio.TimeoutError, Exception):
                                pass
                        except Exception:
                            pass
                
                # Clear clients dict
                with self._lock:
                    self._clients.clear()
                
                # Cancel all pending tasks
                pending = [task for task in asyncio.all_tasks(self._loop) if task is not asyncio.current_task()]
                for task in pending:
                    task.cancel()
                # Wait for cancelled tasks to complete
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            
            # Run shutdown with timeout
            try:
                fut = self._run_coro(_shutdown_all)
                if fut:
                    fut.result(timeout=1.5)  # Max 1.5 seconds total for all disconnects
            except (TimeoutError, Exception):
                # Force clear clients anyway
                with self._lock:
                    self._clients.clear()
        
        # Stop the event loop more aggressively
        if self._loop:
            try:
                # Stop the loop
                if self._loop.is_running():
                    # Cancel all tasks first
                    try:
                        pending = asyncio.all_tasks(self._loop)
                        for task in pending:
                            task.cancel()
                    except Exception:
                        pass
                    
                    # Stop the loop
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    # Give it a tiny moment to stop (but don't block long)
                    import time
                    time.sleep(0.05)
            except Exception:
                pass
