"""Models for aiorussound."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import SerializationStrategy


class RussoundBool(SerializationStrategy):
    def deserialize(self, value: str) -> bool:
        if value and (value == "ON" or value == "TRUE"):
            return True
        return False


class RussoundInt(SerializationStrategy):
    def deserialize(self, value: str) -> int:
        return int(value)


@dataclass
class Zone(DataClassORJSONMixin):
    """Data class representing Russound state."""

    name: str = field(default=None)
    volume: int = field(
        metadata=field_options(serialization_strategy=RussoundInt()), default=0
    )
    bass: int = field(
        metadata=field_options(serialization_strategy=RussoundInt()), default=0
    )
    treble: int = field(
        metadata=field_options(serialization_strategy=RussoundInt()), default=0
    )
    balance: int = field(
        metadata=field_options(serialization_strategy=RussoundInt()), default=0
    )
    loudness: bool = field(
        metadata=field_options(serialization_strategy=RussoundBool()), default=False
    )
    turn_on_volume: int = field(
        metadata=field_options(
            alias="turnOnVolume", serialization_strategy=RussoundInt()
        ),
        default=20,
    )
    do_not_disturb: bool = field(
        metadata=field_options(
            alias="doNotDisturb", serialization_strategy=RussoundBool()
        ),
        default=False,
    )
    party_mode: bool = field(
        metadata=field_options(
            alias="partyMode", serialization_strategy=RussoundBool()
        ),
        default=False,
    )
    status: bool = field(
        metadata=field_options(serialization_strategy=RussoundBool()), default=False
    )
    is_mute: bool = field(
        metadata=field_options(alias="mute", serialization_strategy=RussoundBool()),
        default=False,
    )
    shared_source: bool = field(
        metadata=field_options(
            alias="sharedSource", serialization_strategy=RussoundBool()
        ),
        default=False,
    )
    last_error: Optional[str] = field(
        metadata=field_options(alias="lastError"), default=None
    )
    page: Optional[str] = field(metadata=field_options(alias="page"), default=None)
    sleep_time_default: Optional[int] = field(
        metadata=field_options(
            alias="sleepTimeDefault", serialization_strategy=RussoundInt()
        ),
        default=None,
    )
    sleep_time_remaining: Optional[int] = field(
        metadata=field_options(
            alias="sleepTimeRemaining", serialization_strategy=RussoundInt()
        ),
        default=None,
    )
    enabled: bool = field(
        metadata=field_options(serialization_strategy=RussoundBool()), default=False
    )
    current_source: int = field(
        metadata=field_options(
            alias="currentSource", serialization_strategy=RussoundInt()
        ),
        default=1,
    )
    enabled_sources: list[int] = field(
        metadata=field_options(alias="enabled_sources"), default_factory=list
    )


class SourceType(StrEnum):
    """Russound source types."""

    AMPLIFIER = "Amplifier"
    TELEVISION = "Television"
    CABLE = "Cable"
    VIDEO_ACCESSORY = "Video Accessory"
    SATELLITE = "Satellite"
    VCR = "VCR"
    BLURAY_DVD = "Blu-ray / DVD"
    RECEIVER = "Receiver"
    MISC_AUDIO = "Misc Audio"
    CD = "CD"
    HOME_CONTROL = "Home Control"
    RUSSOUND_MEDIA_STREAMER = "Russound Media Streamer"
    RUSSOUND_DMS_3_1_AM_FM_TUNER = "Russound DMS 3.1 AM/FM Tuner"
    RUSSOUND_ST_1_AM_FM_TUNER = "Russound ST.1 AM/FM Tuner"
    RUSSOUND_BLUETOOTH_MODULE = "Russound Bluetooth Module"


class SourceMode(StrEnum):
    """Russound source modes."""

    UNKNOWN = "Unknown"
    AIRPLAY = "AirPlay"
    SPOTIFY = "Spotify"
    PANDORA = "Pandora"
    SIRIUS_XM = "SiriusXM"
    TUNE_IN = "TuneIn"
    INTERNET_RADIO = "Internet Radio"
    MEDIA_SERVER = "Media Server"
    USB = "USB"
    AIRABLE_RADIO = "Airable Radio"
    DEEZER = "Deezer"
    TIDAL = "Tidal"
    NAPSTER = "Napster"
    CHROMECAST = "Chromecast"
    BLUETOOTH = "Bluetooth"


class RepeatMode(StrEnum):
    """Repeat mode."""

    OFF = "OFF"
    ALL = "ALL"
    SINGLE = "SINGLE"


class PlayStatus(StrEnum):
    """Play status"""

    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    TRANSITIONING = "transitioning"


@dataclass
class Source(DataClassORJSONMixin):
    """Data class representing Russound source."""

    name: str = field(default=None)
    type: SourceType = field(
        metadata={"deserialize": lambda v: SourceType.MISC_AUDIO if not v else v},
        default=SourceType.MISC_AUDIO,
    )
    channel: Optional[str] = field(default=None)
    cover_art_url: Optional[str] = field(
        metadata=field_options(alias="coverArtURL"), default=None
    )
    channel_name: Optional[str] = field(
        metadata=field_options(alias="channelName"), default=None
    )
    genre: Optional[str] = field(default=None)
    artist_name: Optional[str] = field(
        metadata=field_options(alias="artistName"), default=None
    )
    album_name: Optional[str] = field(
        metadata=field_options(alias="albumName"), default=None
    )
    playlist_name: Optional[str] = field(
        metadata=field_options(alias="playlistName"), default=None
    )
    song_name: Optional[str] = field(
        metadata=field_options(alias="songName"), default=None
    )
    program_service_name: Optional[str] = field(
        metadata=field_options(alias="programServiceName"), default=None
    )
    radio_text: Optional[str] = field(
        metadata=field_options(alias="radioText"), default=None
    )
    shuffle_mode: bool = field(
        metadata=field_options(
            alias="shuffleMode", serialization_strategy=RussoundBool()
        ),
        default=False,
    )
    repeat_mode: Optional[RepeatMode] = field(
        metadata=field_options(alias="repeatMode"), default=None
    )
    mode: SourceMode = field(
        metadata={"deserialize": lambda v: SourceMode.UNKNOWN if not v else v},
        default=SourceMode.UNKNOWN,
    )
    play_status: Optional[PlayStatus] = field(
        metadata=field_options(alias="playStatus"), default=None
    )
    sample_rate: Optional[int] = field(
        metadata=field_options(
            alias="sampleRate", serialization_strategy=RussoundInt()
        ),
        default=None,
    )
    bit_rate: Optional[int] = field(
        metadata=field_options(alias="bitRate", serialization_strategy=RussoundInt()),
        default=None,
    )
    bit_depth: Optional[int] = field(
        metadata=field_options(alias="bitDepth", serialization_strategy=RussoundInt()),
        default=None,
    )
    play_time: Optional[int] = field(
        metadata=field_options(alias="playTime", serialization_strategy=RussoundInt()),
        default=None,
    )
    track_time: Optional[int] = field(
        metadata=field_options(alias="trackTime", serialization_strategy=RussoundInt()),
        default=None,
    )


class CallbackType(StrEnum):
    """Callback type."""

    STATE = "state"
    CONNECTION = "connection"


class MessageType(StrEnum):
    """Message type."""

    STATE = "S"
    NOTIFICATION = "N"
    ERROR = "E"


@dataclass
class RussoundMessage:
    """Incoming russound message."""

    type: str
    branch: Optional[str] = None
    leaf: Optional[str] = None
    value: Optional[str] = None
