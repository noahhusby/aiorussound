import asyncio
import re
import logging

from aiorussound.const import FeatureFlag, MINIMUM_API_SUPPORT, FLAGS_BY_VERSION
from aiorussound.exceptions import UncachedVariable, CommandException, UnsupportedRussoundVersion
from aiorussound.util import is_feature_supported, is_fw_version_higher

# Maintain compat with various 3.x async changes
if hasattr(asyncio, "ensure_future"):
    ensure_future = asyncio.ensure_future
else:
    ensure_future = getattr(asyncio, "async")

_LOGGER = logging.getLogger(__package__)

_re_response = re.compile(
    r"(?:(?:C\[(?P<controller>\d+)](?:\.Z\[(?P<zone>\d+)])?|C\[(?P<controller_alt>\d+)]\.S\[(?P<source>\d+)])?\.("
    r"?P<variable>\S+)|(?P<variable_no_prefix>\S+))=\s*\"(?P<value>.*)\""
)


class Russound:
    """Manages the RIO connection to a Russound device."""

    def __init__(self, loop, host, port=9621):
        """
        Initialize the Russound object using the event loop, host and port
        provided.
        """
        self._loop = loop
        self._host = host
        self._port = port
        self._ioloop_future = None
        self._cmd_queue = asyncio.Queue()
        self._source_state = {}
        self._zone_state = {}
        self._controller_state = {}
        self._zone_callbacks = []
        self._source_callbacks = []
        self.rio_version = None

    def _retrieve_cached_zone_variable(self, controller_id, zone_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        zone. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._zone_state[f"C[{controller_id}].Z[{zone_id}]"][name.lower()]
            _LOGGER.debug(
                "Zone Cache retrieve %s.%s = %s", f"C[{controller_id}.Z[{zone_id}]", name, s
            )
            return s
        except KeyError:
            raise UncachedVariable

    def _store_cached_zone_variable(self, zone_id, name, value):
        """
        Stores the current known value of a zone variable into the cache.
        Calls any zone callbacks.
        """
        zone_state = self._zone_state.setdefault(zone_id, {})
        name = name.lower()
        zone_state[name] = value
        _LOGGER.debug("Zone Cache store %s.%s = %s", zone_id.device_str(), name, value)
        for callback in self._zone_callbacks:
            callback(zone_id, name, value)

    def _retrieve_cached_source_variable(self, source_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        source. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._source_state[source_id][name.lower()]
            _LOGGER.debug("Source Cache retrieve S[%d].%s = %s", source_id, name, s)
            return s
        except KeyError:
            raise UncachedVariable

    def _store_cached_source_variable(self, source_id, name, value):
        """
        Stores the current known value of a source variable into the cache.
        Calls any source callbacks.
        """
        source_state = self._source_state.setdefault(source_id, {})
        name = name.lower()
        source_state[name] = value
        _LOGGER.debug("Source Cache store S[%d].%s = %s", source_id, name, value)
        for callback in self._source_callbacks:
            callback(source_id, name, value)

    def _process_response(self, res):
        s = str(res, "utf-8").strip()
        ty, payload = s[0], s[2:]
        if ty == "E":
            _LOGGER.debug("Device responded with error: %s", payload)
            raise CommandException(payload)

        m = _re_response.match(payload)
        if not m:
            return ty, None

        p = m.groupdict()
        if p["source"]:
            source_id = int(p["source"])
            self._store_cached_source_variable(source_id, p["variable"], p["value"])
        elif p["zone"]:
            print(")")
            # zone_id = ZoneID(controller=p["controller"], zone=p["zone"])
            # self._store_cached_zone_variable(zone_id, p["variable"], p["value"])

        return ty, p["value"]

    async def _ioloop(self, reader, writer):
        queue_future = ensure_future(self._cmd_queue.get())
        net_future = ensure_future(reader.readline())
        try:
            _LOGGER.debug("Starting IO loop")
            while True:
                done, pending = await asyncio.wait(
                    [queue_future, net_future], return_when=asyncio.FIRST_COMPLETED
                )

                if net_future in done:
                    response = net_future.result()
                    try:
                        self._process_response(response)
                    except CommandException:
                        pass
                    net_future = ensure_future(reader.readline())

                if queue_future in done:
                    cmd, future = queue_future.result()
                    cmd += "\r"
                    writer.write(bytearray(cmd, "utf-8"))
                    await writer.drain()

                    queue_future = ensure_future(self._cmd_queue.get())

                    while True:
                        response = await net_future
                        net_future = ensure_future(reader.readline())
                        try:
                            ty, value = self._process_response(response)
                            if ty == "S":
                                future.set_result(value)
                                break
                        except CommandException as e:
                            future.set_exception(e)
                            break
            _LOGGER.debug("IO loop exited")
        except asyncio.CancelledError:
            _LOGGER.debug("IO loop cancelled")
            writer.close()
            queue_future.cancel()
            net_future.cancel()
            raise
        except Exception:
            _LOGGER.exception("Unhandled exception in IO loop")
            raise

    async def _send_cmd(self, cmd):
        future = asyncio.Future()
        await self._cmd_queue.put((cmd, future))
        r = await future
        return r

    def add_zone_callback(self, callback):
        """
        Registers a callback to be called whenever a zone variable changes.
        The callback will be passed three arguments: the zone_id, the variable
        name and the variable value.
        """
        self._zone_callbacks.append(callback)

    def remove_zone_callback(self, callback):
        """
        Removes a previously registered zone callback.
        """
        self._zone_callbacks.remove(callback)

    def add_source_callback(self, callback):
        """
        Registers a callback to be called whenever a source variable changes.
        The callback will be passed three arguments: the source_id, the
        variable name and the variable value.
        """
        self._source_callbacks.append(callback)

    def remove_source_callback(self, source_id, callback):
        """
        Removes a previously registered zone callback.
        """
        self._source_callbacks.remove(callback)

    async def connect(self):
        """
        Connect to the controller and start processing responses.
        """
        _LOGGER.info("Connecting to %s:%s", self._host, self._port)
        reader, writer = await asyncio.open_connection(self._host, self._port)
        self._ioloop_future = ensure_future(self._ioloop(reader, writer))
        rio_version = await self._send_cmd('VERSION')
        if not is_fw_version_higher(rio_version, MINIMUM_API_SUPPORT):
            raise UnsupportedRussoundVersion(f"Russound RIO API v{rio_version} is not supported. The minimum "
                                             f"supported version is v{MINIMUM_API_SUPPORT}")
        self.rio_version = rio_version
        _LOGGER.info(f"Connected (Russound RIO v{self.rio_version})")

    async def close(self):
        """
        Disconnect from the controller.
        """
        _LOGGER.info("Closing connection to %s:%s", self._host, self._port)
        self._ioloop_future.cancel()
        try:
            await self._ioloop_future
        except asyncio.CancelledError:
            pass

    async def set_zone_variable(self, zone_id, variable, value):
        """
        Set a zone variable to a new value.
        """
        return self._send_cmd(f'SET {zone_id.device_str()}.{variable}="{value}"')

    async def get_zone_variable(self, controller_id, zone_id, variable):
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller."""

        try:
            return self._retrieve_cached_zone_variable(controller_id, zone_id, variable)
        except UncachedVariable:
            return await self._send_cmd(f"GET C[{controller_id}].Z[{zone_id}].{variable}")

    def get_cached_zone_variable(self, controller_id, zone_id, variable, default=None):
        """Retrieve the current value of a zone variable from the cache or
        return the default value if the variable is not present."""

        try:
            return self._retrieve_cached_zone_variable(controller_id, zone_id, variable)
        except UncachedVariable:
            return default

    async def enumerate_controllers(self):
        """Return a list of (controller_id, controller_macAddress, controller_type) tuples"""
        controllers: list[Controller] = []
        # Search for first controller, then iterate if RNET is supported
        for controller_id in range(1, 8):
            try:
                mac_address = await self.get_controller_variable(
                    controller_id, "macAddress"
                )
                if not mac_address:
                    continue
                controller_type = None
                if is_feature_supported(self.rio_version, FeatureFlag.PROPERTY_CTRL_TYPE):
                    controller_type = await self.get_controller_variable(
                        controller_id, "type"
                    )
                firmware_version = None
                if is_feature_supported(self.rio_version, FeatureFlag.PROPERTY_FIRMWARE_VERSION):
                    firmware_version = await self.get_controller_variable(
                        controller_id, "firmwareVersion"
                    )
                controllers.append(Controller(self, controller_id, mac_address, controller_type, firmware_version))
            except CommandException:
                continue

        return controllers

    async def set_source_variable(self, source_id, variable, value):
        """Change the value of a source variable."""
        source_id = int(source_id)
        return self._send_cmd(
            f'SET S[{source_id}].{variable}="{value}"'
        )

    async def get_source_variable(self, source_id, variable):
        """Get the current value of a source variable. If the variable is not
        in the cache it will be retrieved from the controller."""

        source_id = int(source_id)
        try:
            return self._retrieve_cached_source_variable(source_id, variable)
        except UncachedVariable:
            return await self._send_cmd(f"GET S[{source_id}].{variable}")

    def get_cached_source_variable(self, source_id, variable, default=None):
        """Get the cached value of a source variable. If the variable is not
        cached return the default value."""

        source_id = int(source_id)
        try:
            return self._retrieve_cached_source_variable(source_id, variable)
        except UncachedVariable:
            return default

    async def watch_source(self, source_id):
        """Add a souce to the watchlist."""
        source_id = int(source_id)
        r = await self._send_cmd(f"WATCH S[{source_id}] ON")
        return r

    async def unwatch_source(self, source_id):
        """Remove a souce from the watchlist."""
        source_id = int(source_id)
        return await self._send_cmd(f"WATCH S[{source_id}] OFF")

    async def enumerate_sources(self):
        """Return a list of (source_id, source_name) tuples"""
        sources = []
        for source_id in range(1, 17):
            try:
                name = await self.get_source_variable(source_id, "name")
                if name:
                    sources.append((source_id, name))
            except CommandException:
                break
        return sources

    async def get_controller_variable(self, controller_id, variable):
        """Get the current value of a controller variable. If the variable is not
        in the cache it will be retrieved from the controller."""

        controller_id = int(controller_id)
        try:
            return self._retrieve_cached_controller_variable(controller_id, variable)
        except UncachedVariable:
            return await self._send_cmd(f"GET C[{controller_id}].{variable}")

    def _retrieve_cached_controller_variable(self, controller_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        controller. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._controller_state[controller_id][name.lower()]
            _LOGGER.debug(
                "Controller Cache retrieve C[%d].%s = %s", controller_id, name, s
            )
            return s
        except KeyError:
            raise UncachedVariable

    def _store_cached_controller_variable(self, controller_id, name, value):
        """
        Stores the current known value of a controller variable into the cache.
        """
        controller_state = self._controller_state.setdefault(controller_id, {})
        name = name.lower()
        controller_state[name] = value
        _LOGGER.debug("Controller Cache store C[%d].%s = %s", controller_id, name, value)

    @property
    def supported_features(self):
        flags: list[FeatureFlag] = []
        for key in FLAGS_BY_VERSION.keys():
            if is_fw_version_higher(self.rio_version, key):
                for flag in FLAGS_BY_VERSION[key]:
                    flags.append(flag)
        return flags


class Controller:
    """Uniquely identifies a controller"""

    def __init__(self, instance: Russound, controller_id: int, mac_address: str, controller_type: str,
                 firmware_version: str):
        self.instance = instance
        self.controller_id = controller_id
        self.mac_address = mac_address
        self.controller_type = controller_type
        self.firmware_version = firmware_version
        self.zones = {}
        self.max_zones = 8
        # TODO: Metadata fetching

    def __str__(self):
        return f"{self.controller_id}"

    def __eq__(self, other):
        return (
                hasattr(other, "controller_id")
                and other.controller_id == self.controller_id
        )

    def __hash__(self):
        return hash(str(self))

    async def enumerate_zones(self):
        """Return a list of (zone_id, zone_name) tuples"""
        zones = []
        for zone_id in range(1, self.max_zones):
            try:
                #
                name = await self.instance.get_zone_variable(self.controller_id, zone_id, "name")
                if name:
                    zones.append((zone_id, Zone(self.instance, self, zone_id, name)))
            except CommandException:
                break
        return zones


class Zone:
    """Uniquely identifies a zone

    Russound controllers can be linked together to expand the total zone count.
    Zones are identified by their zone index (1-N) within the controller they
    belong to and the controller index (1-N) within the entire system.
    """

    def __init__(self, instance: Russound, controller: Controller, zone_id: int, name: str):
        self.instance = instance
        self.controller = controller
        self.zone_id = int(zone_id)
        self.name = name

    def __str__(self):
        return f"{self.controller.controller_id}:{self.zone_id}"

    def __eq__(self, other):
        return (
                hasattr(other, "zone")
                and hasattr(other, "controller")
                and other.zone == self.zone_id
                and other.controller == self.controller
        )

    def __hash__(self):
        return hash(str(self))

    def device_str(self):
        """
        Generate a string that can be used to reference this zone in a RIO
        command
        """
        return f"C[{self.controller.controller_id}].Z[{self.zone_id}]"

    async def watch(self):
        """Add a zone to the watchlist.
        Zones on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client"""
        r = await self.instance._send_cmd(f"WATCH {self.device_str()} ON")
        return r

    async def unwatch(self):
        """Remove a zone from the watchlist."""
        return await self.instance._send_cmd(f"WATCH {self.device_str()} OFF")

    async def send_event(self, event_name, *args):
        """Send an event to a zone."""
        cmd = "EVENT %s!%s %s" % (
            self.device_str(),
            event_name,
            " ".join(str(x) for x in args),
        )
        return await self.instance._send_cmd(cmd)

    async def _get(self, variable):
        return await self.instance.get_zone_variable(self.controller.controller_id, self.zone_id, variable)

    @property
    def current_source(self):
        return self._get('currentSource')

    @property
    def volume(self):
        return self._get('volume')

    @property
    def bass(self):
        return self._get('bass')

    @property
    def treble(self):
        return self._get('treble')

    @property
    def balance(self):
        return self._get('balance')

    @property
    def loudness(self):
        return self._get('loudness')

    @property
    def turn_on_volume(self):
        return self._get('turnOnVolume')

    @property
    def do_not_disturb(self):
        return self._get('doNotDisturb')

    @property
    def party_mode(self):
        return self._get('partyMode')

    @property
    def status(self):
        return self._get('status')

    @property
    def mute(self):
        return self._get('mute')

    @property
    def shared_source(self):
        return self._get('sharedSource')

    @property
    def last_error(self):
        return self._get('lastError')

    @property
    def page(self):
        return self._get('page')

    @property
    def sleep_time_default(self):
        return self._get('sleepTimeDefault')

    @property
    def sleep_time_remaining(self):
        return self._get('sleepTimeRemaining')

    @property
    def enabled(self):
        return self._get('enabled')
