import asyncio
import logging

# Add project directory to the search path so that version of the module
# is used for tests.
import sys
import os

from aiorussound.const import FeatureFlag

sys.path.insert(1, os.path.join(os.path.dirname(__file__), '..'))

from aiorussound import Russound  # noqa: E402


async def demo(loop, host):
    rus = Russound(loop, host)
    await rus.connect()
    print("Supported Features:")
    for flag in rus.supported_features:
        print(flag)
    print("Finding controllers")
    controllers = await rus.enumerate_controllers()

    for c in controllers:
        print("%s (%s): %s" % (c.controller_id, c.mac_address, c.controller_type))

        print("Determining valid zones")
        # Determine Zones
        valid_zones = await c.enumerate_zones()

        for zone_id, zone in valid_zones:
            await zone.watch()
            print("%s: %s" % (zone_id, zone.name))

        sources = await c.enumerate_sources()
        for source_id, source in sources:
            await source.watch()
            print("%s: %s" % (source_id, source.name))

    await rus.close()
    print("Done")


logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()
loop.set_debug(True)
loop.run_until_complete(demo(loop, sys.argv[1]))
loop.close()
