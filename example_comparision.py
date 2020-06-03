from volttron_optimizer import *
import numpy as np

if __name__ == '__main__':
    seed0()

    solar_panel_profile = np.linspace(0, 1, 20)
    request1 = Request(1, 'teapot', 0.1 * np.ones(8), 99)
    request2 = Request(2, 'oven', 0.8 * np.ones(6), 99)

    for scheduler in NoDelayScheduler(), LinearProgrammingScheduler(lookahead=20), BruteForceScheduler(lookahead=20):
        hub = Hub(scheduler)

        hub.update_source_profile('solar_panel', solar_panel_profile, autoschedule=False)
        hub.add_request(request1, autoschedule=False)
        hub.add_request(request2, autoschedule=False)
        hub.schedule()

        scheduler_name = scheduler.__class__.__name__
        print(scheduler_name, hub.score)
        hub.visualize(20).savefig(f'img/example_comparision_{scheduler_name}.png')
