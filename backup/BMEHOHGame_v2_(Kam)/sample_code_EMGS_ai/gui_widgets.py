from PyQt6 import QtWidgets, QtCore, QtGui

import ble_device
import default


class CustomTable(QtWidgets.QTableWidget):
    """ Table Widget with customized sizing and content update """

    def setup(self, object: ble_device.EmgsDevice, n_row: int=10):
        # Use the object as template to define column header
        self.header = object.param.keys()
        
        # Setup the table dimension and column header
        self.setRowCount(n_row)
        self.setColumnCount(len(object.param.keys()) + 1)
        self.setHorizontalHeaderLabels(list(object.param.keys()) + ['Setting'])
        
        # Enable multiple row selection
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        
        # Disable user editing the table
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Tracking sort state for each column, default False
        self.sort_states = {}

    def set_column_width(self, widths):
        # Provide a list of width setting in pixel for each column
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)
        
        # Adjust the TableWidget minimum width according to the updated columns
        table_width = self.verticalHeader().width() + sum(widths)
        table_height = self.horizontalHeader().height() + sum([self.rowHeight(i) for i in range(self.rowCount())])
        self.setMinimumSize(table_width, table_height)

    def set_value_by_device(self, row: int, object: ble_device.EmgsDevice):
        # Use the parameter of the provided object to fill the table on selected row
        for n, col in enumerate(self.header):
            value = str(object.param[col])          # object parameter value on specific column
            item = QtWidgets.QTableWidgetItem()     # displayable item on the respective table cell

            if col == 'Address':
                # BLE address column
                # Add Bluetooth icon before uuid address string
                icon = default.ICONS['bluetooth']
                item.setIcon(icon)
                item.setText(value)

            elif col == 'Status':
                # BLE connection status column
                # Replace status string with icon
                if value == 'Connected':
                    icon = default.ICONS['tick']
                    item.setIcon(icon)
                    item.setText('')
                elif value == 'Disconnected':
                    icon = default.ICONS['cross']
                    item.setIcon(icon)
                    item.setText('')
                else:
                    item.setText(value)

            elif col == 'Battery':
                # Only add icon if it has non-default value
                if not value == default.EMGS_BATTERY and value.endswith(' %'):
                    # Get the battery level in percentage integer
                    batt_lv = int(value.split(' ')[0])
                    if batt_lv >= 80:        # Full battery >80%
                        icon = default.ICONS['battery-full']
                    elif 40 <= batt_lv <= 80:       # Normal battery >40%
                        icon = default.ICONS['battery']
                    elif 10 <= batt_lv <= 40:       # Low battery <40%
                        icon = default.ICONS['battery-low']
                    elif batt_lv <= 10:        # Empty battery <10%
                        icon = default.ICONS['battery-empty']

                    if object.is_charging:          # Charging battery
                        icon = default.ICONS['battery-charge']
                
                    item.setIcon(icon)

                item.setText(value)

            elif col == 'Mode':
                # Only add icon if it has non-default value
                if not value == default.EMGS_MODE:
                    value_split = value.split(' ')
                    mode_letters = value_split[0] if value_split else ''
                    linear = len(value_split) > 1 and value_split[1] == '(Linear)'
                    png_list = []

                    for letter in ['g', 'a', 'm', 'e', 'q']:
                        if letter in mode_letters or letter.upper() in mode_letters:

                            # Linear special case for 'a'/'A'
                            if letter == 'a' and linear and ('a' in mode_letters or 'A' in mode_letters):
                                png_list.append('icon/alpha-a-circle.512.png')

                            else:
                                # General IMU enable modes
                                idx = mode_letters.find(letter)
                                idx_upper = mode_letters.find(letter.upper())

                                if idx != -1 and (idx_upper == -1 or idx < idx_upper):
                                    # Lowercase present first
                                    png_list.append(f'icon/alpha-{letter}-box-outline.512.png')
                                
                                else:
                                    # Uppercase present
                                    png_list.append(f'icon/alpha-{letter}-box.512.png')
                        else:
                            # Not present
                            png_list.append(f'icon/alpha-{letter}.512.png')

                    # Insert the multi-icon widget to the table cell
                    self.setCellWidget(row, n, IconCell(png_list))
                    continue

                else:
                    item.setText(value)

            elif col == 'Timestamp':
                # Only add icon if it has non-default value
                if not value == default.EMGS_TIMESTAMP:
                    icon = default.ICONS['clock']
                    item.setIcon(icon)

                item.setText(value)

            else:
                # Other columns
                item.setText(value)

            self.setItem(row, n, item)

        # Setting button at the end of the table column
        btn = QtWidgets.QPushButton('Setting')
        btn.setEnabled(object.is_connect)
        btn.clicked.connect(lambda checked, dev=object: self.open_setting_dialog(dev))
        self.setCellWidget(row, len(self.header), btn)

    def sort_device_by_column(self, col, devices):
        # Only sort column within emgs device number of headers
        if col >= len(self.header):
            return
        
        # Get the column name the user choose to sort
        sort_key = list(self.header)[col]

        # Toggle sort order for this column
        ascending = self.sort_states.get(col, True)
        self.sort_states[col] = not ascending  # Toggle for next time

        # Sort devices by the selected column
        sorted_devices = sorted(
            devices.items(),
            key=lambda item: str(item[1].param[sort_key]),
            reverse=not ascending
        )
        # Return the sorted devices dictionary
        return dict(sorted_devices)
    
    def open_setting_dialog(self, object: ble_device.EmgsDevice):
        # Pop-up dialog for emgs device settings
        dialog = SettingDialog(object, parent=self)
        dialog.exec()
    
    def select_all_rows(self):
        # Select all rows where the Address column is not empty
        address_col = list(self.header).index('Address')
        self.clearSelection()
        for row in range(self.rowCount()):
            item = self.item(row, address_col)
            if item and item.text().strip():
                self.selectRow(row)

    def focusOutEvent(self, event):
        # When user clicked outside the table widget
        super().focusOutEvent(event)
        
        # Clear user selection if user clicked outside table widget
        self.clearSelection()

    def mousePressEvent(self, event):
        # When user clicked inside the table widget
        super().mousePressEvent(event)
        
        # Clear user selection if user clicked on empty row
        # Empty row defined as the Address column is empty string
        address_col = list(self.header).index('Address')
        for idx in self.selectionModel().selectedRows():
            item = self.item(idx.row(), address_col)
            if not item or not item.text().strip():
                self.clearSelection()
                break


