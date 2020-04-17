from PySide2.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsView, QGraphicsScene, QWidget, QFormLayout, \
    QLineEdit, QSpinBox, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItemGroup, QGraphicsLineItem
from PySide2.QtCore import QRectF, QSize, Qt, QPoint, QMarginsF, QPointF, QTimer, QSizeF
from PySide2.QtGui import QPen, QPainter, QMouseEvent, QPolygon, QPainterPath, QPainterPathStroker
from descriptors import *

_GATE_SIZE = QSizeF(100, 100)
_EXT_LENGTH = 20


def _pin_pos(rect, x, y):
    margins = (_EXT_LENGTH, ) * 4
    rect = rect.marginsAdded(QMarginsF(*margins))
    return QPointF(rect.x() + rect.width() * x - Pin._SIZE.width() / 2, rect.y() + rect.height() * y - Pin._SIZE.height() / 2)


def _make_wire_item(x1, y1, x2, y2):
    path = QPainterPath()

    path.moveTo(x1, y1)
    path.lineTo(x2, y2)

    path_item = QGraphicsPathItem(path)

    stroker = QPainterPathStroker(QPen(Qt.black, 5, c=Qt.RoundCap))
    stroke_path = stroker.createStroke(path)
    stroke_item = QGraphicsPathItem(stroke_path)

    path_item.setPen(QPen(Qt.white, 5, c=Qt.RoundCap))
    stroke_item.setPen(QPen(Qt.black, 1.5, c=Qt.RoundCap))

    group = QGraphicsItemGroup()
    group.addToGroup(path_item)
    group.addToGroup(stroke_item)

    group.setFlag(QGraphicsItem.ItemIsSelectable)

    return group


class Schematic:
    def __init__(self):
        self.root = Composite()
        self.scene = QGraphicsScene()

    def add_element(self, element):
        self.root.add_child(element.desc)
        self.scene.addItem(element)


class SchematicEditor(QGraphicsView):
    def __init__(self, schematic):
        super().__init__()
        self.schematic = schematic
        self.setScene(schematic.scene)

        self.setRenderHint(QPainter.Antialiasing)
        # self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setDragMode(QGraphicsView.RubberBandDrag)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)


class Pin(QGraphicsEllipseItem):
    _SIZE = QSizeF(10, 10)

    def __init__(self, element, path):
        super().__init__(element)
        self.path = path

        self.setPen(QPen(Qt.black, 2))
        self.setBrush(Qt.white)
        self.setRect(QRectF(QPoint(), self._SIZE))

        self.setFlag(QGraphicsItem.ItemIsSelectable)

        def _update_pin():
            lit = element.simulator.get_pin_value(path) > 0
            self.setBrush(Qt.green if lit else Qt.white)
            self.update()

        element.simulator.observe(path, _update_pin)


class Element(QGraphicsRectItem):
    def __init__(self, simulator, desc):
        super().__init__()
        self.simulator = simulator
        self.desc = desc
        self.item_move_callback = None

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setPen(QPen(Qt.transparent))

    def editor(self):
        raise NotImplementedError

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            if callable(self.item_move_callback):
                self.item_move_callback()
            return value
        return value


class NotElement(Element):
    _SIZE = _GATE_SIZE

    def __init__(self, simulator, desc):
        super().__init__(simulator, desc)

        self.setRect(QRectF(QPoint(), self._SIZE))
        r = self.rect()
        pen = QPen(Qt.black, 2, c=Qt.RoundCap)
        ext1 = QGraphicsLineItem(r.left() - _EXT_LENGTH, r.height() / 2,
                                 r.left(), r.height() / 2, self)
        ext2 = QGraphicsLineItem(r.right() + _EXT_LENGTH, r.height() / 2,
                                 r.right(), r.height() / 2, self)
        ext1.setPen(pen)
        ext2.setPen(pen)
        ext1.setFlag(QGraphicsItem.ItemStacksBehindParent)
        ext2.setFlag(QGraphicsItem.ItemStacksBehindParent)

        pin = Pin(self, desc.get_pin('in'))
        pin.setPos(_pin_pos(self.rect(), 0, 0.5))

        pin = Pin(self, desc.get_pin('out'))
        pin.setPos(_pin_pos(self.rect(), 1, 0.5))

    def editor(self):
        w = QWidget()
        l = QFormLayout(w)

        width = QSpinBox()
        width.setMinimum(1)
        width.setMaximum(MAX_WIDTH)
        width.setValue(self.desc.width)

        l.addRow('Width', width)

        def _set_width(value):
            self.desc.width = value

        width.valueChanged.connect(_set_width)

        return w

    def paint(self, painter, *args):
        super().paint(painter, *args)

        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.white)

        path = QPainterPath()
        r = self.rect()
        path.moveTo(r.topLeft())
        path.lineTo(r.topRight() + QPointF(-5, r.height() / 2))
        path.lineTo(r.bottomLeft())
        path.closeSubpath()
        painter.drawPath(path)

        painter.drawEllipse(QPointF(r.right() - 5, r.height() / 2), 5, 5)


