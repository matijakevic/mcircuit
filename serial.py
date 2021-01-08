import json
from json.decoder import JSONDecodeError
from bidict import bidict

from version import VERSION

from descriptors import ExposedPin, Gate, Not, Schematic


_DESC_TO_NAME = bidict({
    Not: 'not',
    Gate: 'gate',
    Schematic: 'schematic',
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
    elif isinstance(desc, Schematic):
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
    elif type is Schematic:
        s = Schematic()
        for name, child in d['children'].items():
            s.add_child(name, _dict_to_desc(child))
        for conn in d['connections']:
            s.connect(*conn)
        return s
    elif type is ExposedPin:
        return ExposedPin(ExposedPin.IN if d['direction'] == 'in' else ExposedPin.OUT, d['width'])


def load(obj):
    d = json.load(obj)

    # version = d['version']
    root = _dict_to_desc(d['root'])

    return root


def save(obj, root):
    d = dict()

    d['version'] = VERSION
    d['root'] = _desc_to_dict(root)

    json.dump(d, obj, indent=4)
