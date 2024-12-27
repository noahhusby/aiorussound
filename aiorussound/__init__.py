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
from .models import Source, RussoundMessage, Zone, Favorite
from .rio import Controller, RussoundClient


__all__ = [
    "RussoundError",
    "CommandError",
    "UnsupportedFeatureError",
    "UnsupportedRussoundVersionError",
    "UncachedVariableError",
    "RussoundClient",
    "Controller",
    "Zone",
    "RussoundTcpConnectionHandler",
    "Favorite",
    "Source",
    "RussoundMessage",
]
