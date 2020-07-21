from PySide2.QtWidgets import QWidget, QOpenGLWidget
from PySide2.QtCore import QRect, QSize, Qt, QPoint, QMargins, QLine, QTimer, QRectF, QPointF, Signal
from PySide2.QtGui import QColor, QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QVector2D, QPainterPathStroker, QPixmap
from descriptors import *
from simulator import Simulator
from elements import *


class Schematic:
    def __init__(self, root):
        self.root = root
        self.wires = list()
        self.junctions = list()
        self.elements = list()


class SchematicEditor(QWidget):
    GRID_PIXMAP = None

    selection_changed = Signal(list)

    def __init__(self, simulator: Simulator, parent=None):
        super().__init__(parent)

        self.simulator = simulator

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._elements = list()
        self._wires = list()
        self._junctions = list()

        self._antialiased = True
        self._grid_shown = True
        self._grid_lines = list()
        SchematicEditor._construct_grid_pixmap()

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

    def add_element(self, element):
        self._elements.append(element)

        for pin in element.pins:
            self.simulator.observe(pin.path, self.update)

    @classmethod
    def _construct_grid_pixmap(cls):
        cls.GRID_PIXMAP = QPixmap(128, 128)

        w, h = cls.GRID_PIXMAP.width(), cls.GRID_PIXMAP.height()
        lines = list()

        for x in range(0, w, TILE):
            lines.append(QPointF(x, 0))
            lines.append(QPointF(x, h))

        for y in range(0, h, TILE):
            lines.append(QPointF(0, y))
            lines.append(QPointF(w, y))

        painter = QPainter(cls.GRID_PIXMAP)
        painter.fillRect(cls.GRID_PIXMAP.rect(), Qt.white)
        painter.setPen(QPen(Qt.gray, 0.3))
        painter.drawLines(lines)

    def _draw_wire(self, painter, p1, p2):
        painter.setPen(QPen(Qt.black, 2))
        painter.drawLine(p1, p2)

    def _draw_grid(self, painter):
        painter.setBrush(self.GRID_PIXMAP)
        painter.drawRect(self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.antialiased:
            painter.setRenderHint(QPainter.Antialiasing)

        if self.grid_shown:
            self._draw_grid(painter)
        else:
            painter.fillRect(self.rect(), Qt.white)

        for element in self._elements:
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

        self._draw_wire(painter, QPoint(10, 10) * TILE, QPoint(20, 10) * TILE)
