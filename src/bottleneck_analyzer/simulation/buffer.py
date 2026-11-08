"""Bounded SimPy stores with occupancy measured at actual put/get transitions."""

import simpy

from bottleneck_analyzer.simulation.events import Gauge


class Buffer(simpy.Store):
    def __init__(self, env: simpy.Environment, capacity: int, gauge: Gauge):
        super().__init__(env, capacity=capacity)
        self.gauge = gauge

    def _do_put(self, event):
        result = super()._do_put(event)
        self.gauge.update(self._env.now, len(self.items))
        return result

    def _do_get(self, event):
        result = super()._do_get(event)
        self.gauge.update(self._env.now, len(self.items))
        return result
