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
    turn_on_volume: str = field(metadata=field_options(alias="turnOnVolume"), default="20")
    do_not_disturb: str = field(metadata=field_options(alias="doNotDisturb"), default="OFF")
    party_mode: str = field(metadata=field_options(alias="partyMode"), default="OFF")
    status: str = field(metadata=field_options(alias="status"), default="OFF")
    is_mute: str = field(metadata=field_options(alias="mute"), default="OFF")
    shared_source: str = field(metadata=field_options(alias="sharedSource"), default="OFF")
    last_error: Optional[str] = field(metadata=field_options(alias="lastError"), default=None)
    page: Optional[str] = field(metadata=field_options(alias="page"), default=None)
    sleep_time_default: Optional[str] = field(metadata=field_options(alias="sleepTimeDefault"), default=None)
    sleep_time_remaining: Optional[str] = field(metadata=field_options(alias="sleepTimeRemaining"), default=None)
    enabled: str = field(metadata=field_options(alias="enabled"), default="False")
    current_source: str = field(metadata=field_options(alias="currentSource"), default="1")


@dataclass
class SourceProperties(DataClassORJSONMixin):
    """Data class representing Russound source."""

    type: str = field(metadata=field_options(alias="type"), default=None)
    channel: str = field(metadata=field_options(alias="channel"), default=None)
    cover_art_url: str = field(metadata=field_options(alias="coverArtURL"), default=None)
    channel_name: str = field(metadata=field_options(alias="channelName"), default=None)
    genre: str = field(metadata=field_options(alias="genre"), default=None)
    artist_name: str = field(metadata=field_options(alias="artistName"), default=None)
    album_name: str = field(metadata=field_options(alias="albumName"), default=None)
    playlist_name: str = field(metadata=field_options(alias="playlistName"), default=None)
    song_name: str = field(metadata=field_options(alias="songName"), default=None)
    program_service_name: str = field(metadata=field_options(alias="programServiceName"), default=None)
    radio_text: str = field(metadata=field_options(alias="radioText"), default=None)
    shuffle_mode: str = field(metadata=field_options(alias="shuffleMode"), default=None)
    repeat_mode: str = field(metadata=field_options(alias="repeatMode"), default=None)
    mode: str = field(metadata=field_options(alias="mode"), default=None)
    play_status: str = field(metadata=field_options(alias="playStatus"), default=None)
    sample_rate: str = field(metadata=field_options(alias="sampleRate"), default=None)
    bit_rate: str = field(metadata=field_options(alias="bitRate"), default=None)
    bit_depth: str = field(metadata=field_options(alias="bitDepth"), default=None)
    play_time: str = field(metadata=field_options(alias="playTime"), default=None)
    track_time: str = field(metadata=field_options(alias="trackTime"), default=None)