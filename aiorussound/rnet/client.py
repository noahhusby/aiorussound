"""Asynchronous Python client for Russound RNET."""

import asyncio
import contextlib
import logging

from aiorussound import RussoundError
from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import TIMEOUT
from aiorussound.rnet.models import RNETQueuedRequest
from aiorussound.util import hex_dump, calculate_checksum

_LOGGER = logging.getLogger(__package__)


class RussoundRNETClient:
    """Manages the RNET connection to a Russound device."""

    def __init__(self, connection_handler: RussoundConnectionHandler) -> None:
        """Initialize the Russound object using the event loop and connection_handler provided."""
        self.connection_handler = connection_handler
        self._queue: asyncio.Queue[RNETQueuedRequest] = asyncio.Queue()
        self._consumer_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Connect to the Russound RNET device."""
        if self.is_connected:
            return
        await self.disconnect()
        await self.connection_handler.connect()
        self._consumer_task = asyncio.create_task(
            self._consumer_handler(), name="rnet_consumer_handler"
        )

    async def disconnect(self) -> None:
        """Disconnect from the RNET device."""
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None

        if self.connection_handler.writer is not None:
            self.connection_handler.writer.close()
            with contextlib.suppress(Exception):
                await self.connection_handler.writer.wait_closed()
            self.connection_handler.writer = None
        self.connection_handler.reader = None

    @property
    def is_connected(self) -> bool:
        """Check if the RNET connection is connected."""
        return bool(
            self.connection_handler.reader is not None
            and self.connection_handler.writer is not None
            and not self.connection_handler.writer.is_closing()
            and self._consumer_task is not None
            and not self._consumer_task.done()
        )

    async def _consumer_handler(self) -> None:
        """Process queued RNET requests serially."""
        try:
            while True:
                request = await self._queue.get()

                try:
                    if self.connection_handler.writer is None:
                        raise RuntimeError("RNET writer is not connected")

                    _LOGGER.debug("RNET send: %s", hex_dump(request.payload))
                    await self.connection_handler.write(request.payload)

                    if not request.expect_response:
                        if not request.future.done():
                            request.future.set_result(None)
                        continue

                    response = await asyncio.wait_for(
                        self._read_message(),
                        timeout=TIMEOUT,
                    )

                    _LOGGER.debug("RNET recv: %s", hex_dump(response))

                    ack = self._build_ack(response)
                    _LOGGER.debug("RNET ack: %s", hex_dump(ack))
                    await self.connection_handler.write(ack)

                    if not request.future.done():
                        request.future.set_result(response)
                except asyncio.CancelledError:
                    if not request.future.done():
                        request.future.cancel()
                    raise

                except Exception as err:
                    _LOGGER.debug("RNET request failed", exc_info=err)
                    if not request.future.done():
                        request.future.set_exception(err)
        except asyncio.CancelledError:
            _LOGGER.debug("RNET consumer handler cancelled")
            raise
        finally:
            while not self._queue.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    pending = self._queue.get_nowait()
                    if not pending.future.done():
                        pending.future.cancel()

    async def _read_message(self) -> bytes:
        """Read one complete RNET packet from the device."""
        if self.connection_handler.reader is None:
            raise RussoundError("RNET reader is not connected")

        while True:
            first = await self.connection_handler.reader.readexactly(1)
            if first[0] == 0xF0:
                break

        packet = bytearray(first)

        while True:
            chunk = await self.connection_handler.reader.readexactly(1)
            packet.extend(chunk)
            if chunk[0] == 0xF7:
                return bytes(packet)

    @staticmethod
    async def _build_ack(message: bytes) -> bytes:
        """Build a minimal RNET ACK for a received message."""
        if len(message) < 8:
            raise ValueError("Message too short to build ACK")
        if message[0] != 0xF0 or message[-1] != 0xF7:
            raise ValueError("Invalid RNET packet")

        target_device_id = message[1:4]
        source_device_id = message[4:7]

        ack_payload = [0xF0, *source_device_id, *target_device_id, 0x02, 0x06]

        checksum = calculate_checksum(ack_payload)
        return bytes([*ack_payload, checksum, 0xF7])