class IconCell(QtWidgets.QWidget):
    """Widget to display multiple icons horizontally."""
    def __init__(self, icon_paths):
        super().__init__()

        # Initiate horizontal layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Memory to store labels with icons
        self.labels = []

        # Put icons to widget item
        self.set_icons(icon_paths)

    def set_icons(self, icon_paths):
        # Remove old labels
        for label in self.labels:
            label.setParent(None)
        self.labels.clear()

        # Add new labels
        for path in icon_paths:
            # Label with icon attached as pixmap
            label = QtWidgets.QLabel()
            icon = self.icon_with_white_bg(path, size=16)
            label.setPixmap(icon)
            
            # Add label to layout
            self.layout().addWidget(label)
            
            # Store label in memory
            self.labels.append(label)

        # Fill the remaining space of the cell with empty stretch
        self.layout().addStretch()

    def update_icons(self, new_paths):
        # Update the icons with new png file paths
        self.set_icons(new_paths)

    def icon_with_white_bg(self, path, size=32):
        """Create a QIcon with a white background from a PNG path."""
        # Make a pixmap and fill background with white
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtGui.QColor('white'))
        
        # Get the icon png with file path
        icon_pix = QtGui.QPixmap(path).scaled(size, size)
        
        # Get center of the pixmap
        x = (size - icon_pix.width()) // 2
        y = (size - icon_pix.height()) // 2

        # Center the icon in the white background
        painter = QtGui.QPainter(pixmap)
        painter.drawPixmap(x, y, icon_pix)
        painter.end()

        return pixmap


