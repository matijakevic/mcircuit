from collections import defaultdict
from itertools import chain
import math
from simulator import JIT
from typing import Text
from PySide2.QtCore import QLine, QLineF, QMargins, QPoint, QRect, QStateMachine, QTime, QTimer, Qt, Signal
from PySide2.QtGui import QColor, QKeySequence, QMouseEvent, QPainter, QPalette, QPen, QStandardItem, QStandardItemModel, QTransform, QVector2D
from diagram import Diagram, EAST, Element, NORTH, SOUTH, WEST, rotate
from descriptors import ExposedPin, Gate, Not

from version import format_version

from PySide2.QtWidgets import QAction, QCheckBox, QComboBox, QCommonStyle, QDockWidget, QFormLayout, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QApplication, QMenu, QMenuBar, QPushButton, QShortcut, QSpinBox, QStyle, QStyleFactory, QToolBar, QTreeView, QTreeWidget, QTreeWidgetItem, QWidget


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


class ElementEditor(QWidget):
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


class DiagramEditor(QWidget):
    EDIT, VIEW = range(2)
    NONE, ELEMENT_CLICK, EMPTY_CLICK, WIRE, DRAG, SELECT, PLACE, CLICK, MOVE = range(
        9)

    element_selected = Signal(Element)

    def __init__(self, diagram, grid_size=16):
        super().__init__()
        self.diagram = diagram
        self.grid_size = grid_size
        self.executor = None

        self._translation = QPoint()

        self._mode = DiagramEditor.EDIT
        self._state = DiagramEditor.NONE

        self._cursor_pos = QPoint()

        self._selected_element = None
        self._placing_element = None
        self._start = None
        self._end = None

        mode_action = QShortcut(QKeySequence(Qt.Key_E), self)
        delete_action = QShortcut(QKeySequence(Qt.Key_Delete), self)
        cancel_action = QShortcut(QKeySequence(Qt.Key_Escape), self)

        def delete_element():
            if self._state == DiagramEditor.SELECT:
                self.diagram.remove_element(self._selected_element)
                self._state = DiagramEditor.NONE
                self.update()

        delete_action.activated.connect(delete_element)

        def cancel():
            self._state = DiagramEditor.NONE
            if self._mode == DiagramEditor.VIEW:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            self.update()

        cancel_action.activated.connect(cancel)

        def switch_mode():
            self._mode = DiagramEditor.EDIT if self._mode == DiagramEditor.VIEW else DiagramEditor.VIEW
            self._state = DiagramEditor.NONE
            if self._mode == DiagramEditor.VIEW:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            self.update()

        mode_action.activated.connect(switch_mode)

        self.setMouseTracking(True)

    def _get_wire(self):
        if self._state != DiagramEditor.WIRE:
            return None
        ws, we = self._start, self._end
        delta = we - ws
        if delta == QPoint():
            return None

        if abs(delta.x()) > abs(delta.y()):
            yield (ws.x(), ws.y(), we.x(), ws.y())
            yield (we.x(), ws.y(), we.x(), we.y())
        else:
            yield (ws.x(), ws.y(), ws.x(), we.y())
            yield (ws.x(), we.y(), we.x(), we.y())

    def start_placing(self, element):
        self._state = DiagramEditor.PLACE
        self._placing_element = element

    def element_at_pos(self, pos):
        gs = self.grid_size

        for element in self.diagram.elements:
            facing = element.facing
            x, y = element.position
            xb, yb, w, h = element.bounding_rect

            transform = QTransform()
            transform.translate(x * gs, y * gs)
            transform.rotate(facing * -90)

            r = QRect(xb * gs, yb * gs, w * gs, h * gs)
            r = transform.mapRect(r)

            for p, _ in chain(element.all_inputs(),
                              element.all_outputs()):
                rx, ry = rotate(x, y, facing)
                pt = QPoint(p[0] + rx, p[1] + ry) * gs
                if QVector2D(pt - pos).length() <= self.grid_size / 2:
                    return None

            if r.contains(pos):
                return element

        return None

    def mousePressEvent(self, event: QMouseEvent):
        gs = self.grid_size
        d = event.pos() - self._translation
        p = QPoint(round(d.x() / gs), round(d.y() / gs))

        if self._mode == DiagramEditor.VIEW:
            self._state = DiagramEditor.CLICK
            self._start = d
            self._end = d
            self.update()
            return

        if self._state == DiagramEditor.NONE:
            selected_element = self.element_at_pos(d)
            if selected_element is not None:
                self._state = DiagramEditor.ELEMENT_CLICK
                self._selected_element = selected_element
                self.element_selected.emit(selected_element)
            else:
                self._state = DiagramEditor.EMPTY_CLICK
            self._start = p
            self._end = p
            self.update()
        elif self._state == DiagramEditor.SELECT:
            selected_element = self.element_at_pos(d)
            if selected_element is None:
                self._state = DiagramEditor.EMPTY_CLICK
                self.element_selected.emit(selected_element)
                self.update()
            else:
                if self._selected_element is not selected_element:
                    self.element_selected.emit(selected_element)
                    self._selected_element = selected_element
                self._state = DiagramEditor.ELEMENT_CLICK
                self.update()
            self._start = p
            self._end = p
        elif self._state != DiagramEditor.PLACE:
            self._state = DiagramEditor.NONE
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        d = event.pos() - self._translation
        gs = self.grid_size
        p = QPoint(round(d.x() / gs), round(d.y() / gs))
        self._cursor_pos = (event.pos() / self.grid_size) * self.grid_size
        self.update()

        if self._mode == DiagramEditor.VIEW:
            if self._state == DiagramEditor.CLICK:
                self._state = DiagramEditor.MOVE
                self.setCursor(Qt.ClosedHandCursor)
                self._end = d
                self.update()
            elif self._state == DiagramEditor.MOVE:
                self.setCursor(Qt.ClosedHandCursor)
                self._end = d
                self.update()
            return

        if self._state == DiagramEditor.PLACE:
            self._placing_element.position = (p.x(), p.y())
            self.update()
        elif self._state == DiagramEditor.ELEMENT_CLICK:
            self._state = DiagramEditor.DRAG
            self._end = p
            self.update()
        elif self._state == DiagramEditor.DRAG:
            self._end = p
            self.update()
        elif self._state == DiagramEditor.EMPTY_CLICK:
            self._state = DiagramEditor.WIRE
            self._end = p
            self.update()
        elif self._state == DiagramEditor.WIRE:
            self._end = p
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._mode == DiagramEditor.VIEW:
            if self._state == DiagramEditor.MOVE:
                self.setCursor(Qt.PointingHandCursor)
                self._state = DiagramEditor.NONE
                self._translation += self._end - self._start
                self.update()
            elif self._state == DiagramEditor.CLICK:
                self._state = DiagramEditor.NONE
                # TODO: interact
                self.update()
            return

        if self._state == DiagramEditor.PLACE:
            self._state = DiagramEditor.SELECT
            self.diagram.add_element(self._placing_element)
            self._selected_element = self._placing_element
            self.element_selected.emit(self._selected_element)
            self.update()
        elif self._state == DiagramEditor.DRAG:
            el = self._selected_element
            pos = QPoint(*el.position)
            pos += self._end - self._start
            el.position = (pos.x(), pos.y())
            self._state = DiagramEditor.NONE
            self.update()
        elif self._state == DiagramEditor.WIRE:
            wires = self._get_wire()
            if wires is not None:
                self.diagram.change_wires(wires)
            self._state = DiagramEditor.NONE
            self.update()
        elif self._state == DiagramEditor.ELEMENT_CLICK:
            self._state = DiagramEditor.SELECT
            self.update()
        elif self._state == DiagramEditor.EMPTY_CLICK:
            self._state = DiagramEditor.NONE
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        back_col = QApplication.palette().color(QPalette.Base)
        tex_col = QApplication.palette().color(QPalette.WindowText)
        wid_col = back_col
        grid_col = tex_col
        wire_col = tex_col
        cur_col = tex_col

        painter.fillRect(self.rect(), wid_col)

        if self._mode == DiagramEditor.VIEW and self._state == DiagramEditor.MOVE:
            trans = self._translation + self._end - self._start
        else:
            trans = self._translation

        painter.translate(trans)
        painter.setPen(QPen(grid_col, 1))
        ttrans = trans / self.grid_size
        tx, ty = ttrans.x() * self.grid_size, ttrans.y() * self.grid_size
        for x in range(0, self.width(), self.grid_size):
            for y in range(0, self.height(), self.grid_size):
                painter.drawPoint(x - tx, y-ty)

        gs = self.grid_size

        for element in self.diagram.elements:
            facing = element.facing
            x, y = element.position
            xb, yb, w, h = element.bounding_rect

            if self._state == DiagramEditor.DRAG and self._selected_element is element:
                continue

            painter.save()
            painter.translate(x * gs, y * gs)
            painter.rotate(facing * -90)

            painter.fillRect(xb * gs, yb * gs, w * gs, h * gs, Qt.white)
            painter.setPen(QPen(Qt.black, 2.0))
            painter.drawRect(xb * gs, yb * gs, w * gs, h * gs)

            if self._state == DiagramEditor.SELECT and self._selected_element is element:
                r = QRect(xb * gs, yb * gs, w * gs, h * gs)
                r = r.marginsAdded(QMargins(*(5,)*4))
                painter.setPen(QPen(Qt.red, 1.0))
                painter.drawRect(r)

            for pos, name in chain(element.all_inputs(),
                                   element.all_outputs()):
                state = -1
                if self.executor is not None:
                    state = self.executor.get_pin_state(
                        element.name + '.' + name)
                if state == -1:
                    painter.setPen(QPen(Qt.blue, 6.0))
                elif state == 0:
                    painter.setPen(QPen(Qt.black, 6.0))
                else:
                    painter.setPen(QPen(Qt.green, 6.0))
                p = QPoint(pos[0], pos[1]) * gs
                painter.drawPoint(p)

            painter.restore()

        if self._state in (DiagramEditor.DRAG, DiagramEditor.PLACE):
            if self._state == DiagramEditor.DRAG:
                element = self._selected_element
                delta = self._end - self._start
                x, y = element.position
                x += delta.x()
                y += delta.y()
            else:
                element = self._placing_element
                x, y = element.position
            facing = element.facing
            xb, yb, w, h = element.bounding_rect

            ghost_black = QColor.fromRgbF(0.0, 0.0, 0.0, 0.5)
            ghost_white = QColor.fromRgbF(1.0, 1.0, 1.0, 0.5)

            painter.save()
            painter.translate(x * gs, y * gs)
            painter.rotate(facing * -90)

            painter.fillRect(xb * gs, yb * gs, w * gs, h * gs, ghost_white)
            painter.setPen(QPen(ghost_black, 2.0))
            painter.drawRect(xb * gs, yb * gs, w * gs, h * gs)

            pins = list()
            for pos, _ in chain(element.all_inputs(),
                                element.all_outputs()):
                pins.append(QPoint(pos[0], pos[1]) * gs)

            painter.setPen(QPen(ghost_black, 6.0))
            painter.drawPoints(pins)

            painter.restore()

        wires = list()

        if self._state == DiagramEditor.WIRE:
            curr_wires = self._get_wire()
            if curr_wires is not None:
                wiremap = self.diagram.construct_wires(curr_wires)
            else:
                wiremap = self.diagram.wires
        else:
            wiremap = self.diagram.wires

        for pos, node in wiremap.items():
            for dir in range(4):
                if node.connections[dir]:
                    p1 = QPoint(*pos) * gs
                    p2 = QPoint(*rotate(1, 0, dir)) * gs + p1
                    wires.append(QLine(p1, p2))

        painter.setPen(QPen(wire_col, 2.0))
        painter.drawLines(wires)

        if self._state not in (DiagramEditor.DRAG, DiagramEditor.PLACE):
            painter.setPen(QPen(cur_col, 2.0))
            painter.drawArc(self._cursor_pos.x() - tx - 6,
                            self._cursor_pos.y() - ty - 6, 12, 12, 0, 360 * 16)


