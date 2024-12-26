import asyncio
import logging
from abc import abstractmethod
from asyncio import StreamReader
from typing import Optional

from aiorussound.const import (
    DEFAULT_PORT,
    TIMEOUT,
)

_LOGGER = logging.getLogger(__package__)


class RussoundConnectionHandler:
    def __init__(self) -> None:
        self.reader: Optional[StreamReader] = None

    async def send(self, cmd: str) -> None:
        """Send a command to the Russound client."""
        pass
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
        self.writer = None

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
        async with asyncio.timeout(TIMEOUT):
            reader, writer = await asyncio.open_connection(self.host, self.port)
        self.reader = reader
        self.writer = writer

    async def send(self, cmd: str) -> None:
        """Send a command to the Russound client."""
        await super().send(cmd)
        self.writer.write(bytearray(f"{cmd}\r", "utf-8"))
        await self.writer.drain()
