import asyncio
import logging
from abc import abstractmethod
from asyncio import StreamReader, StreamWriter
from typing import Optional

import serial_asyncio_fast

from aiorussound.const import (
    DEFAULT_PORT,
    DEFAULT_BAUDRATE,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__package__)


class RussoundConnectionHandler:
    def __init__(self) -> None:
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

    async def send(self, cmd: str) -> None:
        """Send a command to the Russound client."""
        self.writer.write(bytearray(f"{cmd}\r", "utf-8"))
        await self.writer.drain()

        # if not self.connected:
        #     raise CommandError("Not connected to device.")

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError


class RussoundTcpConnectionHandler(RussoundConnectionHandler):
    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        """Initialize the Russound object using the event loop, host and port
        provided.
        """
        super().__init__()
        self.host = host
        self.port = port

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
        async with asyncio.timeout(TIMEOUT):
            reader, writer = await asyncio.open_connection(self.host, self.port)
        self.reader = reader
        self.writer = writer


class RussoundSerialConnectionHandler(RussoundConnectionHandler):
    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        """Initialize the Russound object using the event loop, port and baudrate provided."""
        super().__init__()
        self.port = port
        self.baudrate = baudrate

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to %s (baudrate: %s)", self.port, self.baudrate)
        async with asyncio.timeout(TIMEOUT):
            self.reader, self.writer = await serial_asyncio_fast.open_serial_connection(
                url=self.port,
                baudrate=self.baudrate,
            )
