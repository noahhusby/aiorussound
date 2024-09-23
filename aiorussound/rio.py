"""Asynchronous Python client for Russound RIO."""

from __future__ import annotations

import logging
from typing import Any, Coroutine

from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import (
    FLAGS_BY_VERSION,
    MAX_SOURCE,
    MINIMUM_API_SUPPORT,
    SOURCE_PROPERTIES,
    ZONE_PROPERTIES,
    FeatureFlag,
    SYSTEM_VARIABLES,
)
from aiorussound.exceptions import (
    CommandError,
    UncachedVariableError,
    UnsupportedFeatureError,
)
from aiorussound.models import RussoundMessage, ZoneProperties, SourceProperties, RussoundFavorite
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

    def __init__(
                self, connection_handler: RussoundConnectionHandler
    ) -> None:
        """Initialize the Russound object using the event loop, host and port
        provided.
        """
        self.connection_handler = connection_handler
        self.connection_handler.add_message_callback(self._on_msg_recv)
        self._state: dict[str, dict[str, str]] = {}
        self._callbacks: dict[str, list[Any]] = {}
        self._watched_devices: dict[str, bool] = {}
        self._controllers: dict[int, Controller] = {}
        self.sources: dict[int, Source] = {}
        self.rio_version: str | None = None

    def _retrieve_cached_variable(self, device_str: str, key: str) -> str:
        """Retrieve the cache state of the named variable for a particular
        device. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._state[device_str][key.lower()]
            _LOGGER.debug("Zone Cache retrieve %s.%s = %s", device_str, key, s)
            return s
        except KeyError:
            raise UncachedVariableError

    def _store_cached_variable(self, device_str: str, key: str, value: str) -> None:
        """Store the current known value of a device variable into the cache.
        Calls any device callbacks.
        """
        zone_state = self._state.setdefault(device_str, {})
        key = key.lower()
        zone_state[key] = value
        _LOGGER.debug("Cache store %s.%s = %s", device_str, key, value)
        # Handle callbacks
        for callback in self._callbacks.get(device_str, []):
            callback(device_str, key, value)
        # Handle source callback
        if device_str[0] == "S":
            for controller in self._controllers.values():
                for zone in controller.zones.values():
                    source = zone.fetch_current_source()
                    if source and source.device_str() == device_str:
                        for callback in self._callbacks.get(zone.device_str(), []):
                            callback(device_str, key, value)

    def _on_msg_recv(self, msg: RussoundMessage) -> None:
        if msg.source:
            source_id = int(msg.source)
            self._store_cached_variable(
                source_device_str(source_id), msg.variable, msg.value
            )
        elif msg.zone:
            controller_id = int(msg.controller)
            zone_id = int(msg.zone)
            self._store_cached_variable(
                zone_device_str(controller_id, zone_id), msg.variable, msg.value
            )
        elif msg.variable:
            self._store_cached_variable(SYSTEM_VARIABLES, msg.variable, msg.value)

    def add_callback(self, device_str: str, callback) -> None:
        """Register a callback to be called whenever a device variable changes.
        The callback will be passed three arguments: the device_str, the variable
        name and the variable value.
        """
        callbacks = self._callbacks.setdefault(device_str, [])
        callbacks.append(callback)

    def remove_callback(self, callback) -> None:
        """Remove a previously registered callback."""
        for callbacks in self._callbacks.values():
            callbacks.remove(callback)

    async def connect(self, reconnect=True) -> None:
        """Connect to the controller and start processing responses."""
        await self.connection_handler.connect(reconnect=reconnect)
        self.rio_version = await self.connection_handler.send("VERSION")
        if not is_fw_version_higher(self.rio_version, MINIMUM_API_SUPPORT):
            await self.connection_handler.close()
            raise UnsupportedFeatureError(
                f"Russound RIO API v{self.rio_version} is not supported. The minimum "
                f"supported version is v{MINIMUM_API_SUPPORT}"
            )
        _LOGGER.info("Connected (Russound RIO v%s})", self.rio_version)
        await self._watch_cached_devices()

    async def close(self) -> None:
        """Disconnect from the controller."""
        await self.connection_handler.close()

    async def set_variable(
        self, device_str: str, key: str, value: str
    ) -> Coroutine[Any, Any, str]:
        """Set a zone variable to a new value."""
        return self.connection_handler.send(f'SET {device_str}.{key}="{value}"')

    def get_cache(self, device_str: str) -> dict:
        """Retrieve the cache for a given device by its device string."""
        return self._state.get(device_str, {})

    async def get_variable(self, device_str: str, key: str) -> str:
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller.
        """
        try:
            return self._retrieve_cached_variable(device_str, key)
        except UncachedVariableError:
            return await self.connection_handler.send(f"GET {device_str}.{key}")

    def get_cached_variable(self, device_str: str, key: str, default=None) -> str:
        """Retrieve the current value of a zone variable from the cache or
        return the default value if the variable is not present.
        """
        try:
            return self._retrieve_cached_variable(device_str, key)
        except UncachedVariableError:
            return default

    async def enumerate_controllers(self) -> dict[int, Controller]:
        """Return a list of (controller_id,
        controller_macAddress, controller_type) tuples.
        """
        controllers: dict[int, Controller] = {}
        # Search for first controller, then iterate if RNET is supported
        for controller_id in range(1, 9):
            device_str = controller_device_str(controller_id)
            try:
                controller_type = await self.get_variable(device_str, "type")
                if not controller_type:
                    continue
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
                    self,
                    controllers.get(1),
                    controller_id,
                    mac_address,
                    controller_type,
                    firmware_version,
                )
                await controller.fetch_configuration()
                controllers[controller_id] = controller
            except CommandError:
                continue
        self._controllers = controllers
        return controllers

    @property
    def supported_features(self) -> list[FeatureFlag]:
        """Gets a list of features supported by the controller."""
        flags: list[FeatureFlag] = []
        for key, value in FLAGS_BY_VERSION.items():
            if is_fw_version_higher(self.rio_version, key):
                for flag in value:
                    flags.append(flag)
        return flags

    async def watch(self, device_str: str) -> str:
        """Watch a device."""
        self._watched_devices[device_str] = True
        return await self.connection_handler.send(f"WATCH {device_str} ON")

    async def unwatch(self, device_str: str) -> str:
        """Unwatch a device."""
        del self._watched_devices[device_str]
        return await self.connection_handler.send(f"WATCH {device_str} OFF")

    async def _watch_cached_devices(self) -> None:
        _LOGGER.debug("Watching cached devices")
        for device in self._watched_devices.keys():
            await self.watch(device)

    async def init_sources(self) -> None:
        """Return a list of (zone_id, zone) tuples."""
        self.sources = {}
        for source_id in range(1, MAX_SOURCE):
            try:
                device_str = source_device_str(source_id)
                name = await self.get_variable(device_str, "name")
                if name:
                    source = Source(self, source_id, name)
                    await source.fetch_configuration()
                    self.sources[source_id] = source
            except CommandError:
                break

    async def enumerate_zone_favorites(self, zone: Zone) -> list[RussoundFavorite]:
        """Return a list of RussoundFavorite for this zone."""
        favorites = []

        for favorite_id in range(1, 2):
            try:
                valid = await self.get_variable(
                    zone.device_str(), f"favorite[{favorite_id}].valid"
                )
                if valid == "TRUE":
                    try:
                        name = await self.get_variable(
                            zone.device_str(), f"favorite[{favorite_id}].name"
                        )
                        providerMode = await self.get_variable(
                            zone.device_str(), f"favorite[{favorite_id}].providerMode"
                        )
                        albumCoverURL = await self.get_variable(
                            zone.device_str(), f"favorite[{favorite_id}].albumCoverURL"
                        )
                        source_id = await self.get_variable(
                            zone.device_str(), f"favorite[{favorite_id}].source"
                        )

                        favorites.append(
                            RussoundFavorite(
                                favorite_id,
                                False,
                                name,
                                providerMode,
                                albumCoverURL,
                                source_id,
                            )
                        )
                    except CommandError:
                        break
            except CommandError:
                continue
        return favorites

    async def enumerate_system_favorites(self) -> list[RussoundFavorite]:
        """Return a list of RussoundFavorite for this system."""
        favorites = []

        for favorite_id in range(1, 32):
            try:
                valid = await self._get_system_favorite_variable(favorite_id, "valid")
                if valid == "TRUE":
                    try:
                        name = await self._get_system_favorite_variable(
                            favorite_id, "name"
                        )
                        providerMode = await self._get_system_favorite_variable(
                            favorite_id, "providerMode"
                        )
                        albumCoverURL = await self._get_system_favorite_variable(
                            favorite_id, "albumCoverURL"
                        )
                        source_id = await self._get_system_favorite_variable(
                            favorite_id, "source"
                        )

                        favorites.append(
                            RussoundFavorite(
                                favorite_id,
                                True,
                                name,
                                providerMode,
                                albumCoverURL,
                                source_id,
                            )
                        )
                    except CommandError:
                        break
            except CommandError:
                continue
        return favorites

    async def _get_system_favorite_variable(self, favorite_id, variable) -> str:
        """Return a system favorite variable."""
        try:
            return await self.get_variable(
                SYSTEM_VARIABLES, f"favorite[{favorite_id}].{variable}"
            )
        except UncachedVariableError:
            return "False"


