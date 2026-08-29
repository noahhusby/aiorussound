"""Controller-routed Russound Media Management sessions."""

from __future__ import annotations

import asyncio
import logging
import re
from asyncio import Future, Task
from typing import Self

from aiorussound.connection import RussoundConnectionHandler
from aiorussound.const import TIMEOUT
from aiorussound.exceptions import CommandError, RussoundError
from aiorussound.rio.models import (
    MediaManagementMenuPage,
    MessageType,
    RussoundMessage,
)
from aiorussound.rio.protocol import process_response

DEFAULT_MEDIA_MANAGEMENT_PAGE_SIZE = 100
DEFAULT_MEDIA_MANAGEMENT_KEEP_ALIVE_INTERVAL = 45.0

_CONTROLLER_ZONE_RE = re.compile(r"^C\[\d+]\.Z\[\d+]$")
_LOGGER = logging.getLogger(__package__)


class MediaManagementSession:
    """A dedicated controller-routed Russound Media Management session.

    Media Management state is scoped to an IP socket. This class owns a dedicated
    connection rather than sharing the RIO client's state and subscription socket.
    """

    def __init__(
        self,
        connection_handler: RussoundConnectionHandler,
        zone_device_str: str,
        *,
        page_size: int = DEFAULT_MEDIA_MANAGEMENT_PAGE_SIZE,
        keep_alive_interval: float = DEFAULT_MEDIA_MANAGEMENT_KEEP_ALIVE_INTERVAL,
    ) -> None:
        """Initialize the session."""
        if not _CONTROLLER_ZONE_RE.match(zone_device_str):
            raise ValueError(
                "Media Management sessions must target a controller zone, such as C[1].Z[1]"
            )
        if not 1 <= page_size <= 255:
            raise ValueError("Media Management page size must be between 1 and 255")
        if keep_alive_interval <= 0:
            raise ValueError("Media Management keep-alive interval must be positive")

        self._connection_handler = connection_handler
        self._zone_device_str = zone_device_str
        self._page_size = page_size
        self._keep_alive_interval = keep_alive_interval
        self._command_lock = asyncio.Lock()
        self._consumer_task: Task[None] | None = None
        self._keep_alive_task: Task[None] | None = None
        self._response_future: Future[RussoundMessage] | None = None
        self._page_future: Future[MediaManagementMenuPage] | None = None

    async def __aenter__(self) -> Self:
        """Connect to the dedicated Media Management socket."""
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the dedicated Media Management socket."""
        await self.close()

    @property
    def is_connected(self) -> bool:
        """Return whether the session consumer is active."""
        return self._consumer_task is not None and not self._consumer_task.done()

    async def connect(self) -> None:
        """Connect and begin consuming RIO responses."""
        if self.is_connected:
            return
        await self._connection_handler.connect()
        if self._connection_handler.reader is None:
            raise RussoundError("Media Management connection did not provide a reader")
        self._consumer_task = asyncio.create_task(self._consume())

    async def initialize(self) -> MediaManagementMenuPage:
        """Configure a JSON session and return the top-level Media Management page."""
        await self.connect()
        async with self._command_lock:
            await self._send_event_locked("MMVerbosity", "2")
            await self._send_event_locked("MMIndex", '"ABSOLUTE"')
            await self._send_event_locked("MMMaxItems", str(self._page_size))
            await self._send_event_locked("MMFormat", '"JSON"')
            page = await self._send_event_locked("MMInit", expect_page=True)

        if page is None:
            raise RussoundError(
                "Media Management initialization did not return a menu page"
            )

        if self._keep_alive_task is None or self._keep_alive_task.done():
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        return page

    async def close(self) -> None:
        """Close the Media Management session and its dedicated connection."""
        if self.is_connected:
            try:
                await self._send_event("MMClose")
            except (CommandError, RussoundError, TimeoutError):
                _LOGGER.debug("Unable to close Media Management session cleanly")

        for task in (self._keep_alive_task, self._consumer_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._keep_alive_task, self._consumer_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._fail_pending(RussoundError("Media Management session closed"))
        await self._connection_handler.close()

    async def _send_event(
        self, event_name: str, *args: str, expect_page: bool = False
    ) -> MediaManagementMenuPage | None:
        """Serialize an MM EVENT and wait for its response."""
        async with self._command_lock:
            return await self._send_event_locked(
                event_name, *args, expect_page=expect_page
            )

    async def _send_event_locked(
        self, event_name: str, *args: str, expect_page: bool = False
    ) -> MediaManagementMenuPage | None:
        """Send an MM EVENT while the command lock is held."""
        if not self.is_connected:
            raise RussoundError("Media Management session is not connected")

        loop = asyncio.get_running_loop()
        response_future: Future[RussoundMessage] = loop.create_future()
        page_future: Future[MediaManagementMenuPage] | None = None
        if expect_page:
            page_future = loop.create_future()
        self._response_future = response_future
        self._page_future = page_future

        command = _event_command(self._zone_device_str, event_name, *args)
        try:
            await self._connection_handler.write_str(command)
            await asyncio.wait_for(response_future, timeout=TIMEOUT)
            if page_future is not None:
                return await asyncio.wait_for(page_future, timeout=TIMEOUT)
            return None
        finally:
            if self._response_future is response_future:
                self._response_future = None
            if self._page_future is page_future:
                self._page_future = None

    async def _consume(self) -> None:
        """Consume responses from the dedicated Media Management connection."""
        reader = self._connection_handler.reader
        if reader is None:
            return
        try:
            async for raw_message in reader:
                message = process_response(raw_message)
                if message is None:
                    continue
                if message.type == MessageType.STATE:
                    self._set_response(message)
                elif message.type == MessageType.ERROR:
                    self._set_error(message)
                if message.media_management_page is not None:
                    self._set_page(message.media_management_page)
        except (asyncio.CancelledError, OSError):
            pass
        finally:
            self._fail_pending(RussoundError("Media Management connection closed"))

    def _set_response(self, message: RussoundMessage) -> None:
        """Resolve the command response currently in flight."""
        if self._response_future is not None and not self._response_future.done():
            self._response_future.set_result(message)

    def _set_error(self, message: RussoundMessage) -> None:
        """Fail the command response currently in flight."""
        error = CommandError(message.value or "Media Management command failed")
        if self._response_future is not None and not self._response_future.done():
            self._response_future.set_exception(error)
        elif self._page_future is not None and not self._page_future.done():
            self._page_future.set_exception(error)

    def _set_page(self, page: MediaManagementMenuPage) -> None:
        """Resolve the page expected by the current navigation operation."""
        if self._page_future is not None and not self._page_future.done():
            self._page_future.set_result(page)

    def _fail_pending(self, error: RussoundError) -> None:
        """Fail outstanding waiters when the socket stops."""
        if self._response_future is not None and not self._response_future.done():
            self._response_future.set_exception(error)
        elif self._page_future is not None and not self._page_future.done():
            self._page_future.set_exception(error)

    async def _keep_alive(self) -> None:
        """Keep an initialized session alive before the device's one-minute timeout."""
        try:
            while True:
                await asyncio.sleep(self._keep_alive_interval)
                await self._send_event("MMKeepAlive")
        except asyncio.CancelledError:
            raise
        except (CommandError, RussoundError, TimeoutError):
            _LOGGER.warning("Media Management keep-alive failed")


def _event_command(zone_device_str: str, event_name: str, *args: str) -> str:
    """Build a controller-routed Media Management EVENT command."""
    arguments = f" {' '.join(args)}" if args else ""
    return f"EVENT {zone_device_str}!{event_name}{arguments}"
