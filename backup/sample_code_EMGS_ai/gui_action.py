import gui_design
import ble_control
import qasync


class UserInterface(gui_design.UserInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track previously selected rows for LED indication
        self.previous_selected_rows = set()
        # Flag to prevent overlapping selection processing
        self._selection_processing = False

    def init_emgs(self):
        # Signals triggered by emgs operations
        # Run the update task in the background parallel to main event loop
        # After the task finished, the table widget will update and dialog will unblock
        self.emgs = ble_control.EmgsWorker()
        # emgs log signal
        self.emgs.signal_log.connect(self.log_message)
        # emgs scan signal
        self.emgs.signal_scan_start.connect(self.table_block)
        self.emgs.signal_scan_end.connect(self.table_unblock)
        self.emgs.signal_scan_end.connect(self.table_update)
        # emgs connect signal
        self.emgs.signal_connecting.connect(self.table_block)
        self.emgs.signal_connected.connect(self.table_unblock)
        self.emgs.signal_connected.connect(self.table_update)
        # emgs disconnect signal
        self.emgs.signal_disconnected.connect(self.table_unblock)
        self.emgs.signal_disconnected.connect(self.table_update)
        # emgs working with ui block signal
        self.emgs.signal_work_start.connect(self.table_block)
        self.emgs.signal_work_end.connect(self.table_unblock)
        # emgs data control
        self.emgs.signal_get_data.connect(self.table_update)
        self.emgs.signal_set_data.connect(self.emgs.handle_update_set)
    
    def init_signals(self):
        # Interact with toolbar buttons
        self.widgets['Action_scan'].triggered.connect(self.scan_devices)
        self.widgets['Action_connect'].triggered.connect(self.connect_devices)
        self.widgets['Action_disconnect'].triggered.connect(self.disconnect_devices)
        self.widgets['Action_update'].triggered.connect(self.update_devices)
        self.widgets['Action_select_all'].triggered.connect(self.widgets['Table_emgs'].select_all_rows)
        self.widgets['Action_timesync'].triggered.connect(self.timesync_devices)
        self.widgets['Action_stream'].triggered.connect(self.stream_devices)
        
        # Interact with table widget
        self.widgets['Table_emgs'].horizontalHeader().sectionClicked.connect(self.table_sort)
        self.widgets['Table_emgs'].itemSelectionChanged.connect(self.table_on_select)

    @qasync.asyncSlot()
    async def scan_devices(self):
        # Scan nearby emgs devices
        await self.emgs.task_scan()

    @qasync.asyncSlot()
    async def connect_devices(self):
        # Get a list of selected emgs devices to connect
        selected_devices_addr = [d.param['Address'] for d in self.table_get_devices() if not d.is_connect]
        await self.emgs.task_connect(selected_devices_addr)

    @qasync.asyncSlot()
    async def disconnect_devices(self, all=False):
        # Get a list of selected emgs devices to disconnect
        selected_devices_addr = [d.param['Address'] for d in self.table_get_devices() if all or d.is_connect]
        self.emgs.task_disconnect(selected_devices_addr)

    @qasync.asyncSlot()
    async def update_devices(self):
        # Get a list of selected emgs devices to update device parameters
        selected_devices_addr = [d.param['Address'] for d in self.table_get_devices() if d.is_connect]
        await self.emgs.task_update(selected_devices_addr)

    @qasync.asyncSlot()
    async def timesync_devices(self):
        # Get a list of selected emgs devices to update timestamp
        selected_devices_addr = [d.param['Address'] for d in self.table_get_devices() if d.is_connect]
        await self.emgs.task_timesync(selected_devices_addr)

    @qasync.asyncSlot()
    async def stream_devices(self):
        # Get a list of selected emgs devices to update timestamp
        selected_devices_addr = [d.param['Address'] for d in self.table_get_devices() if d.is_connect]
        await self.emgs.task_stream(selected_devices_addr)

    async def indicate_devices(self):
        # Get UI state, whether user is selecting device (clicked) or not
        selected_rows = set(idx.row() for idx in self.widgets['Table_emgs'].selectedIndexes())
        selected_devices_addr = []
        unselected_devices_addr = []
        for n, addr in enumerate(self.emgs.devices):
            dev = self.emgs.devices[addr]
            if dev.is_connect:
                if n in selected_rows:
                    selected_devices_addr.append(addr)
                else:
                    unselected_devices_addr.append(addr)

        await self.emgs.task_indicator_led(addrs=selected_devices_addr, state='purple')
        await self.emgs.task_indicator_led(addrs=unselected_devices_addr, state='off')

    def table_block(self, id=None):
        # Show a blocking dialog to prevent user interaction
        self.widgets['Dialog_wait'].block_init(id)

    def table_unblock(self, id=None):
        # Terminate the blocking dialog for user interaction
        self.widgets['Dialog_wait'].block_stop(id)

    def table_update(self, id=None):
        # Dereference customized widget before clearContents
        # Avoid memory leak due to accumulated widget not deleted
        table =  self.widgets['Table_emgs']
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                widget = table.cellWidget(row, col)
                if widget is not None:
                    # Remove cell widget items
                    table.removeCellWidget(row, col)
                    widget.deleteLater()        # Marks for deletion when safe

        # Reset the content of the table widget
        table.clearContents()
        # Load all info of emgs devices to the table widget
        for i, addr in enumerate(self.emgs.devices):
            table.set_value_by_device(i, self.emgs.devices[addr])

    def table_sort(self, col):
        # Sort the content of the table widget according to the column values
        self.emgs.devices = self.widgets['Table_emgs'].sort_device_by_column(col, self.emgs.devices)
        self.table_update()

    def table_get_devices(self):
        # Get a list of selected rows of the table widget
        selected_rows = set(idx.row() for idx in self.widgets['Table_emgs'].selectedIndexes())
        
        # Get a list of emgs devices that are selected by the user
        selected_devices = []
        for n, addr in enumerate(self.emgs.devices):
            if n in selected_rows:
                selected_devices.append(self.emgs.devices[addr])

        return selected_devices

    @qasync.asyncSlot()
    async def table_on_select(self):
        # Enable ToolButton if there is any selection on emgs devices
        has_selection = len(self.widgets['Table_emgs'].selectedIndexes()) > 0
        self.widgets['Action_connect'].setEnabled(has_selection)
        self.widgets['Action_disconnect'].setEnabled(has_selection)
        self.widgets['Action_update'].setEnabled(has_selection)
        self.widgets['Action_timesync'].setEnabled(has_selection)
        self.widgets['Action_stream'].setEnabled(has_selection)

        # Prevent overlapping selection processing
        if self._selection_processing:
            return
        
        self._selection_processing = True
        try:
            await self.indicate_devices()
        finally:
            self._selection_processing = False

    def log_message(self, message, history=False):
        # An option to clear the log area and start fresh
        if not history:
            self.widgets['TextEdit_log'].clear()

        # Show debug message at the log area
        self.widgets['TextEdit_log'].append(message)

    def test(self):
        # Show debug message at the terminal
        print('test')

    def closeEvent(self, event):
        # Disconnect all devices synchronously to avoid pending tasks
        for addr in self.emgs.devices:
            if self.emgs.devices[addr].is_connect:
                self.emgs.devices[addr].reset()  # Force immediate disconnection
        return super().closeEvent(event)
