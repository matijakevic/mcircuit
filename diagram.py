from collections import defaultdict
from copy import deepcopy

from descriptors import ExposedPin, Gate, Not, Schematic, topology


EAST, NORTH, WEST, SOUTH = range(4)


def rotate(x, y, dir):
    if dir == EAST:
        return x, y
    elif dir == NORTH:
        return y, -x
    elif dir == WEST:
        return -x, y
    else:
        return -y, x


class Element:
    def __init__(self, name, descriptor, position=(0, 0), facing=EAST):
        self.name = name
        self.descriptor = descriptor
        self.position = position
        self.facing = facing

    @property
    def bounding_rect(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            return -4, -1, 4, 2
        elif isinstance(desc, Gate):
            h = desc.num_inputs // 2
            return -4, -h - 1, 4, h * 2 + 2
        elif isinstance(desc, ExposedPin):
            if desc.direction == ExposedPin.OUT:
                return 0, -1, 1, 2
            else:
                return -1, -1, 1, 2
        elif isinstance(desc, Schematic):
            num_inputs = len(tuple(desc.all_inputs()))
            num_outputs = len(tuple(desc.all_outputs()))
            h = max(num_inputs, num_outputs) + 1
            w = int(h / 1.61)
            return 0, 0, w, h

    def all_inputs(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            yield (-4, 0), 'in'
        elif isinstance(desc, Gate):
            h = desc.num_inputs // 2
            index = 0
            rest = desc.num_inputs % 2 == 0
            for i in range(desc.num_inputs + rest):
                if rest == 1 and i == h:
                    continue
                yield (-4, -h + i), 'in' + str(index)
                index += 1
        elif isinstance(desc, ExposedPin) and desc.direction == ExposedPin.OUT:
            yield (0, 0), 'pin'
        elif isinstance(desc, Schematic):
            for i, name in enumerate(desc.all_inputs()):
                yield (0, i + 1), name

    def all_outputs(self):
        desc = self.descriptor

        if isinstance(desc, Not):
            yield (0, 0), 'out'
        elif isinstance(desc, Gate):
            yield (0, 0), 'out'
        elif isinstance(desc, ExposedPin) and desc.direction == ExposedPin.IN:
            yield (0, 0), 'pin'
        elif isinstance(desc, Schematic):
            bb = self.bounding_rect
            for i, name in enumerate(desc.all_outputs()):
                yield (bb[2], i + 1), name


class WireNode:
    def __init__(self):
        self.connections = [False] * 4
        self.junction = False


class Diagram:
    def __init__(self, name):
        self.name = name
        self.elements = list()
        self.wires = defaultdict(WireNode)
        self.schematic = Schematic()

    def reconstruct(self):
        s = self.schematic

        self.schematic.children.clear()
        self.schematic.connections.clear()
        self.schematic.desc_conns.clear()

        sources = list()
        dests = list()

        for element in self.elements:
            epos = element.position
            s.add_child(element.name, element.descriptor)

            for pos, pin_name in element.all_outputs():
                rpos = rotate(*pos, element.facing)
                tpos = (epos[0] + rpos[0], epos[1] + rpos[1])
                sources.append((element.name, pin_name, tpos))

            for pos, pin_name in element.all_inputs():
                rpos = rotate(*pos, element.facing)
                tpos = (epos[0] + rpos[0], epos[1] + rpos[1])
                dests.append((element.name, pin_name, tpos))

        def _bfs(source):
            desc1, pin1 = source[0], source[1]
            to_explore = [source[2]]
            visited = set()

            while to_explore:
                pos1 = to_explore.pop()

                if pos1 in visited:
                    continue
                visited.add(pos1)

                for desc2, pin2, pos2 in dests:
                    if pos1 == pos2:
                        s.connect(desc1, pin1, desc2, pin2)
                        break

                node = self.wires[pos1]

                for dir in range(4):
                    if node.connections[dir]:
                        r = rotate(1, 0, dir)
                        to_explore.append((pos1[0] + r[0], pos1[1] + r[1]))

        for source in sources:
            _bfs(source)

        return s

    def remove_element(self, element):
        self.elements.remove(element)
        self.reconstruct()

    def add_element(self, element):
        self.elements.append(element)
        self.reconstruct()

    def construct_wires(self, to_place):
        wires = deepcopy(self.wires)

        for x1, y1, x2, y2 in to_place:
            dx = x2 - x1
            dy = y2 - y1

            if dx == 0 and dy == 0:
                continue

            if dx == 0:
                for y in range(min(y1, y2), max(y1, y2)):
                    wires[(x1, y)].connections[SOUTH] ^= True
                    wires[(x1, y + 1)].connections[NORTH] ^= True
                continue

            if dy == 0:
                for x in range(min(x1, x2), max(x1, x2)):
                    wires[(x, y1)].connections[EAST] ^= True
                    wires[(x + 1, y1)].connections[WEST] ^= True
                continue

            raise ValueError('wire must be either horizontal or vertical')

        return wires

    def change_wires(self, to_place):
        self.wires = self.construct_wires(to_place)
        self.reconstruct()
