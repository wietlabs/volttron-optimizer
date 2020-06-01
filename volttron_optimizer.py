from itertools import product
from collections import defaultdict
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import List, Dict
import random
import numpy as np
import matplotlib.pyplot as plt
from pulp import LpMinimize, LpProblem, LpStatus, LpVariable, value
import utils


@dataclass
class Request:
    request_id: int  # must be unique for all devices
    device_name: str
    profile: np.array
    timeout: int  # 0 = don't postpone
    # priority: float = 1

    def __hash__(self) -> int:
        return hash(self.request_id)


@dataclass
class Job:
    request_id: int
    device_name: str
    profile: np.array


class IScheduler(ABC):
    def __init__(self, lookahead: int):
        self.lookahead: int = lookahead
        # TODO: metric parameters

    @abstractmethod
    def schedule(self, available_energy: np.array, requests: List[Request]) -> Dict[int, int]:
        pass


class BruteForceScheduler(IScheduler):
    def schedule(self, available_energy: np.array, requests: List[Request]) -> Dict[int, int]:
        if not requests:
            return {}

        calculate_max_offset = lambda request: min(request.timeout, self.lookahead - len(request.profile)) + 1
        max_offsets = tuple(map(calculate_max_offset, requests))

        best_offsets = (0,) * len(requests)
        best_score = np.inf

        available_energy = utils.pad(available_energy, self.lookahead)

        for offsets in product(*map(range, max_offsets)):
            planned_energy = np.zeros(self.lookahead)

            for request, offset in zip(requests, offsets):
                profile = request.profile[:self.lookahead-offset]
                planned_energy[offset:][:len(profile)] += profile

            delta_energy = available_energy - planned_energy

            energy_lost = sum(delta_energy[delta_energy < 0])  # TODO: rename
            energy_to_buy = sum(delta_energy[delta_energy > 0])
            average_delay = sum(offsets) / len(requests)

            score = 1*energy_to_buy + 0.05*energy_lost + 0.1*average_delay  # TODO: use metric object

            if score < best_score:
                best_offsets = offsets
                best_score = score

        #print(best_score)

        plan = {
            request.request_id: offset
            for request, offset in zip(requests, best_offsets)
        }
        return plan


class LinearProgrammingScheduler(IScheduler):
    def schedule(self, available_energy: np.array, requests: List[Request]) -> Dict[int, int]:
        if not requests:
            return {}

        available_energy = utils.pad(available_energy, len(available_energy) - self.lookahead)

        offset_ranges = {
            r: min(self.lookahead - len(r.profile) + 1, r.timeout + 1) for r in requests
        }
        model = LpProblem("schedule", LpMinimize)

        # Prepare offset variables for all requests
        offset_vars = {r: [] for r in requests}  # binary
        offset_value_vars = {r: [] for r in requests}

        for request in requests:
            for offset in range(offset_ranges[request]):
                b_var = LpVariable(f'b_{offset}_{request.request_id}', cat='Binary')
                v_var = LpVariable(f'v_{offset}_{request.request_id}', lowBound=0, upBound=offset, cat='Integer')

                offset_vars[request].append(b_var)
                offset_value_vars[request].append(v_var)

                if offset > 0:
                    model += v_var >= offset * b_var

        # "choose 1 offset" constraint
        for request in requests:
            offset_sum = sum(offset_vars[request])
            model += offset_sum >= 1  # TODO: check ==
            model += offset_sum <= 1

        # Prepare required energy variables for all requests and time instants
        req_energy_vars = {r: [] for r in requests}

        for request in requests:
            for i, offset in enumerate(range(offset_ranges[request] + len(request.profile) - 1)):
                req_var = LpVariable(f'req_{offset}_{request.request_id}', lowBound=0, cat='Continuous')
                req_energy_vars[request].append(req_var)

        # Enforce lower bound on required energy and
        # collect all variables that will enforce upper bound
        upper_bounds = {r: defaultdict(list) for r in requests}

        for request in requests:
            profile = request.profile
            for offset, offset_var in enumerate(offset_vars[request]):
                for i, req in enumerate(profile):
                    model += req * offset_var <= req_energy_vars[request][offset + i]
                    upper_bounds[request][offset + i].append((req, offset_var))

        # Enforce upper bounds (if time instant not chosen -> zero energy required)
        for request in requests:
            for offset in upper_bounds[request]:
                upper_bound = sum([u[0] * u[1] for u in upper_bounds[request][offset]])
                model += upper_bound >= req_energy_vars[request][offset]

        # Prepare cost function variables
        pos_cost_vars = [LpVariable(f'pos_{offset}', lowBound=0, cat='Continuous') for offset in range(self.lookahead)]
        neg_cost_vars = [LpVariable(f'neg_{offset}', upBound=0, cat='Continuous') for offset in range(self.lookahead)]

        for offset in range(self.lookahead):
            remaining_energy = available_energy[offset]
            planned_energy = []
            for request in requests:
                if offset < offset_ranges[request] + len(request.profile) - 1:
                    planned_energy.append(req_energy_vars[request][offset])

            if planned_energy:
                delta_energy = remaining_energy - sum(planned_energy)
                model += pos_cost_vars[offset] >= delta_energy
                model += neg_cost_vars[offset] <= delta_energy

        # Optimize
        cost_f = 0.05 * sum(pos_cost_vars)
        cost_f -= 1 * sum(neg_cost_vars)
        for request in requests:
            cost_f += 0.1 * (sum(offset_value_vars[request])) / len(requests)

        model += cost_f
        model.solve()  # CBC solver

        #print(LpStatus[model.status])
        #print(value(model.objective))

        # Create plan
        offsets = {}
        for var in model.variables():
            if var.name.startswith('b_') and var.varValue == 1:
                offset_str, rid_str = var.name[2:].split('_')
                offsets[int(rid_str)] = int(offset_str)

        plan = {
            request.request_id: offsets[request.request_id]
            for request in requests
        }
        return plan


