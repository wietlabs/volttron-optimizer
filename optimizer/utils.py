import matplotlib.pyplot as plt
import numpy as np
from uuid import uuid4


def pad(profile: np.array, n: int):
    profile = profile[:n]
    return np.pad(profile, (0, n-len(profile)))


def simulate_solar_profile(ticks_per_day, current_tick: int, a: float = 0.0) -> np.array:
    time = np.linspace(0, 24, ticks_per_day)
    noise = np.random.uniform(low=-0.1, high=0, size=len(time))
    power = np.clip(np.sin((2*np.pi/24)*(time-6)) + a + noise, 0, 1)
    return np.concatenate((power[current_tick:], power[:current_tick]))


def getid() -> int:
    return int(uuid4())