class Controller:
    """Uniquely identifies a controller."""

    def __init__(
        self,
        instance: RussoundClient,
        parent_controller: Controller,
        controller_id: int,
        mac_address: str,
        controller_type: str,
        firmware_version: str,
    ) -> None:
        """Initialize the controller."""
        self.instance = instance
        self.parent_controller = parent_controller
        self.controller_id = controller_id
        self.mac_address = mac_address
        self.controller_type = controller_type
        self.firmware_version = firmware_version
        self.zones: dict[int, Zone] = {}
        self.max_zones = get_max_zones(controller_type)

    async def fetch_configuration(self) -> None:
        """Fetches source and zone configuration from controller."""
        await self._init_zones()

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

    async def _init_zones(self) -> None:
        """Return a list of (zone_id, zone) tuples."""
        self.zones = {}
        for zone_id in range(1, self.max_zones + 1):
            try:
                device_str = zone_device_str(self.controller_id, zone_id)
                name = await self.instance.get_variable(device_str, "name")
                if name:
                    zone = Zone(self.instance, self, zone_id, name)
                    await zone.fetch_configuration()
                    self.zones[zone_id] = zone

            except CommandError:
                break

    def add_callback(self, callback) -> None:
        """Add a callback function to be called when a zone is changed."""
        self.instance.add_callback(controller_device_str(self.controller_id), callback)

    def remove_callback(self, callback) -> None:
        """Remove a callback function to be called when a zone is changed."""
        self.instance.remove_callback(callback)


