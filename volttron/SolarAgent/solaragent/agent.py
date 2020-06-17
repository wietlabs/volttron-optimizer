"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.messaging import topics, headers as headers_mod
import time
import math
import random
import pyowm
import os

import numpy as np

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def solaragent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Solaragent
    :rtype: Solaragent
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Solaragent(setting1,
                          setting2,
                          **kwargs)


class Solaragent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Solaragent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.setting1 = setting1
        self.setting2 = setting2

        self.default_config = {"setting1": setting1,
                               "setting2": setting2}


        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.set_weather_factor()

    def set_weather_factor(self):
        owm = pyowm.OWM(os.environ["pyowm_api_key"])
        observation = owm.weather_at_place('Krakow,PL')
        w = observation.get_weather()
        status = w.get_detailed_status()
        status2factor = {
                'clear sky': 1,
                'few clouds': 0.7,
                'scattered clouds': 0.5,
                'broken clouds': 0.3
            }

        self.weather_factor = status2factor.get(status,1.0)

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            setting1 = int(config["setting1"])
            setting2 = str(config["setting2"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.setting1 = setting1
        self.setting2 = setting2

        self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        pass


    def simulate_solar_profile(self, time: int, a: float = 0.0):  # a -> pora roku
        czas = np.arange(0, 24, 15/60)
        noise = np.random.uniform(low=-0.2, high=0, size=len(czas))
        power = np.sin((2*np.pi/24)*(czas-6)) + a + noise
        power = np.clip(power, 0, 1)
        power *= self.weather_factor
        return np.concatenate((power[time:], power[:time]))

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        #Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")

        #Exmaple RPC call
        #self.vip.rpc.call("some_agent", "some_method", arg1, arg2)
        while True:
            for i in range(24*4):
                if i%4 == 0:
                    self.set_weather_factor()

                profile = self.simulate_solar_profile(i)
                request = {
                    'device': 'SolarAgent',
                    'profile': list(profile),
                    'timeout': 0,
                    'id': 0
                }
                self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Panel/all", message=
                    [{'moc': profile[0],
                    'czas': i/4 },{'moc':{'type':'float','tz':'US/Pacific','units':'Watt'},
                                                'czas':{'type':'float','tz':'US/Pacific','units':'Hours'}}])

                self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Panel/profile", message=[request])
                time.sleep(1)




        while True:
            for hour in range(24):
                for minutes in range(0,60,15):
                    self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Panel/all", message=
                        [{'moc': self.clipped_power(hour+minutes/60, 0),
                        'czas': hour+minutes/60 },{'moc':{'type':'float','tz':'US/Pacific','units':'Watt'},
                                                    'czas':{'type':'float','tz':'US/Pacific','units':'Hours'}}])
                    time.sleep(0.1)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(solaragent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
