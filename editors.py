from PySide6.QtWidgets import *
from PySide6.QtCore import *
from diagram import EAST, NORTH, SOUTH, WEST
from core.descriptors import ExposedPin, Gate, Not


def make_line_edit(desc, attribute, callback=None):
    value = getattr(desc, attribute)

    le = QLineEdit()
    le.setText(value)

    def assigner():
        txt = le.text().strip()
        le.setText(txt)
        setattr(desc, attribute, txt)
        if callback is not None:
            callback()

    le.editingFinished.connect(assigner)

    return le


def make_spin_box(desc, attribute, min, max, callback=None):
    value = getattr(desc, attribute)

    sb = QSpinBox()
    sb.setValue(value)
    sb.setMinimum(min)
    sb.setMaximum(max)

    def assigner(value):
        setattr(desc, attribute, value)
        if callback is not None:
            callback()

    sb.valueChanged.connect(assigner)

    return sb


def make_check_box(desc, attribute, callback=None):
    value = getattr(desc, attribute)

    chk = QCheckBox()
    chk.setChecked(value)

    def assigner(value):
        setattr(desc, attribute, bool(value))
        if callback is not None:
            callback()

    chk.stateChanged.connect(assigner)

    return chk


def make_combo_box(desc, attribute, values, callback=None):
    curr_value = getattr(desc, attribute)

    cb = QComboBox()

    for name, value in values.items():
        cb.addItem(name, value)
        if value == curr_value:
            cb.setCurrentText(name)

    def assigner(text):
        setattr(desc, attribute, values[text])
        if callback is not None:
            callback()

    cb.currentTextChanged.connect(assigner)

    return cb


class ElementPropertyEditor(QWidget):
    edited = Signal()

    def __init__(self, element):
        super().__init__()
        self.element = element
        self.setLayout(QFormLayout())

        self._make_widgets()

    def _make_widgets(self):
        element = self.element
        desc = element.descriptor
        layout = self.layout()

        def emit_edited():
            self.edited.emit()

        layout.addRow('Name:', make_line_edit(
            element, 'name', callback=emit_edited))

        layout.addRow('Facing:', make_combo_box(element, 'facing', {
            'East': EAST,
            'North': NORTH,
            'West': WEST,
            'South': SOUTH
        }, callback=emit_edited))

        if isinstance(desc, Not):
            layout.addRow('Width:', make_spin_box(
                desc, 'width', 1, 64, callback=emit_edited))
        elif isinstance(desc, Gate):
            layout.addRow('Width:', make_spin_box(
                desc, 'width', 1, 64, callback=emit_edited))
            layout.addRow('Inputs:', make_spin_box(
                desc, 'num_inputs', 2, 64, callback=emit_edited))
            layout.addRow('Negated:', make_check_box(
                desc, 'negated', callback=emit_edited))
            layout.addRow('Logic:', make_combo_box(desc, 'op', {
                'And': Gate.AND,
                'Or': Gate.OR,
                'Xor': Gate.XOR
            }, callback=emit_edited))
        elif isinstance(desc, ExposedPin):
            layout.addRow('Width:', make_spin_box(
                desc, 'width', 1, 64, callback=emit_edited))
            layout.addRow('Direction:', make_combo_box(desc, 'direction', {
                'In': ExposedPin.IN,
                'Out': ExposedPin.OUT,
            }, callback=emit_edited))
