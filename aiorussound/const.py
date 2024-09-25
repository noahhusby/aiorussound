"""Asynchronous Python client for Russound RIO."""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
import re

MINIMUM_API_SUPPORT = "1.05.00"

DEFAULT_PORT = 9621

RECONNECT_DELAY = 5.0
TIMEOUT = 5.0

KEEP_ALIVE_INTERVAL = 60

MAX_SOURCE = 17

MAX_RNET_CONTROLLERS = 6

RESPONSE_REGEX = re.compile(
    r'(?:(\w+(?:\[\d+])?(?:\.\w+(?:\[\d+])?)*)\.)?(\w+)="([^"]*)"'
)


class FeatureFlag(Enum):
    """A list of Russound RIO API features."""

    SUPPORT_POWER_MGMT = 1
    SUPPORT_ZONE_PARAMETERS = 2
    SUPPORT_SOURCE_PARAMETERS = 3
    SUPPORT_CONTROLLER_PARAMETERS = 4
    SUPPORT_SYSTEM_PARAMETERS = 5
    SUPPORT_DMS_3_1_MM = 6
    EVENT_KEY_CODE = 7
    PROPERTY_IP_ADDRESS = 8
    SUPPORT_SHUFFLE = 9
    COMMAND_MM_CLOSE = 10
    SUPPORT_PAGE_ZONE = 11
    SUPPORT_REPEAT = 12
    PROPERTY_CTRL_TYPE = 13
    PROPERTY_SYS_LANG = 14
    NOTIFICATION_SYS_LANG = 15
    SUPPORT_MM_LONG_LIST = 16
    TEMPLATES_MM_SCREEN = 17
    PROPERTY_SLEEP_TIME_REMAINING = 18
    SUPPORT_PRESETS_BANKS = 19
    SUPPORT_FAVORITES = 20
    SUPPORT_ZONE_SOURCE_EXCLUSION = 21
    SUPPORT_FORMS = 22
    SUPPORT_MEDIA_RATING = 23
    SUPPORT_HIDDEN_ATTRIBUTE = 24
    SUPPORT_SYSTEM_FAVORITE_RENAME = 25
    COMMANDS_ZONE_MUTE_OFF_ON = 26
    SUPPORT_WATCH_FAVORITES = 27
    SUPPORT_SYSTEM = 28
    SUPPORT_DEVICE_GROUPING = 29
    SUPPORT_ALARM = 30
    NOTIFICATION_ALARM_ZONE_WATCH = 31
    PROPERTY_FIRMWARE_VERSION = 32
    SUPPORT_MBX_DISPLAY_ITEMS = 33
    PROPERTY_PLAY_STATUS = 34
    PROPERTY_AVAILABLE_CONTROLS = 35
    PROPERTY_SAMPLE_RATE = 36
    PROPERTY_BIT_RATE = 37
    PROPERTY_BIT_DEPTH = 38
    PROPERTY_PLAY_TIME = 39
    PROPERTY_TRACK_TIME = 40
    PROPERTY_SET_SEEK_TIME = 41
    SUPPORT_MM_CONTEXT_MENU = 42
    PROPERTY_SLEEP_TIME_DEFAULT = 43
    PROPERTY_SUPPORT_SLEEP_TIME = 44
    EVENT_REBOOT = 45
    SUPPORT_SYSTEM_FAVORITE_SOURCE = 46
    ATTRIBUTE_USER_LOGIN = 47


FLAGS_BY_VERSION = {
    "1.01.00": [
        FeatureFlag.SUPPORT_POWER_MGMT,
    ],
    "1.02.00": [
        FeatureFlag.SUPPORT_ZONE_PARAMETERS,
        FeatureFlag.SUPPORT_SOURCE_PARAMETERS,
        FeatureFlag.SUPPORT_CONTROLLER_PARAMETERS,
        FeatureFlag.SUPPORT_SYSTEM_PARAMETERS,
    ],
    "1.03.00": [
        FeatureFlag.SUPPORT_DMS_3_1_MM,
        FeatureFlag.EVENT_KEY_CODE,
        FeatureFlag.PROPERTY_IP_ADDRESS,
    ],
    "1.04.00": [
        FeatureFlag.SUPPORT_SHUFFLE,
        FeatureFlag.COMMAND_MM_CLOSE,
        FeatureFlag.SUPPORT_PAGE_ZONE,
    ],
    "1.05.00": [
        FeatureFlag.SUPPORT_REPEAT,
        FeatureFlag.PROPERTY_CTRL_TYPE,
        FeatureFlag.PROPERTY_SYS_LANG,
    ],
    "1.06.00": [
        FeatureFlag.NOTIFICATION_SYS_LANG,
        FeatureFlag.SUPPORT_MM_LONG_LIST,
        FeatureFlag.TEMPLATES_MM_SCREEN,
    ],
    "1.07.00": [
        FeatureFlag.PROPERTY_SLEEP_TIME_REMAINING,
        FeatureFlag.SUPPORT_PRESETS_BANKS,
        FeatureFlag.SUPPORT_FAVORITES,
        FeatureFlag.SUPPORT_ZONE_SOURCE_EXCLUSION,
        FeatureFlag.SUPPORT_FORMS,
        FeatureFlag.SUPPORT_MEDIA_RATING,
        FeatureFlag.SUPPORT_HIDDEN_ATTRIBUTE,
    ],
    "1.08.00": [FeatureFlag.SUPPORT_SYSTEM_FAVORITE_RENAME],
    "1.09.00": [
        FeatureFlag.COMMANDS_ZONE_MUTE_OFF_ON,
    ],
    "1.11.00": [
        FeatureFlag.SUPPORT_WATCH_FAVORITES,
    ],
    "1.12.00": [
        FeatureFlag.SUPPORT_SYSTEM,
        FeatureFlag.SUPPORT_DEVICE_GROUPING,
        FeatureFlag.SUPPORT_ALARM,
    ],
    "1.12.01": [
        FeatureFlag.NOTIFICATION_ALARM_ZONE_WATCH,
    ],
    "1.12.02": [
        FeatureFlag.PROPERTY_FIRMWARE_VERSION,
    ],
    "1.14.00": [
        FeatureFlag.SUPPORT_MBX_DISPLAY_ITEMS,
        FeatureFlag.PROPERTY_PLAY_STATUS,
        FeatureFlag.PROPERTY_AVAILABLE_CONTROLS,
        FeatureFlag.PROPERTY_SAMPLE_RATE,
        FeatureFlag.PROPERTY_BIT_RATE,
        FeatureFlag.PROPERTY_BIT_DEPTH,
        FeatureFlag.PROPERTY_PLAY_TIME,
        FeatureFlag.PROPERTY_TRACK_TIME,
        FeatureFlag.PROPERTY_SET_SEEK_TIME,
        FeatureFlag.SUPPORT_MM_CONTEXT_MENU,
    ],
    "1.14.01": [
        FeatureFlag.PROPERTY_SLEEP_TIME_DEFAULT,
        FeatureFlag.PROPERTY_SUPPORT_SLEEP_TIME,
    ],
    "1.15.00": [FeatureFlag.EVENT_REBOOT, FeatureFlag.SUPPORT_SYSTEM_FAVORITE_SOURCE],
    "1.15.02": [
        FeatureFlag.ATTRIBUTE_USER_LOGIN,
    ],
}

VERSIONS_BY_FLAGS = defaultdict(list)

for version, flags in FLAGS_BY_VERSION.items():
    for flag in flags:
        VERSIONS_BY_FLAGS[flag] = version
