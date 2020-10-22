from collections import defaultdict

import llvmlite.ir as ll
import llvmlite.binding as llvm
from ctypes import CFUNCTYPE, POINTER, c_size_t, c_ulonglong, cast

from descriptors import Descriptor, INT_TYPE

llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

BURST_SIZE = 1000


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

    def is_valid(self):
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

    def unobserve(self, path, func):
        self._observers[path].remove(func)
        if not self._observers[path]:
            del self._observers[path]

    def set_root(self, descriptor):
        self.root = descriptor
        descriptor.simulator = self

    def cleanup(self):
        if self._exec_engine is not None:
            self._exec_engine.close()
        self._exec_engine = None
        self._burst_fn = None
        self._step_fn = None
        self._module = None

        old_pins = self._pins
        self._pins = list()

        for name in old_pins:
            for obs in self._observers[name]:
                obs()

        self._last_state.clear()
        self.ready = False

    def init(self):
        if not self.is_valid():
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
        if self.ready:
            return self._get_global_ptr(path)[0]
        return None

    def set_pin_value(self, path, value):
        self._get_global_ptr(path)[0] = value
