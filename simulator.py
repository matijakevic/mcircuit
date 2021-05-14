
from ctypes import CFUNCTYPE, POINTER, cast, c_ulonglong
from llvmlite.ir.builder import IRBuilder

import networkx as nx

import llvmlite.ir as ll
import llvmlite.binding as llvm

from descriptors import Adder, Clock, Constant, Not, Gate, Register, Schematic, Counter

llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()


def iter_simulation_pins(node: Schematic, path='/'):
    for name in node.graph.nodes:
        desc = node.get_child(name)

        if isinstance(desc, Schematic):
            yield from iter_simulation_pins(desc, path + name + '/')
        else:
            yield from map(lambda p: (path + name + '/' + p[0], p[1], 'in'), desc.all_inputs())
            yield from map(lambda p: (path + name + '/' + p[0], p[1], 'out'), desc.all_outputs())
            yield from map(lambda p: (path + name + '/' + p[0], p[1], 'internal'), desc.all_internals())


def iter_simulation_connections(node: Schematic, path='/'):
    for name in nx.dfs_postorder_nodes(node.graph):
        desc = node.get_child(name)

        if isinstance(desc, Schematic):
            yield from iter_simulation_connections(desc, path + name + '/')

        for conn in node.connections:
            if conn[0].split('/')[0] != name:
                continue
            yield path + conn[0] + '/' + conn[1], path + conn[2] + '/' + conn[3]


def iter_simulation_topology(node: Schematic, path='/'):
    for name in nx.dfs_postorder_nodes(node.graph):
        desc = node.get_child(name)

        if isinstance(desc, Schematic):
            yield from iter_simulation_topology(desc, path + name + '/')
        else:
            yield 'emit', (desc, path + name + '/')

        for conn in node.connections:
            if conn[0].split('/')[0] != name:
                continue
            yield 'propagate', (path + conn[0] + '/' + conn[1], path + conn[2] + '/' + conn[3])


def _translate_not(b: IRBuilder, desc: Gate, path, get_global):
    inp = b.load(get_global(path, 'in'))
    v = b.not_(inp)
    b.store(v, get_global(path, 'out'))


def _translate_gate(b: IRBuilder, desc: Gate, path, get_global):
    res = None
    for i in range(desc.num_inputs):
        v = b.load(get_global(path, 'in' + str(i)))
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
    b.store(res, get_global(path, 'out'))


def _map_to_sources(desc: Schematic):
    conns = dict()
    for src, dest in iter_simulation_connections(desc):
        conns[dest] = src

    def _trace_pin(path):
        curr = path
        if curr not in conns:
            return None
        while curr in conns:
            curr = conns[curr]
        return curr

    traces = dict()

    for pin, _, tp in iter_simulation_pins(desc):
        traces[pin] = _trace_pin(pin)

    return traces


def _translate_counter(b: IRBuilder, desc: Counter, path, get_global):
    prevclk = get_global(path, 'prevclock')
    out = get_global(path, 'out')
    clk = get_global(path, 'clock')

    itype = ll.IntType(desc.width)
    v1 = b.load(prevclk)
    v2 = b.load(clk)
    v3 = b.zext(b.and_(b.not_(v1), v2), itype)

    b.store(b.or_(b.and_(v3, b.add(b.load(out), ll.Constant(itype, 1))),
            b.and_(b.not_(v3), b.load(out))), out)
    b.store(b.load(clk), prevclk)


def _translate_register(b: IRBuilder, desc: Counter, path, get_global):
    prevclk = get_global(path, 'prevclock')
    data = get_global(path, 'data')
    out = get_global(path, 'out')
    clk = get_global(path, 'clock')

    v1 = b.load(prevclk)
    v2 = b.load(clk)
    v3 = b.and_(b.not_(v1), v2)

    b.store(b.or_(b.and_(v3, b.load(data)),
            b.and_(b.not_(v3), out)), out)
    b.store(b.load(clk), prevclk)


def _translate_clock(b: IRBuilder, desc: Clock, path, get_global):
    out = get_global(path, 'out')
    b.store(b.not_(b.load(out)), out)


