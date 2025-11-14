from PyQt6 import QtWidgets, QtCore, QtGui

import default

import gui_widgets
import gui_dialogs
import ble_device


class UserInterface(QtWidgets.QMainWindow):
    
    def init_ui(self, title: str, app: QtWidgets.QApplication):

        default.init_icons()

        # UI configuration
        self.setWindowTitle(title)
        self.app = app
        self.widgets = {}
        
        self.addToolBar(self.toolbar_top())         # Header
        self.setCentralWidget(self.content_top())   # Content
        self.setStatusBar(QtWidgets.QStatusBar())   # Footer

    def toolbar_top(self):
        # Toolbar (Header) configuration
        toolbar = QtWidgets.QToolBar('EMGS')
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        self.widgets['Action_scan'] = QtGui.QAction(icon=default.ICONS['magnifier'], text='Scan')
        self.widgets['Action_scan'].setEnabled(True)
        self.widgets['Action_scan'].setStatusTip('Quick scan nearby EMGS')
        toolbar.addAction(self.widgets['Action_scan'])
        
        self.widgets['Action_select_all'] = QtGui.QAction(icon=default.ICONS['node-select-all'], text='Select All')
        self.widgets['Action_select_all'].setEnabled(True)
        self.widgets['Action_select_all'].setStatusTip('Select all EMGS from the table')
        toolbar.addAction(self.widgets['Action_select_all'])

        self.widgets['Action_connect'] = QtGui.QAction(icon=default.ICONS['bluetooth'], text='Connect')
        self.widgets['Action_connect'].setEnabled(False)
        self.widgets['Action_connect'].setStatusTip('Quick connect to discovered EMGS')
        toolbar.addAction(self.widgets['Action_connect'])

        self.widgets['Action_disconnect'] = QtGui.QAction(icon=default.ICONS['plug-disconnect'], text='Disconnect')
        self.widgets['Action_disconnect'].setEnabled(False)
        self.widgets['Action_disconnect'].setStatusTip('Disconnect from EMGS')
        toolbar.addAction(self.widgets['Action_disconnect'])

        self.widgets['Action_update'] = QtGui.QAction(icon=default.ICONS['tick-white'], text='Update')
        self.widgets['Action_update'].setEnabled(False)
        self.widgets['Action_update'].setStatusTip('Update device parameters of the selected EMGS')
        toolbar.addAction(self.widgets['Action_update'])

        self.widgets['Action_timesync'] = QtGui.QAction(icon=default.ICONS['clock'], text='Time Sync')
        self.widgets['Action_timesync'].setEnabled(False)
        self.widgets['Action_timesync'].setStatusTip('Update timestamp of the selected EMGS')
        toolbar.addAction(self.widgets['Action_timesync'])

        self.widgets['Action_stream'] = QtGui.QAction(icon=default.ICONS['system-monitor'], text='Data Stream')
        self.widgets['Action_stream'].setEnabled(False)
        self.widgets['Action_stream'].setStatusTip('Start/Stop data stream of the connected EMGS')
        toolbar.addAction(self.widgets['Action_stream'])

        self.widgets['Action_stream'] = QtGui.QAction(icon=default.ICONS['system-monitor'], text='Data Stream')
        self.widgets['Action_stream'].setEnabled(False)
        self.widgets['Action_stream'].setStatusTip('Start/Stop data stream of the connected EMGS')
        toolbar.addAction(self.widgets['Action_stream'])

        self.widgets['Toolbar_top'] = toolbar
        return toolbar
    
    def content_top(self):
        # Content in the form of tabs
        tab = QtWidgets.QTabWidget()
        tab.addTab(self.page_connect(), 'EMGS')
        tab.addTab(self.page_data(), 'Data')
        tab.addTab(self.page_setting(), 'Setting')

        self.widgets['Central'] = tab
        return tab
        
    def page_connect(self):
        page = QtWidgets.QWidget()

        layout_vbox = QtWidgets.QVBoxLayout()

        # Table of EMGS
        self.widgets['Table_emgs'] = gui_widgets.CustomTable()
        self.widgets['Table_emgs'].setup(object=ble_device.EmgsDevice(), n_row=default.TABLE_N_ROW)
        layout_vbox.addWidget(self.widgets['Table_emgs'])
        # Wait Dialog on Table Widget
        self.widgets['Dialog_wait'] = gui_dialogs.WaitDialog(parent=self.widgets['Table_emgs'])

        # Log Status
        self.widgets['TextEdit_log'] = QtWidgets.QTextEdit()
        self.widgets['TextEdit_log'].setReadOnly(True)
        layout_vbox.addWidget(self.widgets['TextEdit_log'])

        page.setLayout(layout_vbox)

        self.widgets['Page_connect'] = page
        return page
    
    def page_data(self):
        page = QtWidgets.QWidget()
        
        self.widgets['Page_data'] = page
        return page
    
    def page_setting(self):
        page = QtWidgets.QWidget()

        layout_vbox = QtWidgets.QVBoxLayout()

        page.setLayout(layout_vbox)
        
        self.widgets['Page_setting'] = page
        return page
    
    def keyPressEvent (self, event: QtGui.QKeyEvent):
        # Key Press Event
        if event.key() == QtCore.Qt.Key.Key_Escape:
            # Press Esc to close program
            self.close()

    def showEvent(self, event: QtGui.QShowEvent):
        # When the app is loaded and UI has been generated
        super().showEvent(event)

        # Adjust the size of the TableWidget after the windows is shown
        default_column_widths = default.TABLE_COL_WIDTH
        self.widgets['Table_emgs'].set_column_width(default_column_widths)
