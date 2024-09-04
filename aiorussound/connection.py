import asyncio
import logging
from abc import abstractmethod
from asyncio import AbstractEventLoop, Queue, StreamReader, StreamWriter, Future
from typing import Any

from aiorussound import CommandError
from aiorussound.const import DEFAULT_PORT, RECONNECT_DELAY, RESPONSE_REGEX

_LOGGER = logging.getLogger(__package__)

# Maintain compat with various 3.x async changes
if hasattr(asyncio, "ensure_future"):
    ensure_future = asyncio.ensure_future
else:
    ensure_future = getattr(asyncio, "async")


def _process_response(res: bytes) -> [str, str]:
    s = str(res, "utf-8").strip()
    if not s:
        return None, None
    ty, payload = s[0], s[2:]
    if ty == "E":
        _LOGGER.debug("Device responded with error: %s", payload)
        raise CommandError(payload)

    m = RESPONSE_REGEX.match(payload)
    if not m:
        return ty, None
    p = m.groupdict()
    return ty, p["value"] or p["value_only"]


class RussoundConnectionHandler:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self._loop = loop
        self._connection_started: bool = False
        self.connected: bool = False
        self._message_callback: list[Any] = []
        self._connection_callbacks: list[Any] = []
        self._cmd_queue: Queue = Queue()

    @abstractmethod
    async def close(self):
        raise NotImplementedError

    async def send(self, cmd: str) -> str:
        """Send a command to the Russound client."""
        _LOGGER.debug("Sending command '%s' to Russound client", cmd)
        future: Future = Future()
        await self._cmd_queue.put((cmd, future))
        return await future

    @abstractmethod
    async def connect(self, reconnect=True) -> None:
        raise NotImplementedError

    async def _keep_alive(self) -> None:
        while True:
            await asyncio.sleep(900)  # 15 minutes
            _LOGGER.debug("Sending keep alive to device")
            await self.send("VERSION")

    def _set_connected(self, connected: bool):
        self.connected = connected
        for callback in self._connection_callbacks:
            callback(connected)

    def add_connection_callback(self, callback) -> None:
        """Register a callback to be called whenever the instance is connected/disconnected.
        The callback will be passed one argument: connected: bool.
        """
        self._connection_callbacks.append(callback)

    def remove_connection_callback(self, callback) -> None:
        """Removes a previously registered callback."""
        self._connection_callbacks.remove(callback)

    def add_message_callback(self, callback) -> None:
        """Register a callback to be called whenever the controller sends a message.
        The callback will be passed one argument: msg: str.
        """
        self._message_callback.append(callback)

    def remove_message_callback(self, callback) -> None:
        """Removes a previously registered callback."""
        self._message_callback.remove(callback)

    def _on_msg_recv(self, msg: str) -> None:
        for callback in self._message_callback:
            callback(msg)


class RussoundTcpConnectionHandler(RussoundConnectionHandler):

    def __init__(self, loop: AbstractEventLoop, host: str, port: int = DEFAULT_PORT) -> None:
        """Initialize the Russound object using the event loop, host and port
        provided.
        """
        super().__init__(loop)
        self.host = host
        self.port = port
        self._ioloop_future = None

    async def connect(self, reconnect=True) -> None:
        self._connection_started = True
        _LOGGER.info("Connecting to %s:%s", self.host, self.port)
        reader, writer = await asyncio.open_connection(self.host, self.port)
        self._ioloop_future = ensure_future(self._ioloop(reader, writer, reconnect))
        self._set_connected(True)

    async def close(self):
        """Disconnect from the controller."""
        self._connection_started = False
        _LOGGER.info("Closing connection to %s:%s", self.host, self.port)
        self._ioloop_future.cancel()
        try:
            await self._ioloop_future
        except asyncio.CancelledError:
            pass
        self._set_connected(False)

    async def _ioloop(
            self, reader: StreamReader, writer: StreamWriter, reconnect: bool
    ) -> None:
        queue_future = ensure_future(self._cmd_queue.get())
        net_future = ensure_future(reader.readline())
        keep_alive_task = asyncio.create_task(self._keep_alive())
        last_command_future = None

        try:
            _LOGGER.debug("Starting IO loop")
            while True:
                done, _ = await asyncio.wait(
                    [queue_future, net_future], return_when=asyncio.FIRST_COMPLETED
                )

                if net_future in done:
                    response = net_future.result()
                    try:
                        ty, value = _process_response(response)
                        response_str = str(response, encoding="utf-8").strip()
                        if response_str:
                            self._on_msg_recv(response_str)
                        if ty == "S" and last_command_future:
                            last_command_future.set_result(value)
                            last_command_future = None
                    except CommandError as e:
                        if last_command_future:
                            last_command_future.set_exception(e)
                            last_command_future = None
                        pass
                    net_future = ensure_future(reader.readline())

                if queue_future in done and not last_command_future:
                    cmd, future = queue_future.result()
                    writer.write(bytearray(f"{cmd}\r", "utf-8"))
                    await writer.drain()
                    last_command_future = future
                    queue_future = ensure_future(self._cmd_queue.get())
        except asyncio.CancelledError:
            _LOGGER.debug("IO loop cancelled")
            self._set_connected(False)
            raise
        except asyncio.TimeoutError:
            _LOGGER.warning("Connection to Russound client timed out")
        except ConnectionResetError:
            _LOGGER.warning("Connection to Russound client reset")
        except Exception:
            _LOGGER.exception("Unhandled exception in IO loop")
            self._set_connected(False)
            raise
        finally:
            _LOGGER.debug("Cancelling all tasks...")
            writer.close()
            queue_future.cancel()
            net_future.cancel()
            keep_alive_task.cancel()
            self._set_connected(False)
            if reconnect and self._connection_started:
                _LOGGER.info("Retrying connection to Russound client in 5s")
                await asyncio.sleep(RECONNECT_DELAY)
                await self.connect(reconnect)
