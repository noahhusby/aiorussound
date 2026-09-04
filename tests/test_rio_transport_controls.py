"""Tests for RIO media transport controls."""

import pytest

from aiorussound.rio.client import ZoneControlSurface


class CommandCapturingClient:
    """A command-capturing client used for transport event assertions."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def request(self, cmd: str) -> str:
        """Capture a command and return an acknowledgement."""
        self.commands.append(cmd)
        return "OK"


@pytest.mark.asyncio
async def test_transport_controls_use_zone_key_releases() -> None:
    """Media transport controls are sent as zone-level key releases."""
    client = CommandCapturingClient()
    zone = ZoneControlSurface()
    zone.client = client
    zone.device_str = "C[2].Z[6]"
    zone.current_source = 4

    await zone.play()
    await zone.pause()
    await zone.stop()
    await zone.next()
    await zone.previous()

    assert client.commands == [
        "EVENT C[2].Z[6]!KeyRelease Play",
        "EVENT C[2].Z[6]!KeyRelease Pause",
        "EVENT C[2].Z[6]!KeyRelease Stop",
        "EVENT C[2].Z[6]!KeyRelease Next",
        "EVENT C[2].Z[6]!KeyRelease Previous",
    ]
