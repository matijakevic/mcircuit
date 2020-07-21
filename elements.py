from PySide2.QtWidgets import QWidget, QOpenGLWidget
from PySide2.QtCore import QRect, QSize, Qt, QPoint, QMargins, QLine, QTimer, QRectF, QPointF
from PySide2.QtGui import QColor, QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QVector2D, QPainterPathStroker, QPixmap
from descriptors import *
from simulator import Simulator

TILE = 8
EAST, SOUTH, WEST, NORTH = range(4)


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
        self.rotation = EAST

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
