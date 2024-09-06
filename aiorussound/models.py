"""Models for aiorussound."""
from dataclasses import dataclass, field
from typing import Optional

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class RussoundMessage:
    """Incoming russound message."""
    tag: str
    variable: Optional[str] = None
    value: Optional[str] = None
    zone: Optional[str] = None
    controller: Optional[str] = None
    source: Optional[str] = None


@dataclass
class ZoneProperties(DataClassORJSONMixin):
    """Data class representing Russound state."""

    volume: str = field(metadata=field_options(alias="volume"), default="0")
    bass: str = field(metadata=field_options(alias="bass"), default="0")
    treble: str = field(metadata=field_options(alias="treble"), default="0")
    balance: str = field(metadata=field_options(alias="balance"), default="0")
    loudness: str = field(metadata=field_options(alias="loudness"), default="OFF")
    turn_on_volume: str = field(metadata=field_options(alias="turnonvolume"), default="20")
    do_not_disturb: str = field(metadata=field_options(alias="donotdisturb"), default="OFF")
    party_mode: str = field(metadata=field_options(alias="partymode"), default="OFF")
    status: str = field(metadata=field_options(alias="status"), default="OFF")
    is_mute: str = field(metadata=field_options(alias="mute"), default="OFF")
    shared_source: str = field(metadata=field_options(alias="sharedsource"), default="OFF")
    last_error: Optional[str] = field(metadata=field_options(alias="lasterror"), default=None)
    page: Optional[str] = field(metadata=field_options(alias="page"), default=None)
    sleep_time_default: Optional[str] = field(metadata=field_options(alias="sleeptimedefault"), default=None)
    sleep_time_remaining: Optional[str] = field(metadata=field_options(alias="sleeptimeremaining"), default=None)
    enabled: str = field(metadata=field_options(alias="enabled"), default="False")
    current_source: str = field(metadata=field_options(alias="currentsource"), default="1")


@dataclass
class SourceProperties(DataClassORJSONMixin):
    """Data class representing Russound source."""

    type: str = field(metadata=field_options(alias="type"), default=None)
    channel: str = field(metadata=field_options(alias="channel"), default=None)
    cover_art_url: str = field(metadata=field_options(alias="covertarturl"), default=None)
    channel_name: str = field(metadata=field_options(alias="channelname"), default=None)
    genre: str = field(metadata=field_options(alias="genre"), default=None)
    artist_name: str = field(metadata=field_options(alias="artistname"), default=None)
    album_name: str = field(metadata=field_options(alias="albumname"), default=None)
    playlist_name: str = field(metadata=field_options(alias="playlistname"), default=None)
    song_name: str = field(metadata=field_options(alias="songname"), default=None)
    program_service_name: str = field(metadata=field_options(alias="programservicename"), default=None)
    radio_text: str = field(metadata=field_options(alias="radiotext"), default=None)
    shuffle_mode: str = field(metadata=field_options(alias="shufflemode"), default=None)
    repeat_mode: str = field(metadata=field_options(alias="repeatmode"), default=None)
    mode: str = field(metadata=field_options(alias="mode"), default=None)
    play_status: str = field(metadata=field_options(alias="playstatus"), default=None)
    sample_rate: str = field(metadata=field_options(alias="samplerate"), default=None)
    bit_rate: str = field(metadata=field_options(alias="bitrate"), default=None)
    bit_depth: str = field(metadata=field_options(alias="bitdepth"), default=None)
    play_time: str = field(metadata=field_options(alias="playtime"), default=None)
    track_time: str = field(metadata=field_options(alias="tracktime"), default=None)