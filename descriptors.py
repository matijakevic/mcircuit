from copy import deepcopy
from collections import defaultdict


class Descriptor:
    def clone(self):
        return deepcopy(self)


class ExposedPin(Descriptor):
    IN, OUT = range(2)

    def __init__(self, direction, width=1):
        super().__init__()
        self.direction = direction
        self.width = width


class Not(Descriptor):
    def __init__(self, width=1):
        super().__init__()
        self.width = width


class Gate(Descriptor):
    AND, OR, XOR = range(3)

    def __init__(self, op, width=1, num_inputs=2, negated=False):
        super().__init__()
        self.op = op
        self.width = width
        self.num_inputs = num_inputs
        self.negated = negated


class Schematic(Descriptor):
    def __init__(self):
        super().__init__()
        self.children = dict()
        self.connections = set()
        self.desc_conns = defaultdict(set)

    def _translate_pin(self, child, pin):
        if child == '':
            return pin, 'pin'
        if isinstance(self.children.get(child), Schematic):
            return child + '.' + pin, 'pin'
        return child, pin

    def connect(self, child1, pin1, child2, pin2):
        child1, pin1 = self._translate_pin(child1, pin1)
        child2, pin2 = self._translate_pin(child2, pin2)
        self.connections.add((child1, pin1, child2, pin2))
        self.desc_conns[child1].add(child2)

    def add_child(self, name, descriptor):
        self.children[name] = descriptor

    def get_child(self, name):
        return self.children[name]

    def all_inputs(self):
        for name, child in self.children.items():
            if not isinstance(child, ExposedPin):
                continue
            if child.direction == ExposedPin.IN:
                yield name + '.pin'

    def all_outputs(self):
        for name, child in self.children.items():
            if not isinstance(child, ExposedPin):
                continue
            if child.direction == ExposedPin.OUT:
                yield name + '.pin'

    # Returns a Schematic equivalent which doesn't contain
    # any other Schematic descriptors in its children.

    def flatten(self):
        s = Schematic()

        to_expand = [('', self)]

        def make_path(path, name):
            return (path + '.' + name).lstrip('.')

        while to_expand:
            path, desc = to_expand.pop()

            for name, child_desc in desc.children.items():
                child_path = make_path(path, name)
                if isinstance(child_desc, Schematic):
                    to_expand.append((child_path, child_desc))
                else:
                    s.add_child(child_path, child_desc)

            for conn in desc.connections:
                s.connect(make_path(path, conn[0]), conn[1],
                          make_path(path, conn[2]), conn[3])

        return s

    def is_flattened(self):
        return all(map(lambda desc: not isinstance(desc, Schematic),
                       self.children.values()))


def topology(root):
    if not isinstance(root, Schematic):
        raise ValueError('root must be a flattened Schematic descriptor')
    if not root.is_flattened():
        raise ValueError('''cannot create a topology for a non-flattened
Schematic descriptor''')

    visited = set()
    topo = list()

    def dfs(name):
        if name in visited:
            return

        visited.add(name)

        for desc_name in root.desc_conns.get(name, set()):
            dfs(desc_name)

        topo.append(name)

    for name in root.children:
        dfs(name)

    topo.reverse()

    return topo