class Hub:
    def __init__(self, scheduler: IScheduler):
        self.scheduler: IScheduler = scheduler
        self.source_profiles: Dict[str, np.array] = {}
        self.waiting_requests: List[Request] = []
        self.running_jobs = []
        self.plan: Dict[int, int] = {}

    def update_source_profile(self, source_name: str, profile: np.array, autoschedule: bool = True):
        self.source_profiles[source_name] = profile
        if autoschedule:
            self.schedule()

    def add_request(self, request: Request, autoschedule: bool = True):
        self.waiting_requests.append(request)
        self.plan[request.request_id] = 0
        if autoschedule:
            self.schedule()

    def schedule(self):
        self.plan = self.scheduler.schedule(self.available_energy, self.waiting_requests)

    @property
    def source_energy(self) -> np.array:
        profiles = self.source_profiles.values()
        if not profiles:
            return np.array([])
        ticks = max(map(len, profiles))
        energy = np.zeros(ticks)
        for profile in profiles:
            energy[:len(profile)] += profile
        return energy

    @property
    def assigned_energy(self) -> np.array:
        profiles = [job.profile for job in self.running_jobs]
        if not profiles:
            return np.array([])
        ticks = max(map(len, profiles))
        energy = np.zeros(ticks)
        for profile in profiles:
            energy[:len(profile)] += profile
        return energy

    @property
    def available_energy(self) -> np.array:
        source_energy = self.source_energy
        assigned_energy = self.assigned_energy
        ticks = max(len(source_energy), len(assigned_energy))
        energy = np.zeros(ticks)
        energy[:len(source_energy)] += source_energy
        energy[:len(assigned_energy)] -= assigned_energy
        return energy

    @property
    def planned_energy(self) -> np.array:
        if not self.waiting_requests:
            return np.array([])
        ticks = max(
            self.plan[request.request_id] + len(request.profile)
            for request in self.waiting_requests
        )
        energy = np.zeros(ticks)
        for request in self.waiting_requests:
            offset = self.plan[request.request_id]
            energy[offset:][:len(request.profile)] += request.profile
        return energy

    @property
    def score(self) -> float:
        delta_energy = self.available_energy - self.planned_energy

        energy_lost = sum(delta_energy[delta_energy < 0])
        energy_to_buy = sum(delta_energy[delta_energy > 0])
        average_delay = sum(self.plan.values()) / len(self.waiting_requests)

        score = 1*energy_to_buy + 0.05*energy_lost + 0.1*average_delay
        return score

    def tick(self):
        for source_name, profile in self.source_profiles.items():
            self.source_profiles[source_name] = self.source_profiles[source_name][1:]

        for request in self.waiting_requests.copy():
            if self.plan[request.request_id] == 0 or request.timeout == 0:
                self.start_request(request)
            else:
                request.timeout -= 1
                self.plan[request.request_id] -= 1

        for job in self.running_jobs.copy():
            job.profile = job.profile[1:]  # this must be executed after request handling
            if not len(job.profile):
                # job has ended
                self.running_jobs.remove(job)

    #private
    def start_request(self, request: Request):
        self.waiting_requests.remove(request)
        del self.plan[request.request_id]
        job = Job(request.request_id, request.device_name, request.profile)
        self.running_jobs.append(job)

    #debug
    def summary(self):
        print('Source profiles:')
        for source_name, source_profile in self.source_profiles.items():
            print(f' * {source_name} ({len(source_profile)} ticks)')
        print('Waiting requests:')
        for request in self.waiting_requests:
            print(f' * {request})')
        print('Running jobs:')
        for job in self.running_jobs:
            print(f' * {job}')
        print('Plan:')
        for request_id, offset in self.plan.items():
            print(f' * request #{request_id} -> +{offset} ticks')
        print()

    #debug
    def visualize(self, lookahead):
        source_energy = utils.pad(self.source_energy, lookahead)
        assigned_energy = utils.pad(self.assigned_energy, lookahead)
        # available_energy = source_energy - assigned_energy
        planned_energy = utils.pad(self.planned_energy, lookahead)
        consumed_energy = assigned_energy + planned_energy

        fig, ax = plt.subplots()
        ax.set_xlabel('ticks')
        ax.set_ylabel('energy')
        ax.set_ylim((-0.25, 1.25))

        ax.plot(source_energy, color='green', label='available')
        ax.plot(assigned_energy, color='red', label='assigned')
        ax.plot(planned_energy, color='blue', label='planned')
        ax.plot(consumed_energy, color='black', label='consumed')

        ax.legend(loc='upper right')
        return fig

def seed0():
    random.seed(0)
    np.random.seed(0)
