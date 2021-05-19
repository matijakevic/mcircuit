from collections import defaultdict
from itertools import chain
from enum import Enum

from core.simulator import JIT, iter_simulation_topology
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from diagram import DIRS, Schematic, Element
from core.descriptors import ExposedPin, Gate, Not, Composite
from editors import *

import networkx as nx

from version import format_version

import pickle


class Mode(Enum):
    EDIT, VIEW = range(2)


class EditState(Enum):
    NONE, ELEMENT_CLICK, EMPTY_CLICK, WIRE, DRAG, SELECT, PLACE = range(7)


class ViewState(Enum):
    NONE, CLICK, MOVE = range(3)


class DiagramEditor(QWidget):
    element_selected = Signal(Element)

    def __init__(self, schematic: Schematic, grid_size=16):
        super().__init__()
        self.schematic = schematic
        self.grid_size = grid_size
        self.executor = None

        self._grid = self._make_grid()

        self._translation = QPoint()

        self._mode = Mode.EDIT
        self._state = EditState.NONE

        self._cursor_pos = QPoint()

        self._selected_element = None
        self._placing_element = None
        self._start = None
        self._end = None

        mode_action = QShortcut(QKeySequence(Qt.Key_E), self)
        delete_action = QShortcut(QKeySequence(Qt.Key_Delete), self)
        cancel_action = QShortcut(QKeySequence(Qt.Key_Escape), self)

        delete_action.activated.connect(self.delete_selected_element)
        cancel_action.activated.connect(self.cancel_interaction)
        mode_action.activated.connect(self.toggle_interaction_mode)

        self.redraw_timer = QTimer()
        self.redraw_timer.setInterval(250)

        def do_stuff():
            self.executor.step()
            self.update()

        self.redraw_timer.timeout.connect(do_stuff)

        self.setMouseTracking(True)

    def toggle_interaction_mode(self):
        self._mode = Mode.EDIT if self._mode == Mode.VIEW else Mode.VIEW
        self._state = EditState.NONE if self._mode == Mode.EDIT else ViewState.NONE
        if self._mode == Mode.VIEW:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def cancel_interaction(self):
        if self._mode == Mode.VIEW:
            self._state = ViewState.NONE
            self.setCursor(Qt.PointingHandCursor)
        else:
            self._state = EditState.NONE
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def select_element(self, element):
        self._state = EditState.SELECT
        curr = self._selected_element
        self._selected_element = element
        if curr is not element:
            self.element_selected.emit(element)
        self.update()

    def unselect(self):
        curr = self._selected_element
        self._selected_element = None
        self._state = EditState.NONE
        if curr is not None:
            self.element_selected.emit(None)
        self.update()

    def delete_element(self, element):
        self.schematic.remove_element(element)
        if self._state == EditState.SELECT and self._selected_element is element:
            self.unselect()

    def delete_selected_element(self):
        self.delete_element(self._selected_element)

    def _get_wire(self):
        if self._state != EditState.WIRE:
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
        if self._mode != Mode.EDIT:
            self.toggle_interaction_mode()
        self._state = EditState.PLACE
        self._placing_element = element
        self.update()

    def stop_placing(self):
        self._mode = Mode.EDIT
        self._state = EditState.NONE
        self.update()

    def element_at_position(self, pos):
        gs = self.grid_size

        for element in self.schematic.elements:
            facing = element.facing
            p = element.position
            bb = element.get_bounding_rect()

            transform = QTransform()
            #transform.scale(gs, gs)
            transform.translate(p.x() * gs, p.y() * gs)
            transform.rotate(facing * -90)

            r = transform.mapRect(
                QRect(bb.x() * gs, bb.y() * gs, bb.width() * gs, bb.height() * gs))

            for p, _ in chain(element.all_inputs(),
                              element.all_outputs()):
                pt = (p + DIRS[facing]) * gs
                if QVector2D(pt - pos).length() <= self.grid_size / 2:
                    return None

            if r.contains(pos):
                return element

        return None

    def mousePressEvent(self, event: QMouseEvent):
        gs = self.grid_size
        d = event.pos() - self._translation
        p = QPoint(round(d.x() / gs), round(d.y() / gs))

        if self._mode == Mode.VIEW:
            self._state = ViewState.CLICK
            self._start = d
            self._end = d
            self.update()
            return

        if self._state == EditState.NONE:
            selected_element = self.element_at_position(d)
            if selected_element is not None:
                self._state = EditState.ELEMENT_CLICK
                self._selected_element = selected_element
                self.element_selected.emit(selected_element)
            else:
                self._state = EditState.EMPTY_CLICK
            self._start = p
            self._end = p
            self.update()
        elif self._state == EditState.SELECT:
            selected_element = self.element_at_position(d)
            if selected_element is None:
                self._state = EditState.EMPTY_CLICK
                self.element_selected.emit(selected_element)
                self.update()
            else:
                if self._selected_element is not selected_element:
                    self.element_selected.emit(selected_element)
                    self._selected_element = selected_element
                self._state = EditState.ELEMENT_CLICK
                self.update()
            self._start = p
            self._end = p
        elif self._state != EditState.PLACE:
            self._state = EditState.NONE
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        ep = event.pos()
        d = ep - self._translation
        gs = self.grid_size
        p = QPoint(round(d.x() / gs), round(d.y() / gs))
        self._cursor_pos = QPoint(round(ep.x() / gs), round(ep.y() / gs)) * gs
        self.update()

        if self._mode == Mode.VIEW:
            if self._state == ViewState.CLICK:
                self._state = ViewState.MOVE
                self.setCursor(Qt.ClosedHandCursor)
                self._end = d
                self.update()
            elif self._state == ViewState.MOVE:
                self.setCursor(Qt.ClosedHandCursor)
                self._end = d
                self.update()
            return

        if self._state == EditState.PLACE:
            self._placing_element.position = p
            self.update()
        elif self._state == EditState.ELEMENT_CLICK:
            self._state = EditState.DRAG
            self._end = p
            self.update()
        elif self._state == EditState.DRAG:
            self._end = p
            self.update()
        elif self._state == EditState.EMPTY_CLICK:
            self._state = EditState.WIRE
            self._end = p
            self.update()
        elif self._state == EditState.WIRE:
            self._end = p
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        ep = event.pos()
        d = ep - self._translation
        gs = self.grid_size
        p = QPoint(round(d.x() / gs), round(d.y() / gs))

        if self._mode == Mode.VIEW:
            if self._state == ViewState.MOVE:
                self.setCursor(Qt.PointingHandCursor)
                self._state = ViewState.NONE
                self._translation += self._end - self._start
                self.update()
            elif self._state == ViewState.CLICK:
                element = self.element_at_position(d)
                if self.executor is not None and element is not None:
                    if isinstance(element.descriptor, ExposedPin):
                        desc = element.descriptor
                        if desc.direction == ExposedPin.IN:
                            p = element.position
                            r = element.get_bounding_rect()
                            transform = QTransform()
                            transform.translate(p.x() * gs, p.y() * gs)
                            transform.rotate(element.facing * -90)
                            state = self.executor.get_pin_state(
                                '/' + element.name + '/pin')
                            for i in range(desc.width):
                                r = QRect(r.x() * gs + gs / 8 + i * gs, r.y() * gs + r.height() / 8 * gs + r.height() * gs / 8 * 6 / 8,
                                          gs / 8 * 6, r.height() * gs / 8 * 6 / 8 * 6)
                                r = transform.mapRect(r)
                                if r.contains(d):
                                    state ^= 1 << i
                                    self.executor.set_pin_state(
                                        '/' + element.name + '/pin', state)
                                    break
                self._state = ViewState.NONE
                self.update()
            return

        if self._state == EditState.PLACE:
            self._state = EditState.SELECT
            self.schematic.add_element(self._placing_element)
            self._selected_element = self._placing_element
            self.element_selected.emit(self._selected_element)
            self.update()
        elif self._state == EditState.DRAG:
            el = self._selected_element
            pos = el.position
            pos += self._end - self._start
            self._state = EditState.NONE
            self.update()
        elif self._state == EditState.WIRE:
            wires = self._get_wire()
            if wires is not None:
                self.schematic.change_wires(wires)
            self._state = EditState.NONE
            self.update()
        elif self._state == EditState.ELEMENT_CLICK:
            self._state = EditState.SELECT
            self.update()
        elif self._state == EditState.EMPTY_CLICK:
            self.schematic.overlap(p)
            self._state = EditState.NONE
            self.update()

    def _make_grid(self):
        pixmap = QPixmap(self.grid_size * 16, self.grid_size * 16)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        back_col = QApplication.palette().color(QPalette.Base)
        grid_col = QApplication.palette().color(QPalette.WindowText)

        painter.fillRect(pixmap.rect(), back_col)

        painter.setPen(QPen(grid_col))
        for x in range(0, pixmap.width(), self.grid_size):
            for y in range(0, pixmap.height(), self.grid_size):
                painter.drawPoint(x, y)

        return pixmap

    def paint_element(self, painter: QPainter, element: Element, position, ghost, selected):
        gs = self.grid_size
        facing = element.facing
        x, y = position.x(), position.y()
        bb = element.get_bounding_rect()
        xb, yb, w, h = bb.topLeft().x(), bb.topLeft().y(), bb.width(), bb.height()

        if ghost:
            black = QColor.fromRgbF(0.0, 0.0, 0.0, 0.5)
            white = QColor.fromRgbF(1.0, 1.0, 1.0, 0.5)
        else:
            black = Qt.black
            white = Qt.white

        painter.save()
        painter.translate(x * gs, y * gs)
        painter.rotate(facing * -90)

        desc = element.descriptor

        if isinstance(desc, Not):
            path = QPainterPath()
            path.moveTo(xb * gs, yb * gs)
            path.lineTo(xb * gs + w * gs, yb * gs + h / 2 * gs)
            path.lineTo(xb * gs, yb * gs + h * gs)
            path.closeSubpath()
            painter.fillPath(path, white)
            painter.setPen(QPen(black, 2.0))
            painter.drawPath(path)

            path = QPainterPath()
            path.addEllipse(xb * gs + w * gs - gs/2.5, yb * gs +
                            h * gs / 2 - gs / 2.5, gs * 4 / 5, gs * 4 / 5)

            painter.fillPath(path, white)
            painter.drawPath(path)
        elif isinstance(desc, ExposedPin):
            path = QPainterPath()
            if desc.direction == ExposedPin.IN:
                path.addRect(xb * gs, yb * gs + h / 8 * gs, w * gs,
                             h * gs / 8 * 6)
            else:
                path.addRoundedRect(xb * gs, yb * gs + h / 8 * gs, w * gs,
                                    h * gs / 8 * 6, gs / 4, gs / 4)
            painter.fillPath(path, white)
            painter.setPen(QPen(black, 2.0))
            painter.drawPath(path)

            if self.executor is None:
                state = None
            else:
                state = self.executor.get_pin_state(
                    '/' + element.name + '/pin')

            painter.setPen(QPen(Qt.black))

            for i in range(desc.width):
                r = QRect(xb * gs + gs / 8 + i * gs, yb * gs + h / 8 * gs + h * gs / 8 * 6 / 8,
                          gs / 8 * 6, h * gs / 8 * 6 / 8 * 6)

                if state is not None:
                    painter.drawText(r, Qt.AlignCenter, str(
                        1 if state & (1 << i) else 0))
        elif isinstance(desc, Gate):
            op = desc.op

            path = QPainterPath()
            if op == Gate.OR:
                path.moveTo(xb * gs, yb * gs)
                path.quadTo(xb * gs + w * gs / 2, yb * gs, xb *
                            gs + w * gs, yb * gs + h * gs / 2)
                path.quadTo(xb * gs + w * gs / 2, yb * gs + h *
                            gs, xb * gs, yb * gs + h * gs)
                path.quadTo(xb * gs + w * gs / 4, yb * gs +
                            h * gs / 2, xb * gs, yb * gs)
            elif op == Gate.AND:

                path.moveTo(xb * gs, yb * gs)
                path.lineTo(xb * gs + w * gs / 2, yb * gs)
                path.quadTo(xb * gs + w * gs, yb * gs, xb *
                            gs + w * gs, yb * gs + h * gs / 2)
                path.quadTo(xb * gs + w * gs, yb * gs + h *
                            gs, xb * gs + w * gs / 2, yb * gs + h * gs)
                path.lineTo(xb * gs, yb * gs + h * gs)
                path.closeSubpath()
            elif op == Gate.XOR:
                path.moveTo(xb * gs + gs / 4, yb * gs)
                path.quadTo(xb * gs + w * gs / 2, yb * gs, xb *
                            gs + w * gs, yb * gs + h * gs / 2)
                path.quadTo(xb * gs + w * gs / 2, yb * gs + h *
                            gs, xb * gs + gs / 4, yb * gs + h * gs)
                path.quadTo(xb * gs + w * gs / 4 + gs / 4, yb * gs +
                            h * gs / 2, xb * gs + gs / 4, yb * gs)
                path.closeSubpath()

                path.moveTo(xb * gs, yb * gs)
                path.quadTo(xb * gs + w * gs / 4, yb * gs +
                            h * gs / 2, xb * gs, yb * gs + h * gs)

            painter.fillPath(path, white)
            painter.setPen(QPen(black, 2.0))
            painter.drawPath(path)

            if desc.negated:
                path = QPainterPath()
                path.addEllipse(xb * gs + w * gs - gs/2.5, yb * gs +
                                h * gs / 2 - gs / 2.5, gs * 4 / 5, gs * 4 / 5)
                painter.fillPath(path, white)
                painter.drawPath(path)
        else:
            painter.fillRect(xb * gs, yb * gs, w * gs, h * gs, white)
            painter.setPen(QPen(black, 2.0))
            painter.drawRect(xb * gs, yb * gs, w * gs, h * gs)

        if selected:
            r = QRect(xb * gs, yb * gs, w * gs, h * gs)
            r = r.marginsAdded(QMargins(*(5,)*4))
            painter.setPen(QPen(Qt.red, 1.0))
            painter.drawRect(r)

        if ghost:
            for pos, name in chain(element.all_inputs(),
                                   element.all_outputs()):
                pins = list()
                for pos, _ in chain(element.all_inputs(),
                                    element.all_outputs()):
                    pins.append(pos * gs)

                painter.setPen(QPen(black, 6.0))
                painter.drawPoints(pins)
        else:
            for pos, name in chain(element.all_inputs(),
                                   element.all_outputs()):
                state = -1
                if self.executor is not None:
                    if isinstance(element.descriptor, Composite):
                        path = '/' + element.name + '/' + name + '/pin'
                    else:
                        path = '/' + element.name + '/' + name
                    state = self.executor.get_pin_state(path)
                if state == -1:
                    painter.setPen(QPen(Qt.blue, 6.0))
                elif state == 0:
                    painter.setPen(QPen(Qt.black, 6.0))
                else:
                    painter.setPen(QPen(Qt.green, 6.0))
                p = pos * gs
                painter.drawPoint(p)

        painter.setPen(Qt.black)
        painter.drawText(QPoint(xb, yb) * gs, element.name)

        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        tex_col = QApplication.palette().color(QPalette.WindowText)
        wire_col = tex_col
        cur_col = tex_col

        if self._mode == Mode.VIEW and self._state == ViewState.MOVE:
            trans = self._translation + self._end - self._start
        else:
            trans = self._translation

        gs = self.grid_size

        ttrans = trans / gs
        tx, ty = ttrans.x() * gs, ttrans.y() * gs

        grid_rect = self.rect().marginsAdded(
            QMargins(*(gs,) * 4)).translated(trans-QPoint(tx, ty))
        painter.drawTiledPixmap(grid_rect, self._grid)

        painter.translate(trans)

        for element in self.schematic.elements:
            if self._state == EditState.DRAG and self._selected_element is element:
                continue

            selected = self._state == EditState.SELECT and self._selected_element is element

            self.paint_element(
                painter, element, element.position, False, selected)

        if self._state in (EditState.DRAG, EditState.PLACE):
            if self._state == EditState.DRAG:
                element = self._selected_element
                delta = self._end - self._start
                p = element.position
                p = p + delta
            else:
                element = self._placing_element
                p = element.position

            self.paint_element(
                painter, element, p, True, False)

        wires = list()

        if self._state == EditState.WIRE:
            curr_wires = self._get_wire()
            if curr_wires is not None:
                self.schematic.construct_wires(curr_wires)

        wiremap = self.schematic.wires

        painter.setPen(QPen(wire_col, 4.0))

        for node in wiremap.nodes:
            if self.schematic.all_connected(node):
                painter.drawPoint(node * gs)
                cc = False
            else:
                cc = self.schematic.cross_connected(node)
            for d in DIRS:
                if wiremap.has_edge(node, node + d) or cc:
                    p1 = QPoint(node) * gs
                    p2 = QPoint(node + d) * gs
                    wires.append(QLine(p1, p2))

        painter.setPen(QPen(wire_col, 2.0))
        painter.drawLines(wires)

        if self._mode != Mode.VIEW and self._state not in (EditState.DRAG, EditState.PLACE):
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

        def open_project():
            nonlocal diagrams, diagram_count
            diag.schematic = Schematic('')
            diagram_tree.clear()
            f = QFileDialog.getOpenFileName(self, 'Open Project')[0]
            with open(f, 'rb') as file:
                diagrams = pickle.load(file)
                print(diagrams)
                for d in diagrams:
                    diagram_count += 1
                    it = QListWidgetItem(d.name)
                    it.setData(Qt.UserRole, d)
                    diagram_tree.addItem(it)
                    if d.name == 'main':
                        diag.schematic = d

        def save_project():
            f = QFileDialog.getSaveFileName(self, 'Save Project')[0]
            with open(f, 'wb') as file:
                pickle.dump(diagrams, file)

        file_menu.addAction('Open...', open_project)
        file_menu.addSeparator()
        file_menu.addAction('Save')
        file_menu.addAction('Save As...', save_project)
        file_menu.addSeparator()
        file_menu.addAction('Exit', self.close)

        menu_bar.addMenu(file_menu)

        project_menu = QMenu('Project')

        diagram_count = 1
        diagrams = list()

        def new_diagram():
            nonlocal diagram_count
            d = Schematic('diagram_' + str(diagram_count))
            diagram_count += 1
            diagrams.append(d)
            it = QListWidgetItem(d.name)
            it.setData(Qt.UserRole, d)
            diagram_tree.addItem(it)

        project_menu.addAction('New Diagram', new_diagram)

        menu_bar.addMenu(project_menu)

        diagram_tree_dock = QDockWidget('Diagrams')
        diagram_tree = QListWidget()

        def change_diagram(item):
            diag.schematic = item.data(Qt.UserRole)
            diag.stop_placing()

        counter = defaultdict(int)

        def add_custom_element(item):
            nonlocal counter
            diagram = item.data(Qt.UserRole)
            base_name = item.text()
            counter[base_name] += 1
            composite = diagram.composite
            element = Element(base_name + '_' +
                              str(counter[base_name]), composite)
            diag.start_placing(element)

        def add_element(item):
            factory = item.data(0, Qt.UserRole)
            if factory is None:
                return
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
                diag.redraw_timer.stop()
            else:
                simulate_btn.setText('Stop')
                diag.schematic.reconstruct()
                s = diag.schematic.composite
                print(list(nx.dfs_postorder_nodes(s.graph)))
                exe = JIT(s, 500, True)
                diag.executor = exe
                diag.redraw_timer.start()
            diag.update()

        simulate_btn.clicked.connect(toggle_simulation)

        d = Schematic('main')
        diagrams.append(d)
        it = QListWidgetItem(d.name)
        it.setData(Qt.ItemDataRole.UserRole, d)
        diagram_tree.addItem(it)
        diag = DiagramEditor(d)

        def on_element_selected(element):
            if element is None:
                element_editor_dock.setWidget(None)
            else:
                ed = ElementPropertyEditor(element)
                ed.edited.connect(diag.update)
                element_editor_dock.setWidget(ed)
                ed.show()

        diag.element_selected.connect(on_element_selected)

        self.setCentralWidget(diag)


def run_app():
    from sys import argv

    app = QApplication(argv)
    window = MainWindow()
    window.show()
    return app.exec_()
