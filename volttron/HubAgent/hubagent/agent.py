"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils as vutils
from volttron.platform.vip.agent import Agent, Core, RPC
from dataclasses import dataclass

import numpy as np
from itertools import product
import threading
import time

from typing import List, Dict
from .volttron_optimizer import *

_log = logging.getLogger(__name__)
vutils.setup_logging()
__version__ = "0.1"




def hubagent(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Hubagent
    :rtype: Hubagent
    """
    try:
        config = vutils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Hubagent(setting1,
                          setting2,
                          **kwargs)


class Hubagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Hubagent, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.setting1 = setting1
        self.setting2 = setting2

        self.default_config = {"setting1": setting1,
                               "setting2": setting2}


        self.sources: Dict[Device, Request] = {}
        self.running: List[Job] = []
        self.waiting: List[Request] = []
        self.plan: Dict[Request, int] = {}
        self.n: int = 6*4  # 6 hours
        self.needs_scheduling = False
        self.scheduled = False


        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        seed0()

        lookahead = 6*4

        scheduler = BruteForceScheduler(lookahead)
        self.hub = Hub(scheduler, self.vip.pubsub)
        self.requestId = 0
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

        self._create_subscriptions()

    def _create_subscriptions(self):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="devices/AGH/D17/Panel/profile",
                                  callback=self.on_source_request)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix="devices/AGH/D17/Device/request",
                                  callback=self.on_device_request)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        pass

    def on_source_request(self, peer, sender, bus, topic, headers,
                            message):
        message[0]['profile'] = np.array(message[0]['profile'])
        #request = Request(Device(message[0]['device']), message[0]['profile'], message[0]['timeout'], message[0]['id'])
        self.hub.update_source_profile(message[0]['device'], message[0]['profile'])

        #self.sources[Device(message[0]['device'])] = request
        self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Receiver/all", message=
                        [{'onOff': 1 },{'onOff':{'type':'integer','tz':'US/Pacific','units':'Watt'}}])
        self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Receiver/all", message=
                        [{'onOff': 0 },{'onOff':{'type':'integer','tz':'US/Pacific','units':'Watt'}}])

    def on_device_request(self, peer, sender, bus, topic, headers,
                            message):
        message[0]['profile'] = np.array(message[0]['profile'])
        request = Request(message[0]['id'], message[0]['device'], message[0]['profile'], message[0]['timeout'])
        #request = Request(Device(message[0]['device']), message[0]['profile'], message[0]['timeout'], message[0]['id'])
        self.hub.add_request(request)
        #self.waiting.append(request)
        self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Receiver/all", message=
                        [{'onOff': 2 },{'onOff':{'type':'integer','tz':'US/Pacific','units':'Watt'}}])
        self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Receiver/all", message=
                        [{'onOff': 0 },{'onOff':{'type':'integer','tz':'US/Pacific','units':'Watt'}}])
        #self.needs_scheduling = True

    


    
    def report_results(self):
        print('PLAN', self.hub.plan)
        if(len(self.hub.available_energy) > 0):
            available_energy = self.hub.available_energy[0]
        else:
            available_energy = 0.0

        if(len(self.hub.assigned_energy) > 0):
            assigned_energy = self.hub.assigned_energy[0]
        else:
            assigned_energy = 0.0

        if(len(self.hub.planned_energy) > 0):
            planned_energy = self.hub.planned_energy[0]
        else:
            planned_energy = 0.0


        self.vip.pubsub.publish('pubsub', "devices/AGH/D17/Results/all", message=
                    [{'available_energy': available_energy ,'assigned_energy': assigned_energy ,'planned_energy': planned_energy },{'available_energy':{'type':'float','tz':'US/Pacific','units':'Watt'},'assigned_energy':{'type':'float','tz':'US/Pacific','units':'Watt'},'planned_energy':{'type':'float','tz':'US/Pacific','units':'Watt'}}])


    def routine(self):
        while True:
            try:
                self.hub.tick()
                self.report_results()
            except Exception as e:
                print(e)
            time.sleep(1)



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
        
        threading.Thread(target=self.routine, daemon=True).start()

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
    vutils.vip_main(hubagent, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
