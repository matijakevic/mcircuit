from collections import defaultdict
from itertools import chain
from PySide2.QtCore import QLine, QMargins, QPoint, QRect, QTime, QTimer, Qt, Signal
from PySide2.QtGui import QColor, QKeySequence, QMouseEvent, QPainter, QPen, QStandardItem, QStandardItemModel, QTransform
from diagram import Diagram, EAST, Element, NORTH, SOUTH, WEST, rotate
from descriptors import ExposedPin, Gate, Not

from version import format_version

from PySide2.QtWidgets import QAction, QCheckBox, QComboBox, QDockWidget, QFormLayout, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QApplication, QMenu, QMenuBar, QPushButton, QShortcut, QSpinBox, QToolBar, QTreeView, QTreeWidget, QTreeWidgetItem, QWidget


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
    element_selected = Signal(Element)

    def __init__(self, diagram, grid_size=16):
        super().__init__()
        self.diagram = diagram
        self.grid_size = grid_size
        self.executor = None

        self.placing_element = None
        self._drag_start = None
        self._drag_end = None
        self._selected_element = None
        self._wire_start = None
        self._wire_end = None

        delete_action = QShortcut(QKeySequence(Qt.Key_Delete), self)

        def delete_element():
            if self._selected_element is not None:
                self.diagram.remove_element(self._selected_element)
                self._selected_element = None
                self.update()
        delete_action.activated.connect(delete_element)

        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent):
        gs = self.grid_size

        selected_element = None

        for element in self.diagram.elements:
            facing = element.facing
            x, y = element.position
            xb, yb, w, h = element.bounding_rect

            transform = QTransform()
            transform.translate(x * gs, y * gs)
            transform.rotate(facing * -90)

            r = QRect(xb * gs,  yb * gs, w * gs, h * gs)
            r = transform.mapRect(r)

            if r.contains(event.pos()):
                selected_element = element
                break

        if selected_element != self._selected_element:
            self.element_selected.emit(selected_element)
            self._selected_element = selected_element
            self.update()

        if selected_element is None:
            self._wire_start = event.pos() / self.grid_size
            self._wire_end = self._wire_start
        else:
            self._drag_start = event.pos() / self.grid_size
            self._drag_end = self._drag_start

    def mouseMoveEvent(self, event: QMouseEvent):
        p = event.pos() / self.grid_size
        self._wire_end = p
        self._drag_end = p
        if self._curr_wire() is not None:
            self.update()
        if self._drag_start is not None:
            self.update()
        if self.placing_element is not None:
            self.placing_element.position = (p.x(), p.y())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_start is not None:
            el = self._selected_element
            pos = QPoint(*el.position)
            pos += self._drag_end - self._drag_start
            el.position = (pos.x(), pos.y())
            self.update()
        else:
            self._wire_end = event.pos() / self.grid_size
            wire = self._curr_wire()
            if wire is not None:
                self.diagram.change_wire(
                    wire.x1(), wire.y1(), wire.x2(), wire.y2())
                self.update()

        if self.placing_element is not None:
            self.diagram.add_element(self.placing_element)
            self.placing_element = None
            self.update()

        self._wire_start = None
        self._drag_start = None

    def _curr_wire(self):
        if self._wire_start is not None:
            ws, we = self._wire_start, self._wire_end
            delta = we - ws
            if delta == QPoint():
                return None
            if abs(delta.x()) > abs(delta.y()):
                return QLine(ws.x(), ws.y(), we.x(), ws.y())
            else:
                return QLine(ws.x(), ws.y(), ws.x(), we.y())
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        painter.fillRect(self.rect(), Qt.white)

        painter.setPen(QPen(Qt.black, 0.1))
        for x in range(self.grid_size, self.width(), self.grid_size):
            painter.drawLine(x, 0, x, self.height())
        for y in range(self.grid_size, self.height(), self.grid_size):
            painter.drawLine(0, y, self.width(), y)

        gs = self.grid_size

        for element in self.diagram.elements:
            facing = element.facing
            x, y = element.position
            xb, yb, w, h = element.bounding_rect

            painter.save()
            painter.translate(x * gs, y * gs)
            painter.rotate(facing * -90)

            painter.fillRect(xb * gs, yb * gs, w * gs, h * gs, Qt.white)
            painter.setPen(QPen(Qt.black, 2.0))
            painter.drawRect(xb * gs, yb * gs, w * gs, h * gs)

            if self._selected_element is element:
                r = QRect(xb * gs, yb * gs, w * gs, h * gs)
                r = r.marginsAdded(QMargins(*(5,)*4))
                painter.setPen(QPen(Qt.red, 1.0))
                painter.drawRect(r)

            pins = list()
            for pos, _ in chain(element.all_inputs(),
                                element.all_outputs()):
                pins.append(QPoint(pos[0], pos[1]) * gs)

            painter.setPen(QPen(Qt.black, 6.0))
            painter.drawPoints(pins)

            painter.restore()

        if self._drag_start is not None or self.placing_element is not None:
            if self._drag_start is not None:
                element = self._selected_element
                delta = self._drag_end - self._drag_start
                x, y = element.position
                x += delta.x()
                y += delta.y()
            else:
                element = self.placing_element
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
        curr_wire = self._curr_wire()

        if self._drag_start is None and curr_wire is not None:
            wiremap = self.diagram.construct_wire(
                curr_wire.x1(), curr_wire.y1(), curr_wire.x2(), curr_wire.y2())
        else:
            wiremap = self.diagram.wires

        for pos, node in wiremap.items():
            for dir in range(4):
                if node.connections[dir]:
                    p1 = QPoint(*pos) * gs
                    p2 = QPoint(*rotate(1, 0, dir)) * gs + p1
                    wires.append(QLine(p1, p2))

        painter.setPen(QPen(Qt.black, 4.0))
        painter.drawLines(wires)


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
            diag.placing_element = element

        def add_element(item):
            factory = item.data(0, Qt.UserRole)
            element = factory()
            diag.placing_element = element

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
            s = d.schematic

        simulate_btn.clicked.connect(toggle_simulation)

        desc1 = Gate(Gate.AND, num_inputs=3)
        desc2 = Not()
        desc3 = ExposedPin(ExposedPin.IN)
        desc4 = ExposedPin(ExposedPin.OUT)

        d = Diagram('main')
        it = QListWidgetItem(d.name)
        it.setData(Qt.ItemDataRole.UserRole, d)
        diagram_tree.addItem(it)
        d.add_element(Element('gate', desc1, (5, 5)))
        d.add_element(Element('not', desc2, (20, 5)))
        d.add_element(Element('in', desc3, (10, 5)))
        d.add_element(Element('out', desc4, (30, 5)))
        d.change_wire(10, 5, 16, 5)
        d.change_wire(20, 5, 30, 5)
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
    app = QApplication()
    window = MainWindow()
    window.showMaximized()
    return app.exec_()
