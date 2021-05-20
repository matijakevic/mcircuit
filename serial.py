from diagram import Schematic, Element
import json
from bidict import bidict

from version import VERSION

from core.descriptors import ExposedPin, Gate, Not, Composite


_DESC_TO_NAME = bidict({
    Not: 'not',
    Gate: 'gate',
    Composite: 'schematic',
    ExposedPin: 'exposed_pin'
})

_OP_TO_NAME = bidict({
    Gate.AND: 'and',
    Gate.OR: 'or',
    Gate.XOR: 'xor'
})


def _desc_to_dict(desc):
    d = dict()

    d['type'] = _DESC_TO_NAME[type(desc)]

    if isinstance(desc, Not):
        d['width'] = desc.width
    elif isinstance(desc, Gate):
        d['num_inputs'] = desc.num_inputs
        d['width'] = desc.width
        d['negated'] = desc.negated
        d['op'] = _OP_TO_NAME[desc.op]
    elif isinstance(desc, Composite):
        d['children'] = dict(map(lambda t: (
            t[0], _desc_to_dict(t[1])), desc.children.items()))
        d['connections'] = list(map(list, desc.connections))
    elif isinstance(desc, ExposedPin):
        d['width'] = desc.width
        d['direction'] = 'in' if desc.direction == ExposedPin.IN else 'out'

    return d


def _dict_to_desc(d):
    type = _DESC_TO_NAME.inverse[d['type']]

    if type is Not:
        return Not(d['width'])
    elif type is Gate:
        return Gate(_OP_TO_NAME.inverse[d['op']], d['width'], d['num_inputs'], d['negated'])
    elif type is Composite:
        s = Composite()
        for name, child in d['children'].items():
            s.add_child(name, _dict_to_desc(child))
        for conn in d['connections']:
            s.connect(*conn)
        return s
    elif type is ExposedPin:
        return ExposedPin(ExposedPin.IN if d['direction'] == 'in' else ExposedPin.OUT, d['width'])


def _dict_to_element(d):
    name = d['name']
    descriptor = _dict_to_desc(d['descriptor'])
    position = tuple(d['position'])
    facing = d['facing']

    return Element(name, descriptor, qAddPostRoutine, facing)


def _element_to_dict(element: Element):
    d = dict()

    d['name'] = element.name
    d['descriptor'] = _desc_to_dict(element.descriptor)
    d['position'] = list(element.position)
    d['facing'] = element.facing

    return d


def load_project(obj):
    d = json.load(obj)

    # version = d['version']
    root = _dict_to_desc(d['root'])

    return root


def save_project(obj, diagrams):
    d = dict()

    d['version'] = VERSION
    dlist = d['diagrams'] = list()

    for diagram in diagrams:
        d['schematic'] = _desc_to_dict()
        d['connections'] = pass

    json.dump(d, obj, indent=4)