def element_factory(cls, name, *args, **kwargs):
    counter = 0

    def wrapper():
        nonlocal counter
        counter += 1
        elem_name = name + '_' + str(counter)
        element = Element(elem_name, cls(*args, **kwargs))
        return element

    return wrapper


LIBRARY = {
    'Wiring': {
        'Input': element_factory(ExposedPin, 'input', ExposedPin.IN),
        'Output': element_factory(ExposedPin, 'output', ExposedPin.OUT),
    },
    'Gates': {
        'NOT Gate': element_factory(Not, 'not'),
        'AND Gate': element_factory(Gate, 'and', Gate.AND),
        'OR Gate': element_factory(Gate, 'or', Gate.OR),
        'XOR Gate':  element_factory(Gate, 'xor', Gate.XOR),
        'NAND Gate':  element_factory(Gate, 'nand', Gate.AND, negated=True),
        'NOR Gate':  element_factory(Gate, 'nor', Gate.OR, negated=True),
        'XNOR Gate':  element_factory(Gate, 'xnor', Gate.XOR, negated=True),
    }
}


class ElementTree:
    pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('mcircuit ' + format_version())
        self.setMinimumSize(640, 480)

        menu_bar = QMenuBar()
        self.setMenuBar(menu_bar)

        file_menu = QMenu('File')
        file_menu.addAction('New')
        file_menu.addAction('Open...')
        file_menu.addSeparator()
        file_menu.addAction('Save')
        file_menu.addAction('Save As...')
        file_menu.addSeparator()
        file_menu.addAction('Exit')

        menu_bar.addMenu(file_menu)

        project_menu = QMenu('Project')

        diagram_count = 1

        def new_diagram():
            nonlocal diagram_count
            d = Diagram('diagram_' + str(diagram_count))
            diagram_count += 1
            it = QListWidgetItem(d.name)
            it.setData(Qt.UserRole, d)
            diagram_tree.addItem(it)

        project_menu.addAction('New Diagram', new_diagram)

        menu_bar.addMenu(project_menu)

        diagram_tree_dock = QDockWidget('Diagrams')
        diagram_tree = QListWidget()

        def change_diagram(item):
            diag.diagram = item.data(Qt.UserRole)
            diag.update()

        counter = defaultdict(int)

        def add_custom_element(item):
            nonlocal counter
            diagram = item.data(Qt.UserRole)
            base_name = item.text()
            counter[base_name] += 1
            schematic = diagram.schematic
            element = Element(base_name + '_' +
                              str(counter[base_name]), schematic)
            diag.start_placing(element)

        def add_element(item):
            factory = item.data(0, Qt.UserRole)
            element = factory()
            diag.start_placing(element)

        diagram_tree.itemClicked.connect(add_custom_element)
        diagram_tree.itemDoubleClicked.connect(change_diagram)
        diagram_tree_dock.setWidget(diagram_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, diagram_tree_dock)

        element_tree_dock = QDockWidget('Elements')
        element_tree = QTreeWidget()
        element_tree.setHeaderHidden(True)

        for root_name, children in LIBRARY.items():
            root_item = QTreeWidgetItem()
            root_item.setText(0, root_name)

            for name, factory in children.items():
                child_item = QTreeWidgetItem()
                child_item.setText(0, name)
                child_item.setData(0, Qt.UserRole, factory)
                root_item.addChild(child_item)

            element_tree.addTopLevelItem(root_item)

        element_tree.expandAll()
        element_tree.itemClicked.connect(add_element)
        element_tree_dock.setWidget(element_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, element_tree_dock)

        element_editor_dock = QDockWidget('Element editor')
        element_editor_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.LeftDockWidgetArea, element_editor_dock)

        toolbar = QToolBar('Toolbar')
        toolbar.setMovable(False)
        simulate_btn = QPushButton('Start')
        toolbar.addWidget(simulate_btn)
        self.addToolBar(toolbar)

        view_menu = self.createPopupMenu()
        view_menu.setTitle('View')
        menu_bar.addMenu(view_menu)

        def toggle_simulation():
            executing = diag.executor is not None
            if executing:
                simulate_btn.setText('Start')
                diag.executor = None
            else:
                simulate_btn.setText('Stop')
                s = d.schematic
                exe = JIT(s)
                diag.executor = exe
                exe.step()
            diag.update()

        simulate_btn.clicked.connect(toggle_simulation)

        desc1 = Gate(Gate.AND, num_inputs=3)
        desc2 = Not()
        desc3 = ExposedPin(ExposedPin.IN)
        desc4 = ExposedPin(ExposedPin.OUT)

        d = Diagram('main')
        it = QListWidgetItem(d.name)
        it.setData(Qt.ItemDataRole.UserRole, d)
        diagram_tree.addItem(it)
        diag = DiagramEditor(d)

        def on_element_selected(element):
            if element is None:
                element_editor_dock.setWidget(None)
            else:
                ed = ElementEditor(element)
                ed.edited.connect(diag.update)
                element_editor_dock.setWidget(ed)
                ed.show()

        diag.element_selected.connect(on_element_selected)

        self.setCentralWidget(diag)


def run_app():
    from sys import argv

    app = QApplication(argv)
    app.setStyle(QStyleFactory.create('fusion'))
    # palette = app.palette()
    # palette.setColor(QPalette.Window, QColor(53, 53, 53))
    # palette.setColor(QPalette.WindowText, Qt.white)
    # palette.setColor(QPalette.Base, QColor(15, 15, 15))
    # palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    # palette.setColor(QPalette.ToolTipBase, Qt.white)
    # palette.setColor(QPalette.ToolTipText, Qt.white)
    # palette.setColor(QPalette.Text, Qt.white)
    # palette.setColor(QPalette.Button, QColor(53, 53, 53))
    # palette.setColor(QPalette.ButtonText, Qt.white)
    # palette.setColor(QPalette.BrightText, Qt.red)
    # palette.setColor(QPalette.Highlight, QColor(44, 117, 255))
    # palette.setColor(QPalette.HighlightedText, Qt.black)
    # app.setPalette(palette)
    # QApplication.setPalette(palette)
    window = MainWindow()
    window.showMaximized()
    return app.exec_()
