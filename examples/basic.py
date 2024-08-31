"""Example for Russound RIO package"""

import asyncio
from asyncio import AbstractEventLoop
import logging
import os

# Add project directory to the search path so that version of the module
# is used for tests.
import sys

sys.path.insert(1, os.path.join(os.path.dirname(__file__), ".."))

from aiorussound import Russound, Zone

_LOGGER = logging.getLogger(__package__)


async def demo(loop: AbstractEventLoop, host: str) -> None:
    rus = Russound(loop, host)
    await rus.connect()
    _LOGGER.info("Supported Features:")
    for flag in rus.supported_features:
        _LOGGER.info(flag)
    _LOGGER.info("Finding controllers")
    controllers = await rus.enumerate_controllers()

    for c in controllers.values():
        _LOGGER.info("%s (%s): %s", c.controller_id, c.mac_address, c.controller_id)

        _LOGGER.info("Determining valid zones")
        # Determine Zones

        for zone_id, zone in c.zones.items():
            await zone.watch()
            _LOGGER.info("%s: %s", zone_id, zone.name)

        for source_id, source in c.sources.items():
            await source.watch()
            _LOGGER.info("%s: %s", source_id, source.name)

        for _ in range(5):
            con: Zone = c.zones.get(1)
            await con.volume_up()
            await asyncio.sleep(1.0)

    while True:
        await asyncio.sleep(1)


logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()
loop.set_debug(True)
loop.run_until_complete(demo(loop, sys.argv[1]))
loop.close()
