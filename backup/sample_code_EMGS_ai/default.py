from PyQt6 import QtWidgets, QtCore, QtGui


# Default EMGS device parameters
EMGS_NAME = '/'
EMGS_ADDR = '/'
EMGS_STATUS = 'Disconnected'
EMGS_BATTERY = '/'
EMGS_TIMESTAMP = '/'
EMGS_MODE = '/'
EMGS_FIRMWARE = '/'
EMGS_HARDWARE = '/'
EMGS_DSP = '/'
EMGS_CONNT = '/'

EMGS_BATTERY_LOW_VOLTAGE = 3.10 * 50.0
EMGS_BATTERY_HIGH_VOLTAGE = 4.15 * 50.0

# Default EMGS device table widget configuration
TABLE_N_ROW = 15
TABLE_COL_WIDTH = [
    100,     # Name
    350,    # Address
    40,     # Status
    200,    # Timestamp
    100,    # Battery
    150,    # Mode
    60,     # Firmware
    60,     # Hardware
    60,     # DSP
    60,     # ConnT
    100,    # Setting button
    ]


def init_icons():
    global ICONS
    
    ICONS = {
        'bluetooth': QtGui.QIcon('./icon/bluetooth.png'),
        'magnifier': QtGui.QIcon('./icon/magnifier.png'),
        'node-select-all': QtGui.QIcon('./icon/node-select-all.png'),
        'tick': QtGui.QIcon('./icon/tick.png'),
        'cross': QtGui.QIcon('./icon/cross.png'),
        'battery-full': QtGui.QIcon('./icon/battery-full.png'),
        'battery': QtGui.QIcon('./icon/battery.png'),
        'battery-charge': QtGui.QIcon('./icon/battery-charge.png'),
        'battery-low': QtGui.QIcon('./icon/battery-low.png'),
        'battery-empty': QtGui.QIcon('./icon/battery-empty.png'),
        'clock': QtGui.QIcon('./icon/clock.png'),
        'plug-disconnect': QtGui.QIcon('./icon/plug-disconnect.png'),
        'tick-white': QtGui.QIcon('./icon/tick-white.png'),
        'system-monitor': QtGui.QIcon('./icon/system-monitor.png'),
    }
