import asyncio
import logging

# Uncomment lines below to use library from local dev
import sys
import os

sys.path.insert(1, os.path.join(os.path.dirname(__file__), ".."))

from aiorussound.rnet import RussoundRNETClient
from aiorussound import RussoundTcpConnectionHandler

HOST = "192.168.20.17"
PORT = 4999


async def main():
    """Subscribe demo entrypoint."""
    conn_handler = RussoundTcpConnectionHandler(HOST, PORT)
    client = RussoundRNETClient(conn_handler)

    await client.connect()

    for zone in range(1, 4):
        print(f"\n===== ZONE {zone} =====")

        # Turn ON
        print("Turning ON")
        await client.set_zone_power(1, zone, True)

        await asyncio.sleep(2)

        print("Get status after ON")
        x = await client.get_all_zone_info(1, zone)
        print(x)
        print(x.power)
        print(x.volume)

        await asyncio.sleep(2)
        print("Set vol")
        await client.set_volume(1, zone, 38)
        await asyncio.sleep(2)

        print("Get status after vol set")
        x = await client.get_all_zone_info(1, zone)
        print(x)

        await asyncio.sleep(2)
        print("Set source")
        await client.select_source(1, zone, 2)
        await asyncio.sleep(2)

        print("Get status after source set")
        x = await client.get_all_zone_info(1, zone)
        print(x)

        await asyncio.sleep(2)

        # Turn OFF
        print("Turning OFF")
        await client.set_zone_power(1, zone, False)

        await asyncio.sleep(2)

    await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
