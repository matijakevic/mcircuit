from descriptors import Schematic


class Element:
    def __init__(self, descriptor):
        self.descriptor = descriptor
        self.position = (0, 0)
        self.size = (0, 0)

class Diagram:
    def __init__(self, schematic=Schematic()):
        self.schematic = schematic
        self.elements = list()
        self.wires = map()
