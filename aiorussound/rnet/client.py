"""Asynchronous Python client for Russound RNET."""

import asyncio
import contextlib
import logging

from aiorussound import RussoundError
from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import RNET_TIMEOUT
from aiorussound.rnet.models import RNETQueuedRequest, RNETZoneInfo
from aiorussound.util import hex_dump, calculate_checksum, build_packet

_LOGGER = logging.getLogger(__package__)


class RussoundRNETClient:
    """Manages the RNET connection to a Russound device."""

    def __init__(
        self,
        connection_handler: RussoundConnectionHandler,
        mca_compatibility: bool = False,
    ) -> None:
        """Initialize the Russound object using the event loop and connection_handler provided."""
        self.connection_handler = connection_handler
        self._queue: asyncio.Queue[RNETQueuedRequest] = asyncio.Queue()
        self._consumer_task: asyncio.Task[None] | None = None
        self.mca_compatibility = mca_compatibility

    async def connect(self) -> None:
        """Connect to the Russound RNET device."""
        if self.is_connected:
            return
        await self.disconnect()
        await self.connection_handler.connect()
        # TODO: Probe device
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

    async def _send_fire_and_forget(self, payload: bytes) -> None:
        """Send a packet that does not expect a response."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes | None] = loop.create_future()

        request = RNETQueuedRequest(
            payload=payload, expect_response=False, future=future
        )
        await self._queue.put(request)
        await future

    async def _send_with_response(
        self,
        payload: bytes,
        response_signature: bytes,
    ) -> bytes:
        """Send a packet and return the raw response bytes."""
        loop = asyncio.get_running_loop()

        future: asyncio.Future[bytes | None] = loop.create_future()

        request = RNETQueuedRequest(
            payload=payload,
            expect_response=True,
            future=future,
            response_signature=response_signature,
        )

        await self._queue.put(request)
        response = await future

        if response is None:
            raise RuntimeError("Expected RNET response but got None")

        return response

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

                    await asyncio.sleep(0.1)

                    if not request.expect_response:
                        cleared = await self._clear_incoming_buffer(delay=0.1)

                        if cleared:
                            _LOGGER.debug("RNET cleared: %s", hex_dump(cleared))
                        if not request.future.done():
                            request.future.set_result(None)
                        continue

                    assert request.response_signature
                    response = await self._read_matching_message(
                        signature=request.response_signature
                    )

                    _LOGGER.debug("RNET recv: %s", hex_dump(response))

                    ack = await self._build_ack(response)
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

    async def _read_matching_message(self, signature: bytes) -> bytes:
        """Read one complete RNET packet from the device."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + RNET_TIMEOUT

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for RNET response containing {hex_dump(signature)}"
                )
            packet = await asyncio.wait_for(self._read_message(), timeout=remaining)

            _LOGGER.debug("RNET recv candidate: %s", hex_dump(packet))

            if signature in packet:
                return packet

    async def _clear_incoming_buffer(self, delay: float = 0.1) -> bytes:
        """Wait briefly, then read and return one chunk of available data.

        Used for commands like zone power where we do not care about a specific
        response, but want to clear any returned bytes before sending the next
        command.
        """
        if self.connection_handler.reader is None:
            raise RuntimeError("RNET reader is not connected")

        await asyncio.sleep(delay)

        try:
            data = await asyncio.wait_for(
                self.connection_handler.reader.read(4096), timeout=0.1
            )
        except asyncio.TimeoutError:
            return b""

        return data

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

    async def set_zone_power(self, controller: int, zone: int, power: bool) -> None:
        """Turn a zone on or off."""
        value = 0x01 if power else 0x00
        controller, zone = self._validate_controller_zone(controller, zone)
        payload = [
            0xF0,
            controller,
            0x00,
            0x7F,
            0x00,
            zone if self.mca_compatibility else 0x00,
            0x70,
            0x05,
            0x02,
            0x02,
            0x00,
            0x00,
            0xF1,
            0x23,
            0x00,
            value,
            0x00,
            zone,
            0x00,
            0x01,
        ]

        packet = build_packet(payload)
        await self._send_fire_and_forget(packet)

    async def set_volume(self, controller: int, zone: int, volume: int) -> None:
        """Set volume (0–50)."""
        controller, zone = self._validate_controller_zone(controller, zone)
        if not 0 <= volume <= 50:
            raise ValueError("Volume must be 0–50")

        payload = [
            0xF0,
            controller,
            0x00,
            0x7F,
            0x00,
            zone if self.mca_compatibility else 0x00,
            0x70,
            0x05,
            0x02,
            0x02,
            0x00,
            0x00,
            0xF1,
            0x21,
            0x00,
            volume,
            0x00,
            zone,
            0x00,
            0x01,
        ]

        packet = build_packet(payload)
        await self._send_fire_and_forget(packet)

    async def select_source(self, controller: int, zone: int, source: int) -> None:
        """Select source (1-based)."""
        controller, zone = self._validate_controller_zone(controller, zone)
        if not 1 <= source <= 8:
            raise ValueError("Source must be 1–8")

        source_raw = source - 1

        payload = [
            0xF0,
            controller,
            0x00,
            0x7F,
            0x00,
            zone,
            0x70,
            0x05,
            0x02,
            0x00,
            0x00,
            0x00,
            0xF1,
            0x3E,
            0x00,
            0x00,
            0x00,
            source_raw,
            0x00,
            0x01,
        ]

        packet = build_packet(payload)
        await self._send_fire_and_forget(packet)

    async def get_all_zone_info(self, controller: int, zone: int) -> RNETZoneInfo:
        """Request all available states for a zone."""
        controller, zone = self._validate_controller_zone(controller, zone)
        payload = [
            0xF0,
            controller,
            0x00,
            0x7F,
            0x00,
            0x00,
            0x70,
            0x01,  # Request Data
            0x04,
            0x02,
            0x00,
            zone,
            0x07,  # Get All Zone Info
            0x00,
            0x00,
        ]

        response_signature = bytes([0x04, 0x02, 0x00, zone, 0x07])

        packet = build_packet(payload)
        response = await self._send_with_response(packet, response_signature)

        if len(response) < 34:
            raise ValueError(
                f"Unexpected Get All Zone Info response length: {len(response)}"
            )

        return RNETZoneInfo(
            power_raw=response[20],
            source_raw=response[21],
            volume_raw=response[22],
            bass_raw=response[23],
            treble_raw=response[24],
            loudness_raw=response[25],
            balance_raw=response[26],
            system_on_raw=response[27],
            shared_source_raw=response[28],
            party_mode_raw=response[29],
            do_not_disturb_raw=response[30],
        )

    async def toggle_mute(self, controller: int, zone: int) -> None:
        """Toggle mute for a zone."""
        controller, zone = self._validate_controller_zone(controller, zone)
        payload = [
            0xF0,
            controller,
            0x00,
            0x7F,
            0x00,
            zone,
            0x70,
            0x05,
            0x02,
            0x02,
            0x00,
            0x00,
            0xF1,
            0x40,
            0x00,
            0x00,
            0x00,
            0x0D,
            0x00,
            0x01,
        ]

        packet = build_packet(payload)
        await self._send_fire_and_forget(packet)

    @staticmethod
    def _validate_controller_zone(controller: int, zone: int) -> tuple[int, int]:
        """Validate the controller and zone are valid."""
        if not (1 <= controller <= 6):
            raise ValueError(f"controller must be in [1, 6], got {controller}")
        if not (1 <= zone <= 8):
            raise ValueError(f"zone must be in [1, 8], got {zone}")
        return controller - 1, zone - 1
