from volttron_optimizer import *

if __name__ == '__main__':
    seed0()

    lookahead = 6*4  # 6 hours

    scheduler = LinearProgrammingScheduler(lookahead)

    hub = Hub(scheduler)

    solar_profile = utils.simulate_solar_profile(24*5, 8*4)  # 5:00-13:00
    hub.update_source_profile('solarpanel1', solar_profile, autoschedule=False)

    dishwasher_profile = np.array([0.1, 0.2, 0.2, 0.1, 0.3, 0.3, 0.1, 0.3, 0.1])
    for i in range(4):
        request = Request(i, f'dishwasher{i}', dishwasher_profile, i*5)
        hub.add_request(request, autoschedule=False)

    fig = hub.visualize(lookahead)
    fig.savefig(f'img/example_washing_before.svg')

    hub.schedule()

    for t in range(25):
        fig = hub.visualize(lookahead)
        fig.savefig(f'img/example_washing_after_{t:003d}.svg')
        plt.close()
        hub.tick()
