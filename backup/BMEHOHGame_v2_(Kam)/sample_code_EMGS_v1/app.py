import os
import sys
import time
import struct
import platform
import collections
import traceback
import importlib

from PyQt6 import QtWidgets, QtCore
import pyqtgraph
import asyncio
import qasync
import bleak

import run1_data_processing
import emgs


os_platform = platform.system()

if os_platform == 'Windows':
    try:
        # tell Bleak we are using a graphical user interface that has been properly
        # configured to work with asyncio
        from bleak.backends.winrt.util import allow_sta
        allow_sta()
    except ImportError:
        # other OSes and older versions of Bleak will raise ImportError which we
        # can safely ignore
        pass

    # Saved EMGS MAC address
    # List of devices that will be displayed for selection after reset
    default_emgs_address = {
        'EMGS-E5': 'E5:01:50:A4:57:9C',
    }

else:
    # Saved EMGS UUID
    # List of devices that will be displayed for selection after reset
    default_emgs_address = {
        'EMGS-9402': '940275A4-0385-85EB-8FEC-C69E78086B09',
    }

# Available BLE services
emgs_uuid = {
    'WRITE': '6e400002-b5a3-f393-e0a9-e50e24dcca9e',    # Nordic UART RX
    'NOTIFY': '6e400003-b5a3-f393-e0a9-e50e24dcca9e',    # Nordic UART TX
}
 

