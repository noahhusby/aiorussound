"""Controller-routed Russound Media Management sessions."""

from __future__ import annotations

import asyncio
import logging
import re
from asyncio import Future, Task
from typing import Protocol, Self

from aiorussound.const import TIMEOUT
from aiorussound.exceptions import CommandError, RussoundError
from aiorussound.rio.models import MediaManagementMenuPage

DEFAULT_MEDIA_MANAGEMENT_PAGE_SIZE = 100
DEFAULT_MEDIA_MANAGEMENT_KEEP_ALIVE_INTERVAL = 45.0

_CONTROLLER_ZONE_RE = re.compile(r"^C\[\d+\]\.Z\[\d+\]$")
_LOGGER = logging.getLogger(__package__)


class MediaManagementClient(Protocol):
    """RIO client surface used by a Media Management session."""

    async def connect(self) -> None:
        """Connect to the RIO controller."""

    async def request(self, cmd: str) -> str:
        """Send a RIO command and wait for its response."""

    def _register_media_management_session(
        self, session: MediaManagementSession
    ) -> None:
        """Register an active Media Management session."""

    def _unregister_media_management_session(
        self, session: MediaManagementSession
    ) -> None:
        """Unregister an active Media Management session."""


class MediaManagementSession:
    """A controller-routed Media Management session on a RIO connection.

    The RIO protocol permits one Media Management session per connection. A
    session therefore shares the client's established TCP or serial connection
    and receives JSON page notifications through the client's consumer.
    """

    def __init__(
        self,
        client: MediaManagementClient,
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

        self._client = client
        self._zone_device_str = zone_device_str
        self._page_size = page_size
        self._keep_alive_interval = keep_alive_interval
        self._command_lock = asyncio.Lock()
        self._keep_alive_task: Task[None] | None = None
        self._page_future: Future[MediaManagementMenuPage] | None = None
        self._is_connected = False

    async def __aenter__(self) -> Self:
        """Connect the client and register the Media Management session."""
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the Media Management session."""
        await self.close()

    @property
    def is_connected(self) -> bool:
        """Return whether this session is registered with its client."""
        return self._is_connected

    async def connect(self) -> None:
        """Connect the RIO client and register this session."""
        if self.is_connected:
            return
        await self._client.connect()
        self._client._register_media_management_session(self)
        self._is_connected = True

    async def initialize(self) -> MediaManagementMenuPage:
        """Configure a JSON session and return the top-level Media Management page."""
        await self.connect()
        async with self._command_lock:
            await self._send_event_locked("MMVerbosity", "2")
            await self._send_event_locked("MMIndex", "ABSOLUTE")
            await self._send_event_locked("MMMaxItems", str(self._page_size))
            await self._send_event_locked("MMFormat", "JSON")
            page = await self._send_event_locked("MMInit", expect_page=True)

        if page is None:
            raise RussoundError(
                "Media Management initialization did not return a menu page"
            )

        if self._keep_alive_task is None or self._keep_alive_task.done():
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        return page

    async def close(self) -> None:
        """Close the Media Management session without closing the client connection."""
        if self.is_connected:
            try:
                await self._send_event("MMClose")
            except (CommandError, RussoundError, TimeoutError):
                _LOGGER.debug("Unable to close Media Management session cleanly")

        if self._keep_alive_task is not None and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
        if self._keep_alive_task is not None:
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass

        self._fail_pending(RussoundError("Media Management session closed"))
        if self.is_connected:
            self._client._unregister_media_management_session(self)
            self._is_connected = False

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

        page_future: Future[MediaManagementMenuPage] | None = None
        if expect_page:
            page_future = asyncio.get_running_loop().create_future()
        self._page_future = page_future

        command = _event_command(self._zone_device_str, event_name, *args)
        try:
            await asyncio.wait_for(self._client.request(command), timeout=TIMEOUT)
            if page_future is not None:
                return await asyncio.wait_for(page_future, timeout=TIMEOUT)
            return None
        finally:
            if self._page_future is page_future:
                self._page_future = None

    def _handle_page(self, page: MediaManagementMenuPage) -> None:
        """Deliver a Media Management page from the shared client consumer."""
        if self._page_future is not None and not self._page_future.done():
            self._page_future.set_result(page)

    def _handle_error(self, error: CommandError) -> None:
        """Fail a pending page request from the shared client consumer."""
        if self._page_future is not None and not self._page_future.done():
            self._page_future.set_exception(error)

    def _fail_pending(self, error: RussoundError) -> None:
        """Fail outstanding waiters when the session closes."""
        if self._page_future is not None and not self._page_future.done():
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