class GateElement(Element):
    _SIZE = _GATE_SIZE

    def __init__(self, simulator, desc):
        super().__init__(simulator, desc)

        self.setRect(QRectF(QPoint(), self._SIZE))

        self._inputs = list()

        r = self.rect()

        pin = Pin(self, desc.get_pin('out'))
        pin.setPos(_pin_pos(self.rect(), 1, 0.5))
        pin.setZValue(1)

        pen = QPen(Qt.black, 2, c=Qt.RoundCap)
        ext1 = QGraphicsLineItem(r.right() + _EXT_LENGTH, r.height() / 2,
                                 r.right(), r.height() / 2, self)
        ext1.setPen(pen)
        ext1.setFlag(QGraphicsItem.ItemStacksBehindParent)

        self._setup_inputs()

    def _setup_inputs(self):
        for inp in self._inputs:
            self.scene().removeItem(inp[0])
            self.scene().removeItem(inp[1])

        self._inputs = list()

        n = self.desc.num_inputs

        for i in range(n):
            pos = _pin_pos(self.rect(), 0, (2 * i + 1) / (n * 2))

            pin = Pin(self, self.desc.get_pin(f'in{i}'))
            pin.setPos(pos)

            pen = QPen(Qt.black, 2, c=Qt.RoundCap)
            r = self.rect()
            yy = r.height() * (2 * i + 1) / (n * 2)
            ext = QGraphicsLineItem(pos.x() + Pin._SIZE.width() / 2, pos.y() + Pin._SIZE.height() / 2,
                                    r.width() / 3, pos.y() + Pin._SIZE.height() / 2, self)
            ext.setPen(pen)
            ext.setFlag(QGraphicsItem.ItemStacksBehindParent)
            self._inputs.append((pin, ext))

    def _set_num_inputs(self, value):
        self.desc.num_inputs = value
        self._setup_inputs()

    def editor(self):
        w = QWidget()
        l = QFormLayout(w)

        width = QSpinBox()
        width.setMinimum(1)
        width.setMaximum(MAX_WIDTH)
        width.setValue(self.desc.width)

        def _set_width(value):
            self.desc.width = value

        width.valueChanged.connect(_set_width)
        l.addRow('Width', width)

        num_inputs = QSpinBox()
        num_inputs.setMinimum(2)
        num_inputs.setValue(self.desc.num_inputs)
        num_inputs.valueChanged.connect(self._set_num_inputs)
        l.addRow('Number of inputs', num_inputs)

        return w

    def paint(self, painter, *args):
        super().paint(painter, *args)

        kind = self.desc.kind
        painter.setPen(QPen(Qt.black, 2))
        path = QPainterPath()
        r = self.rect()

        if kind == 'and':
            path.moveTo(r.topLeft())
            path.lineTo(r.center().x(), r.top())
            path.quadTo(r.topRight(), QPoint(r.right(), r.height() / 2))
            path.quadTo(r.bottomRight(), QPoint(r.width() / 2, r.bottom()))
            path.lineTo(r.bottomLeft())
            path.closeSubpath()
        elif kind == 'or':
            path.moveTo(r.topLeft())
            path.lineTo(r.width() / 4, r.top())
            path.quadTo(QPoint(r.width() / 4 * 3, r.top()),
                        QPoint(r.right(), r.height() / 2))
            path.quadTo(QPoint(r.width() / 4 * 3, r.bottom()),
                        QPoint(r.width() / 4, r.bottom()))
            path.lineTo(r.bottomLeft())
            path.quadTo(r.center(), r.topLeft())

        painter.drawPath(path)
