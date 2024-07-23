import asyncio
import logging

# Add project directory to the search path so that version of the module
# is used for tests.
import sys
import os

from aiorussound.const import FeatureFlag

sys.path.insert(1, os.path.join(os.path.dirname(__file__), '..'))

from aiorussound import Russound, Controller, Zone  # noqa: E402


async def demo(loop, host):
    rus = Russound(loop, host)
    await rus.connect()
    print("Supported Features:")
    for flag in rus.supported_features:
        print(flag)
    print("Finding controllers")
    controllers = await rus.enumerate_controllers()

    for c in controllers.values():
        print("%s (%s): %s" % (c.controller_id, c.mac_address, c.controller_type))

        print("Determining valid zones")
        # Determine Zones

        for zone_id, zone in c.zones.items():
            await zone.watch()
            print("%s: %s" % (zone_id, zone.name))

        for source_id, source in c.sources.items():
            await source.watch()
            print("%s: %s" % (source_id, source.name))

        for i in range (5):
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
