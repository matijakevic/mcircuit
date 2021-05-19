from collections import defaultdict
from copy import deepcopy
from itertools import product
from typing import List
from PySide6.QtGui import QTransform

import networkx as nx

from PySide6.QtCore import QPoint, QRect

from core.descriptors import ExposedPin, Gate, Not, Composite


EAST, NORTH, WEST, SOUTH = range(4)
DIRS = (QPoint(1, 0), QPoint(0, -1), QPoint(-1, 0), QPoint(0, 1))


class Element:
    def __init__(self, name, descriptor, position=QPoint(), facing=EAST):
        self.name = name
        self.descriptor = descriptor
        self.position = position
        self.facing = facing
        self.visuals = None

    def get_bounding_rect(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            return QRect(-4, -1, 4, 2)
        elif isinstance(desc, Gate):
            h = desc.num_inputs // 2
            return QRect(-4, -h - 1, 4, h * 2 + 2)
        elif isinstance(desc, ExposedPin):
            if desc.direction == ExposedPin.OUT:
                return QRect(0, -1, desc.width, 2)
            else:
                return QRect(-desc.width, -1, desc.width, 2)
        elif isinstance(desc, Composite):
            num_inputs = len(tuple(desc.all_inputs()))
            num_outputs = len(tuple(desc.all_outputs()))
            h = max(num_inputs, num_outputs) + 1
            w = int(h * 1.61)
            return QRect(0, 0, w, h)

    def all_inputs(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            yield QPoint(-4, 0), 'in'
        elif isinstance(desc, Gate):
            h = desc.num_inputs // 2
            index = 0
            rest = desc.num_inputs % 2 == 0
            for i in range(desc.num_inputs + rest):
                if rest == 1 and i == h:
                    continue
                yield QPoint(-4, -h + i), 'in' + str(index)
                index += 1
        elif isinstance(desc, ExposedPin) and desc.direction == ExposedPin.OUT:
            yield QPoint(0, 0), 'pin'
        elif isinstance(desc, Composite):
            for i, name in enumerate(desc.all_inputs()):
                yield QPoint(0, i + 1), name[0]

    def all_outputs(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            yield QPoint(0, 0), 'out'
        elif isinstance(desc, Gate):
            yield QPoint(0, 0), 'out'
        elif isinstance(desc, ExposedPin) and desc.direction == ExposedPin.IN:
            yield QPoint(0, 0), 'pin'
        elif isinstance(desc, Composite):
            bb = self.get_bounding_rect()
            for i, name in enumerate(desc.all_outputs()):
                yield QPoint(bb.width(), i + 1), name[0]


class Schematic:
    def __init__(self, name):
        self.name = name
        self.elements: List[Element] = list()
        self.wires = nx.Graph()
        self.composite = Composite()

    def reconstruct(self):
        s = self.composite = Composite()

        sources = list()
        dests = list()

        def _add_pin(container, desc, pin, pos):
            p = transform.map(pos) + element.position
            if not self.wires.has_node(p):
                return
            container.append((desc, pin, p))

        for element in self.elements:
            s.add_child(element.name, element.descriptor)

            transform = QTransform()
            transform.rotate(-90 * element.facing)

            for pos, pin_name in element.all_outputs():
                _add_pin(sources, element.name, pin_name, pos)

            for pos, pin_name in element.all_inputs():
                _add_pin(dests, element.name, pin_name, pos)

        for src, dest in product(sources, dests):
            if not nx.has_path(self.wires, src[2], dest[2]):
                continue
            s.connect(*src[:2], *dest[:2])

        return s

    def remove_element(self, element):
        self.elements.remove(element)
        self.reconstruct()

    def add_element(self, element):
        self.elements.append(element)
        self.reconstruct()

    def construct_wires(self, to_place):
        wires = self.wires.copy()

        for x1, y1, x2, y2 in to_place:
            dx = x2 - x1
            dy = y2 - y1

            if dx == 0 and dy == 0:
                continue

            if dx == 0:
                for y in range(min(y1, y2), max(y1, y2)):
                    wires.add_edge(QPoint(x1, y), QPoint(x1, y + 1))
                continue

            if dy == 0:
                for x in range(min(x1, x2), max(x1, x2)):
                    wires.add_edge(QPoint(x, y1), QPoint(x + 1, y1))
                continue

            raise ValueError('wire must be either horizontal or vertical')

        return wires

    def all_connected(self, p):
        if not self.wires.has_node(p):
            return False
        return len(list(nx.neighbors(self.wires, p))) == 4

    def cross_connected(self, p):
        if not self.wires.has_node(p):
            return False
        return self.wires.has_edge(
            p + DIRS[WEST], p + DIRS[EAST]) and self.wires.has_edge(p + DIRS[NORTH], p + DIRS[SOUTH])

    def overlap(self, p):
        if self.all_connected(p):
            for d in DIRS:
                self.wires.remove_edge(p, p + d)
            self.wires.add_edge(p + DIRS[EAST], p + DIRS[WEST])
            self.wires.add_edge(p + DIRS[NORTH], p + DIRS[SOUTH])
            return

        if self.cross_connected(p):
            self.wires.remove_edge(p + DIRS[EAST], p + DIRS[WEST])
            self.wires.remove_edge(p + DIRS[NORTH], p + DIRS[SOUTH])
            for d in DIRS:
                self.wires.add_edge(p, p + d)

    def change_wires(self, to_place):
        self.wires = self.construct_wires(to_place)
        self.reconstruct()
