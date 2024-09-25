import asyncio
import logging

from aiorussound import RussoundTcpConnectionHandler, RussoundClient
from aiorussound.models import CallbackType

HOST = "192.168.20.17"
PORT = 4999


async def on_state_change(client: RussoundClient, callback_type: CallbackType):
    """Called when new information is received."""
    print(f"Callback Type: {callback_type}")
    print(f"Sources: {client.sources}")


async def main():
    """Subscribe demo entrypoint."""
    conn_handler = RussoundTcpConnectionHandler(asyncio.get_running_loop(), HOST, PORT)
    client = RussoundClient(conn_handler)

    await client.register_state_update_callbacks(on_state_change)
    await client.connect()

    for s_id, source in client.sources.items():
        print(f"Found source {s_id} - {source.name}")

    for c_id, controller in client.controllers.items():
        print(f"Found controller {c_id} - {controller.mac_address}")
        for z_id, zone in controller.zones.items():
            print(f"Found zone {z_id} - {zone.name}")
    print(client.state)

    # Play media using the unit's front controls or Russound app
    await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
