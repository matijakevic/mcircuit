from time import time
from core.descriptors import Clock, Composite, Counter
from core.simulator import JIT

s = Composite()
counter = Counter(16)
clock = Clock()


s.add_child('clk', clock)
s.add_child('r', counter)
s.connect('clk', 'out', 'r', 'clock')


burst_size = 501
sim = JIT(s, burst_size, True)

N = 1000
iters = N * burst_size

a = time()
for i in range(N * burst_size):
    sim.step()
b = time()
A = (b - a) / (N * burst_size)

a = time()
for i in range(N):
    sim.burst()
b = time()
B = (b - a) / (N * burst_size)

print('step', A)
print('burst', B)
print(A / B)
