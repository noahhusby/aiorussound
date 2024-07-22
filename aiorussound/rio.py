import asyncio
import logging
from asyncio import StreamWriter, StreamReader, AbstractEventLoop

from aiorussound.const import FeatureFlag, MINIMUM_API_SUPPORT, FLAGS_BY_VERSION, RESPONSE_REGEX, DEFAULT_PORT, \
    RECONNECT_DELAY
from aiorussound.exceptions import UncachedVariable, CommandException, UnsupportedRussoundVersion
from aiorussound.util import is_feature_supported, is_fw_version_higher, zone_device_str, source_device_str, \
    controller_device_str

# Maintain compat with various 3.x async changes
if hasattr(asyncio, "ensure_future"):
    ensure_future = asyncio.ensure_future
else:
    ensure_future = getattr(asyncio, "async")

_LOGGER = logging.getLogger(__package__)


class Russound:
    """Manages the RIO connection to a Russound device."""

    def __init__(self, loop: AbstractEventLoop, host: str, port=DEFAULT_PORT):
        """
        Initialize the Russound object using the event loop, host and port
        provided.
        """
        self._loop = loop
        self._host = host
        self._port = port
        self._ioloop_future = None
        self._cmd_queue = asyncio.Queue()
        self._state = {}
        self._callbacks = {}
        self._connection_started = False
        self._watched_devices = {}
        self.rio_version = None

    def _retrieve_cached_variable(self, device_str: str, key: str):
        """
        Retrieves the cache state of the named variable for a particular
        device. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._state[device_str][key.lower()]
            _LOGGER.debug(
                "Zone Cache retrieve %s.%s = %s", device_str, key, s
            )
            return s
        except KeyError:
            raise UncachedVariable

    def _store_cached_variable(self, device_str: str, key: str, value: str):
        """
        Stores the current known value of a device variable into the cache.
        Calls any device callbacks.
        """
        zone_state = self._state.setdefault(device_str, {})
        key = key.lower()
        zone_state[key] = value
        _LOGGER.debug("Cache store %s.%s = %s", device_str, key, value)
        # Handle callbacks
        for callback in self._callbacks.get(device_str, []):
            callback(device_str, key, value)

    def _process_response(self, res: bytes):
        s = str(res, "utf-8").strip()
        ty, payload = s[0], s[2:]
        if ty == "E":
            _LOGGER.debug("Device responded with error: %s", payload)
            raise CommandException(payload)

        m = RESPONSE_REGEX.match(payload)
        if not m:
            return ty, None

        p = m.groupdict()
        if p["source"]:
            source_id = int(p["source"])
            self._store_cached_variable(source_device_str(source_id), p["variable"], p["value"])
        elif p["zone"]:
            controller_id = int(p["controller"])
            zone_id = int(p["zone"])
            self._store_cached_variable(zone_device_str(controller_id, zone_id), p["variable"], p["value"])

        return ty, p["value"] or p["value_only"]

    async def _ioloop(self, reader: StreamReader, writer: StreamWriter, reconnect: bool):
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
        except asyncio.CancelledError:
            _LOGGER.debug("IO loop cancelled")
            writer.close()
            queue_future.cancel()
            net_future.cancel()
            raise
        except asyncio.TimeoutError:
            _LOGGER.warning("Connection to Russound client timed out")
        except ConnectionResetError:
            _LOGGER.warning("Connection to Russound client reset")
        except Exception:
            _LOGGER.exception("Unhandled exception in IO loop")
            raise
        finally:
            if reconnect and self._connection_started:
                _LOGGER.info("Retrying connection to Russound client in 5s")
                await asyncio.sleep(RECONNECT_DELAY)
                await self.connect(reconnect)

    async def _send_cmd(self, cmd: str):
        future = asyncio.Future()
        await self._cmd_queue.put((cmd, future))
        r = await future
        return r

    def _add_callback(self, device_str: str, callback):
        """
        Registers a callback to be called whenever a device variable changes.
        The callback will be passed three arguments: the device_str, the variable
        name and the variable value.
        """
        callbacks = self._callbacks.setdefault(device_str, [])
        callbacks.append(callback)

    def _remove_callback(self, callback):
        """
        Removes a previously registered callback.
        """
        for callbacks in self._callbacks.values():
            callbacks.remove(callback)

    async def connect(self, reconnect=True):
        """
        Connect to the controller and start processing responses.
        """
        self._connection_started = True
        _LOGGER.info("Connecting to %s:%s", self._host, self._port)
        reader, writer = await asyncio.open_connection(self._host, self._port)
        self._ioloop_future = ensure_future(self._ioloop(reader, writer, reconnect))
        self.rio_version = await self._send_cmd('VERSION')
        if not is_fw_version_higher(self.rio_version, MINIMUM_API_SUPPORT):
            raise UnsupportedRussoundVersion(f"Russound RIO API v{self.rio_version} is not supported. The minimum "
                                             f"supported version is v{MINIMUM_API_SUPPORT}")
        _LOGGER.info(f"Connected (Russound RIO v{self.rio_version})")
        await self._watch_cached_devices()

    async def close(self):
        """
        Disconnect from the controller.
        """
        self._connection_started = False
        _LOGGER.info("Closing connection to %s:%s", self._host, self._port)
        self._ioloop_future.cancel()
        try:
            await self._ioloop_future
        except asyncio.CancelledError:
            pass

    async def set_variable(self, device_str: str, key: str, value: str):
        """
        Set a zone variable to a new value.
        """
        return self._send_cmd(f'SET {device_str}.{key}="{value}"')

    async def get_variable(self, device_str: str, key: str):
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller."""

        try:
            return self._retrieve_cached_variable(device_str, key)
        except UncachedVariable:
            return await self._send_cmd(f"GET {device_str}.{key}")

    def get_cached_variable(self, device_str: str, key: str, default=None):
        """Retrieve the current value of a zone variable from the cache or
        return the default value if the variable is not present."""
        try:
            return self._retrieve_cached_variable(device_str, key)
        except UncachedVariable:
            return default

    async def enumerate_controllers(self):
        """Return a list of (controller_id, controller_macAddress, controller_type) tuples"""
        controllers: list[Controller] = []
        # Search for first controller, then iterate if RNET is supported
        for controller_id in range(1, 8):
            device_str = controller_device_str(controller_id)
            try:
                mac_address = await self.get_variable(
                    device_str, "macAddress"
                )
                if not mac_address:
                    continue
                controller_type = None
                if is_feature_supported(self.rio_version, FeatureFlag.PROPERTY_CTRL_TYPE):
                    controller_type = await self.get_variable(
                        device_str, "type"
                    )
                firmware_version = None
                if is_feature_supported(self.rio_version, FeatureFlag.PROPERTY_FIRMWARE_VERSION):
                    firmware_version = await self.get_variable(
                        device_str, "firmwareVersion"
                    )
                controller = Controller(self, controller_id, mac_address, controller_type, firmware_version)
                await controller.fetch_configuration()
                controllers.append(controller)
            except CommandException:
                continue

        return controllers

    @property
    def supported_features(self):
        flags: list[FeatureFlag] = []
        for key in FLAGS_BY_VERSION.keys():
            if is_fw_version_higher(self.rio_version, key):
                for flag in FLAGS_BY_VERSION[key]:
                    flags.append(flag)
        return flags

    async def _watch(self, device_str: str):
        self._watched_devices[device_str] = True
        return await self._send_cmd(f"WATCH {device_str} ON")

    async def _unwatch(self, device_str: str):
        del self._watched_devices[device_str]
        return await self._send_cmd(f"WATCH {device_str} OFF")

    async def _watch_cached_devices(self):
        _LOGGER.debug("Watching cached devices")
        for device in self._watched_devices.keys():
            await self._watch(device)


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
        self.sources = {}
        self.max_zones = 8
        # TODO: Metadata fetching

    async def fetch_configuration(self):
        await self._init_zones()
        await self._init_sources()

    def __str__(self):
        return f"{self.controller_id}"

    def __eq__(self, other):
        return (
                hasattr(other, "controller_id")
                and other.controller_id == self.controller_id
        )

    def __hash__(self):
        return hash(str(self))

    async def _init_zones(self):
        """Return a list of (zone_id, zone) tuples"""
        self.zones = {}
        for zone_id in range(1, self.max_zones):
            try:
                device_str = zone_device_str(self.controller_id, zone_id)
                name = await self.instance.get_variable(device_str, "name")
                if name:
                    self.zones[zone_id] = Zone(self.instance, self, zone_id, name)
            except CommandException:
                break

    async def _init_sources(self):
        """Return a list of (zone_id, zone) tuples"""
        self.sources = {}
        for source_id in range(1, 17):
            try:
                device_str = source_device_str(source_id)
                name = await self.instance.get_variable(device_str, "name")
                if name:
                    self.sources[source_id] = Source(self.instance, self, source_id, name)
            except CommandException:
                break

    def add_callback(self, callback):
        self.instance._add_callback(controller_device_str(self.controller_id), callback)

    def remove_callback(self, callback):
        self.instance._remove_callback(callback)


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
        return f"{self.controller.mac_address} > Z{self.zone_id}"

    def __eq__(self, other):
        return (
                hasattr(other, "zone_id")
                and hasattr(other, "controller")
                and other.zone_id == self.zone_id
                and other.controller == self.controller
        )

    def __hash__(self):
        return hash(str(self))

    def device_str(self):
        """
        Generate a string that can be used to reference this zone in a RIO
        command
        """
        return zone_device_str(self.controller.controller_id, self.zone_id)

    async def watch(self):
        """Add a zone to the watchlist.
        Zones on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client"""
        return await self.instance._watch(self.device_str())

    async def unwatch(self):
        """Remove a zone from the watchlist."""
        return await self.instance._unwatch(self.device_str())

    def add_callback(self, callback):
        self.instance._add_callback(self.device_str(), callback)

    def remove_callback(self, callback):
        self.instance._remove_callback(callback)

    async def send_event(self, event_name, *args):
        """Send an event to a zone."""
        cmd = "EVENT %s!%s %s" % (
            self.device_str(),
            event_name,
            " ".join(str(x) for x in args),
        )
        return await self.instance._send_cmd(cmd)

    def _get(self, variable):
        return self.instance.get_cached_variable(self.device_str(), variable)

    @property
    def current_source(self):
        current_source = int(self._get('currentSource'))
        return self.controller.sources[current_source]

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


