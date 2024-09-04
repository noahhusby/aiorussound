"""Example for Russound RIO package"""

import asyncio
from asyncio import AbstractEventLoop
import logging
import os

# Add project directory to the search path so that version of the module
# is used for tests.
import sys

from aiorussound.connection import RussoundTcpConnectionHandler

sys.path.insert(1, os.path.join(os.path.dirname(__file__), ".."))

from aiorussound import Russound, Zone

_LOGGER = logging.getLogger(__package__)


async def demo(loop: AbstractEventLoop, host: str) -> None:
    conn_handler = RussoundTcpConnectionHandler(loop, host, 4999)
    rus = Russound(conn_handler)
    await rus.connect()
    _LOGGER.info("Supported Features:")
    for flag in rus.supported_features:
        _LOGGER.info(flag)

    _LOGGER.info("Finding sources")
    await rus.init_sources()
    for source_id, source in rus.sources.items():
        await source.watch()
        _LOGGER.info("%s: %s", source_id, source.name)

    _LOGGER.info("Finding controllers")
    controllers = await rus.enumerate_controllers()

    for c in controllers.values():
        _LOGGER.info("%s (%s): %s", c.controller_id, c.mac_address, c.controller_id)

        _LOGGER.info("Determining valid zones")
        # Determine Zones

        for zone_id, zone in c.zones.items():
            await zone.watch()
            _LOGGER.info("%s: %s", zone_id, zone.name)

        await asyncio.sleep(3.0)
        for source_id, source in rus.sources.items():
            print(source.properties)


    while True:
        await asyncio.sleep(1)


logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()
loop.set_debug(True)
loop.run_until_complete(demo(loop, sys.argv[1]))
loop.close()