class Zone:
    """Uniquely identifies a zone

    Russound controllers can be linked together to expand the total zone count.
    Zones are identified by their zone index (1-N) within the controller they
    belong to and the controller index (1-N) within the entire system.
    """

    def __init__(
        self, instance: RussoundClient, controller: Controller, zone_id: int, name: str
    ) -> None:
        """Initialize a zone object."""
        self.instance = instance
        self.controller = controller
        self.zone_id = int(zone_id)
        self.name = name

    async def fetch_configuration(self) -> None:
        """Fetches zone configuration from controller."""
        for prop in ZONE_PROPERTIES:
            try:
                await self.instance.get_variable(self.device_str(), prop)
            except CommandError:
                continue

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

    async def watch(self) -> str:
        """Add a zone to the watchlist.
        Zones on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client.
        """
        return await self.instance.watch(self.device_str())

    async def unwatch(self) -> str:
        """Remove a zone from the watchlist."""
        return await self.instance.unwatch(self.device_str())

    def add_callback(self, callback) -> None:
        """Adds a callback function to be called when a zone is changed."""
        self.instance.add_callback(self.device_str(), callback)

    def remove_callback(self, callback) -> None:
        """Remove a zone from the watchlist."""
        self.instance.remove_callback(callback)

    async def send_event(self, event_name, *args) -> str:
        """Send an event to a zone."""
        cmd = f"EVENT {self.device_str()}!{event_name} {" ".join(str(x) for x in args)}"
        return await self.instance.connection_handler.send(cmd)

    def _get(self, variable, default=None) -> str:
        return self.instance.get_cached_variable(self.device_str(), variable, default)

    def fetch_current_source(self) -> Source:
        """Return the current source as a source object."""
        current_source = int(self.properties.current_source)
        return self.instance.sources[current_source]

    @property
    def properties(self) -> ZoneProperties:
        return ZoneProperties.from_dict(self.instance.get_cache(self.device_str()))

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


class Source:
    """Uniquely identifies a Source."""

    def __init__(
                self, instance: RussoundClient, source_id: int, name: str
    ) -> None:
        """Initialize a Source."""
        self.instance = instance
        self.source_id = int(source_id)
        self.name = name

    async def fetch_configuration(self) -> None:
        """Fetch the current configuration of the source."""
        for prop in SOURCE_PROPERTIES:
            try:
                await self.instance.get_variable(self.device_str(), prop)
            except CommandError:
                continue

    def __str__(self) -> str:
        """Return the current configuration of the source."""
        return f"S{self.source_id}"

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        return (
                hasattr(other, "source_id")
                and other.source_id == self.source_id
        )

        def __hash__(self) -> int:
        """Hash the current configuration of the source."""
        return hash(str(self))

    def device_str(self) -> str:
        """Generate a string that can be used to reference this zone in a RIO
        command.
        """
        return source_device_str(self.source_id)

    def add_callback(self, callback: Any) -> None:
        """Add a callback function to the zone."""
        self.instance.add_callback(self.device_str(), callback)

    def remove_callback(self, callback: Any) -> None:
        """Remove a callback from the source."""
        self.instance.remove_callback(callback)

    async def watch(self) -> str:
        """Add a source to the watchlist.
        Sources on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client.
        """
        return await self.instance.watch(self.device_str())

    async def unwatch(self) -> str:
        """Remove a source from the watchlist."""
        return await self.instance.unwatch(self.device_str())

    async def send_event(self, event_name: str, *args: tuple[str, ...]) -> str:
        """Send an event to a source."""
        cmd = (
            f"EVENT {self.device_str()}!{event_name} %{" ".join(str(x) for x in args)}"
        )
        return await self.instance.connection_handler.send(cmd)

    def _get(self, variable: str) -> str:
        return self.instance.get_cached_variable(self.device_str(), variable)

    @property
    def properties(self) -> SourceProperties:
        return SourceProperties.from_dict(self.instance.get_cache(self.device_str()))

