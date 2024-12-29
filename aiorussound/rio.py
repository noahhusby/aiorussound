"""Asynchronous Python client for Russound RIO."""

from __future__ import annotations

import asyncio
import logging
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
    RESPONSE_REGEX,
    KEEP_ALIVE_INTERVAL,
    TIMEOUT,
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
    MessageType,
)
from aiorussound.util import (
    controller_device_str,
    is_feature_supported,
    is_fw_version_higher,
    source_device_str,
    zone_device_str,
    is_rnet_capable,
    get_max_zones,
    map_rio_to_dict,
)

_LOGGER = logging.getLogger(__package__)


class RussoundClient:
    """Manages the RIO connection to a Russound device."""

    def __init__(self, connection_handler: RussoundConnectionHandler) -> None:
        """Initialize the Russound object using the event loop, host and port
        provided.
        """
        self.connection_handler = connection_handler
        self._loop: AbstractEventLoop = asyncio.get_running_loop()
        self._subscriptions: dict[str, Any] = {}
        self.connect_result: Future | None = None
        self.connect_task: Task | None = None
        self._reconnect_task: Optional[Task] = None
        self._state_update_callbacks: list[Any] = []
        self.controllers: dict[int, Controller] = {}
        self.sources: dict[int, Source] = {}
        self.rio_version: str | None = None
        self.state = {}
        self._futures: Queue = Queue()
        self._attempt_reconnection = False
        self._do_state_update = False

    async def register_state_update_callbacks(self, callback: Any):
        """Register state update callback."""
        self._state_update_callbacks.append(callback)
        if self._do_state_update:
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
        except Exception as ex:
            _ = await self._futures.get()
            future.set_exception(ex)
        return await future

    async def connect(self) -> None:
        """Connect to the controller and start processing responses."""
        if not self.is_connected():
            self.connect_result = self._loop.create_future()
            self._reconnect_task = asyncio.create_task(
                self._reconnect_handler(self.connect_result)
            )
        return await self.connect_result

    async def disconnect(self) -> None:
        """Disconnect from the Russound controller."""
        if self.is_connected():
            self._attempt_reconnection = False
            self.connect_task.cancel()
            try:
                await self.connect_task
            except asyncio.CancelledError:
                pass

    def is_connected(self) -> bool:
        """Return True if device is connected."""
        return self.connect_task is not None and not self.connect_task.done()

    async def _reconnect_handler(self, res):
        reconnect_delay = 0.5
        while True:
            try:
                self.connect_task = asyncio.create_task(self._connect_handler(res))
                await self.connect_task
            except Exception as ex:
                _LOGGER.error(ex)
                pass
            await self.do_state_update_callbacks(CallbackType.CONNECTION)
            if not self._attempt_reconnection:
                _LOGGER.debug(
                    "Failed to connect to device on initial pass, skipping reconnect."
                )
                break
            reconnect_delay = min(reconnect_delay * 2, 30)
            _LOGGER.debug(
                f"Attempting reconnection to Russound device in {reconnect_delay} seconds..."
            )
            await asyncio.sleep(reconnect_delay)

    async def _connect_handler(self, res):
        handler_tasks = set()
        try:
            self._do_state_update = False
            async with asyncio.timeout(TIMEOUT):
                await self.connection_handler.connect()
            handler_tasks.add(
                asyncio.create_task(self.consumer_handler(self.connection_handler))
            )
            self.rio_version = await self.request("VERSION")
            if not is_fw_version_higher(self.rio_version, MINIMUM_API_SUPPORT):
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

            self._do_state_update = True
            self._attempt_reconnection = True
            if not res.done():
                res.set_result(True)
            handler_tasks.add(asyncio.create_task(self._keep_alive()))
            await asyncio.wait(handler_tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception as ex:
            if not res.done():
                res.set_exception(ex)
            _LOGGER.error(ex, exc_info=True)
        finally:
            for task in handler_tasks:
                if not task.done():
                    task.cancel()

            while not self._futures.empty():
                future = await self._futures.get()
                future.cancel()

            self._do_state_update = False

            closeout = set()
            closeout.update(handler_tasks)

            if closeout:
                closeout_task = asyncio.create_task(asyncio.wait(closeout))
                while not closeout_task.done():
                    try:
                        await asyncio.shield(closeout_task)
                    except asyncio.CancelledError:
                        pass

    async def load_zone_source_metadata(self) -> None:
        """Fetches and subscribes to all the zone and source metadata"""

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

        if is_feature_supported(
            self.rio_version, FeatureFlag.SUPPORT_ZONE_SOURCE_EXCLUSION
        ):
            _LOGGER.debug(
                "Zone source exclusion is supported. Fetching excluded sources."
            )
            await self._load_zone_source_exclusion()
            # Reload zones from state
            await self._async_handle_zone()

        await self.do_state_update_callbacks(CallbackType.STATE)

        # Delay to ensure async TTL
        await asyncio.sleep(0.5)

    @staticmethod
    def process_response(res: bytes) -> Optional[RussoundMessage]:
        """Process an incoming string of bytes into a RussoundMessage"""
        try:
            # Attempt to decode in Latin and re-encode in UTF-8 to support international characters
            str_res = (
                res.decode(encoding="iso-8859-1")
                .encode(encoding="utf-8")
                .decode(encoding="utf-8")
                .strip()
            )
        except UnicodeDecodeError as e:
            _LOGGER.warning("Failed to decode Russound response %s", res, e)
            return None
        if not str_res:
            return None
        if len(str_res) == 1 and str_res[0] == "S":
            return RussoundMessage(MessageType.STATE, None, None, None)
        tag, payload = str_res[0], str_res[2:]
        if tag == "E":
            _LOGGER.debug("Device responded with error: %s", payload)
            return RussoundMessage(tag, None, None, payload)
        m = RESPONSE_REGEX.match(payload.strip())
        if not m:
            return RussoundMessage(tag, None, None, None)
        value = m.group(3)
        value = None if not value or value == "------" else value
        return RussoundMessage(tag, m.group(1) or None, m.group(2), value)

    async def consumer_handler(self, handler: RussoundConnectionHandler):
        """Callback consumer handler."""
        try:
            async for raw_msg in handler.reader:
                msg = self.process_response(raw_msg)
                if msg:
                    _LOGGER.debug(f"recv ({msg})")
                    if msg.type == "S" and not self._futures.empty():
                        future: Future = await self._futures.get()
                        if not future.done():
                            future.set_result(msg.value)
                    elif msg.type == "E" and not self._futures.empty():
                        future: Future = await self._futures.get()
                        if not future.done():
                            future.set_exception(CommandError)
                    if msg.branch and msg.leaf and msg.type == "N":
                        map_rio_to_dict(self.state, msg.branch, msg.leaf, msg.value)
                        subscription = self._subscriptions.get(msg.branch)
                        if subscription:
                            await subscription()
        except (asyncio.CancelledError, OSError):
            pass

    async def _keep_alive(self) -> None:
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            _LOGGER.debug("Sending keep alive to device")
            try:
                async with asyncio.timeout(TIMEOUT):
                    await self.request("VERSION")
            except asyncio.TimeoutError:
                _LOGGER.warning("Keep alive request to the Russound device timed out")
                break
        _LOGGER.debug("Ending keep alive task to attempt reconnection")

    async def subscribe(self, callback: Any, branch: str) -> None:
        self._subscriptions[branch] = callback
        try:
            await self.request(f"WATCH {branch} ON")
        except (asyncio.CancelledError, asyncio.TimeoutError, CommandError):
            del self._subscriptions[branch]
            raise

    async def _async_handle_system(self) -> None:
        """Handle async info update."""
        if self._do_state_update:
            await self.do_state_update_callbacks()

    async def _async_handle_source(self) -> None:
        """Handle async info update."""
        for source_id, source_data in self.state["S"].items():
            source = Source.from_dict(source_data)
            source.client = self
            self.sources[source_id] = source
        if self._do_state_update:
            await self.do_state_update_callbacks()

    async def _async_handle_zone(self) -> None:
        """Handle async info update."""
        for controller_id, controller_data in self.state["C"].items():
            for zone_id, zone_data in controller_data["Z"].items():
                zone = ZoneControlSurface.from_dict(zone_data)
                zone.client = self
                zone.device_str = zone_device_str(controller_id, zone_id)
                self.controllers[controller_id].zones[zone_id] = zone
        if self._do_state_update:
            await self.do_state_update_callbacks()

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
            controller = Controller(
                controller_id,
                controller_type,
                self,
                controller_device_str(controller_id),
                mac_address,
                firmware_version,
                {},
            )
            return controller
        except CommandError:
            return None

    # ----------------------
    # Manual state fixes
    # ----------------------

    async def _load_zone_source_exclusion(self) -> None:
        """Loads whether a source is available to a specific zone."""
        for controller_id, controller in self.controllers.items():
            for zone_id in controller.zones.keys():
                for source_id in self.sources.keys():
                    try:
                        enabled = await self.get_variable(
                            f"C[{controller_id}].Z[{zone_id}].S[{source_id}]", "enabled"
                        )
                    except CommandError:
                        continue
                    if enabled == "TRUE":
                        if (
                            "enabled_sources"
                            not in self.state["C"][controller_id]["Z"][zone_id]
                        ):
                            self.state["C"][controller_id]["Z"][zone_id][
                                "enabled_sources"
                            ] = []
                        self.state["C"][controller_id]["Z"][zone_id][
                            "enabled_sources"
                        ].append(source_id)

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

    def fetch_current_source(self) -> Source:
        """Return the current source as a source object."""
        return self.client.sources[self.current_source]

    async def mute(self) -> str:
        """Mute the zone."""
        return await self.send_event("ZoneMuteOn")

    async def unmute(self) -> str:
        """Unmute the zone."""
        return await self.send_event("ZoneMuteOff")

    async def toggle_mute(self) -> str:
        """Toggle the mute state of the zone."""
        return await self.send_event("KeyRelease", "Mute")

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

    controller_id: int
    controller_type: str
    client: RussoundClient
    device_str: str
    mac_address: Optional[str]
    firmware_version: Optional[str]
    zones: dict[int, ZoneControlSurface] = field(default_factory=dict)
