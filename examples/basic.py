import asyncio
import logging

# Add project directory to the search path so that version of the module
# is used for tests.
import sys
import os

from aiorussound.const import FeatureFlag
from aiorussound.util import is_fw_version_higher, check_feature_flag

sys.path.insert(1, os.path.join(os.path.dirname(__file__), '..'))

from aiorussound import Russound  # noqa: E402


async def demo(loop, host):
    rus = Russound(loop, host)
    await rus.connect()
    print("Finding controllers")
    controllers = await rus.enumerate_controllers()

    for c in controllers:
        print("%s (%s): %s" % (c.controller_id, c.mac_address, c.controller_type))

        print("Determining valid zones")
        # Determine Zones
        valid_zones = await c.enumerate_zones()

        for zone_id, zone in valid_zones:
            print("%s: %s" % (zone_id, await zone.volume))

        sources = await rus.enumerate_sources()
        for source_id, name in sources:
            print("%s: %s" % (source_id, name))

        # await rus.watch_zone(ZoneID(1))
        # await asyncio.sleep(1)
        # await rus.send_zone_event(ZoneID(1), "KeyPress", "Volume", 40)
        # await asyncio.sleep(1)
        # r = await rus.get_zone_variable(ZoneID(1), "volume")
        # print("Volume:", r)
        # source = rus.get_cached_zone_variable(ZoneID(1), "currentsource")
        # name = await rus.get_source_variable(source, 'name')
        # print("Zone 1 source name: %s" % name)
    await rus.close()
    print("Done")


logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()
loop.set_debug(True)
loop.run_until_complete(demo(loop, sys.argv[1]))
loop.close()
