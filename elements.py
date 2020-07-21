from PySide2.QtWidgets import QWidget, QOpenGLWidget
from PySide2.QtCore import QRect, QSize, Qt, QPoint, QMargins, QLine, QTimer, QRectF, QPointF
from PySide2.QtGui import QColor, QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QVector2D, QPainterPathStroker, QPixmap
from descriptors import *
from simulator import Simulator

TILE = 8
EAST, SOUTH, WEST, NORTH = range(4)


class SchematicEditor(QWidget):
    GRID_PIXMAP = None

    def __init__(self, simulator: Simulator, parent=None):
        super().__init__(parent)

        self.simulator = simulator

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._elements = list()

        self._grid_lines = list()
        SchematicEditor._construct_grid_pixmap()

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

    def _draw_grid(self, painter):
        painter.setBrush(self.GRID_PIXMAP)
        painter.drawRect(self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self._draw_grid(painter)

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


class Element:
    def __init__(self, desc: Descriptor = None):
        self.simulator = None
        self.desc = desc
        self.pos = QPointF()
        self.bb = QRectF()
        self.rotation = EAST
        self.pins = list()

    def paint(self, painter: QPainter):
        raise NotImplementedError


class Pin:
    def __init__(self, path=None):
        self.pos = QPointF()
        self.path = path


class NotElement(Element):
    def __init__(self, desc):
        super().__init__(desc)

        self.pos = QPointF(10, 10)
        self.bb = QRectF(0, 0, TILE * 12, TILE * 10)
        self.rotation = NORTH

        pin_in = Pin(self.desc.get_pin('in'))
        pin_in.pos = QPointF(self.bb.left(), self.bb.center().y())
        pin_out = Pin(self.desc.get_pin('out'))
        pin_out.pos = QPointF(self.bb.right(), self.bb.center().y())

        self.pins.extend((pin_in, pin_out))

    def paint(self, painter):
        painter.setBrush(Qt.white)
        painter.setPen(QPen(Qt.black, 1.5))

        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(self.bb.width(), self.bb.height() / 2)
        path.lineTo(0, self.bb.height())
        path.closeSubpath()

        painter.drawPath(path)
