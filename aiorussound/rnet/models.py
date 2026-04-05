"""Models for Russound RNET devices."""

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class RNETQueuedRequest:
    payload: bytes
    expect_response: bool
    future: asyncio.Future[bytes | None]
    response_signature: bytes | None = None


@dataclass
class RNETZoneInfo:
    power_raw: int  # byte 21
    source_raw: int  # byte 22 (source - 1)
    volume_raw: int  # byte 23 (0x00..0x32 => 0..100 displayed in steps of 2)
    bass_raw: int  # byte 24 (0x00..0x14 => -10..+10)
    treble_raw: int  # byte 25 (0x00..0x14 => -10..+10)
    loudness_raw: int  # byte 26
    balance_raw: int  # byte 27 (0x00..0x14 => left..center..right)
    system_on_raw: int  # byte 28
    shared_source_raw: int  # byte 29
    party_mode_raw: int  # byte 30
    do_not_disturb_raw: int  # byte 31

    @property
    def power(self) -> bool:
        """Get the power status of the zone."""
        return self.power_raw == 0x01

    @property
    def source(self) -> int:
        """Return 1-based source number."""
        return self.source_raw + 1

    @property
    def volume(self) -> int:
        """Displayed volume: 0..50."""
        return self.volume_raw

    @property
    def bass(self) -> int:
        """Displayed bass: -10..+10."""
        return self.bass_raw - 10

    @property
    def treble(self) -> int:
        """Displayed treble: -10..+10."""
        return self.treble_raw - 10

    @property
    def loudness(self) -> bool:
        return self.loudness_raw == 0x01

    @property
    def balance(self) -> int:
        """Displayed balance: -10..+10 where 0 is center."""
        return self.balance_raw - 10

    @property
    def system_on(self) -> bool:
        """Get status of system on."""
        return self.system_on_raw == 0x01

    @property
    def shared_source(self) -> bool:
        """Get the shared source status"""
        return self.shared_source_raw == 0x01

    @property
    def party_mode(self) -> str:
        return {
            0x00: "off",
            0x01: "on",
            0x02: "master",
        }.get(self.party_mode_raw, f"unknown:{self.party_mode_raw}")

    @property
    def do_not_disturb(self) -> bool:
        """Get status of DnD for the zone."""
        return self.do_not_disturb_raw == 0x01
