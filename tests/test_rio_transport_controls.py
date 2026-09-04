"""Tests for RIO media transport controls."""

from unittest.mock import AsyncMock, call

import pytest

from aiorussound.rio.client import ZoneControlSurface


@pytest.mark.asyncio
async def test_transport_controls_use_zone_key_releases() -> None:
    """Media transport controls are sent as zone-level key releases."""
    zone = ZoneControlSurface()
    zone.client = AsyncMock()
    zone.device_str = "C[2].Z[6]"
    zone.current_source = 4

    await zone.play()
    await zone.pause()
    await zone.stop()
    await zone.next()
    await zone.previous()

    zone.client.request.assert_has_awaits(
        [
            call("EVENT C[2].Z[6]!KeyRelease Play"),
            call("EVENT C[2].Z[6]!KeyRelease Pause"),
            call("EVENT C[2].Z[6]!KeyRelease Stop"),
            call("EVENT C[2].Z[6]!KeyRelease Next"),
            call("EVENT C[2].Z[6]!KeyRelease Previous"),
        ]
    )
