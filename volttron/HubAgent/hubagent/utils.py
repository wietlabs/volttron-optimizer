import matplotlib.pyplot as plt
import numpy as np
from uuid import uuid4


def pad(profile: np.array, n: int):
    profile = profile[:n]
    return np.pad(profile, (0, n-len(profile)))


def simulate_solar_profile(ticks_per_day, current_tick: int, a: float = 0.0) -> np.array:  # a -> pora roku
    time = np.linspace(0, 24, ticks_per_day)
    noise = np.random.uniform(low=-0.1, high=0, size=len(time))
    power = np.clip(np.sin((2*np.pi/24)*(time-6)) + a + noise, 0, 1)
    return np.concatenate((power[current_tick:], power[:current_tick]))


def getid() -> int:
    return int(uuid4())


def show_profile(profile: np.array) -> None:
    plt.plot(profile)
    # plt.bar(np.arange(len(profile)), profile, width=1)
    plt.ylim((0, 1))
    plt.show()
    plt.cla()


def visualize_plan(self):
    available_energy = self.available_energy
    assigned_energy = self.assigned_energy
    planned_energy = self.planned_energy
    consumed_energy = assigned_energy + planned_energy

    fig, ax = plt.subplots()
    ax.set_xlabel('ticks')
    ax.set_ylabel('energy')
    ax.set_ylim((-0.25, 1.25))

    ax.plot(available_energy, color='green', label='available')
    ax.plot(assigned_energy, color='red', label='assigned')
    ax.plot(planned_energy, color='blue', label='planned')
    ax.plot(consumed_energy, color='black', label='consumed')

    ax.legend(loc='upper right')
    return fig
