"""
.. include:: ../README.md
"""

from .exceptions import (
    RussoundError,
    CommandError,
    UncachedVariableError,
    UnsupportedFeatureError,
    UnsupportedRussoundVersionError,
)
from .connection import RussoundTcpConnectionHandler
from .models import SourceProperties, ZoneProperties, RussoundMessage
from .rio import Controller, RussoundClient, Source, Zone

__all__ = [
    "RussoundError",
    "CommandError",
    "UnsupportedFeatureError",
    "UnsupportedRussoundVersionError",
    "UncachedVariableError",
    "RussoundClient",
    "Controller",
    "Zone",
    "Source",
    "RussoundTcpConnectionHandler",
    "ZoneProperties",
    "SourceProperties",
    "RussoundMessage",
]