class UserInterface(QtWidgets.QMainWindow):
    """ PyQt6 UI application
        - Scan nearby BLE devices
        - Connect to selected BLE device
        - Read and write to the BLE services
    """
    
    def __init__(self):
        super().__init__()
        
        # Set up UI and variables
        self.setup_layout()
        self.setup_vars()
        self.setup_graphs()
        self.setup_signals()
        
    def setup_layout(self):
        
        # Setup Window
        self.setWindowTitle('EMGS Interface')
        self.setGeometry(0, 0, 1500, 1000)

        # ===================================================
        # Setup Widget
        
        self.widgets = {}

        # -----------------
        self.widgets['btn_scan'] = QtWidgets.QPushButton('Scan')
        self.widgets['btn_connect'] = QtWidgets.QPushButton('Connect')
        self.widgets['btn_connect'].setEnabled(False)
        self.widgets['btn_connect'].setCheckable(True)
        
        self.widgets['list_devices'] = QtWidgets.QListWidget()
        self.widgets['list_devices'].setFixedHeight(50)
        
        self.widgets['btn_clear'] = QtWidgets.QPushButton('Clear to Default Connected Devices')
        
        self.widgets['txt_output'] = QtWidgets.QTextEdit()
        
        # -----------------
        self.widgets['txt_command'] = QtWidgets.QPlainTextEdit()
        self.widgets['txt_command'].setFixedHeight(40)
        self.widgets['btn_send'] = QtWidgets.QPushButton('Send')
        
        self.widgets['btn_timestamp'] = QtWidgets.QPushButton('Timestamp Sync')
        self.widgets['str_timestamp'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_name'] = QtWidgets.QLabel('BLE Device Name')
        self.widgets['lbl_name'].setStyleSheet('font-weight: bold')
        self.widgets['str_name'] = QtWidgets.QLineEdit('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_ver_fw'] = QtWidgets.QLabel('Version Firmware')
        self.widgets['lbl_ver_fw'].setStyleSheet('font-weight: bold')
        self.widgets['str_ver_fw'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_ver_hw'] = QtWidgets.QLabel('Version Hardware')
        self.widgets['lbl_ver_hw'].setStyleSheet('font-weight: bold')
        self.widgets['str_ver_hw'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_ver_sw'] = QtWidgets.QLabel('Version Firmware DSP')
        self.widgets['lbl_ver_sw'].setStyleSheet('font-weight: bold')
        self.widgets['str_ver_sw'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_battery'] = QtWidgets.QLabel('Battery Level')
        self.widgets['lbl_battery'].setStyleSheet('font-weight: bold')
        self.widgets['str_battery'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        
        self.widgets['lbl_charge'] = QtWidgets.QLabel('Charging?')
        self.widgets['lbl_charge'].setStyleSheet('font-weight: bold')
        self.widgets['str_charge'] = QtWidgets.QLabel('-', alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        # -----------------
        self.widgets['chkbox_raw_acc'] = QtWidgets.QCheckBox('0: Raw ACC')
        self.widgets['chkbox_cal_acc'] = QtWidgets.QCheckBox('1: Calibrated ACC')
        self.widgets['chkbox_lin_acc'] = QtWidgets.QCheckBox('2: Linear ACC')
        self.widgets['chkbox_raw_gyr'] = QtWidgets.QCheckBox('3: Raw GYRO')
        self.widgets['chkbox_cal_gyr'] = QtWidgets.QCheckBox('4: Calibrated GYRO')
        self.widgets['chkbox_raw_mag'] = QtWidgets.QCheckBox('5: Raw MAG')
        self.widgets['chkbox_cal_mag'] = QtWidgets.QCheckBox('6: Calibrated MAG')
        self.widgets['chkbox_quat_vec'] = QtWidgets.QCheckBox('7: Quaternion Vector')
        self.widgets['chkbox_quat_mag'] = QtWidgets.QCheckBox('8: Quaternion Vector + MAG')
        self.widgets['chkbox_emg'] = QtWidgets.QCheckBox("1': Raw EMG & 2': RMS")
        
        # -----------------
        self.widgets['btn_update'] = QtWidgets.QPushButton('Update System Info')
        self.widgets['btn_stream_start'] = QtWidgets.QPushButton('Stream Start / Restart')
        self.widgets['btn_stream_stop'] = QtWidgets.QPushButton('Stream Stop')
        
        self.widgets['btn_offset_set'] = QtWidgets.QPushButton('Set Offset')
        self.widgets['btn_offset_reset'] = QtWidgets.QPushButton('Reset Offset')
        
        self.widgets['btn_data_processing'] = QtWidgets.QPushButton('Data Processing')
        self.widgets['btn_update_library'] = QtWidgets.QPushButton('Update Library')
        
        # ===================================================
        # Setup Layout
        
        # -----------------
        layout_connect_btn = QtWidgets.QHBoxLayout()
        layout_connect_btn.addWidget(self.widgets['btn_scan'])
        layout_connect_btn.addWidget(self.widgets['btn_connect'])
        layout_connect_btn.setContentsMargins(0, 0, 0, 0)
        layout_connect_btn.setSpacing(0)
        
        layout_connect_form = QtWidgets.QFormLayout()
        layout_connect_form.addRow(QtWidgets.QLabel('Status'), self.widgets['txt_output'])
        layout_connect_form.setContentsMargins(0, 0, 0, 0)
        layout_connect_form.setSpacing(0)
        
        layout_connect = QtWidgets.QVBoxLayout()
        layout_connect.addLayout(layout_connect_btn)
        layout_connect.addWidget(self.widgets['list_devices'])
        layout_connect.addWidget(self.widgets['btn_clear'])
        layout_connect.addLayout(layout_connect_form)
        layout_connect.setContentsMargins(0, 0, 0, 0)
        layout_connect.setSpacing(0)

        group_connect = QtWidgets.QGroupBox('Connection Panel')
        group_connect.setStyleSheet('font-size: 50; font-weight: bold')
        group_connect.setLayout(layout_connect)
        group_connect.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

        # -----------------
        layout_control_input = QtWidgets.QHBoxLayout()
        layout_control_input.addWidget(self.widgets['txt_command'])
        layout_control_input.addWidget(self.widgets['btn_send'])
        layout_control_input.setContentsMargins(0, 0, 0, 0)
        layout_control_input.setSpacing(0)
        
        layout_control_form = QtWidgets.QFormLayout()
        layout_control_form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout_control_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout_control_form.addRow(self.widgets['btn_timestamp'], self.widgets['str_timestamp'])
        layout_control_form.addRow(self.widgets['lbl_name'], self.widgets['str_name'])
        layout_control_form.addRow(self.widgets['lbl_ver_fw'], self.widgets['str_ver_fw'])
        layout_control_form.addRow(self.widgets['lbl_ver_hw'], self.widgets['str_ver_hw'])
        layout_control_form.addRow(self.widgets['lbl_ver_sw'], self.widgets['str_ver_sw'])
        layout_control_form.addRow(self.widgets['lbl_battery'], self.widgets['str_battery'])
        layout_control_form.addRow(self.widgets['lbl_charge'], self.widgets['str_charge'])
        layout_connect_form.setContentsMargins(0, 0, 0, 0)
        layout_connect_form.setSpacing(0)
        
        layout_control_chkbox = QtWidgets.QVBoxLayout()
        layout_control_chkbox.addWidget(self.widgets['chkbox_raw_acc'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_cal_acc'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_lin_acc'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_raw_gyr'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_cal_gyr'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_raw_mag'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_cal_mag'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_quat_vec'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_quat_mag'])
        layout_control_chkbox.addWidget(self.widgets['chkbox_emg'])
        layout_control_chkbox.setContentsMargins(0, 0, 0, 0)
        layout_control_chkbox.setSpacing(0)
        
        layout_control_btn_sub = QtWidgets.QHBoxLayout()
        layout_control_btn_sub.addWidget(self.widgets['btn_offset_set'])
        layout_control_btn_sub.addWidget(self.widgets['btn_offset_reset'])
        layout_control_btn_sub.setContentsMargins(0, 0, 0, 0)
        layout_control_btn_sub.setSpacing(0)
        
        layout_control_btn = QtWidgets.QVBoxLayout()
        layout_control_btn.addWidget(self.widgets['btn_update'])
        layout_control_btn.addWidget(self.widgets['btn_stream_start'])
        layout_control_btn.addWidget(self.widgets['btn_stream_stop'])
        layout_control_btn.addLayout(layout_control_btn_sub)
        layout_control_btn.addWidget(self.widgets['btn_data_processing'])
        layout_control_btn.addWidget(self.widgets['btn_update_library'])
        layout_control_btn.setContentsMargins(0, 0, 0, 0)
        layout_control_btn.setSpacing(0)
        
        layout_control = QtWidgets.QVBoxLayout()
        layout_control.addLayout(layout_control_input)
        layout_control.addLayout(layout_control_form)
        layout_control.addLayout(layout_control_chkbox)
        layout_control.addLayout(layout_control_btn)
        layout_control.setContentsMargins(0, 0, 0, 0)
        layout_control.setSpacing(0)
        
        group_control = QtWidgets.QGroupBox('Control Panel')
        group_control.setStyleSheet('font-size: 50; font-weight: bold')
        group_control.setLayout(layout_control)
        group_control.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        
        # -----------------
        layout_operator = QtWidgets.QVBoxLayout()
        layout_operator.addWidget(group_connect, stretch=1)
        layout_operator.addStretch(0)
        layout_operator.addWidget(group_control, stretch=1)
        layout_operator.setContentsMargins(0, 0, 0, 0)
        layout_operator.setSpacing(0)
        
        # -----------------
        self.layout_graph_angle = QtWidgets.QHBoxLayout()
        self.layout_graph_icm = QtWidgets.QHBoxLayout()
        self.layout_graph_emg = QtWidgets.QHBoxLayout()
        
        layout_graphs = QtWidgets.QVBoxLayout()
        layout_graphs.addLayout(self.layout_graph_angle)
        layout_graphs.addLayout(self.layout_graph_icm)
        layout_graphs.addLayout(self.layout_graph_emg)
        
        # -----------------
        layout_main = QtWidgets.QHBoxLayout()
        layout_main.addLayout(layout_operator)
        layout_main.addLayout(layout_graphs)
        
        # -----------------
        central_widget = QtWidgets.QWidget(self)
        central_widget.setLayout(layout_main)
        
        self.setCentralWidget(central_widget)
        # -----------------
        
    def setup_vars(self):
        self.vars = {}
        self.vars['devices_list'] = []
        self.vars['t0'] = time.time()
        self.vars['current_dev_addr'] = None
        self.vars['list_emgs'] = list(default_emgs_address.items())
        
        self.sensors = {}
        
    def setup_graphs(self):
        # Prepare drawing pen with colors
        self.plot_pen = {}
        self.plot_pen['x'] = pyqtgraph.mkPen(color=(0, 0, 255))         # blue
        self.plot_pen['y'] = pyqtgraph.mkPen(color=(255, 0, 0))         # red
        self.plot_pen['z'] = pyqtgraph.mkPen(color=(0, 255, 0))         # green
        self.plot_pen['e'] = pyqtgraph.mkPen(color=(255, 255, 255))     # white
        self.plot_pen['r'] = pyqtgraph.mkPen(color=(255, 0, 0))         # red
        # Prepare text font with color and size
        self.font_style = {'color': 'white', 'font-size': '10px'}
        
        self.graphs = {}        # Store graph widget
        self.lines = {}         # Store line objects
        self.legends = {}
        
        # Prepare chart for plotting data
        for dev in ['roll', 'pitch', 'yaw', 'acc', 'gyr', 'mag', 'emg', 'freq']:
            self.graphs[dev] = pyqtgraph.PlotWidget()
            self.graphs[dev].setBackground('k')
            self.graphs[dev].showGrid(x=True, y=True)
            
            if dev in ['acc', 'gyr', 'mag']:
                self.lines[dev] = {}
                
                for axe in ['x', 'y', 'z']:
                    self.lines[dev][axe] = self.graphs[dev].plot(
                        [0, 1],
                        [0, 0],
                        name=f'{dev.upper()}{axe.upper()}',
                        pen=self.plot_pen[axe],
                    )
                
                self.graphs[dev].setLabel('bottom', 'Time (ms)', **self.font_style)
                self.layout_graph_icm.addWidget(self.graphs[dev])
            
            elif dev in ['roll', 'pitch', 'yaw']:
                self.lines[dev] = self.graphs[dev].plot(
                    [0, 1],
                    [0, 0],
                    name=f'{dev.upper()}',
                    pen=self.plot_pen['e'],
                )
                self.lines[f'{dev}_'] = self.graphs[dev].plot(
                    [0, 1],
                    [0, 0],
                    name=f'{dev.upper()}_',
                    pen=self.plot_pen['r'],
                )
                
                self.graphs[dev].setLabel('bottom', 'Time (ms)', **self.font_style)
                self.layout_graph_angle.addWidget(self.graphs[dev])
                
            else:
                self.lines[dev] = self.graphs[dev].plot(
                    [0, 1],
                    [0, 0],
                    name=f'{dev.upper()}',
                    pen=self.plot_pen['e'],
                )
                
                if dev in ['emg']:
                    self.lines['rms'] = self.graphs[dev].plot(
                        [0, 1],
                        [0, 0],
                        name='RMS',
                        pen=self.plot_pen['r'],
                    )
                    self.graphs[dev].setLabel('bottom', 'Time (ms)', **self.font_style)
                    
                else:
                    self.graphs[dev].setLabel('bottom', 'Frequency (Hz)', **self.font_style)

                self.layout_graph_emg.addWidget(self.graphs[dev])
        
        self.graphs['acc'].setTitle('Accelerometer (ACC)', **self.font_style)
        self.graphs['acc'].setLabel('left', 'Acc (Normalized)', **self.font_style)
        self.graphs['acc'].setYRange(-1, 1)
        
        self.graphs['gyr'].setTitle('Gyroscope (GYR)', **self.font_style)
        self.graphs['gyr'].setLabel('left', 'Gyr (deg/s)', **self.font_style)
        self.graphs['gyr'].setYRange(-2000, 2000)
        
        self.graphs['mag'].setTitle('Magnetometer (MAG)', **self.font_style)
        self.graphs['mag'].setLabel('left', 'Mag (Normalized)', **self.font_style)
        self.graphs['mag'].setYRange(-1, 1)
        
        self.graphs['roll'].setTitle('Roll Angle', **self.font_style)
        self.graphs['roll'].setLabel('left', 'degree', **self.font_style)
        self.graphs['roll'].setYRange(-180, 180)
        
        self.graphs['pitch'].setTitle('Pitch Angle', **self.font_style)
        self.graphs['pitch'].setLabel('left', 'degree', **self.font_style)
        self.graphs['pitch'].setYRange(-180, 180)
        
        self.graphs['yaw'].setTitle('Yaw Angle', **self.font_style)
        self.graphs['yaw'].setLabel('left', 'degree', **self.font_style)
        self.graphs['yaw'].setYRange(-180, 180)
        
        self.graphs['emg'].setTitle('Electromygraphy (EMG)', **self.font_style)
        self.graphs['emg'].setLabel('left', 'EMG (mV)', **self.font_style)
        self.graphs['emg'].setYRange(-1.5, 1.5)
        
        self.graphs['freq'].setTitle('Frequency Spectrum', **self.font_style)
        self.graphs['freq'].setLabel('left', '', **self.font_style)
        self.graphs['freq'].setYRange(0, 0.002)
        
        self.legends['freq'] = pyqtgraph.TextItem('MNF = ?, MDF = ?')
        self.legends['freq'].setPos(0, 0.002)
        self.graphs['freq'].addItem(self.legends['freq'])
        
    def setup_signals(self):
        # Set up connects and slots
        
        self.widgets['btn_scan'].clicked.connect(self.handle_scan)
        self.widgets['btn_connect'].clicked.connect(self.handle_disconnect)
        self.widgets['btn_clear'].clicked.connect(self.handle_clear_scanned_list)
        self.widgets['btn_send'].clicked.connect(self.handle_manual_input)
        self.widgets['btn_timestamp'].clicked.connect(self.handle_time_sync)
        self.widgets['btn_update'].clicked.connect(self.handle_manual_update)
        self.widgets['btn_stream_start'].clicked.connect(lambda: self.handle_send('A5'))
        self.widgets['btn_stream_stop'].clicked.connect(lambda: self.handle_send('A7'))
        self.widgets['btn_data_processing'].clicked.connect(self.handle_data_processing)
        self.widgets['btn_update_library'].clicked.connect(self.handle_update_library)
        self.widgets['btn_offset_set'].clicked.connect(self.handle_offset_set)
        self.widgets['btn_offset_reset'].clicked.connect(self.handle_offset_reset)
        
        self.widgets['chkbox_raw_acc'].clicked.connect(lambda: self.clicked_checkbox_icm(0))
        self.widgets['chkbox_cal_acc'].clicked.connect(lambda: self.clicked_checkbox_icm(1))
        self.widgets['chkbox_lin_acc'].clicked.connect(lambda: self.clicked_checkbox_icm(2))
        self.widgets['chkbox_raw_gyr'].clicked.connect(lambda: self.clicked_checkbox_icm(3))
        self.widgets['chkbox_cal_gyr'].clicked.connect(lambda: self.clicked_checkbox_icm(4))
        self.widgets['chkbox_raw_mag'].clicked.connect(lambda: self.clicked_checkbox_icm(5))
        self.widgets['chkbox_cal_mag'].clicked.connect(lambda: self.clicked_checkbox_icm(6))
        self.widgets['chkbox_quat_vec'].clicked.connect(lambda: self.clicked_checkbox_icm(7))
        self.widgets['chkbox_quat_mag'].clicked.connect(lambda: self.clicked_checkbox_icm(8))
        self.widgets['chkbox_emg'].clicked.connect(lambda x: self.clicked_checkbox_emg(x))
        
        self.widgets['str_name'].editingFinished.connect(self.change_ble_name)
        
        self.widgets['list_devices'].itemSelectionChanged.connect(self.change_state_selecting_ble)
        
        # Set up widgets states

        self.widgets['btn_clear'].clicked.emit()
        
    def show_message(self, txt):
        # Print message to stdout and text widget
        output = time.strftime(f'%Y-%m-%d %H:%M:%S >> {txt}')
        print(output)
        self.widgets['txt_output'].append(output)
        
    def show_warning(self, txt):
        # Print warning to stdout and text widget
        msg_err = f'An error occurred: {str(txt)}'
        self.show_message(msg_err)
        QtWidgets.QMessageBox.critical(self, 'Error', msg_err)
        
    def handle_clear_scanned_list(self):
        # Clear the list of scanned BLE devices
        self.widgets['list_devices'].blockSignals(True)
        self.widgets['list_devices'].clear()
        self.widgets['list_devices'].blockSignals(False)
        
        # Replace the list with the default list of connected BLE devices
        self.vars['devices_list'] = []
        for emgs_name, emgs_addr in self.vars['list_emgs']:
            self.widgets['list_devices'].addItem(f'{emgs_name}\t - {emgs_addr}')
            self.vars['devices_list'].append((emgs_name, emgs_addr))
            
    def handle_clear_system_status(self):
        self.widgets['str_name'].setText('-')
        self.widgets['str_battery'].setText('-')
        self.widgets['str_charge'].setText('-')
        self.widgets['str_timestamp'].setText('-')
        self.widgets['str_ver_fw'].setText('-')
        self.widgets['str_ver_hw'].setText('-')
        self.widgets['str_ver_sw'].setText('-')
        self.widgets['chkbox_raw_acc'].setChecked(False)
        self.widgets['chkbox_cal_acc'].setChecked(False)
        self.widgets['chkbox_lin_acc'].setChecked(False)
        self.widgets['chkbox_raw_gyr'].setChecked(False)
        self.widgets['chkbox_cal_gyr'].setChecked(False)
        self.widgets['chkbox_raw_mag'].setChecked(False)
        self.widgets['chkbox_cal_mag'].setChecked(False)
        self.widgets['chkbox_quat_vec'].setChecked(False)
        self.widgets['chkbox_quat_vec'].setChecked(False)
        self.widgets['chkbox_emg'].setCheckState(QtCore.Qt.CheckState.Unchecked)
        
    @qasync.asyncSlot()
    async def handle_scan(self):
        # To scan and get a list of BLE devices
        
        self.widgets['list_devices'].setCurrentRow(-1)
        self.widgets['list_devices'].clear()
        list_of_scanned_devices = collections.defaultdict(list)

        self.show_message('Scanning nearby BLE devices...')
        
        try:
            # Scan nearby BLE devices (takes some time ~10 sec)
            # Group scanned devices depends on the availability of name
            devices = await bleak.BleakScanner.discover(timeout=1)
            for device in devices:
                types_of_device = 'named' if device.name is not None else 'unnamed'
                list_of_scanned_devices[types_of_device].append(device)
            
            # Sort the list of scanned devices according to name or address depending on its group
            # Organize the sorted list of devices to a dedicated list
            self.vars['devices_list'] = []
            for t_dev in ['named', 'unnamed']:
                list_of_scanned_devices[t_dev].sort(key=lambda x, t=t_dev: x.name if t == 'named' else x.address)
                list_of_sorted_device = [(dev.name, dev.address) for dev in list_of_scanned_devices[t_dev]]
                self.vars['devices_list'].extend(list_of_sorted_device)
                
            # Display the organized list of devices onto the listbox for selection
            for device in self.vars['devices_list']:
                self.widgets['list_devices'].addItem(f'{device[0]}\t - {device[1]}')
                
        except Exception as e:
            # Capture any exceptions and errors
            str_err = traceback.format_exc()
            self.show_warning(str_err)
            
        self.show_message('Scan completed.')
        
    @qasync.asyncSlot()
    async def handle_connect(self):
        # To connect selected BLE device
        
        # Get the selected device from the selected row
        # Check if the address is registered
        addr = self.vars['current_dev_addr']
        if addr not in self.sensors:
            self.sensors[addr] = emgs.EMGS(addr)
            
        if self.sensors[addr].is_connected:
            return
        
        self.sensors[addr].is_connected = True
        
        self.show_message(f'Selected device:\n {addr}')
        self.show_message('Connecting to selected BLE devices...')
        
        try:
            # Start the BLE connection using Bleak client
            async with bleak.BleakClient(addr) as self.sensors[addr].client:
                
                # Connect to BLE device
                # await self.sensors[addr].client.connect()
                if not self.sensors[addr].client.is_connected:
                    return
                
                # Start notification of the BLE after connection successful
                await self.sensors[addr].client.start_notify(emgs_uuid['NOTIFY'], lambda client, data, address=addr: self.handle_notify(client, data, address))
                
                # Set up connection flag to control connect state
                # Display time elapse since connected
                self.vars['t0'] = time.time()
                self.change_state_connecting_ble(True)
                self.show_message(time.strftime(f'Connected. ({addr[:4]})'))
                
                # Update the list of EMGS connected
                if addr not in [dev[1] for dev in self.vars['list_emgs']]:
                    # Get more info about the selected BLE device to be connected
                    selected_index = self.widgets['list_devices'].row(self.widgets['list_devices'].selectedItems()[0])
                    target_dev_name, addr = self.vars['devices_list'][selected_index]
                    self.vars['list_emgs'].append((target_dev_name, addr))
                
                # Clear and update the list of BLE devices
                self.handle_clear_scanned_list()
                # Highlight the selected device to start update system status
                dev_index = [dev[1] for dev in self.vars['list_emgs']].index(addr)
                self.widgets['list_devices'].setCurrentRow(dev_index)
                
                await self.handle_sleep(dt=3)
                
                # Assign tasks to do that run in a loop
                # Use connection flag to control loop
                while self.sensors[addr].is_connected:
                    await self.handle_sleep(dt=1)
                    
                try:
                    # User decided to end the loop and disconnect from BLE device
                    # Stop notification of the BLE before disconnection
                    await self.sensors[addr].client.stop_notify(emgs_uuid['NOTIFY'])
                    await self.sensors[addr].client.disconnect()
                    # Allow some time for the BLE to end completely
                    await self.handle_sleep(dt=3)
                    
                except AttributeError as e:
                    # When there was errors in the while loop
                    # with immature termination of communication
                    pass
                
                self.change_state_connecting_ble(False)
                self.handle_clear_system_status()
                self.show_message(f'Disconnected. ({addr[:4]})')
        
        except bleak.exc.BleakDeviceNotFoundError as e:
            # When the BLE device is not turned on
            # Failed to search the device
            self.sensors[addr].is_connected = False
            self.show_warning(e)
        
        except Exception as e:
            # Capture any exceptions and errors
            self.sensors[addr].is_connected = False
            str_err = traceback.format_exc()
            self.show_warning(str_err)

    def handle_disconnect(self):
        # Change the connection state to OFF
        # Exit the BLE loop and then continue to disconnect device
        addr = self.vars['current_dev_addr']
        self.sensors[addr].is_connected = False
        self.show_message(f'Disconnecting... ({addr[:4]})')
        
    @qasync.asyncSlot()
    async def handle_notify(self, client, data, addr):
        # Get headers and length of data packet
        # Validate format of the data packet
        n = len(data)
        if n >= 3 and chr(data[0]) == 'S':
            
            # Data packet is for general commands
            if chr(data[1]) == 'A':
                cmd = chr(data[2])   # Command byte
                
                if cmd in ['0', '3', '5', '7', 'a']:    # Get battery and charge
                    batt_lo = self.sensors[addr].list_str_battery['low']
                    batt_hi = self.sensors[addr].list_str_battery['high']
                    batt_val = (data[3] - batt_lo) / (batt_hi - batt_lo) * 100.0
                    batt_val = batt_val if batt_val <= 100.0 else 100.0
                    batt_val = batt_val if batt_val >= 0.0 else 0.0
                    self.sensors[addr].battery = batt_val
                    self.widgets['str_battery'].setText(f'{batt_val:1.0f}%')
                    
                    charging = (data[4] == 1)
                    self.sensors[addr].is_charging = charging
                    self.widgets['str_charge'].setText('Yes' if charging else 'No')
                    
                if cmd == '0':      # Get version
                    self.sensors[addr].ver_fw = f'{data[5]}.{data[6]}'
                    self.widgets['str_ver_fw'].setText(self.sensors[addr].ver_fw)
                    
                    self.sensors[addr].ver_hw = f'{data[7]}.{data[8]}'
                    self.widgets['str_ver_hw'].setText(self.sensors[addr].ver_hw)
                    
                elif cmd == '3':      # Get time sync
                    ts = struct.unpack('Q', data[5:13])[0]
                    self.sensors[addr].timestamp = ts
                    self.widgets['str_timestamp'].setText(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts / 1000.0)))
                    
                elif cmd == 'a':      # Get version DSP
                    self.sensors[addr].ver_sw = f'{data[5]}.{data[6]}.{data[7]}'
                    self.widgets['str_ver_sw'].setText(self.sensors[addr].ver_sw)
                    
                elif cmd == 'G':      # Get timestamp
                    ts = struct.unpack('Q', data[3:11])[0]
                    self.sensors[addr].timestamp = ts
                    self.widgets['str_timestamp'].setText(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts / 1000.0)))
                    
                elif cmd == 'X':      # Get ICM Enable Mode
                    mode_code = data[3]
                    mode_str = self.sensors[addr].list_str_icm_mode[mode_code]
                    if 0 <= mode_code <= 8:
                        val = (data[4] == 1)
                        
                        self.sensors[addr].icm_mode[mode_str] = val
                        self.change_state_checkbox_icm(mode_code, val)
                    
                elif cmd == 'x':      # Get EMG Enable Mode
                    mode_code = data[3]
                    if 0 <= mode_code <= 2:
                        self.sensors[addr].emg_mode = mode_code
                        self.change_state_checkbox_emg(mode_code)
                    
                elif cmd == 'K':      # Get BLE advertising name
                    txt = data[3:15]
                    name = ''
                    
                    for ch in txt:
                        if ch == 0:
                            break
                        # Accept the string as name until reaching \0
                        name += chr(ch)
                    
                    self.sensors[addr].name = name
                    self.widgets['str_name'].setText(name)
                
                elif cmd == '5':
                    self.show_message(f'Streaming Start... ({addr[:4]})')
                    
                    self.sensors[addr].is_streaming = True
                    self.sensors[addr].t0 = 0.0
                    self.sensors[addr].signal.set_zero()
                    
                elif cmd == '7':
                    if self.sensors[addr].is_streaming:
                        self.sensors[addr].is_streaming = False
                        
                        self.show_message(f'Streaming Stop... ({addr[:4]})')
                        
                        self.handle_data_processing()
                
                elif cmd in ['W', 'w', 'F']:
                    print('OK                                                          \r', end='')
                
                else:
                    print(struct.unpack(f'{n}B', data))
                    
            # Data packet is for charger notification
            elif chr(data[1]) == 'C':
                print(f'{addr} : Charging?                                       \r', end='')
            
            # Data packet is for charger notification
            elif chr(data[1]) == 'X':
                print(f'{addr} : Error!                                       \r', end='')
                      
            # Data packet is for ICM data transfer
            elif chr(data[1]) == 'I':
                # Decode data packet
                datalen = data[2]                                   # data packet length
                packet_id = struct.unpack('H', data[3:5])[0]        # packet id 
                sensor_type = data[5]                               # sensor type: 1=acc, 4=gyr, 6=mag
                timestamp = struct.unpack('Q', data[6:14])[0]       # timestamp: long 8 bytes
                samplingfreq = data[14]                             # sampling frequency: 100 Hz
                
                data_packet_count = int((datalen - 15) / 4)                     # how many xyz data in the packet
                readings = struct.unpack(data_packet_count * 'f', data[15:])    # decode unpack the data packets into xyz
                imu_sensor = self.sensors[addr].list_str_imu_sensor[sensor_type]
                
                # When the buffer needs to be extended to accomondate new data
                # Add zero padding with the following length
                extension_buffer_count = 25
                
                # For the first data packet after streaming start
                # Get ABSOULATE timestamp for the streaming start time
                if self.sensors[addr].t0 == 0.0:
                    self.sensors[addr].t0 = timestamp
                    self.sensors[addr].signal.add_zero('icm', extension_buffer_count)
                    self.sensors[addr].signal.add_zero('emg', extension_buffer_count)
                    dt = 0

                else:
                    # Get RELATIVE timestamp of the subsequent data packets
                    dt = int(round((timestamp - self.sensors[addr].t0) / 10.0))
                    
                    if dt + extension_buffer_count >= self.sensors[addr].signal.data_count['icm']:
                        adding_length = (((dt + extension_buffer_count - self.sensors[addr].signal.data_count['icm']) // extension_buffer_count) + 1) * extension_buffer_count
                        self.sensors[addr].signal.add_zero('icm', adding_length)
                    
                for i, reading in enumerate(readings):
                    # Fill in the expected data value of the frame
                    # Readings should be in sequence XYZ, XYZ, XYZ...
                    self.sensors[addr].signal.data['icm'][f'{imu_sensor}{"XYZ"[i%3]}'][dt] = reading
                    
                    # Fill in the expected time value of the frame
                    if i % 3 == 0:
                        self.sensors[addr].signal.data['icm']['icmT'][dt] = dt * 10.0
                        self.sensors[addr].signal.data['icm'][f'{imu_sensor}T'][dt] = dt * 10.0
                        self.sensors[addr].signal.add_data_buffer(f'{imu_sensor}T', dt * 10.0 / 1000.0)
                        dt += 1     # Unit 10 milliseconds
                
                # Computation of Euler angle requires all concurrent 9-axis channel data
                # Using quaternion with respect to reference offset frame
                self.sensors[addr].signal.extract_features_from_icm(dt-1)
                
                if addr == self.vars['current_dev_addr']:
                    # Update the ACC, GYR, MAG graphs
                    for i in range(3):
                        self.lines[imu_sensor]['xyz'[i]].setData(
                            self.sensors[addr].signal.buffer[f'{imu_sensor}T'],
                            self.sensors[addr].signal.buffer[f'{imu_sensor}{"XYZ"[i]}_'])
                    
                    # Update the Euler angle graphs
                    self.lines['roll'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['roll'])
                    self.lines['pitch'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['pitch'])
                    self.lines['yaw'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['yaw'])
                    self.lines['roll_'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['roll_'])
                    self.lines['pitch_'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['pitch_'])
                    self.lines['yaw_'].setData(self.sensors[addr].signal.buffer[f'{imu_sensor}T'], self.sensors[addr].signal.buffer['yaw_'])
                        
            # Data packet is for EMG data transfer
            elif chr(data[1]) == 'E':
                # Decode data packet
                datalen = data[2]                                   # data packet length (constant 216)
                batt = data[3]                                      # m_batt
                charge_state = data[4]                              # charge_state
                packet_id = struct.unpack('H', data[5:7])[0]        # packet id 
                timestamp = struct.unpack('Q', data[7:15])[0]       # timestamp: long 8 bytes
                packet_mode_pos = data[15]                          # sampling frequency: 100 Hz
                snr = data[16]                                      # SNR
                rms = struct.unpack('>H', data[17:19])[0]           # RMS
                
                data_packet_count = int((datalen - 16) / 2)         # how many emg data in the packet
                readings = struct.unpack('>' + data_packet_count * 'H', data[19:])    # decode unpack the data packets into emg
                
                # When the buffer needs to be extended to accomondate new data
                # Add zero padding with the following length
                extension_buffer_count = 250
                
                # For the first data packet after streaming start
                # Get ABSOULATE timestamp for the streaming start time
                if self.sensors[addr].t0 == 0.0:
                    self.sensors[addr].t0 = timestamp
                    self.sensors[addr].signal.add_zero('icm', extension_buffer_count)
                    self.sensors[addr].signal.add_zero('emg', extension_buffer_count)
                    dt = 0
                    
                else:
                    # Get RELATIVE timestamp of the subsequent data packets
                    dt = int(round((timestamp - self.sensors[addr].t0)))
                    
                    if dt + extension_buffer_count >= self.sensors[addr].signal.data_count['emg']:
                        adding_length = (((dt + extension_buffer_count - self.sensors[addr].signal.data_count['emg']) // extension_buffer_count) + 1) * extension_buffer_count
                        self.sensors[addr].signal.add_zero('emg', adding_length)
                        
                for i, reading in enumerate(readings):
                    # Fill in the expected data value of the frame
                    emg = (reading / 65535.0 * 3.0 - 1.5) / 1200.0 * 1000.0
                    self.sensors[addr].signal.data['emg']['emg'][dt] = emg
                    self.sensors[addr].signal.add_data_buffer('emg', emg)
                    self.sensors[addr].signal.add_data_buffer('rms100', emg)
                    
                    # Fill in the expected time value of the frame
                    self.sensors[addr].signal.data['emg']['emgT'][dt] = dt
                    self.sensors[addr].signal.add_data_buffer('emgT', dt / 1000.0)

                    # Compute EMG features (RMS, Power Spectrum, etc)
                    frequencies, power_spectrum = self.sensors[addr].signal.extract_features_from_emg(dt)
                    # EMG data in Frequency Domain 
                    mnf = self.sensors[addr].signal.data['emg']['mnf'][dt]
                    mdf = self.sensors[addr].signal.data['emg']['mdf'][dt]
                    
                    output_txt_for_freq = f'MNF = {mnf:1.0f}Hz\nMDF = {mdf:1.0f}Hz'
                    self.legends['freq'].setText(output_txt_for_freq)

                    dt += 1     # Unit 1 millisecond

                # Update the EMG graph
                if addr == self.vars['current_dev_addr']:
                    self.lines['emg'].setData(self.sensors[addr].signal.buffer['emgT'],
                                            self.sensors[addr].signal.buffer['emg'])
                    self.lines['rms'].setData(self.sensors[addr].signal.buffer['emgT'],
                                            self.sensors[addr].signal.buffer['rms'])
                    
                    # Update the Frequency Spectrum of the EMG graph
                    self.lines['freq'].setData(frequencies, power_spectrum)
                    
                # Update per each EMG data packet
                # Additional info for real-time monitoring battery level
                # EMG data packet contains battery info
                
                batt_lo = self.sensors[addr].list_str_battery['low']
                batt_hi = self.sensors[addr].list_str_battery['high']
                batt_val = (batt - batt_lo) / (batt_hi - batt_lo) * 100.0
                batt_val = batt_val if batt_val <= 100.0 else 100.0
                batt_val = batt_val if batt_val >= 0.0 else 0.0
                self.sensors[addr].battery = batt_val
                self.widgets['str_battery'].setText(f'{batt_val:1.0f}%')
                
                charging = (charge_state == 1)
                self.sensors[addr].is_charging = charging
                self.widgets['str_charge'].setText('Yes' if charging else 'No')
                
            # Other unattended data packets
            else:
                print(struct.unpack(f'{n}B', data))
        
    @qasync.asyncSlot()
    async def handle_sleep(self, dt):
        # Produce a time delay of duration dt
        await asyncio.sleep(dt)
        # Display a time elapse since connected message that update every second
        print(time.strftime("Time elapse: %H:%M:%S                                                \r", time.gmtime(time.time() - self.vars['t0'])), end='')
        
    @qasync.asyncSlot()
    async def handle_manual_input(self):
        # Write command packet to BLE device with user input strings
        
        # User can type in command string to execuate write command to BLE
        output = self.widgets['txt_command'].toPlainText()
        await self.handle_send(output)
        
    @qasync.asyncSlot()
    async def handle_time_sync(self):
        # Set timestamp and form a string for send to BLE
        timestamp_list = list(struct.unpack('BBBBBBBB', int(time.time() * 1000).to_bytes(8, byteorder='little')))
        output = 'A,9'       # Command to set timestamp
        for ts_byte in timestamp_list:
            output += f',{str(ts_byte)}'
            
        await self.handle_send(output)
        
    @qasync.asyncSlot()
    async def handle_auto_update(self):
        await self.handle_send('A3')            # Get Time Sync (get battery, charge, timestamp)
        
    @qasync.asyncSlot()
    async def handle_manual_update(self):
        # Get current EMGS status
        await self.handle_send('A0')            # Get version
        await self.handle_send('Aa')            # Get version DSP
        await self.handle_send('AG')            # Get timestamp
        await self.handle_send('AK')            # Get BLE advertising name
        await self.handle_send('A,X,0')         # Get ICM Enable 0: Raw Acc
        await self.handle_send('A,X,1')         # Get ICM Enable 1: Cal Acc
        await self.handle_send('A,X,2')         # Get ICM Enable 2: Lin Acc
        await self.handle_send('A,X,3')         # Get ICM Enable 3: Raw Gyr
        await self.handle_send('A,X,4')         # Get ICM Enable 4: Cal Gyr
        await self.handle_send('A,X,5')         # Get ICM Enable 5: Raw Mag
        await self.handle_send('A,X,6')         # Get ICM Enable 6: Cal Mag
        await self.handle_send('A,X,7')         # Get ICM Enable 7: Quat Vec
        await self.handle_send('A,X,8')         # Get ICM Enable 8: Quat Mag
        await self.handle_send('Ax')            # Get EMG RMS Enable
        
    @qasync.asyncSlot()
    async def handle_send(self, cmd):
        # Write command packet to BLE device
        addr = self.vars['current_dev_addr']
        if not addr in self.sensors or not self.sensors[addr].is_connected:
            return
        
        try:
            # Validate input command is a list array
            if type(cmd) is not str:
                return
            
            # Accept a list of string or a list of byte integers
            output = []
            if ',' in cmd:
                # Format 1: Comma-separated string
                for item in cmd.split(','):
                    try:
                        output.append(int(item))
                    except ValueError:
                        output.append(ord(item))
            else:
                # Format 2: ASCII String
                for item in cmd:
                    output.append(ord(item))
            
            # Pack up the byte array
            # Write the input command to the BLE
            n = len(output)
            
            await self.sensors[addr].client.write_gatt_char(emgs_uuid['WRITE'], struct.pack(f'{n}B', *output))
            await asyncio.sleep(0.1)
            
        except bleak.exc.BleakError as e:
            # Can no longer send heartbeat, i.e. command A3 to the device
            self.show_warning(f'Connection lost to BLE ({addr[:4]})')
            self.handle_disconnect()
        
        except Exception as e:
            # Capture any exceptions and errors
            str_err = traceback.format_exc() 
            self.show_message(f'Error in send packet to BLE ({addr[:4]}): {cmd}\n{str_err}')
            
    def handle_offset_set(self):
        # Write command packet to BLE device
        addr = self.vars['current_dev_addr']
        if not addr in self.sensors or not self.sensors[addr].is_connected:
            return
        
        self.sensors[addr].signal.set_offset()
    
    def handle_offset_reset(self):
        # Write command packet to BLE device
        addr = self.vars['current_dev_addr']
        if not addr in self.sensors or not self.sensors[addr].is_connected:
            return
        
        self.sensors[addr].signal.set_offset(is_reset=True)    
    
    def handle_update_library(self):
        # Intended to revised the algorithm during runtime
        # So user can test the revised algorithm instantly
        importlib.reload(run1_data_processing)
        
        self.show_message('Updated algorithm library')
            
    def handle_data_processing(self):
        
        addr = self.vars['current_dev_addr']
        
        self.show_message(f'Start data processing... ({addr[:4]})')
        
        # Run the data processing algorithm
        self.sensors[self.vars['current_dev_addr']].data_processing()
        
        self.show_message(f'Finish data processing... ({addr[:4]})')
        
    def update_connected_emgs(self):
        # Get selected BLE device and address
        selected_item = self.widgets['list_devices'].selectedItems()
        if not selected_item:
            return
        
        selected_index = self.widgets['list_devices'].row(selected_item[0])
        target_dev_name, addr = self.vars['devices_list'][selected_index]
        
        # Add to the list of connected device if not already exist
        list_of_addr = [dev[1] for dev in self.vars['list_emgs']]
        if not addr in list_of_addr:
            self.vars['list_emgs'].append((target_dev_name, addr))
            list_of_addr = [dev[1] for dev in self.vars['list_emgs']]
        
        # Clear the list of BLE device
        self.handle_clear_scanned_list()
        
        # Highlight the selected device to start update system status
        dev_index = list_of_addr.index(addr)
        self.widgets['list_devices'].setCurrentRow(dev_index)
            
    @qasync.asyncSlot()
    async def change_ble_name(self):
        # User has changed the input entry field
        name_str = self.widgets['str_name'].text()[:12]

        # Prepare data packet to change BLE name
        output = 'A,F'
        for i in range(len(name_str)):
            output += f',{ord(name_str[i])}'
        
        await self.handle_send(output)
            
    def change_state_connecting_ble(self, val):
        # When BLE connection is being changed...
        # Auto update the "Connect" button properties
        self.widgets['btn_connect'].setText('Disconnect' if val else 'Connect')
        self.widgets['btn_connect'].clicked.disconnect()
        self.widgets['btn_connect'].clicked.connect(self.handle_disconnect if val else self.handle_connect)
        
    @qasync.asyncSlot()
    async def change_state_selecting_ble(self):
        # When BLE device selection is being changed...
        # Auto update the "Connect" button availability only when user has at least select one item
        
        if self.widgets['list_devices'].currentItem() is None or self.widgets['list_devices'].currentRow() < 0:
            self.widgets['btn_connect'].setEnabled(False)
            return
        
        self.widgets['btn_connect'].setEnabled(True)
        
        # Continue if the user has selected a row
        selected_item = self.widgets['list_devices'].selectedItems()
        
        if not selected_item:
            return
            
        # Get the selected BLE name and address
        selected_index = self.widgets['list_devices'].row(selected_item[0])
        target_dev_name, addr = self.vars['devices_list'][selected_index]
        
        self.vars['current_dev_addr'] = addr
    
        # Get the system status update if the selected BLE is connected
        if addr in self.sensors and self.sensors[addr].is_connected:
            self.change_state_connecting_ble(True)
            await self.handle_manual_update()
        
        else:
            # Reset system status If the selected BLE is not connected
            self.change_state_connecting_ble(False)
            self.handle_clear_system_status()
            
    def change_state_checkbox_icm(self, mode, val):
        # When receiving state change from BLE
        # Only update UI widget if the state is not matched
        
        if mode == 0 and self.widgets['chkbox_raw_acc'].isChecked != val:       # 0: Raw Acc
            self.widgets['chkbox_raw_acc'].setChecked(val)
        elif mode == 1 and self.widgets['chkbox_cal_acc'].isChecked != val:     # 1: Cal Acc
            self.widgets['chkbox_cal_acc'].setChecked(val)
        elif mode == 2 and self.widgets['chkbox_lin_acc'].isChecked != val:     # 2: Lin Acc
            self.widgets['chkbox_lin_acc'].setChecked(val)
        elif mode == 3 and self.widgets['chkbox_raw_gyr'].isChecked != val:     # 3: Raw Gyr
            self.widgets['chkbox_raw_gyr'].setChecked(val)            
        elif mode == 4 and self.widgets['chkbox_cal_gyr'].isChecked != val:     # 4: Cal Gyr
            self.widgets['chkbox_cal_gyr'].setChecked(val)
        elif mode == 5 and self.widgets['chkbox_raw_mag'].isChecked != val:     # 5: Raw Mag
            self.widgets['chkbox_raw_mag'].setChecked(val)
        elif mode == 6 and self.widgets['chkbox_cal_mag'].isChecked != val:     # 6: Cal Mag
            self.widgets['chkbox_cal_mag'].setChecked(val)
        elif mode == 7 and self.widgets['chkbox_quat_vec'].isChecked != val:     # 7: Quat Vec
            self.widgets['chkbox_quat_vec'].setChecked(val)
        elif mode == 8 and self.widgets['chkbox_quat_mag'].isChecked != val:     # 8: Quat Mag
            self.widgets['chkbox_quat_mag'].setChecked(val)
        else:
            return
        
    def change_state_checkbox_emg(self, mode):
        # When receiving state change from BLE
        # Only update UI widget if the state is not matched
        
        if mode == 2 != self.widgets['chkbox_emg'].checkState():           # Raw EMG + RMS
            self.widgets['chkbox_emg'].setCheckState(QtCore.Qt.CheckState.Checked)
        elif mode == 1 != self.widgets['chkbox_emg'].checkState():         # Raw EMG
            self.widgets['chkbox_emg'].setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
        elif mode == 0 != self.widgets['chkbox_emg'].checkState():
            self.widgets['chkbox_emg'].setCheckState(QtCore.Qt.CheckState.Unchecked)
        else:
            return
        
    @qasync.asyncSlot()
    async def clicked_checkbox_icm(self, mode):
        # User changed the checkbox state in UI
        # Send command to BLE to change state in device
        
        addr = self.vars['current_dev_addr']
        if not addr in self.sensors or not self.sensors[addr].is_connected:
            return
            
        if mode == 0:       # 0: Raw Acc
            widget = self.widgets['chkbox_raw_acc']
        elif mode == 1:     # 1: Cal Acc
            widget = self.widgets['chkbox_cal_acc']
        elif mode == 2:     # 2: Lin Acc
            widget = self.widgets['chkbox_lin_acc']
        elif mode == 3:     # 3: Raw Gyr
            widget = self.widgets['chkbox_raw_gyr']          
        elif mode == 4:     # 4: Cal Gyr
            widget = self.widgets['chkbox_cal_gyr']
        elif mode == 5:     # 5: Raw Mag
            widget = self.widgets['chkbox_raw_mag']
        elif mode == 6:     # 6: Cal Mag
            widget = self.widgets['chkbox_cal_mag']
        elif mode == 7:     # 7: Quat Vec
            widget = self.widgets['chkbox_quat_vec']
        elif mode == 8:     # 8: Quat Mag
            widget = self.widgets['chkbox_quat_mag']
        else:
            return
        
        val = 1 if widget.isChecked() else 0
        
        # Change enable state at the BLE device
        await self.handle_send(f'A,W,{mode},{val}')
        
        # Update variable storing stste of device
        mode_str = self.sensors[addr].list_str_icm_mode[mode]
        self.sensors[addr].icm_mode[mode_str] = val
        
    @qasync.asyncSlot()
    async def clicked_checkbox_emg(self, state):
        # User changed the checkbox state in UI
        # Send command to BLE to change state in device
        
        addr = self.vars['current_dev_addr']
        if not addr in self.sensors or not self.sensors[addr].is_connected:
            return
        
        state = self.widgets['chkbox_emg'].checkState()

        if state == QtCore.Qt.CheckState.Checked:
            val = 2
        elif state == QtCore.Qt.CheckState.PartiallyChecked:
            val = 1
        elif state == QtCore.Qt.CheckState.Unchecked:
            val = 0
        else:
            return
        
        # Change enable state at the BLE device
        await self.handle_send(f'A,w,{val}')
        
        # Update variable storing state of device
        self.sensors[addr].emg_mode = val
    
        
def main():
    # Load and shiw UI from QT Designer
    app = QtWidgets.QApplication(sys.argv)
    ui = UserInterface()
    ui.show()
    
    # app.exec()
    # # # Set up and run event loop for asyncio
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
