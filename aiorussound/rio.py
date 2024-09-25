"""Asynchronous Python client for Russound RIO."""

from __future__ import annotations

import asyncio
import logging
import re
from asyncio import Future, Task, AbstractEventLoop
from typing import Any, Coroutine, Optional

from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import (
    FLAGS_BY_VERSION,
    MAX_SOURCE,
    MINIMUM_API_SUPPORT,
    FeatureFlag,
)
from aiorussound.exceptions import (
    CommandError,
    UnsupportedFeatureError,
    RussoundError,
)
from aiorussound.models import (
    RussoundMessage,
    ZoneProperties,
    CallbackType,
    Source,
)
from aiorussound.util import (
    controller_device_str,
    get_max_zones,
    is_feature_supported,
    is_fw_version_higher,
    source_device_str,
    zone_device_str,
)

_LOGGER = logging.getLogger(__package__)


class RussoundClient:
    """Manages the RIO connection to a Russound device."""

    def __init__(self, connection_handler: RussoundConnectionHandler) -> None:
        """Initialize the Russound object using the event loop, host and port
        provided.
        """
        self.connection_handler = connection_handler
        self.connection_handler.add_message_callback(self._on_msg_recv)
        self._loop: AbstractEventLoop = asyncio.get_running_loop()
        self._subscriptions: dict[str, Any] = {}
        self.connect_result: Future | None = None
        self.connect_task: Task | None = None
        self._state_update_callbacks: list[Any] = []
        self.controllers: dict[int, Controller] = {}
        self.sources: dict[int, Source] = {}
        self.rio_version: str | None = None
        self.state = {}

    async def register_state_update_callbacks(self, callback: Any):
        """Register state update callback."""
        self._state_update_callbacks.append(callback)
        await callback(self, CallbackType.STATE)

    def unregister_state_update_callbacks(self, callback: Any):
        """Unregister state update callback."""
        if callback in self._state_update_callbacks:
            self._state_update_callbacks.remove(callback)

    def clear_state_update_callbacks(self):
        """Clear state update callbacks."""
        self._state_update_callbacks.clear()

    async def do_state_update_callbacks(
        self, callback_type: CallbackType = CallbackType.STATE
    ):
        """Call state update callbacks."""
        if not self._state_update_callbacks:
            return
        callbacks = set()
        for callback in self._state_update_callbacks:
            callbacks.add(callback(self, callback_type))

        if callbacks:
            await asyncio.gather(*callbacks)

    async def _on_msg_recv(self, msg: RussoundMessage) -> None:
        if msg.branch and msg.leaf and msg.type == "N":
            path = re.findall(r"\w+\[?\d*]?", msg.branch)

            # Navigate through the dictionary according to the path
            current = self.state
            for part in path:
                # Check if part contains an index (e.g., 'favorite[1]')
                match = re.match(r"(\w+)\[(\d+)]", part)
                if match:
                    key, index = match.groups()
                    index = int(index)
                    # Create the key if it doesn't exist
                    if key not in current:
                        current[key] = {}
                    # Create the indexed dictionary if it doesn't exist
                    if index not in current[key]:
                        current[key][index] = {}
                    # Move into the indexed part of the dictionary
                    current = current[key][index]
                else:
                    # Normal key without index
                    if part not in current:
                        current[part] = {}
                    # Move into the dictionary
                    current = current[part]

            # Set the leaf and value in the final dictionary location
            current[msg.leaf] = msg.value
            subscription = self._subscriptions.get(msg.branch)
            if subscription:
                await subscription()

    async def connect(self) -> None:
        """Connect to the controller and start processing responses."""
        if not self.is_connected():
            self.connect_result = self._loop.create_future()
            self.connect_task = asyncio.create_task(
                self.connect_handler(self.connect_result)
            )
        return await self.connect_result

    def is_connected(self) -> bool:
        """Return True if device is connected."""
        return self.connect_task is not None and not self.connect_task.done()

    async def connect_handler(self, res):
        await self.connection_handler.connect(reconnect=True)
        self.rio_version = await self.connection_handler.send("VERSION")
        if not is_fw_version_higher(self.rio_version, MINIMUM_API_SUPPORT):
            await self.connection_handler.close()
            raise UnsupportedFeatureError(
                f"Russound RIO API v{self.rio_version} is not supported. The minimum "
                f"supported version is v{MINIMUM_API_SUPPORT}"
            )
        _LOGGER.info("Connected (Russound RIO v%s})", self.rio_version)

        # Fetch parent controller
        has_parent_controller = await self._load_controller(1)
        if not has_parent_controller:
            raise RussoundError("No primary controller found.")

        # self.controllers[1] = parent_controller

        # Only search for daisy-chained controllers if the parent supports RNET
        # if is_rnet_capable(parent_controller.controller_type):
        #     for controller_id in range(2, MAX_RNET_CONTROLLERS + 1):
        #         controller = await self._get_controller(controller_id)
        #         if controller:
        #             self.controllers[controller_id] = controller

        subscribe_state_updates = {self.subscribe(self._async_handle_system, "System")}

        # Load source structure
        for source_id in range(1, MAX_SOURCE):
            try:
                device_str = source_device_str(source_id)
                name = await self.get_variable(device_str, "name")
                if name:
                    subscribe_state_updates.add(
                        self.subscribe(self._async_handle_source, device_str)
                    )
            except CommandError:
                break

        for controller_id in self.controllers.keys():
            for zone_id in range(1, 8 + 1):
                try:
                    device_str = zone_device_str(controller_id, zone_id)
                    name = await self.get_variable(device_str, "name")
                    if name:
                        subscribe_state_updates.add(
                            self.subscribe(self._async_handle_zone, device_str)
                        )
                except CommandError:
                    break

        subscribe_tasks = set()
        for state_update in subscribe_state_updates:
            subscribe_tasks.add(asyncio.create_task(state_update))
        await asyncio.wait(subscribe_tasks)

        # Delay to ensure async TTL
        await asyncio.sleep(0.2)

        res.set_result(True)

    async def subscribe(self, callback: Any, branch: str) -> None:
        self._subscriptions[branch] = callback
        try:
            await self.connection_handler.send(f"WATCH {branch} ON")
        except (asyncio.CancelledError, asyncio.TimeoutError, CommandError):
            del self._subscriptions[branch]
            raise

    async def _async_handle_system(self) -> None:
        """Handle async info update."""
        await self.do_state_update_callbacks()

    async def _async_handle_source(self) -> None:
        """Handle async info update."""
        for source_id, source_data in self.state["S"].items():
            source = Source.from_dict(source_data)
            source.client = self
            self.sources[source_id] = source
        await self.do_state_update_callbacks()

    async def _async_handle_zone(self) -> None:
        """Handle async info update."""
        print("Handle Zone", self.state)
        await self.do_state_update_callbacks()

    async def close(self) -> None:
        """Disconnect from the controller."""
        await self.connection_handler.close()

    async def set_variable(
        self, device_str: str, key: str, value: str
    ) -> Coroutine[Any, Any, str]:
        """Set a zone variable to a new value."""
        return self.connection_handler.send(f'SET {device_str}.{key}="{value}"')

    async def get_variable(self, device_str: str, key: str) -> str:
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller.
        """
        return await self.connection_handler.send(f"GET {device_str}.{key}")

    async def _load_controller(self, controller_id: int) -> bool:
        device_str = controller_device_str(controller_id)
        try:
            controller_type = await self.get_variable(device_str, "type")
            if not controller_type:
                return False
            mac_address = None
            try:
                mac_address = await self.get_variable(device_str, "macAddress")
            except CommandError:
                pass
            firmware_version = None
            if is_feature_supported(
                self.rio_version, FeatureFlag.PROPERTY_FIRMWARE_VERSION
            ):
                firmware_version = await self.get_variable(
                    device_str, "firmwareVersion"
                )
            controller_state = self.state.get("C", {})
            controller_state[controller_id] = {
                "type": controller_type,
                "mac_address": mac_address,
                "firmware_version": firmware_version,
            }
            self.state["C"] = controller_state
            return True
        except CommandError:
            return None

    @property
    def supported_features(self) -> list[FeatureFlag]:
        """Gets a list of features supported by the controller."""
        flags: list[FeatureFlag] = []
        for key, value in FLAGS_BY_VERSION.items():
            if is_fw_version_higher(self.rio_version, key):
                for flag in value:
                    flags.append(flag)
        return flags


class Controller:
    """Uniquely identifies a controller."""

    def __init__(
        self,
        client: RussoundClient,
        controller_id: int,
        mac_address: str,
        controller_type: str,
        firmware_version: str,
    ) -> None:
        """Initialize the controller."""
        self.client = client
        self.controller_id = controller_id
        self.mac_address = mac_address
        self.controller_type = controller_type
        self.firmware_version = firmware_version
        self.zones: dict[int, Zone] = {}
        self.max_zones = get_max_zones(controller_type)

    def __str__(self) -> str:
        """Returns a string representation of the controller."""
        return f"{self.controller_id}"

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        return (
            hasattr(other, "controller_id")
            and other.controller_id == self.controller_id
        )

    def __hash__(self) -> int:
        """Hashes the controller id."""
        return hash(str(self))


class Zone:
    """Uniquely identifies a zone

    Russound controllers can be linked together to expand the total zone count.
    Zones are identified by their zone index (1-N) within the controller they
    belong to and the controller index (1-N) within the entire system.
    """

    def __init__(
        self, client: RussoundClient, controller: Controller, zone_id: int, name: str
    ) -> None:
        """Initialize a zone object."""
        self.client = client
        self.controller = controller
        self.zone_id = int(zone_id)
        self.name = name

    def __str__(self) -> str:
        """Return a string representation of the zone."""
        return f"{self.controller.mac_address} > Z{self.zone_id}"

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        return (
            hasattr(other, "zone_id")
            and hasattr(other, "controller")
            and other.zone_id == self.zone_id
            and other.controller == self.controller
        )

    def __hash__(self) -> int:
        """Hashes the zone id."""
        return hash(str(self))

    def device_str(self) -> str:
        """Generate a string that can be used to reference this zone in a RIO
        command
        """
        return zone_device_str(self.controller.controller_id, self.zone_id)

    async def send_event(self, event_name, *args) -> str:
        """Send an event to a zone."""
        args = " ".join(str(x) for x in args)
        cmd = f"EVENT {self.device_str()}!{event_name} {args}"
        return await self.client.connection_handler.send(cmd)

    # def fetch_current_source(self) -> Source:
    #     """Return the current source as a source object."""
    #     current_source = int(self.properties.current_source)
    #     return self.client.sources[current_source]

    async def mute(self) -> str:
        """Mute the zone."""
        return await self.send_event("ZoneMuteOn")

    async def unmute(self) -> str:
        """Unmute the zone."""
        return await self.send_event("ZoneMuteOff")

    async def set_volume(self, volume: str) -> str:
        """Set the volume."""
        return await self.send_event("KeyPress", "Volume", volume)

    async def volume_up(self) -> str:
        """Volume up the zone."""
        return await self.send_event("KeyPress", "VolumeUp")

    async def volume_down(self) -> str:
        """Volume down the zone."""
        return await self.send_event("KeyPress", "VolumeDown")

    async def previous(self) -> str:
        """Go to the previous song."""
        return await self.send_event("KeyPress", "Previous")

    async def next(self) -> str:
        """Go to the next song."""
        return await self.send_event("KeyPress", "Next")

    async def stop(self) -> str:
        """Stop the current song."""
        return await self.send_event("KeyPress", "Stop")

    async def pause(self) -> str:
        """Pause the current song."""
        return await self.send_event("KeyPress", "Pause")

    async def play(self) -> str:
        """Play the queued song."""
        return await self.send_event("KeyPress", "Play")

    async def zone_on(self) -> str:
        """Turn on the zone."""
        return await self.send_event("ZoneOn")

    async def zone_off(self) -> str:
        """Turn off the zone."""
        return await self.send_event("ZoneOff")

    async def select_source(self, source: int) -> str:
        """Select a source."""
        return await self.send_event("SelectSource", source)


class AbstractRussoundClientSurface:
    def __init__(self):
        self.client: Optional[RussoundClient] = None


class ZoneControlSurface(ZoneProperties, AbstractRussoundClientSurface):
    async def do_something(self):
        print(self.client.is_connected())