class Source:
    """Uniquely identifies a Source"""

    def __init__(self, instance: Russound, controller: Controller, source_id: int, name: str):
        self.instance = instance
        self.controller = controller
        self.source_id = int(source_id)
        self.name = name

    def __str__(self):
        return f"{self.controller.mac_address} > S{self.source_id}"

    def __eq__(self, other):
        return (
                hasattr(other, "source_id")
                and hasattr(other, "controller")
                and other.source_id == self.source_id
                and other.controller == self.controller
        )

    def __hash__(self):
        return hash(str(self))

    def device_str(self):
        """
        Generate a string that can be used to reference this zone in a RIO
        command
        """
        return source_device_str(self.source_id)

    def add_callback(self, callback):
        self.instance._add_callback(self.device_str(), callback)

    def remove_callback(self, callback):
        self.instance._remove_callback(callback)

    async def watch(self):
        """Add a source to the watchlist.
        Sources on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client"""
        return await self.instance._watch(self.device_str())

    async def unwatch(self):
        """Remove a source from the watchlist."""
        return await self.instance._unwatch(self.device_str())

    async def send_event(self, event_name, *args):
        """Send an event to a source."""
        cmd = "EVENT %s!%s %s" % (
            self.device_str(),
            event_name,
            " ".join(str(x) for x in args),
        )
        return await self.instance._send_cmd(cmd)

    def _get(self, variable):
        return self.instance.get_cached_variable(self.device_str(), variable)

    @property
    def type(self):
        return self._get('type')

    @property
    def channel(self):
        return self._get('channel')

    @property
    def cover_art_url(self):
        return self._get('coverArtURL')

    @property
    def channel_name(self):
        return self._get('channelName')

    @property
    def genre(self):
        return self._get('genre')

    @property
    def artist_name(self):
        return self._get('artistName')

    @property
    def album_name(self):
        return self._get('albumName')

    @property
    def playlist_name(self):
        return self._get('playlistName')

    @property
    def song_name(self):
        return self._get('songName')

    @property
    def program_service_name(self):
        return self._get('programServiceName')

    @property
    def radio_text(self):
        return self._get('radioText')

    @property
    def shuffle_mode(self):
        return self._get('shuffleMode')

    @property
    def repeat_mode(self):
        return self._get('repeatMode')

    @property
    def mode(self):
        return self._get('mode')

    @property
    def play_status(self):
        return self._get('playStatus')

    @property
    def sample_rate(self):
        return self._get('sampleRate')

    @property
    def bit_rate(self):
        return self._get('bitRate')

    @property
    def bit_depth(self):
        return self._get('bitDepth')

    @property
    def play_time(self):
        return self._get('playTime')

    @property
    def track_time(self):
        return self._get('trackTime')
