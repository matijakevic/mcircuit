import json
from version import format_version


def save(obj, schematic):
    d = dict()
    d['version'] = format_version()

    json.dump(d, obj)


def load(obj):
    pass
