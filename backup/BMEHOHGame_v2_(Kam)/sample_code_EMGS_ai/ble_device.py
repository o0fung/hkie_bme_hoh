import default
import struct
import time


EMG_MODES = {
    'OFF': 0,
    'EMG_RMS': 1,
    'EMG_RAW': 2,
}


class EmgsDevice():
    def __init__(self, name: str=default.EMGS_NAME, address: str=default.EMGS_ADDR):
        self.client = None              # bleak.BleakClient
        
        self.param = {}                 # emgs device parameters
        self.param['Name'] = name
        self.param['Address'] = address

        self.icm_mode = []      # channel name / current state / the state to be set (wait for acknowledgement)
        self.icm_mode.append({'channel': 'ACC_RAW', 'state': False})    # 0
        self.icm_mode.append({'channel': 'ACC_CAL', 'state': False})    # 1
        self.icm_mode.append({'channel': 'ACC_LIN', 'state': False})    # 2
        self.icm_mode.append({'channel': 'GYR_RAW', 'state': False})    # 3
        self.icm_mode.append({'channel': 'GYR_CAL', 'state': False})    # 4
        self.icm_mode.append({'channel': 'MAG_RAW', 'state': False})    # 5
        self.icm_mode.append({'channel': 'MAG_CAL', 'state': False})    # 6
        self.icm_mode.append({'cåhannel': 'QUAT_VEC', 'state': False})   # 7
        self.icm_mode.append({'channel': 'QUAT_MAG', 'state': False})   # 8

        self.emg_mode = EMG_MODES['OFF']

        self._callback = {}             # PyQt Signal Callback functions

        self.reset()                    # initialize default device parameters and state

    def reset(self):
        # Default device parameters
        self.param['Status'] = default.EMGS_STATUS
        self.param['Timestamp'] = default.EMGS_TIMESTAMP
        self.param['Battery'] = default.EMGS_BATTERY
        self.param['Mode'] = default.EMGS_MODE
        self.param['Firmware'] = default.EMGS_FIRMWARE
        self.param['Hardware'] = default.EMGS_HARDWARE
        self.param['DSP'] = default.EMGS_DSP
        self.param['ConnT'] = default.EMGS_CONNT
        
        # Default device status
        self.is_connect = False
        self.is_stream = False
        self.is_charging = False
        
        # Default icm mode
        for mode in self.icm_mode:
            mode['state'] = False
        # Default emg mode
        self.emg_mode = EMG_MODES['OFF']
        # Get sensor modes
        self.convert_displayable_mode()

        # Other parameters to reset
        self.name_to_set = ''
        self.t0 = 0.0

    def set_callback(self, event: str, callback):
        # Link up the PyQt signal with callback
        self._callback[event] = callback

    def emit(self, event: str, *args, **kwargs):
        # Call the registered callback for the event, if any
        if event in self._callback:
            self._callback[event](*args, **kwargs)

    def connect(self):
        # Set connection state of BLE device
        self.param['Status'] = 'Connected'
        self.is_connect = True

    def decode(self, data: bytearray):
        """Systematic decode of EMGS data packet."""
        addr = self.param['Address']

        # 1. Validate header and minimum length
        if not data or len(data) < 3:
            # Packet too short or empty
            self.emit('log', f'>> [{addr}] EMGS Error: Packet too short or empty: {data}', True)
            return
        if chr(data[0]) != 'S':
            # Invalid header S
            self.emit('log', f'>> [{addr}] EMGS Error: Invalid header: {data}', True)
            return

        # 2. Parse packet type and command
        packet_type = chr(data[1])

        # 3. Dispatch table for packet types
        packet_handlers = {
            'C': self._handle_notify_charging,
            'A': self._handle_notify_app_helper,
            'E': self._handle_notify_data_emg,
            'I': self._handle_notify_data_imu,
            'G': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Connection Interval: {data}', True),
            'X': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Error: {data}', True),
            'D': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Debug in Data Pin Reset: {data}', True),
            'F': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Error in RTC Lost: {data}', True),
            'J': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Error in Read Memory: {data}', True),
            'M': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS DSP Upgraded OK: {data}', True),
            'N': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS DSP Upgraded Failed: {data}', True),
            'q': lambda data, addr: self.emit('log', f'>> [{addr}] EMGS Debug Offline Data: {data}', True),
        }

        # 4. Call the appropriate handler
        handler = packet_handlers.get(packet_type)
        if handler:
            # Run the handler according to packet type
            handler(data, addr)
        else:
            # Unknown packet type
            self.emit('log', f'>> [{addr}] EMGS Warning: Unknown packet type {packet_type}: {data}', True)

    def _handle_notify_charging(self, data: bytearray, addr):
        # Get charging state
        self.is_charging = (data[2] == 1)
        # Trigger the emgs param update
        self.emit('update_get', addr)

    def _handle_notify_app_helper(self, data: bytearray, addr):
        """ General App Helper with command dispatching """
        cmd = chr(data[2])      # Get the command type

        # Command dispatch table
        command_handlers = {
            '0': lambda x: (self._handle_battery(x), self._handle_version(x)),
            '3': lambda x: (self._handle_battery(x), self._handle_time_sync(x)),
            '5': lambda x: (self._handle_battery(x), self._handle_stream_start(x)),
            '7': lambda x: (self._handle_battery(x), self._handle_stream_stop(x)),
            'a': lambda x: (self._handle_battery(x), self._handle_dsp_version(x)),
            'G': self._handle_timestamp,
            'X': self._handle_icm_enable,
            'x': self._handle_emg_enable,
            'K': self._handle_ble_name,
            'n': self._handle_conn_interval,
            'W': self._handle_acknowledgement,      # W = set ICM mode
            'w': self._handle_acknowledgement,      # w = set EMG option
            '9': self._handle_acknowledgement,      # 9 = set timestamp
            'F': self._handle_acknowledgement,      # F = set BLE name
            'm': self._handle_acknowledgement,      # m = set BLE connection interval
            'r': self._handle_acknowledgement,      # r = set RGB Vibrator
        }

        # Call the appropriate handler if exists
        handler = command_handlers.get(cmd)
        if handler:
            # Run the command
            handler(data)
            # Only update the table when it is the last command to update_get
            if cmd in ['3', '5', '7', '9', 'x', 'w']:
                # Trigger the emgs param update
                self.emit('update_get', addr)

        else:
            # Unknown command
            self.emit('log', f'>> [{addr}] EMGS Received Unknown Command {cmd}: {data}', True)

    # Helper functions for each command
    def _handle_battery(self, data: bytearray):
        # Update Battery and Charging state
        batt_lo = default.EMGS_BATTERY_LOW_VOLTAGE
        batt_hi = default.EMGS_BATTERY_HIGH_VOLTAGE
        batt_val = (data[3] - batt_lo) / (batt_hi - batt_lo) * 100.0
        batt_val = max(0.0, min(100.0, batt_val))
        self.param['Battery'] = f'{batt_val:1.0f} %'
        self.is_charging = (data[4] == 1)

    def _handle_version(self, data: bytearray):
        # Update Firmware and Hardware versions
        self.param['Firmware'] = f'{data[5]}.{data[6]}'
        self.param['Hardware'] = f'{data[7]}.{data[8]}'

    def _handle_time_sync(self, data: bytearray):
        # Update timestamp
        timestamp = struct.unpack('Q', data[5: 13])[0]
        self.param['Timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp / 1000.0))

    def _handle_stream_start(self, data: bytearray):
        # Get Stream start notice
        self.is_stream = True
        self.t0 = 0.0

    def _handle_stream_stop(self, data: bytearray):
        # Get Stream stop notice
        self.is_stream = False

    def _handle_dsp_version(self, data: bytearray):
        # Update DSP version
        self.param['DSP'] = f'{data[5]}.{data[6]}.{data[7]}'

    def _handle_timestamp(self, data: bytearray):
        # Update timestamp
        timestamp = struct.unpack('Q', data[3: 11])[0]
        self.param['Timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp / 1000.0))

    def _handle_icm_enable(self, data: bytearray):
        # Update IMU enable mode
        self.icm_mode[data[3]]['state'] = (data[4] == 1)
        self.convert_displayable_mode()

    def _handle_emg_enable(self, data: bytearray):
        # Update EMG enable mode
        self.emg_mode = data[3]
        self.convert_displayable_mode()

    def _handle_ble_name(self, data: bytearray):
        # Update EMGS sensor BLE name
        txt = data[3: 15]
        name = ''
        for ch in txt:
            if ch == 0:    # Non-printable characters
                break
            name += chr(ch)
        self.param['Name'] = name

    def _handle_conn_interval(self, data: bytearray):
        # Update the connection interval
        min_conn_interval = struct.unpack('<H', data[3:5])[0]
        max_conn_interval = struct.unpack('<H', data[5:7])[0]
        self.param['ConnT'] = f'{min_conn_interval},{max_conn_interval}'

    def _handle_acknowledgement(self, data: bytearray):
        # Receive successful emgs setting
        pass        # Do nothing

    def convert_displayable_mode(self):
        # Signal Enable mode save to EMGS parameters
        self.param['Mode'] = ''
        self.param['Mode'] += 'g' if self.icm_mode[3]['state'] else ''
        self.param['Mode'] += 'G' if self.icm_mode[4]['state'] else ''
        self.param['Mode'] += 'a' if self.icm_mode[0]['state'] else ''
        self.param['Mode'] += 'A' if self.icm_mode[1]['state'] else ''
        self.param['Mode'] += 'm' if self.icm_mode[5]['state'] else ''
        self.param['Mode'] += 'M' if self.icm_mode[6]['state'] else ''
        self.param['Mode'] += 'e' if self.emg_mode == EMG_MODES['EMG_RMS'] else ''
        self.param['Mode'] += 'E' if self.emg_mode == EMG_MODES['EMG_RAW'] else ''
        self.param['Mode'] += 'q' if self.icm_mode[7]['state'] else ''
        self.param['Mode'] += 'Q' if self.icm_mode[8]['state'] else ''
        self.param['Mode'] += ' (Linear)' if self.icm_mode[2]['state'] else ''

    def _handle_notify_data_imu(self, data, addr):
        """ EMG Packet """
        # Decode EMG data packet
        return
        self.emit('log', f'>> [{addr}] EMGS Data IMU: {data}', True)

    def _handle_notify_data_emg(self, data, addr):
        """ IMU Packet """
        # Decode EMG data packet
        return
        self.emit('log', f'>> [{addr}] EMGS Data EMG: {data}', True)
