from PyQt6 import QtWidgets, QtCore, QtGui


class WaitDialog(QtWidgets.QDialog):
    """ Pop-up Modal Dialog to block UI with message """

    def __init__(self, parent: QtWidgets.QWidget=None, title='Working', message='Please wait...'):
        super().__init__(parent)

        # Disable the window toolbar (buttons for close/minimize/maximum dialog)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Dialog)
        # Block user interaction when the dialog is in effect
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QLabel(message))

        self.setLayout(layout)

        # A list of task id that the dialog is waiting
        self.tasks = []

    def block_init(self, id: str=None):
        print(f'>> block_init', id, self.tasks)
        # Add the unique task id if not present
        if id is not None and id not in self.tasks:
            self.tasks.append(id)

        # Show the dialog if it is hidden
        if self.isHidden():
            self.show()

    def block_stop(self, id: str=None):
        print(f'>> block_stop', id, self.tasks)
        # Remove the unique task id
        if id is not None and id in self.tasks:
            self.tasks.remove(id)

        # Close the UI blocking dialog if no tasks remain
        if not self.tasks:
            self.accept()
