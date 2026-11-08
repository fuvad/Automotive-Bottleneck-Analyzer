"""Independent indexed random streams and positive lognormal sampling."""

import hashlib
import math
import random

from bottleneck_analyzer.simulation.config import Distribution


def stream(seed: int, *keys) -> random.Random:
    digest = hashlib.sha256("/".join(map(str, (seed, *keys))).encode()).digest()
    return random.Random(int.from_bytes(digest[:16]))


def sample(distribution: Distribution, rng: random.Random) -> float:
    if distribution.cv == 0:
        return distribution.mean
    sigma = math.sqrt(math.log1p(distribution.cv**2))
    mu = math.log(distribution.mean) - sigma * sigma / 2
    return max(distribution.minimum, rng.lognormvariate(mu, sigma))
