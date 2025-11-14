from PyQt6 import QtWidgets, QtCore, QtGui

import ble_device

import time
import struct
import bleak
import asyncio
import qasync
import traceback


class EmgsWorker(QtCore.QObject):
    """
    QObject that can be assigned to run in parallel with the PyQt event loop
    Designed for BLE communication that take time to work in the background
    """
    CHAR_UUID = {
        'WRITE': '6e400002-b5a3-f393-e0a9-e50e24dcca9e',    # Nordic UART RX
        'NOTIFY': '6e400003-b5a3-f393-e0a9-e50e24dcca9e',   # Nordic UART TX
    }
    signal_log = QtCore.pyqtSignal(str, bool)               # Post a message to log
    signal_scan_start = QtCore.pyqtSignal(str)              # When ble scan to start
    signal_scan_end = QtCore.pyqtSignal(str)                # When ble scan completed
    signal_connecting = QtCore.pyqtSignal(str)              # When a ble device has just started connecting
    signal_connected = QtCore.pyqtSignal(str)               # When a ble device has just finished connected
    signal_disconnected = QtCore.pyqtSignal(str)            # When ble device is disconnected
    signal_work_start = QtCore.pyqtSignal(str)              # When ble device is working on something need ui blocking
    signal_work_end = QtCore.pyqtSignal(str)                # When ble device has finished working on something need ui blocking
    signal_get_data = QtCore.pyqtSignal(str)                # When ble device received data, and request update param
    signal_set_data = QtCore.pyqtSignal(str)                # When ble device received data, and request update param
    
    def __init__(self):
        super().__init__()
        self.devices = {}

    async def task_scan(self):
        """ Scan nearby EMGS """
        self.signal_log.emit(f'>> Scan nearby EMGS', False)
        
        # Reset list of emgs devices that were scanned but not connected
        self.clear_scanned_devices()
        # Scan a new list of emgs devices
        await self.service_scan_devices()

    async def task_connect(self, addrs: list):
        """ Connect selected EMGS """
        # Connect to the list of selected devices
        await asyncio.gather(*[self.service_run_device(addr) for addr in addrs])

    def task_disconnect(self, addrs: list):
        """ Disconnect selected EMGS """
        # Setup the disconnection of selected devices
        for addr in addrs:
            self.devices[addr].reset()

    @staticmethod
    def require_ui_block(func):
        """ Decorator to trigger UI blocking for the rest of the function """
        async def wrapper(self, addr: str, *args, **kwargs):
            # Begin work with ui block
            self.signal_work_start.emit('work')

            # Doing the work function
            result = await func(self, addr, *args, **kwargs)
        
            # End work with ui unblock
            self.signal_work_end.emit('work')

            return result
        
        return wrapper

    @require_ui_block
    async def task_update(self, addrs: list):
        """ Update selected EMGS """
        # Update the device parameters of the selected devices
        await asyncio.gather(*[self.handle_update_get(addr) for addr in addrs])

    @require_ui_block
    async def task_timesync(self, addrs: list):
        """ Update timestamp of selected EMGS """
        # Update the timestamp of the selected devices
        await asyncio.gather(*[self.handle_timesync(addr) for addr in addrs])

    async def task_stream(self, addrs: list):
        """ Start stream of selected EMGS """
        # Start/stop streaming of the selected devices
        await asyncio.gather(*[self.handle_stream(addr) for addr in addrs])

    async def task_indicator_led(self, addrs: list, state: str):
        """ Turn on/off LED indicators of selected EMGS """
        await asyncio.gather(*[self.handle_indicator_led(addr, state) for addr in addrs])

    async def task_indicator_vib(self, addrs: list, state: str):
        """ Turn on/off Vibrator indicators of selected EMGS """
        await asyncio.gather(*[self.handle_indicator_vib(addr, state) for addr in addrs])

    async def service_scan_devices(self):
        """ Service to scan nearby EMGS """
        # Begin scanning nearby emgs devices
        self.signal_scan_start.emit('scan')
        
        # Scan nearby emgs devices
        discovered_devices = await bleak.BleakScanner.discover(timeout=1)

        for dd in discovered_devices:
            # Filter new BLE devices that have name and the name string starts with 'EMGS'
            if dd.address not in self.devices and dd.name is not None and dd.name.startswith('EMGS'):
                # Load the discovered emgs device to list
                device = ble_device.EmgsDevice(name=dd.name, address=dd.address)
                device.set_callback(event='log', callback=self.signal_log.emit)     # Link up the log callback
                device.set_callback(event='update_get', callback=self.signal_get_data.emit)     # Link up the update callback
                device.set_callback(event='update_set', callback=self.signal_set_data.emit)     # Link up the update callback

                self.devices[dd.address] = device
                
                self.signal_log.emit(f'>> [{dd.address}] EMGS Found', True)

        # Finished scanning nearby emgs devices
        self.signal_scan_end.emit('scan')

    async def service_run_device(self, addr: str):
        """ Service to run connected EMGS """
        try:
            if not addr in self.devices:
                # BLE already cleared from the record
                self.signal_log.emit(f'>> [{addr}] EMGS not found', True)
                return

            # Start UI blocking when the emgs is connecting
            self.signal_connecting.emit(addr)

            # Start the BLE connection operation
            async with bleak.BleakClient(address_or_ble_device=addr, disconnected_callback=lambda client: self.devices[addr].reset()) as client:
                # Setup the connection of the emgs device
                self.devices[addr].connect()
                # Remember the connected BLE client
                self.devices[addr].client = client

                self.signal_connected.emit(addr)
                self.signal_log.emit(f'>> [{addr}] EMGS Connected', True)

                # Start notification of the BLE client, for decode data packet
                await client.start_notify(self.CHAR_UUID['NOTIFY'], lambda client, data, address=addr: self.handle_notification(client, data, address))
                await self.handle_update_get(addr)
                
                # Loop that maintain the emgs BLE connection
                while self.devices[addr].is_connect:
                    await asyncio.sleep(delay=1.0)

                # Start notification of the BLE client
                if client.is_connected:
                    await client.stop_notify(self.CHAR_UUID['NOTIFY'])

            # End the BLE operation
            self.devices[addr].reset()
            self.signal_disconnected.emit(addr)
            self.signal_log.emit(f'>> [{addr}] EMGS Disconnected', True)

        except bleak.exc.BleakDeviceNotFoundError as e:
            # BLE not found during connection
            self.devices.pop(addr, None)
            self.signal_disconnected.emit(addr)
            self.signal_log.emit(f'>> [{addr}] EMGS not found', True)

        except Exception as e:
            # Other errors
            tb_str = traceback.format_exc()
            self.signal_log.emit(f'[{addr}] EMGS Error: {e}\n{tb_str}', True)

    def handle_notification(self, sender, data: bytearray, addr: str):
        """ Task to do when received data packet """
        self.devices[addr].decode(data)

    @staticmethod
    def require_connection(func):
        """ Decorator to validate device connection before executing async functions """
        async def wrapper(self, addr: str, *args, **kwargs):
            # Validate connection to the BLE client
            if addr not in self.devices or not self.devices[addr].is_connect:
                self.signal_log.emit(f'>> [{addr}] EMGS Error: device not connected', True)
                return
            return await func(self, addr, *args, **kwargs)
        
        return wrapper
    
    @require_connection
    async def handle_update_get(self, addr: str):
        """ Task to do when user call to update devices """
        await self.handle_send_bytes(addr, 2, 'A0')    # Get version
        await self.handle_send_bytes(addr, 2, 'Aa')    # Get version of DSP
        await self.handle_send_bytes(addr, 2, 'AG')    # Get timestamp
        await self.handle_send_bytes(addr, 2, 'AK')    # Get BLE advertising name
        await self.handle_send_bytes(addr, 2, 'An')    # Get BLE connection interval
        await self.handle_send_bytes(addr, 3, 'AX', 0)   # Get ICM Enable state: Raw ACC
        await self.handle_send_bytes(addr, 3, 'AX', 1)   # Get ICM Enable state: Calibrated ACC
        await self.handle_send_bytes(addr, 3, 'AX', 2)   # Get ICM Enable state: Linear ACC
        await self.handle_send_bytes(addr, 3, 'AX', 3)   # Get ICM Enable state: Raw GYR
        await self.handle_send_bytes(addr, 3, 'AX', 4)   # Get ICM Enable state: Calibrated GYR
        await self.handle_send_bytes(addr, 3, 'AX', 5)   # Get ICM Enable state: Raw MAG
        await self.handle_send_bytes(addr, 3, 'AX', 6)   # Get ICM Enable state: Calibrated ACC
        await self.handle_send_bytes(addr, 3, 'AX', 7)   # Get ICM Enable state: QUAT Vector
        await self.handle_send_bytes(addr, 3, 'AX', 8)   # Get ICM Enable state: QUAT with MAG
        await self.handle_send_bytes(addr, 2, 'Ax')      # Get EMG Enable state: EMG and RMS

        print('ok')

    @qasync.asyncSlot(str)
    @require_connection
    async def handle_update_set(self, addr: str):
        """ Task to do when user call to set mode for sensor """        
        # Set BLE advertising name
        device_name = self.devices[addr].param['Name'][:12]  # Truncate to max 12 chars
        new_name = device_name + '\0' * (12 - len(device_name))  # Pad with null bytes to exactly 12 bytes
        await self.handle_send_bytes(addr, 14, 'AF', new_name)                           # Set BLE Advertising Name
        
        # Set BLE connection interval
        conn_t_min, conn_t_max = self.devices[addr].param['ConnT'].split(',')
        conn_t_min_byte = struct.pack('<H', int(conn_t_min))
        conn_t_max_byte = struct.pack('<H', int(conn_t_max))
        await self.handle_send_bytes(addr, 6, 'Am', conn_t_min_byte[0], conn_t_min_byte[1], conn_t_max_byte[0], conn_t_max_byte[1])  # Set BLE connection interval
        
        # Set EMGS sensor modes
        await self.handle_send_bytes(addr, 4, 'AW', 0, int(self.devices[addr].icm_mode[0]['state']))    # Set ICM Enable state: Raw ACC
        await self.handle_send_bytes(addr, 4, 'AW', 1, int(self.devices[addr].icm_mode[1]['state']))    # Set ICM Enable state: Calibrated ACC
        await self.handle_send_bytes(addr, 4, 'AW', 2, int(self.devices[addr].icm_mode[2]['state']))    # Set ICM Enable state: Linear ACC
        await self.handle_send_bytes(addr, 4, 'AW', 3, int(self.devices[addr].icm_mode[3]['state']))    # Set ICM Enable state: Raw GYR
        await self.handle_send_bytes(addr, 4, 'AW', 4, int(self.devices[addr].icm_mode[4]['state']))    # Set ICM Enable state: Calibrated GYR
        await self.handle_send_bytes(addr, 4, 'AW', 5, int(self.devices[addr].icm_mode[5]['state']))    # Set ICM Enable state: Raw MAG
        await self.handle_send_bytes(addr, 4, 'AW', 6, int(self.devices[addr].icm_mode[6]['state']))    # Set ICM Enable state: Calibrated ACC
        await self.handle_send_bytes(addr, 4, 'AW', 7, int(self.devices[addr].icm_mode[7]['state']))    # Set ICM Enable state: QUAT Vector
        await self.handle_send_bytes(addr, 4, 'AW', 8, int(self.devices[addr].icm_mode[8]['state']))    # Set ICM Enable state: QUAT with MAG
        await self.handle_send_bytes(addr, 3, 'Aw', int(self.devices[addr].emg_mode))                   # Set EMG Enable state: EMG and RMS
    
    @require_connection
    async def handle_timesync(self, addr: str):
        """ Task to do when user call to sync time for sensor """
        # Set timestamp as current time, and form a bytearray in list of integer for send to BLE
        now = time.time()
        time_now = time.localtime(now)
        timestamp_list = list(struct.unpack('BBBBBBBB', int(now * 1000).to_bytes(8, byteorder='little')))
        self.devices[addr].param['Timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S', time_now)
        await self.handle_send_bytes(addr, 10, 'A9', *timestamp_list)

    @require_connection
    async def handle_stream(self, addr: str, is_stream: bool=True):
        """ Task to do when user call to stream data for sensor """
        cmd_stream = 'A5' if is_stream else 'A7'
        await self.handle_send_bytes(addr, 2, cmd_stream)
    
    @require_connection
    async def handle_indicator_led(self, addr: str, state: str):
        """
        For RGB control,
            byte 2 is 0
            byte 3 is in format: 0rgb 
        For Vibrator control,
            byte 2 is 1
            byte 3 is 2, i.e., format: 0000 0010
        """
        # User select to change LED indicator
        rgb_code = {
            'off': b'00000000',
            'blue': b'00001001',
            'yellow': b'00010001',
            'purple': b'00011001',
        }
        if state in rgb_code:
            await self.handle_send_bytes(addr, 4, 'Ar', 0, int(rgb_code[state], 2))

    @require_connection
    async def handle_indicator_vib(self, addr: str, state: str):
        """
        For Vibrator control,
            byte 2 is 1
            byte 3 is 2, i.e., format: 0000 0010
        """
        # User select to change Vibrator indicator
        vib_code = {
            'off': b'00000000',
            'on': b'00000010',
        }
        if state in vib_code:
            await self.handle_send_bytes(addr, 4, 'Ar', 1, int(vib_code[state], 2))

    async def handle_send_bytes(self, addr: str, n: int, *cmd):
        # Assemble the data packet from *cmd
        data = []
        for c in cmd:
            if isinstance(c, str):
                data.extend(ord(ch) for ch in c)
            elif isinstance(c, int):
                data.append(c)
            else:
                self.signal_log.emit(f'>> [{addr}] EMGS Error: invalid byte argument {c}', True)
                return

        try:
            # Validate the length of data packet
            if not n == len(data):
                self.signal_log.emit(f'>> [{addr}] EMGS Error: bad byte format to write (expected {n}, got {len(data)})', True)
                return
            
            # Write the constructed data packet to the BLE client
            await self.devices[addr].client.write_gatt_char(self.CHAR_UUID['WRITE'], struct.pack(f'{n}B', *data))
            await asyncio.sleep(delay=0.1)
        
        except Exception as e:
            tb_str = traceback.format_exc()
            self.signal_log.emit(f'[{addr}] EMGS Error: {e}\n{tb_str}', True)

    def clear_scanned_devices(self):
        # Remove emgs devices that are marked as disconnected
        addr_to_clear = [addr for addr in self.devices.keys() if not self.devices[addr].is_connect]
        for addr in addr_to_clear:
            self.devices.pop(addr)
