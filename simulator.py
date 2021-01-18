
from itertools import chain
from ctypes import CFUNCTYPE, POINTER, cast, addressof, c_ulonglong, windll

import llvmlite.ir as ll
import llvmlite.binding as llvm

from descriptors import ExposedPin, Not, Gate, Schematic, topology

llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()


class Executor:
    def get_pin_state(self, pin):
        raise NotImplementedError

    def set_pin_state(self, pin, value):
        raise NotImplementedError

    def step(self):
        raise NotImplementedError

    def burst(self):
        raise NotImplementedError


class Interpreter(Executor):
    def __init__(self, root: Schematic):
        self.states = dict()
        self._flat = root.flatten()
        self._topo = topology(self._flat)

        self._initialize()

    def _initialize(self):
        for name, desc in self._flat.children.items():
            if isinstance(desc, Gate):
                self.states[name + '.out'] = 0
                for i in range(desc.num_inputs):
                    self.states[name + '.in' + str(i)] = 0
            elif isinstance(desc, Not):
                self.states[name + '.in'] = 0
                self.states[name + '.out'] = 0
            elif isinstance(desc, ExposedPin):
                self.states[name + '.pin'] = 0

    def get_pin_state(self, pin):
        return self.states[pin]

    def set_pin_state(self, pin, value):
        self.states[pin] = value

    def step(self):
        for name in self._topo:
            desc = self._flat.children[name]
            if isinstance(desc, Gate):
                MASK = (1 << desc.width) - 1

                if desc.op == Gate.AND:
                    val = MASK
                else:
                    val = 0

                for i in range(desc.num_inputs):
                    input_state = self.states[name + '.in' + str(i)]
                    if desc.op == Gate.AND:
                        val &= input_state
                    elif desc.op == Gate.OR:
                        val |= input_state
                    else:
                        val ^= input_state

                if desc.negated:
                    val ^= MASK

                self.states[name + '.out'] = val
            elif isinstance(desc, Not):
                MASK = (1 << desc.width) - 1
                self.states[name + '.out'] = self.states[name + '.in'] ^ MASK

            for desc1, pin1, desc2, pin2 in self._flat.connections:
                if desc1 != name:
                    continue
                self.states[desc2 + '.' +
                            pin2] = self.states[desc1 + '.' + pin1]

    def burst(self):
        for _ in range(1000):
            self.step()


class JIT(Executor):
    def __init__(self, root: Schematic, burst_size=1001):
        self.root = root
        self._burst_size = burst_size
        self._flat = root.flatten()
        self._topo = topology(self._flat)

        mod = self._module = ll.Module()

        all_pins = set()

        for name, desc in self._flat.children.items():
            if isinstance(desc, Gate):
                all_pins.add((name, 'out', desc.width))
                for i in range(desc.num_inputs):
                    all_pins.add((name, 'in' + str(i), desc.width))
            elif isinstance(desc, Not):
                all_pins.add((name, 'in', desc.width))
                all_pins.add((name, 'out', desc.width))
            elif isinstance(desc, ExposedPin):
                all_pins.add((name, 'pin', desc.width))

        self._mapper = dict()
        pins = set()

        def _trace_pin(desc, pin):
            for desc1, pin1, desc2, pin2 in self._flat.connections:
                if desc2 == desc and pin2 == pin:
                    return _trace_pin(desc1, pin1)
            return desc, pin

        for desc, pin, width in all_pins:
            trace = _trace_pin(desc, pin)
            path1 = '.'.join((desc, pin))
            path2 = '.'.join(trace)
            pins.add((path2, width))
            self._mapper[path1] = path2

        for pin_name, pin_width in pins:
            pin_type = ll.IntType(pin_width)
            var = ll.GlobalVariable(mod, pin_type, pin_name)
            var.align = 8
            var.initializer = ll.Constant(pin_type, 0)
            var.storage_class = 'dllexport'

        int_type = ll.IntType(64)

        func_type = ll.FunctionType(ll.VoidType(), tuple())
        step_func = ll.Function(mod, func_type, name='step')

        b_entry = step_func.append_basic_block()
        b = ll.IRBuilder(b_entry)

        def get_global(path, pin):
            return mod.get_global(self._mapper[path + '.' + pin])

        for name in self._topo:
            desc = self._flat.children[name]
            if isinstance(desc, Not):
                inp = b.load(get_global(name, 'in'))
                v = b.not_(inp)
                b.store(v, get_global(name, 'out'))
            elif isinstance(desc, Gate):
                res = None
                for i in range(desc.num_inputs):
                    v = b.load(get_global(name, 'in' + str(i)))
                    if res is None:
                        res = v
                    elif desc.op == Gate.AND:
                        res = b.and_(res, v)
                    elif desc.op == Gate.OR:
                        res = b.or_(res, v)
                    elif desc.op == Gate.XOR:
                        res = b.xor(res, v)
                if desc.negated:
                    res = b.not_(res)
                b.store(res, get_global(name, 'out'))

            for desc1, pin1, desc2, pin2 in self._flat.connections:
                if desc1 != name:
                    continue
                v = b.load(get_global(desc1, pin1))
                b.store(v, get_global(desc2, pin2))

        b.ret_void()

        burst_func = ll.Function(mod, func_type, name='burst')
        b_entry = burst_func.append_basic_block()
        b_loop = burst_func.append_basic_block()
        b_exit = burst_func.append_basic_block()
        b = ll.IRBuilder()

        b.position_at_end(b_entry)
        cnt_p = b.alloca(int_type)
        b.store(ll.Constant(int_type, burst_size), cnt_p)
        b.branch(b_loop)

        b.position_at_end(b_loop)
        b.call(step_func, tuple())
        cnt = b.load(cnt_p)
        v = b.sub(cnt, ll.Constant(int_type, 1))
        b.store(v, cnt_p)
        cond = b.icmp_unsigned('==', cnt, ll.Constant(int_type, 0))
        b.cbranch(cond, b_loop, b_exit)

        b.position_at_end(b_exit)
        b.ret_void()

        llmod = self._llmod = llvm.parse_assembly(str(mod))

        pmb = llvm.create_pass_manager_builder()
        pmb.opt_level = 3
        pmb.inlining_threshold = 1
        pm = llvm.create_module_pass_manager()
        pmb.populate(pm)
        pm.run(llmod)

        # print(llmod)

        self._machine = llvm.Target.from_default_triple().create_target_machine()

        self._ee = llvm.create_mcjit_compiler(llmod, self._machine)
        self._ee.finalize_object()
        ptr = self._ee.get_function_address('step')
        self._step_func = CFUNCTYPE(None)(ptr)

        ptr = self._ee.get_function_address('burst')
        self._burst_func = CFUNCTYPE(None)(ptr)

    @ property
    def burst_size(self):
        return self._burst_size

    def get_pin_state(self, pin):
        ptr = self._ee.get_global_value_address(self._mapper[pin])
        return cast(ptr, POINTER(c_ulonglong))[0]

    def set_pin_state(self, pin, value):
        ptr = self._ee.get_global_value_address(self._mapper[pin])
        cast(ptr, POINTER(c_ulonglong))[0] = value

    def step(self):
        self._step_func()

    def burst(self):
        self._burst_func()
