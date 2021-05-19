import random
from time import time
from core.descriptors import Constant, Gate, Composite, ExposedPin, Not
from core.simulator import JIT

ein = ExposedPin(ExposedPin.IN)
eout = ExposedPin(ExposedPin.OUT)
nor = Gate(Gate.OR, negated=True)
xor_ = Gate(Gate.XOR)
and_ = Gate(Gate.AND)
or_ = Gate(Gate.OR)
not_ = Not()
c = Constant(1, 0)


adder = Composite()
adder.add_child('a', ein)
adder.add_child('b', ein)
adder.add_child('cin', ein)
adder.add_child('s', eout)
adder.add_child('cout', eout)

adder.add_child('xor1', xor_)
adder.add_child('xor2', xor_)
adder.add_child('and1', and_)
adder.add_child('and2', and_)
adder.add_child('or1', or_)

adder.connect('a', '', 'xor1', 'in0')
adder.connect('b', '', 'xor1', 'in1')
adder.connect('xor1', 'out', 'xor2', 'in0')
adder.connect('cin', '', 'xor2', 'in1')
adder.connect('xor2', 'out', 's', '')
adder.connect('a', '', 'and2', 'in0')
adder.connect('b', '', 'and2', 'in1')
adder.connect('xor1', 'out', 'and1', 'in0')
adder.connect('cin', '', 'and1', 'in1')
adder.connect('and1', 'out', 'or1', 'in0')
adder.connect('and2', 'out', 'or1', 'in1')
adder.connect('or1', 'out', 'cout', '')

clock = Composite()
clock.add_child('not', not_)
clock.add_child('out', eout)
clock.connect('not', 'out', 'not', 'in')
clock.connect('not', 'out', 'out', '')


srlatch = Composite()
srlatch.add_child('nor1', nor)
srlatch.add_child('nor2', nor)
srlatch.add_child('s', ein)
srlatch.add_child('r', ein)
srlatch.add_child('q', eout)
srlatch.connect('nor2', 'out', 'nor1', 'in1')
srlatch.connect('nor1', 'out', 'nor2', 'in0')
srlatch.connect('s', '', 'nor2', 'in1')
srlatch.connect('r', '', 'nor1', 'in0')
srlatch.connect('nor1', 'out', 'q', '')


dlatch = Composite()
dlatch.add_child('sr', srlatch)
dlatch.add_child('and1', and_)
dlatch.add_child('and2', and_)
dlatch.add_child('not', not_)
dlatch.add_child('d', ein)
dlatch.add_child('clk', ein)
dlatch.add_child('q', eout)

dlatch.connect('d', '', 'not', 'in')
dlatch.connect('not', 'out', 'and1', 'in0')
dlatch.connect('clk', '', 'and1', 'in1')
dlatch.connect('clk', '', 'and2', 'in0')
dlatch.connect('d', '', 'and2', 'in1')
dlatch.connect('and1', 'out', 'sr', 'r')
dlatch.connect('and2', 'out', 'sr', 's')
dlatch.connect('sr', 'q', 'q', '')

latch = Composite()
latch.add_child('clk', ein)
latch.add_child('d', ein)
latch.add_child('q', eout)
latch.add_child('not', not_)
latch.add_child('dl1', dlatch)
latch.add_child('dl2', dlatch)
latch.connect('clk', '', 'dl2', 'clk')
latch.connect('clk', '', 'not', 'in')
latch.connect('not', 'out', 'dl1', 'clk')
latch.connect('dl1', 'q', 'dl2', 'd')
latch.connect('d', '', 'dl1', 'd')
latch.connect('dl2', 'q', 'q', '')


bits = 2
main = Composite()
main.add_child('clk', clock)
visible = set()

for i in range(1, bits+1):
    b = f'b{i}'
    a = f'a{i}'
    visible.add(f'/{b}/q/pin')
    main.add_child(b, latch)
    main.add_child(a, adder)

l = list(range(1, bits+1))
random.shuffle(l)
for i in l:
    b = f'b{i}'
    a = f'a{i}'
    main.connect('clk', 'out', b, 'clk')
    main.connect(b, 'q', a, 'a')

random.shuffle(l)
for i in l:
    b = f'b{i}'
    a = f'a{i}'
    if i < bits:
        main.connect(a, 'cout', f'a{i + 1}', 'cin')
    main.connect(a, 's', b, 'd')


burst_size = 1000
sim = JIT(main, burst_size, True)
sim.set_pin_state('/a1/cin/pin', 1)

for j in range(10):
    sim.step()
    s = 0
    for i in range(1, bits + 1):
        s |= (1 << (i - 1)) * sim.get_pin_state(f'/b{i}/q/pin')
    print(s)
