"""Tests for controller-routed RIO Media Management support."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest

from aiorussound.connection import (
    RussoundConnectionHandler,
    RussoundSerialConnectionHandler,
)
from aiorussound.exceptions import CommandError, RussoundError
from aiorussound.rio.client import RussoundRIOClient
from aiorussound.rio.media_management import MediaManagementSession
from aiorussound.rio.models import MediaManagementMenuPage
from aiorussound.rio.protocol import process_response

MENU_PAGE = json.dumps(
    {
        "totalItems": 2,
        "numItems": 2,
        "menuItems": [
            {
                "id": 1,
                "text": "Tidal",
                "isFirst": True,
                "isLast": False,
                "isMenu": True,
                "BOT": True,
                "EOT": False,
                "attributes": "BFM",
            },
            {
                "id": 2,
                "text": "Station One",
                "isFirst": False,
                "isLast": True,
                "isMenu": False,
                "BOT": False,
                "EOT": True,
                "value": "Live",
                "imgURL": "https://example.invalid/station.png",
                "uri": "spotify:station:1",
                "attributes": "ELI",
            },
        ],
    },
    separators=(",", ":"),
)


class FakeMediaManagementClient:
    """A shared RIO client that emits Media Management responses."""

    def __init__(
        self,
        *,
        fail_command: str | None = None,
        page_error_after_response: bool = False,
    ) -> None:
        self.commands: list[str] = []
        self.fail_command = fail_command
        self.page_error_after_response = page_error_after_response
        self.connected = False
        self.session: MediaManagementSession | None = None

    async def connect(self) -> None:
        self.connected = True

    async def request(self, cmd: str) -> str:
        self.commands.append(cmd)
        if self.fail_command is not None and cmd.endswith(self.fail_command):
            raise CommandError("unsupported command")
        if cmd.endswith("MMInit"):
            assert self.session is not None
            if self.page_error_after_response:
                self.session._handle_error(CommandError("menu unavailable"))
            else:
                self.session._handle_page(MediaManagementMenuPage.from_json(MENU_PAGE))
        return ""

    def _register_media_management_session(
        self, session: MediaManagementSession
    ) -> None:
        if self.session is not None:
            raise RussoundError("A Media Management session is already active")
        self.session = session

    def _unregister_media_management_session(
        self, session: MediaManagementSession
    ) -> None:
        if self.session is session:
            self.session = None


class FakeReaderConnection(RussoundConnectionHandler):
    """A connection whose reader is controlled by a test."""

    async def connect(self) -> None:
        self.reader = asyncio.StreamReader()


def test_processes_json_media_management_notification() -> None:
    """A JSON notification is converted to a typed menu page."""
    message = process_response(f"N {MENU_PAGE}\r\n".encode())

    assert message is not None
    assert message.media_management_page is not None
    page = message.media_management_page
    assert page.total_items == 2
    assert page.num_items == 2
    assert page.menu_items[0].item_id == 1
    assert page.menu_items[0].is_menu is True
    assert page.menu_items[1].image_url == "https://example.invalid/station.png"
    assert page.menu_items[1].uri == "spotify:station:1"


def test_ignores_malformed_media_management_notification() -> None:
    """A malformed page does not interrupt the protocol consumer."""
    message = process_response(
        b'N {"totalItems":1,"numItems":1,"menuItems":["not-an-object"]}\r\n'
    )

    assert message is not None
    assert message.media_management_page is None


@pytest.mark.asyncio
async def test_initializes_controller_json_session() -> None:
    """Initialize a controller-zone session using the documented command order."""
    client = FakeMediaManagementClient()
    session = MediaManagementSession(client, "C[1].Z[2]", page_size=25)

    page = await session.initialize()

    assert page.num_items == 2
    assert client.connected is True
    assert client.commands == [
        "EVENT C[1].Z[2]!MMVerbosity 2",
        'EVENT C[1].Z[2]!MMIndex "ABSOLUTE"',
        "EVENT C[1].Z[2]!MMMaxItems 25",
        'EVENT C[1].Z[2]!MMFormat "JSON"',
        "EVENT C[1].Z[2]!MMInit",
    ]

    await session.close()

    assert client.commands[-1] == "EVENT C[1].Z[2]!MMClose"
    assert client.connected is True
    assert client.session is None


@pytest.mark.asyncio
async def test_propagates_media_management_command_error() -> None:
    """A command error fails the initializing call rather than timing out."""
    client = FakeMediaManagementClient(fail_command='MMFormat "JSON"')
    session = MediaManagementSession(client, "C[1].Z[2]")

    with pytest.raises(CommandError, match="unsupported command"):
        await session.initialize()

    await session.close()


@pytest.mark.asyncio
async def test_propagates_media_management_page_error_after_acknowledgement() -> None:
    """An error after MMInit's acknowledgement fails the expected page request."""
    client = FakeMediaManagementClient(page_error_after_response=True)
    session = MediaManagementSession(client, "C[1].Z[2]")

    with pytest.raises(CommandError, match="menu unavailable"):
        await session.initialize()

    await session.close()


@pytest.mark.asyncio
async def test_client_dispatches_media_management_notifications() -> None:
    """The client's shared consumer delivers JSON pages to the active session."""
    connection = FakeReaderConnection()
    await connection.connect()
    assert connection.reader is not None
    client = RussoundRIOClient(connection)
    session = Mock()
    client._media_management_session = session
    connection.reader.feed_data(f"N {MENU_PAGE}\r\n".encode())
    connection.reader.feed_eof()

    await client.consumer_handler(connection)

    page = MediaManagementMenuPage.from_json(MENU_PAGE)
    session._handle_page.assert_called_once_with(page)


@pytest.mark.asyncio
async def test_serial_client_creates_media_management_session() -> None:
    """Media Management sessions use the caller's serial RIO connection."""
    client = RussoundRIOClient(RussoundSerialConnectionHandler("COM1"))

    session = client.create_media_management_session("C[1].Z[1]")

    assert isinstance(session, MediaManagementSession)


@pytest.mark.asyncio
async def test_rejects_a_second_shared_media_management_session() -> None:
    """The protocol permits only one active session on a RIO connection."""
    client = FakeMediaManagementClient()
    first = MediaManagementSession(client, "C[1].Z[1]")
    second = MediaManagementSession(client, "C[1].Z[2]")
    await first.connect()

    with pytest.raises(RussoundError, match="already active"):
        await second.connect()

    await first.close()


@pytest.mark.parametrize("page_size", [0, 256])
def test_rejects_invalid_media_management_page_size(page_size: int) -> None:
    """The RIO protocol permits a page size from 1 through 255."""
    with pytest.raises(ValueError, match="between 1 and 255"):
        MediaManagementSession(
            FakeMediaManagementClient(), "C[1].Z[1]", page_size=page_size
        )


def test_rejects_non_controller_media_management_target() -> None:
    """The initial implementation intentionally supports only controller routing."""
    with pytest.raises(ValueError, match="controller zone"):
        MediaManagementSession(FakeMediaManagementClient(), "S[1]")
