from collections import defaultdict

import llvmlite.ir as ll
import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, POINTER, c_size_t, c_ulonglong, cast

llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

MAX_WIDTH = 64
INT_TYPE = ll.IntType(MAX_WIDTH)
BURST_SIZE = 1000


def _make_pin(module, path):
    glob = ll.GlobalVariable(module, INT_TYPE, path)
    glob.linkage = 'dllexport'
    return glob


class Descriptor:
    def __init__(self):
        self.parent = None
        self.name = None

    @property
    def path(self):
        if self.parent is None:
            return self.name
        return self.parent.full_name + '_' + self.name

    def get_pin(self, name):
        return self.path + '_' + name

    def setup(self, module: ll.Module):
        raise NotImplementedError

    def compile(self, module: ll.Module, builder: ll.IRBuilder):
        raise NotImplementedError


class NotGate(Descriptor):
    def __init__(self, width: int):
        super().__init__()
        self.width = width

    def setup(self, module: ll.Module):
        pin_in = self.get_pin('in')
        pin_out = self.get_pin('out')

        pin_in = _make_pin(module, pin_in)
        pin_out = _make_pin(module, pin_out)

    def compile(self, module: ll.Module, builder: ll.IRBuilder):
        pin_in = self.get_pin('in')
        pin_out = self.get_pin('out')

        pin_in = module.get_global(pin_in)
        pin_out = module.get_global(pin_out)

        v = builder.load(pin_in)
        v = builder.not_(v)
        builder.store(v, pin_out)


class Gate(Descriptor):
    def __init__(self, kind, width, num_inputs, negated):
        super().__init__()
        self.kind = kind
        self.width = width
        self.num_inputs = num_inputs
        self.negated = negated

    def setup(self, module: ll.Module):
        for i in range(self.num_inputs):
            path = self.get_pin(f'in{i}')
            _make_pin(module, path)

        _make_pin(module, self.get_pin('out'))

    def compile(self, module: ll.Module, builder: ll.IRBuilder):
        inputs = []

        for i in range(self.num_inputs):
            path = self.get_pin(f'in{i}')
            inputs.append(module.get_global(path))

        output = module.get_global(self.get_pin('out'))

        output_v = ll.Constant(INT_TYPE, 0)

        if self.kind == 'and':
            output_v = builder.not_(output_v)

        for inp in inputs:
            v = builder.load(inp)
            if self.kind == 'and':
                output_v = builder.and_(output_v, v)
            elif self.kind == 'or':
                output_v = builder.or_(output_v, v)
            elif self.kind == 'xor':
                output_v = builder.xor(output_v, v)

        if self.negated:
            output_v = builder.not_(output_v)

        builder.store(output_v, output)


class Composite(Descriptor):
    def __init__(self):
        super().__init__()
        self.children = dict()
        self._conns = defaultdict(lambda: defaultdict(set))
        self._deps = defaultdict(set)

    def add_child(self, desc):
        self.children[desc.name] = desc

    def get_desc(self, name):
        if name == '.':
            return self
        return self.children[name]

    def connect(self, desc1, pin1, desc2, pin2):
        self._conns[desc1][pin1].add((desc2, pin2))
        self._deps[desc1].add(desc2)

    def setup(self, module: ll.Module):
        for cdesc in self.children.values():
            cdesc.setup(module)

    def _toposort(self):
        visited = set()
        topo = list()

        def _impl(cname):
            if cname in visited:
                return

            visited.add(cname)

            for cname2 in self._deps[cname]:
                _impl(cname2)

            topo.append(cname)

        for cname in self.children:
            _impl(cname)

        topo.reverse()

        return topo

    def compile(self, module: ll.Module, builder: ll.IRBuilder):
        for cname in self._toposort():
            cdesc = self.children[cname]
            cdesc.compile(module, builder)
            for pin1 in self._conns.get(cname, dict()):
                for desc2, pin2 in self._conns[cname][pin1]:
                    p1 = self.get_desc(cname).get_pin(pin1)
                    p2 = self.get_desc(desc2).get_pin(pin2)
                    p1 = module.get_global(p1)
                    p2 = module.get_global(p2)
                    v = builder.load(p1)
                    builder.store(v, p2)


class Simulator:
    def __init__(self):
        self.root = None
        self._module = None
        self._step_fn = None
        self._burst_fn = None
        self._exec_engine = None
        self.ready = False
        self._last_state = defaultdict(int)
        self._observers = defaultdict(list)
        self._pins = list()

    def is_ready(self):
        return isinstance(self.root, Descriptor)

    def get_debug_info(self):
        if self._module is None:
            return ''
        return str(self._module)

    def _run_observers(self):
        for name in self._pins:
            state = self.get_pin_value(name)
            if self._last_state[name] != state:
                self._last_state[name] = state
                for obs in self._observers[name]:
                    obs()

    def observe(self, path, func):
        self._observers[path].append(func)

    def set_root(self, descriptor):
        self.root = descriptor

    def cleanup(self):
        if self._exec_engine is not None:
            self._exec_engine.close()
        self._exec_engine = None
        self._burst_fn = None
        self._step_fn = None
        self._module = None
        self._pins = list()
        self.ready = False

    def init(self):
        if not self.is_ready():
            raise TypeError('cannot initialize, root descriptor not set')

        self._module = m = ll.Module()

        self.root.setup(m)

        fty = ll.FunctionType(ll.VoidType(), tuple())
        f_step = ll.Function(m, fty, name='step')
        f_burst = ll.Function(m, fty, name='burst')

        builder = ll.IRBuilder()

        # f_step
        block = f_step.append_basic_block()
        builder.position_at_end(block)

        self.root.compile(m, builder)

        builder.ret_void()

        # f_burst
        block = f_burst.append_basic_block()
        loop = f_burst.append_basic_block()
        exit = f_burst.append_basic_block()

        builder.position_at_end(block)
        cnt = builder.alloca(INT_TYPE)
        builder.store(ll.Constant(INT_TYPE, BURST_SIZE), cnt)
        builder.branch(loop)
        builder.position_at_end(loop)

        # Actual simulation code
        builder.call(f_step, tuple())

        # Loop code
        v = builder.load(cnt)
        v = builder.sub(v, ll.Constant(INT_TYPE, 1))
        builder.store(v, cnt)
        cond = builder.icmp_unsigned('==', v, ll.Constant(INT_TYPE, 0))
        builder.cbranch(cond, loop, exit)
        builder.position_at_end(exit)
        builder.ret_void()

        llmod = llvm.parse_assembly(str(m))

        target = llvm.Target.from_default_triple().create_target_machine()

        self._exec_engine = ee = llvm.create_mcjit_compiler(llmod, target)
        ee.finalize_object()

        self._step_fn = CFUNCTYPE(None)(ee.get_function_address('step'))
        self._burst_fn = CFUNCTYPE(None)(ee.get_function_address('burst'))

        for v in m.global_values:
            if isinstance(v, ll.GlobalVariable):
                self._pins.append(v.name)

        self.ready = True

    def step(self):
        if self._step_fn is not None:
            self._step_fn()
            self._run_observers()

    def burst(self):
        self._burst_fn()
        self._run_observers()

    def _get_global_ptr(self, path):
        adr = self._exec_engine.get_global_value_address(path)
        return cast(adr, POINTER(c_ulonglong))

    def get_pin_value(self, path):
        return self._get_global_ptr(path)[0]

    def set_pin_value(self, path, value):
        self._get_global_ptr(path)[0] = value
