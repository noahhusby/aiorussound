"""Tests for controller-routed RIO Media Management support."""

from __future__ import annotations

import asyncio
import json

import pytest

from aiorussound.connection import (
    RussoundConnectionHandler,
    RussoundTcpConnectionHandler,
)
from aiorussound.exceptions import CommandError
from aiorussound.rio.media_management import MediaManagementSession
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


class FakeMediaManagementConnection(RussoundConnectionHandler):
    """A connection that emits protocol responses for test commands."""

    def __init__(
        self,
        *,
        fail_command: str | None = None,
        page_error_after_response: bool = False,
    ) -> None:
        super().__init__()
        self.commands: list[str] = []
        self.fail_command = fail_command
        self.page_error_after_response = page_error_after_response
        self.closed = False

    async def connect(self) -> None:
        self.reader = asyncio.StreamReader()

    async def write_str(self, cmd: str) -> None:
        self.commands.append(cmd)
        assert self.reader is not None
        if self.fail_command is not None and cmd.endswith(self.fail_command):
            self.reader.feed_data(b"E unsupported command\r\n")
            return
        self.reader.feed_data(b"S\r\n")
        if cmd.endswith("MMInit"):
            if self.page_error_after_response:
                self.reader.feed_data(b"E menu unavailable\r\n")
            else:
                self.reader.feed_data(f"N {MENU_PAGE}\r\n".encode())

    async def close(self) -> None:
        self.closed = True
        assert self.reader is not None
        self.reader.feed_eof()


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
    connection = FakeMediaManagementConnection()
    session = MediaManagementSession(connection, "C[1].Z[2]", page_size=25)

    page = await session.initialize()

    assert page.num_items == 2
    assert connection.commands == [
        "EVENT C[1].Z[2]!MMVerbosity 2",
        'EVENT C[1].Z[2]!MMIndex "ABSOLUTE"',
        "EVENT C[1].Z[2]!MMMaxItems 25",
        'EVENT C[1].Z[2]!MMFormat "JSON"',
        "EVENT C[1].Z[2]!MMInit",
    ]

    await session.close()

    assert connection.commands[-1] == "EVENT C[1].Z[2]!MMClose"
    assert connection.closed is True


@pytest.mark.asyncio
async def test_propagates_media_management_command_error() -> None:
    """A command error fails the initializing call rather than timing out."""
    connection = FakeMediaManagementConnection(fail_command='MMFormat "JSON"')
    session = MediaManagementSession(connection, "C[1].Z[2]")

    with pytest.raises(CommandError, match="unsupported command"):
        await session.initialize()

    await session.close()


@pytest.mark.asyncio
async def test_propagates_media_management_page_error_after_acknowledgement() -> None:
    """An error after MMInit's acknowledgement fails the expected page request."""
    connection = FakeMediaManagementConnection(page_error_after_response=True)
    session = MediaManagementSession(connection, "C[1].Z[2]")

    with pytest.raises(CommandError, match="menu unavailable"):
        await session.initialize()

    await session.close()


@pytest.mark.parametrize("page_size", [0, 256])
def test_rejects_invalid_media_management_page_size(page_size: int) -> None:
    """The RIO protocol permits a page size from 1 through 255."""
    with pytest.raises(ValueError, match="between 1 and 255"):
        MediaManagementSession(
            FakeMediaManagementConnection(), "C[1].Z[1]", page_size=page_size
        )


def test_rejects_non_controller_media_management_target() -> None:
    """The initial implementation intentionally supports only controller routing."""
    with pytest.raises(ValueError, match="controller zone"):
        MediaManagementSession(FakeMediaManagementConnection(), "S[1]")


def test_tcp_handler_creates_dedicated_media_management_connection() -> None:
    """A Media Management session gets a new TCP socket configuration."""
    connection = RussoundTcpConnectionHandler("192.0.2.1", 9621)

    dedicated_connection = connection.create_media_management_connection()

    assert dedicated_connection is not connection
    assert dedicated_connection.host == "192.0.2.1"
    assert dedicated_connection.port == 9621