def _translate_adder(b: IRBuilder, desc: Adder, path, get_global):
    a_ = get_global(path, 'a')
    b_ = get_global(path, 'b')
    cin = get_global(path, 'cin')
    sum_ = get_global(path, 'sum')
    cout = get_global(path, 'cout')

    s1 = b.sadd_with_overflow(b.load(a_), b.load(b_))
    s2 = b.sadd_with_overflow(
        b.extract_value(s1, 0), b.zext(b.load(cin), ll.IntType(desc.width)))
    b.store(b.extract_value(s2, 0), sum_)
    b.store(b.or_(b.extract_value(s1, 1),
            b.extract_value(s2, 1)), cout)


TRANSLATOR = {
    Gate: _translate_gate,
    Adder: _translate_adder,
    Clock: _translate_clock,
    Not: _translate_not,
    Register: _translate_register,
    Counter: _translate_counter
}


class Executor:
    def get_pin_state(self, pin):
        raise NotImplementedError

    def set_pin_state(self, pin, value):
        raise NotImplementedError

    def step(self):
        raise NotImplementedError

    def burst(self):
        raise NotImplementedError


class JIT(Executor):
    def __init__(self, root: Schematic, burst_size, map_pins):
        self.root = root

        mod = self._module = ll.Module()

        if map_pins:
            self._pin_map = _map_to_sources(root)
        else:
            self._pin_map = None

        for pin_path, pin_width, tp in iter_simulation_pins(root):
            if map_pins and self._pin_map[pin_path] is not None:
                continue
            pin_type = ll.IntType(pin_width)
            var = ll.GlobalVariable(mod, pin_type, pin_path)
            var.initializer = ll.Constant(pin_type, 0)
            var.align = 8

        int_type = ll.IntType(64)

        func_type = ll.FunctionType(ll.VoidType(), tuple())
        step_func = ll.Function(mod, func_type, name='step')

        b_entry = step_func.append_basic_block()
        b = ll.IRBuilder(b_entry)

        constants = list()

        def get_global_at(path):
            return mod.get_global(self._get_source_path(path))

        def get_global(desc, pin):
            return get_global_at(desc + pin)

        for op, data in iter_simulation_topology(root):
            if op == 'propagate':
                path1, path2 = data
                v = b.load(get_global_at(path1))
                b.store(v, get_global_at(path2))
            else:
                desc = data[0]
                path = data[1]
                tp = type(desc)
                if tp in TRANSLATOR:
                    TRANSLATOR[tp](b, desc, path, get_global)
                elif tp is Constant:
                    constants.append(data)

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
        cond = b.icmp_unsigned('!=', cnt, ll.Constant(int_type, 0))
        b.cbranch(cond, b_loop, b_exit)

        b.position_at_end(b_exit)
        b.ret_void()

        llmod = self._llmod = llvm.parse_assembly(str(mod))

        #print(str(mod), file=open('out.txt', 'w'))

        pmb = llvm.create_pass_manager_builder()
        pm = llvm.create_module_pass_manager()
        pmb.populate(pm)
        pm.run(llmod)

        # print(llmod,
        #       file=open('out.txt', 'w'), flush=True)

        self._machine = llvm.Target.from_default_triple().create_target_machine()

        self._ee = llvm.create_mcjit_compiler(llmod, self._machine)
        self._ee.finalize_object()

        print(self._machine.emit_assembly(llmod),
              file=open('out.txt', 'w'), flush=True)

        ptr = self._ee.get_function_address('step')
        self._step_func = CFUNCTYPE(None)(ptr)

        ptr = self._ee.get_function_address('burst')
        self._burst_func = CFUNCTYPE(None)(ptr)

        for desc, path in constants:
            self.set_pin_state(path + 'out', desc.value)

    def _get_source_path(self, path):
        if self._pin_map is None:
            return path
        if self._pin_map[path] is None:
            return path
        return self._pin_map[path]

    def get_pin_state(self, pin):
        ptr = self._ee.get_global_value_address(self._get_source_path(pin))
        return cast(ptr, POINTER(c_ulonglong))[0]

    def set_pin_state(self, pin, value):
        ptr = self._ee.get_global_value_address(self._get_source_path(pin))
        cast(ptr, POINTER(c_ulonglong))[0] = value

    def step(self):
        self._step_func()

    def burst(self):
        self._burst_func()
