from time import time
from descriptors import Clock, Schematic, Counter
from simulator import JIT

s = Schematic()
counter = Counter(16)
clock = Clock()


s.add_child('clk', clock)
s.add_child('r', counter)
s.connect('clk', 'out', 'r', 'clock')


burst_size = 501
sim = JIT(s, burst_size, False)

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
