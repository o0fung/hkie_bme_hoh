from PyQt6 import QtWidgets, QtCore, QtGui

import gui_action
import sys
import logging
import asyncio
import qasync


def main():
    # Initiate application
    app = QtWidgets.QApplication(sys.argv)

    # Initiate async event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Setup the stylesheet
    with open('style.qss', 'r') as f:
        app.setStyleSheet(f.read())
    
    # Setup the user interface
    ui = gui_action.UserInterface()
    ui.init_ui(title='EMGS', app=app)   # Setup UI
    ui.init_emgs()                      # Setup emgs sensor
    ui.init_signals()                   # Setup signal connections
    ui.show()                           # Show the app
    ui.move(0, 0)                       # Move to top left corner
    
    # Run the application until termination
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    # Logging to inspect issues in BLE
    # logging.basicConfig(level=logging.DEBUG)
    main()
