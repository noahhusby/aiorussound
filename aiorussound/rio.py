"""Asynchronous Python client for Russound RIO."""

from __future__ import annotations

import asyncio
import logging
import re
from asyncio import Future, Task, AbstractEventLoop, Queue
from dataclasses import field, dataclass
from typing import Any, Coroutine, Optional

from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import (
    FLAGS_BY_VERSION,
    MAX_SOURCE,
    MINIMUM_API_SUPPORT,
    FeatureFlag,
    MAX_RNET_CONTROLLERS,
)
from aiorussound.exceptions import (
    CommandError,
    UnsupportedFeatureError,
    RussoundError,
)
from aiorussound.models import (
    RussoundMessage,
    CallbackType,
    Source,
    Zone,
)
from aiorussound.util import (
    controller_device_str,
    is_feature_supported,
    is_fw_version_higher,
    source_device_str,
    zone_device_str,
    is_rnet_capable,
    get_max_zones,
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
        self._futures: Queue = Queue()

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

    async def request(self, cmd: str):
        _LOGGER.debug("Sending command '%s' to Russound client", cmd)
        future: Future = Future()
        await self._futures.put(future)
        try:
            await self.connection_handler.send(cmd)
        except (CommandError, RussoundError) as ex:
            _ = await self._futures.get()
            future.set_exception(ex)
        return await future

    async def _on_msg_recv(self, msg: RussoundMessage) -> None:
        if msg.type == "S":
            future: Future = await self._futures.get()
            future.set_result(msg.value)
        elif msg.type == "E":
            future: Future = await self._futures.get()
            future.set_exception(CommandError)
        if msg.branch and msg.leaf and msg.type == "N":
            # Map the RIO syntax to a state dict
            path = re.findall(r"\w+\[?\d*]?", msg.branch)
            current = self.state
            for part in path:
                match = re.match(r"(\w+)\[(\d+)]", part)
                if match:
                    key, index = match.groups()
                    index = int(index)
                    if key not in current:
                        current[key] = {}
                    if index not in current[key]:
                        current[key][index] = {}
                    current = current[key][index]
                else:
                    if part not in current:
                        current[part] = {}
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
        self.rio_version = await self.request("VERSION")
        if not is_fw_version_higher(self.rio_version, MINIMUM_API_SUPPORT):
            await self.connection_handler.close()
            raise UnsupportedFeatureError(
                f"Russound RIO API v{self.rio_version} is not supported. The minimum "
                f"supported version is v{MINIMUM_API_SUPPORT}"
            )
        _LOGGER.info("Connected (Russound RIO v%s})", self.rio_version)

        # Fetch parent controller
        parent_controller = await self._load_controller(1)
        if not parent_controller:
            raise RussoundError("No primary controller found.")

        self.controllers[1] = parent_controller

        # Only search for daisy-chained controllers if the parent supports RNET
        if is_rnet_capable(parent_controller.controller_type):
            for controller_id in range(2, MAX_RNET_CONTROLLERS + 1):
                controller = await self._load_controller(controller_id)
                if controller:
                    self.controllers[controller_id] = controller

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

        for controller_id, controller in self.controllers.items():
            for zone_id in range(1, get_max_zones(controller.controller_type) + 1):
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
            await self.request(f"WATCH {branch} ON")
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
        for controller_id, controller_data in self.state["C"].items():
            for zone_id, zone_data in controller_data["Z"].items():
                zone = ZoneControlSurface.from_dict(zone_data)
                zone.client = self
                zone.device_str = zone_device_str(controller_id, zone_id)
                self.controllers[controller_id].zones[zone_id] = zone
        await self.do_state_update_callbacks()

    async def close(self) -> None:
        """Disconnect from the controller."""
        await self.connection_handler.close()

    async def set_variable(
        self, device_str: str, key: str, value: str
    ) -> Coroutine[Any, Any, str]:
        """Set a zone variable to a new value."""
        return self.request(f'SET {device_str}.{key}="{value}"')

    async def get_variable(self, device_str: str, key: str) -> str:
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller.
        """
        return await self.request(f"GET {device_str}.{key}")

    async def _load_controller(self, controller_id: int) -> Optional[Controller]:
        device_str = controller_device_str(controller_id)
        try:
            controller_type = await self.get_variable(device_str, "type")
            if not controller_type:
                return None
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
            return Controller(controller_type, mac_address, firmware_version, {})
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


class AbstractControlSurface:
    def __init__(self):
        self.client: Optional[RussoundClient] = None
        self.device_str: Optional[str] = None


class ZoneControlSurface(Zone, AbstractControlSurface):
    async def send_event(self, event_name, *args) -> str:
        """Send an event to a zone."""
        args = " ".join(str(x) for x in args)
        cmd = f"EVENT {self.device_str}!{event_name} {args}"
        return await self.client.request(cmd)

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


@dataclass
class Controller:
    """Data class representing a Russound controller."""

    controller_type: str
    mac_address: Optional[str]
    firmware_version: Optional[str]
    zones: dict[int, ZoneControlSurface] = field(default_factory=dict)
