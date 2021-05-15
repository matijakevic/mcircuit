from copy import deepcopy
from collections import defaultdict

import networkx as nx


class Descriptor:
    def clone(self):
        return deepcopy(self)

    def all_inputs(self):
        yield from []

    def all_outputs(self):
        yield from []

    def all_internals(self):
        yield from []

    def all_pins(self):
        yield from self.all_inputs()
        yield from self.all_outputs()
        yield from self.all_internals()


class ExposedPin(Descriptor):
    IN, OUT = range(2)

    def __init__(self, direction, width=1):
        super().__init__()
        self.direction = direction
        self.width = width

    def all_inputs(self):
        if self.direction == ExposedPin.OUT:
            yield 'pin', self.width

    def all_outputs(self):
        if self.direction == ExposedPin.IN:
            yield 'pin', self.width


class Constant(Descriptor):
    def __init__(self, width=1, value=0):
        super().__init__()
        self.width = width
        self.value = value

    def all_outputs(self):
        yield 'out', self.width


class Not(Descriptor):
    def __init__(self, width=1):
        super().__init__()
        self.width = width

    def all_inputs(self):
        yield 'in', self.width

    def all_outputs(self):
        yield 'out', self.width


class Gate(Descriptor):
    AND, OR, XOR = range(3)

    def __init__(self, op, width=1, num_inputs=2, negated=False):
        super().__init__()
        self.op = op
        self.width = width
        self.num_inputs = num_inputs
        self.negated = negated

    def all_inputs(self):
        yield from map(lambda i: (f'in{i}', self.width), range(self.num_inputs))

    def all_outputs(self):
        yield 'out', self.width


class Register(Descriptor):
    def __init__(self, width=1):
        super().__init__()
        self.width = width

    def all_inputs(self):
        yield 'clock', 1
        yield 'data', self.width

    def all_outputs(self):
        yield 'out', self.width

    def all_internals(self):
        yield 'prevclock', 1


class Counter(Descriptor):
    def __init__(self, width=1):
        super().__init__()
        self.width = width

    def all_inputs(self):
        yield 'clock', 1

    def all_outputs(self):
        yield 'out', self.width

    def all_internals(self):
        yield 'prevclock', 1


class Clock(Descriptor):
    def __init__(self):
        super().__init__()
        self.short = 1
        self.long = 1

    def all_outputs(self):
        yield 'out', 1

    def all_internals(self):
        yield 'count', 64


class Adder(Descriptor):
    def __init__(self, width=1):
        super().__init__()
        self.width = width

    def all_inputs(self):
        yield 'cin', 1
        yield 'a', self.width
        yield 'b', self.width

    def all_outputs(self):
        yield 'cout', 1
        yield 'sum', self.width


class Schematic(Descriptor):
    def __init__(self):
        super().__init__()
        self.graph = nx.DiGraph()
        self.connections = set()

    def _translate_pin(self, child, pin):
        desc = self.get_child(child)
        if isinstance(desc, ExposedPin):
            return child, 'pin'
        if isinstance(desc, Schematic):
            return child + '/' + pin, 'pin'
        return child, pin

    def connect(self, child1, pin1, child2, pin2):
        self.graph.add_edge(child2, child1)
        child1, pin1 = self._translate_pin(child1, pin1)
        child2, pin2 = self._translate_pin(child2, pin2)
        self.connections.add((child1, pin1, child2, pin2))

    def add_child(self, name, descriptor):
        self.graph.add_node(name, descriptor=descriptor, label=name)

    def get_child(self, name) -> Descriptor:
        return self.graph.nodes[name]['descriptor']

    def all_inputs(self):
        for name, data in self.graph.nodes.items():
            desc = data['descriptor']
            if not isinstance(desc, ExposedPin):
                continue
            if desc.direction == ExposedPin.IN:
                yield name + '/pin', desc.width

    def all_outputs(self):
        for name, data in self.graph.nodes.items():
            desc = data['descriptor']
            if not isinstance(desc, ExposedPin):
                continue
            if desc.direction == ExposedPin.OUT:
                yield name + '/pin', desc.width
