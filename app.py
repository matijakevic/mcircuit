from descriptors import Descriptor, Gate, Not
import sys

from version import format_version

from PySide2.QtCore import Qt, QSize

from PySide2.QtWidgets import QCheckBox, QComboBox, QFormLayout, QMainWindow, QApplication, QSpinBox, QWidget


def make_spin_box(desc, attribute, min, max):
    value = getattr(desc, attribute)

    sb = QSpinBox()
    sb.setValue(value)
    sb.setMinimum(min)
    sb.setMaximum(max)

    def assigner(value):
        setattr(desc, attribute, value)

    sb.valueChanged.connect(assigner)

    return sb


def make_check_box(desc, attribute):
    value = getattr(desc, attribute)

    chk = QCheckBox()
    chk.setChecked(value)

    def assigner(value):
        setattr(desc, attribute, bool(value))

    chk.stateChanged.connect(assigner)

    return chk


def make_combo_box(desc, attribute, values):
    curr_value = getattr(desc, attribute)

    cb = QComboBox()

    for name, value in values.items():
        cb.addItem(name, value)
        if value == curr_value:
            cb.setCurrentText(name)

    def assigner(text):
        setattr(desc, attribute, values[text])

    cb.currentTextChanged.connect(assigner)

    return cb


class DescriptorEditor(QWidget):
    def __init__(self, descriptor):
        super().__init__()
        self.descriptor = descriptor
        self.setLayout(QFormLayout())

        self._make_widgets()

    def _make_widgets(self):
        desc = self.descriptor
        layout = self.layout()

        if isinstance(desc, Not):
            layout.addRow('Width:', make_spin_box(desc, 'width', 1, 64))
        elif isinstance(desc, Gate):
            layout.addRow('Width:', make_spin_box(desc, 'width', 1, 64))
            layout.addRow('Inputs:', make_spin_box(desc, 'num_inputs', 1, 64))
            layout.addRow('Negated:', make_check_box(desc, 'negated'))
            layout.addRow('Logic:', make_combo_box(desc, 'op', {
                'And': Gate.AND,
                'Or': Gate.OR,
                'Xor': Gate.XOR
            }))


class DiagramEditor:
    pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('mcircuit ' + format_version())
        self.setMinimumSize(640, 480)

        desc = Gate(Gate.AND)
        self.setCentralWidget(DescriptorEditor(desc))


def run_app():
    app = QApplication()
    window = MainWindow()
    window.show()
    return app.exec_()
