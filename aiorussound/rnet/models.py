"""Models for Russound RNET devices."""

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class RNETQueuedRequest:
    payload: bytes
    expect_response: bool
    future: asyncio.Future[bytes | None]
