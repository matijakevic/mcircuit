from os import sched_get_priority_max
from PySide2.QtWidgets import QWidget, QOpenGLWidget
from PySide2.QtCore import QRect, QSize, Qt, QPoint, QMargins, QLine, QTimer, QRectF, QPointF, Signal
from PySide2.QtGui import QColor, QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QVector2D, QPainterPathStroker, QPixmap
from llvmlite.ir.values import Value
from descriptors import *
from simulator import Simulator
from elements import *


class WireMap:
    def __init__(self):
        self._map = defaultdict(set)
        self._conns = defaultdict(set)

    def add_wire(self, l):
        if l.dy() == 0:
            sx = min(l.x1(), l.x2())
            ex = max(l.x1(), l.x2())
            y = l.y1()
            for x in range(sx + 1, ex + 1):
                self._map[(x, y)].add((x - 1, y))
                self._map[(x - 1, y)].add((x, y))
        else:
            sy = min(l.y1(), l.y2())
            ey = max(l.y1(), l.y2())
            x = l.x1()
            for y in range(sy + 1, ey + 1):
                self._map[(x, y)].add((x, y - 1))
                self._map[(x, y - 1)].add((x, y))

    def remove_wire(self, l):
        if l.dy() == 0:
            sx = min(l.x1(), l.x2())
            ex = max(l.x1(), l.x2())
            y = l.y1()
            for x in range(sx + 1, ex + 1):
                self._map[(x, y)].discard((x - 1, y))
                self._map[(x - 1, y)].discard((x, y))
        else:
            sy = min(l.y1(), l.y2())
            ey = max(l.y1(), l.y2())
            x = l.x1()
            for y in range(sy + 1, ey + 1):
                self._map[(x, y)].discard((x, y - 1))
                self._map[(x, y - 1)].discard((x, y))

    def _rebuild(self):
        pass

    def get_connected_pins(self, desc, pin):
        return self._conns[desc][pin]


class Schematic:
    def __init__(self, root):
        self.root = root
        self.wires = set()
        self.junctions = set()
        self.elements = list()
        self._wire_map = WireMap()

    def add_element(self, element):
        self.elements.append(element)

    def remove_element(self, element):
        self.elements.remove(element)

    def _check_wire(self, l):
        if l.dx() != 0 and l.dy() != 0:
            raise ValueError('a wire should be either horizontal or vertical')

    def add_wire(self, l):
        self._check_wire(l)
        self.wires.add(l)
        self._wire_map.add_wire(l)

    def remove_wire(self, l):
        self._check_wire(l)
        self._wire_map.remove_wire(l)
        self.wires.discard(l)

    def add_junction(self, p):
        self.junctions.add(p)


def _construct_grid_pixmap():
    pixmap = QPixmap(128, 128)

    w, h = pixmap.width(), pixmap.height()
    lines = list()

    for x in range(0, w, TILE):
        lines.append(QPointF(x, 0))
        lines.append(QPointF(x, h))

    for y in range(0, h, TILE):
        lines.append(QPointF(0, y))
        lines.append(QPointF(w, y))

    painter = QPainter(pixmap)
    painter.fillRect(pixmap.rect(), Qt.white)
    painter.setPen(QPen(Qt.gray, 0.3))
    painter.drawLines(lines)

    return pixmap


_GRID_PIXMAP = None


class SchematicEditor(QWidget):

    selection_changed = Signal(list)

    def __init__(self, simulator: Simulator, parent=None):
        super().__init__(parent)

        self.simulator = simulator
        self._schematic = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._antialiased = True
        self._grid_shown = True
        self._grid_lines = list()

        global _GRID_PIXMAP
        if _GRID_PIXMAP is None:
            _GRID_PIXMAP = _construct_grid_pixmap()

    def add_element(self, element):
        self.schematic.add_element(element)
        self._observe_element(element)
        self.update()

    def remove_element(self, element):
        self.schematic.remove_element(element)
        self._unobserve_element(element)
        self.update()

    def _observe_element(self, element):
        for pin in element.pins:
            self.simulator.observe(pin.path, self.update)

    def _unobserve_element(self, element):
        for pin in element.pins:
            self.simulator.observe(pin.path, self.update)

    @property
    def schematic(self):
        return self._schematic

    @schematic.setter
    def schematic(self, schematic):
        if self.schematic is not None:
            for element in self.schematic.elements:
                self._unobserve_element(element)

        self._schematic = schematic

        for element in self.schematic.elements:
            self._observe_element(element)

        self.update()

    @property
    def grid_shown(self):
        return self._grid_shown

    @grid_shown.setter
    def grid_shown(self, value):
        self._grid_shown = bool(value)
        self.update()

    @property
    def antialiased(self):
        return self._antialiased

    @antialiased.setter
    def antialiased(self, value):
        self._antialiased = bool(value)
        self.update()

    def _draw_wire(self, painter, p1, p2):
        painter.setPen(QPen(Qt.black, 2))
        painter.drawLine(p1, p2)

    def _draw_grid(self, painter):
        painter.setBrush(_GRID_PIXMAP)
        painter.drawRect(self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.antialiased:
            painter.setRenderHint(QPainter.Antialiasing)

        if self.grid_shown:
            self._draw_grid(painter)
        else:
            painter.fillRect(self.rect(), Qt.white)

        for element in self.schematic.elements:
            bb = QRectF(element.bb)
            bb.translate(element.pos * TILE)

            painter.translate(bb.center())
            painter.rotate(90 * element.rotation)
            painter.translate(-bb.center() + bb.topLeft())
            element.paint(painter)
            for pin in element.pins:
                val = self.simulator.get_pin_value(pin.path)
                if val is None:
                    painter.setPen(QPen(Qt.blue, 6))
                elif val != 0:
                    painter.setPen(QPen(Qt.green, 6))
                else:
                    painter.setPen(QPen(Qt.black, 6))
                painter.drawPoint(pin.pos)
            painter.translate(-bb.topLeft())

        for wire in self.schematic.wires:
            self._draw_wire(painter, wire.p1() * TILE, wire.p2() * TILE)
