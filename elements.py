from PySide2.QtWidgets import QWidget, QOpenGLWidget
from PySide2.QtCore import QRect, QSize, Qt, QPoint, QMargins, QLine
from PySide2.QtGui import QColor, QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QVector2D, QPainterPathStroker
from descriptors import *


class SchematicEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.elements = list()
        self.pins = list()
        self.wires = list()
        self.junctions = list()

        self.guidepoints = list()
        self.guidelines = list()
        self.wiring_assistant = False

        self.selected_elements = list()
        self.moved = False
        self.grabbed_element = None
        self.grab_offset = None
        self.closest_point = None

        self.elements.append(NotElement(None))
        self.wires.append(QLine(100, 100, 200, 100))

    def _draw_wire(self, painter, line):
        p = QPen(Qt.black, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        path = QPainterPath(line.p1())
        path.lineTo(line.p2())
        stroker = QPainterPathStroker(p)
        stroke = stroker.createStroke(path)
        painter.setPen(QPen(Qt.black, 2))
        painter.fillPath(stroke, Qt.white)
        painter.drawPath(stroke)

    def paintEvent(self, *args):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        r = self.rect()
        painter.fillRect(r, Qt.white)

        for element in self.elements:
            painter.translate(element.bounding_box.topLeft())
            element.paint(painter)
            painter.translate(-element.bounding_box.topLeft())

        for wire in self.wires:
            self._draw_wire(painter, wire)

        painter.setPen(QPen(Qt.red, 1, Qt.DashLine))
        painter.setBrush(Qt.transparent)
        for element in self.selected_elements:
            bb = element.bounding_box
            bb = bb.marginsAdded(QMargins(2, 2, 1, 1))
            painter.drawRect(bb)

        if self.wiring_assistant:
            painter.setPen(QPen(Qt.red, 1, Qt.PenStyle.DotLine))
            for line in self.guidelines:
                painter.drawLine(line)

            painter.setPen(QPen(Qt.red, 1, Qt.PenStyle.SolidLine))
            for p in self.guidepoints:
                painter.drawEllipse(p.x() - 4, p.y() - 4, 8, 8)

            if self.closest_point is not None:
                p = self.closest_point
                painter.drawEllipse(p.x() - 4, p.y() - 4, 8, 8)

    def _pick(self, p):
        for element in self.elements:
            if element.bounding_box.contains(p):
                return element
        return None

    def _closest_point(self, line, point):
        d = QVector2D(line.p2() - line.p1())
        d.normalize()
        v = QVector2D(point - line.p1())
        return line.p1() + (d * QVector2D.dotProduct(d, v)).toPoint()

    def _closest_guideline_point(self, point):
        currd = None
        closest = None
        for line in self.guidelines:
            p = self._closest_point(line, point)
            d = QVector2D(p - point).lengthSquared()
            if (currd is None or d < currd) and d < 2500:
                currd = d
                closest = p
        return closest

    def _closest_assist_point(self, point):
        gp = self._closest_guideline_point(point)

        d1 = QVector2D(gp - point).lengthSquared()

    def mousePressEvent(self, e):
        self.grabbed_element = self._pick(e.pos())
        if self.grabbed_element is not None:
            self.grab_offset = self.grabbed_element.bounding_box.topLeft() - e.pos()

    def mouseMoveEvent(self, e):
        if self.grabbed_element is not None:
            self.grabbed_element.bounding_box.moveTopLeft(
                e.pos() + self.grab_offset)
            self.moved = True
            self.update()

        self.closest_point = self._closest_guideline_point(e.pos())
        self.update()

    def mouseReleaseEvent(self, e):
        moved = self.moved

        if self.grabbed_element is not None:
            self.grabbed_element = None
            self.moved = False

        if not moved:
            self.selected_elements = list()
            for element in self.elements:
                bb = element.bounding_box
                if bb.contains(e.pos()):
                    self.selected_elements.append(element)
            self.update()

    def _build_guidelines(self):
        self.guidelines = list()
        for element in self.elements:
            for p in element.guideline_points():
                self.guidelines.append(
                    QLine(0, p.y(), self.rect().width(), p.y()))
                self.guidelines.append(
                    QLine(p.x(), 0, p.x(), self.rect().height()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._build_guidelines()
        self.update()

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_W:
            self.wiring_assistant ^= True
            self._build_guidelines()
            self.update()


class Element:
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.bounding_box = QRect()
        self.schematic = None

    def pins(self):
        raise NotImplementedError

    def paint(self, painter):
        raise NotImplementedError


class Pin:
    def __init__(self, pin, direction, position):
        self.pin = pin
        self.direction = direction
        self.position = position


class NotElement(Element):
    SIZE = QSize(100, 75)

    def __init__(self, descriptor):
        super().__init__(descriptor)
        self.bounding_box = QRect(QPoint(), self.SIZE)

    def pins(self):
        pass

    def paint(self, painter):
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.white)

        path = QPainterPath()
        s = self.SIZE
        path.moveTo(QPoint())
        path.lineTo(QPoint(s.width() - 5, s.height() / 2))
        path.lineTo(QPoint(0, s.height()))
        path.closeSubpath()
        painter.drawPath(path)

        painter.drawEllipse(QPoint(s.width() - 2, s.height() / 2), 3, 3)
