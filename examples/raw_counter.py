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


zbrajalo = Composite()
zbrajalo.add_child('a', ein)
zbrajalo.add_child('b', ein)
zbrajalo.add_child('cin', ein)
zbrajalo.add_child('s', eout)
zbrajalo.add_child('cout', eout)

zbrajalo.add_child('xor1', xor_)
zbrajalo.add_child('xor2', xor_)
zbrajalo.add_child('and1', and_)
zbrajalo.add_child('and2', and_)
zbrajalo.add_child('or1', or_)

zbrajalo.connect('a', '', 'xor1', 'in0')
zbrajalo.connect('b', '', 'xor1', 'in1')
zbrajalo.connect('xor1', 'out', 'xor2', 'in0')
zbrajalo.connect('cin', '', 'xor2', 'in1')
zbrajalo.connect('xor2', 'out', 's', '')
zbrajalo.connect('a', '', 'and2', 'in0')
zbrajalo.connect('b', '', 'and2', 'in1')
zbrajalo.connect('xor1', 'out', 'and1', 'in0')
zbrajalo.connect('cin', '', 'and1', 'in1')
zbrajalo.connect('and1', 'out', 'or1', 'in0')
zbrajalo.connect('and2', 'out', 'or1', 'in1')
zbrajalo.connect('or1', 'out', 'cout', '')

takt = Composite()
takt.add_child('not', not_)
takt.add_child('out', eout)
takt.connect('not', 'out', 'not', 'in')
takt.connect('not', 'out', 'out', '')


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

bistabil = Composite()
bistabil.add_child('clk', ein)
bistabil.add_child('d', ein)
bistabil.add_child('q', eout)
bistabil.add_child('not', not_)
bistabil.add_child('dl1', dlatch)
bistabil.add_child('dl2', dlatch)
bistabil.connect('clk', '', 'dl2', 'clk')
bistabil.connect('clk', '', 'not', 'in')
bistabil.connect('not', 'out', 'dl1', 'clk')
bistabil.connect('dl1', 'q', 'dl2', 'd')
bistabil.connect('d', '', 'dl1', 'd')
bistabil.connect('dl2', 'q', 'q', '')


bits = 8
main = Composite()
main.add_child('clk', takt)
main.add_child('zero', c)
visible = set()

for i in range(1, bits+1):
    b = f'b{i}'
    a = f'a{i}'
    visible.add(f'/{b}/q/pin')
    main.add_child(b, bistabil)
    main.add_child(a, zbrajalo)

for i in range(1, bits+1):
    b = f'b{i}'
    a = f'a{i}'
    main.connect('clk', 'out', b, 'clk')
    main.connect(b, 'q', a, 'a')
    main.connect('zero', 'out', a, 'b')
    if i < bits:
        main.connect(a, 'cout', f'a{i + 1}', 'cin')
    main.connect(a, 's', b, 'd')


burst_size = 1000
sim = JIT(main, burst_size, True)
sim.set_pin_state('/a1/cin/pin', 1)

N = 10000
iters = N * burst_size

a = time()
for i in range(iters):
    sim.step()
b = time()
A = (b - a) / iters

a = time()
for i in range(N):
    sim.burst()
b = time()
B = (b - a) / iters

print('step', A)
print('burst', B)
print(A / B)