class SettingDialog(QtWidgets.QDialog):
    """ Pop-up dialog for control EMGS settings """
    def __init__(self, object: ble_device.EmgsDevice, parent=None):
        super().__init__(parent)

        # Dialog ui content
        self.setWindowTitle(f"Setting - {object.param['Name']} ({object.param['Address']})")
        self.setModal(True)
        
        # EMGS sensor
        self.emgs = object
        # Dialog UI control
        self.widgets = {}

        # Construct the UI
        self.init_dialog()

    def init_dialog(self):
        layout_vbox = QtWidgets.QVBoxLayout(self)

        # BLE configurations
        name_substr = self.emgs.param['Name'].split('EMGS')
        name = name_substr[1] if len(name_substr) > 1 else ''

        conn_t_min, conn_t_max = self.emgs.param['ConnT'].split(',')

        self.widgets['Textedit_ble_name'] = QtWidgets.QLineEdit(name)
        self.widgets['Textedit_connt_min'] = QtWidgets.QLineEdit(conn_t_min)
        self.widgets['Textedit_connt_max'] = QtWidgets.QLineEdit(conn_t_max)

        # GYR Mode selection
        mode = int(self.emgs.icm_mode[3]['state']) + int(self.emgs.icm_mode[4]['state']) * 2
        self.widgets['Combo_gyr_mode'] = QtWidgets.QComboBox()
        self.widgets['Combo_gyr_mode'].addItems(['OFF', 'RAW', 'CALIBRATE'])
        self.widgets['Combo_gyr_mode'].setCurrentIndex(mode)

        # ACC Mode selection
        mode = int(self.emgs.icm_mode[0]['state']) + int(self.emgs.icm_mode[1]['state']) * 2 + int(self.emgs.icm_mode[2]['state']) * 3
        self.widgets['Combo_acc_mode'] = QtWidgets.QComboBox()
        self.widgets['Combo_acc_mode'].addItems(['OFF', 'RAW', 'CALIBRATE', 'LINEAR'])
        self.widgets['Combo_acc_mode'].setCurrentIndex(mode)

        # MAG Mode selection
        mode = int(self.emgs.icm_mode[5]['state']) + int(self.emgs.icm_mode[6]['state']) * 2
        self.widgets['Combo_mag_mode'] = QtWidgets.QComboBox()
        self.widgets['Combo_mag_mode'].addItems(['OFF', 'RAW', 'CALIBRATE'])
        self.widgets['Combo_mag_mode'].setCurrentIndex(mode)

        # EMG Mode selection
        self.widgets['Combo_emg_mode'] = QtWidgets.QComboBox()
        self.widgets['Combo_emg_mode'].addItems(['OFF', 'EMG_RMS', 'EMG_RAW'])
        self.widgets['Combo_emg_mode'].setCurrentIndex(self.emgs.emg_mode)
        
        # QUAT Mode selection
        mode = int(self.emgs.icm_mode[7]['state']) + int(self.emgs.icm_mode[8]['state']) * 2
        self.widgets['Combo_quat_mode'] = QtWidgets.QComboBox()
        self.widgets['Combo_quat_mode'].addItems(['OFF', 'QUAT VECTOR', 'QUAT GEO MAG'])
        self.widgets['Combo_quat_mode'].setCurrentIndex(mode)

        # Layout
        layout_form = QtWidgets.QFormLayout()
        layout_form.addRow(QtWidgets.QLabel('BLE Name (EMGS_???)'), self.widgets['Textedit_ble_name'])
        layout_form.addRow(QtWidgets.QLabel('Connection Interval (min)'), self.widgets['Textedit_connt_min'])
        layout_form.addRow(QtWidgets.QLabel('Connection Interval (max)'), self.widgets['Textedit_connt_max'])
        layout_form.addRow(QtWidgets.QLabel('GYR Mode'), self.widgets['Combo_gyr_mode'])
        layout_form.addRow(QtWidgets.QLabel('ACC Mode'), self.widgets['Combo_acc_mode'])
        layout_form.addRow(QtWidgets.QLabel('MAG Mode'), self.widgets['Combo_mag_mode'])
        layout_form.addRow(QtWidgets.QLabel('EMG Mode'), self.widgets['Combo_emg_mode'])
        layout_form.addRow(QtWidgets.QLabel('QUAT Mode'), self.widgets['Combo_quat_mode'])
        
        layout_vbox.addLayout(layout_form)

        # OK/Cancel buttons
        self.widgets['ButtonBox_dialog'] = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.widgets['ButtonBox_dialog'].accepted.connect(self.accept)
        self.widgets['ButtonBox_dialog'].rejected.connect(self.reject)
        layout_vbox.addWidget(self.widgets['ButtonBox_dialog'])

    def accept(self):
        # User confirm the setting prompt dialog

        """ BLE Configuration (Connection Interval) """
        connt_min = self.widgets['Textedit_connt_min'].text()
        connt_max = self.widgets['Textedit_connt_max'].text()
        if connt_min.isnumeric() and connt_max.isnumeric():
            self.emgs.param['ConnT'] = f"{connt_min},{connt_max}"
        else:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Connection intervals must be numeric values.")
            return
        
        """ BLE Configuration (BLE Name) """
        ble_name_suffix = self.widgets['Textedit_ble_name'].text()
        self.emgs.param['Name'] = f'EMGS{ble_name_suffix}' if ble_name_suffix else 'EMGS'

        """ Sensor Mode """
        # Reset all mode
        for i in range(9):
            self.emgs.icm_mode[i]['state'] = False

        # ACC convert combo selection to mode code
        mode = self.widgets['Combo_acc_mode'].currentIndex()
        if mode:
            self.emgs.icm_mode[mode - 1]['state'] = True

        # GYR convert combo selection to mode code
        mode = self.widgets['Combo_gyr_mode'].currentIndex()
        if mode:
            self.emgs.icm_mode[mode + 2]['state'] = True

        # MAG convert combo selection to mode code
        mode = self.widgets['Combo_mag_mode'].currentIndex()
        if mode:
            self.emgs.icm_mode[mode + 4]['state'] = True

        # QUAT convert combo selection to mode code
        mode = self.widgets['Combo_quat_mode'].currentIndex()
        if mode:
            self.emgs.icm_mode[mode + 6]['state'] = True

        # EMG convert combo selection to mode code
        self.emgs.emg_mode = self.widgets['Combo_emg_mode'].currentIndex()

        self.emgs.convert_displayable_mode()

        # Trigger the emgs send command to set modes
        self.emgs.emit('update_set', self.emgs.param['Address'])

        super().accept()
