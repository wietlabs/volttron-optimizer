from volttron_optimizer import *
import numpy as np

if __name__ == '__main__':
    seed0()

    source_profile = 0.5 * np.ones(20)
    request1 = Request(1, 'foo', np.array([0.1, 0.3, 0.1, 0.3, 0.1, 0.3, 0.1, 0.3]), 0)
    request2 = Request(2, 'bar', np.array([0.1, 0.3, 0.1, 0.3, 0.1, 0.3, 0.1, 0.3]), 2)

    scheduler = BruteForceScheduler(20)
    hub = Hub(scheduler)

    hub.update_source_profile('source', source_profile, autoschedule=False)
    hub.add_request(request1, autoschedule=False)
    hub.add_request(request2, autoschedule=False)
    hub.schedule()

    hub.visualize(20).savefig('img/example_complementary.png')
