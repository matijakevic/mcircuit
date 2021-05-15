from core.descriptors import Composite, Not
from core.simulator import JIT

s = Composite()
not_ = Not()


s.add_child('not', not_)
s.connect('not', 'out', 'not', 'in')


burst_size = 501
sim = JIT(s, burst_size, True)


for i in range(10):
    sim.step()
    print(sim.get_pin_state('/not/out'))
