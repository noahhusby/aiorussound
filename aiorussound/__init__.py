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

__all__ = [
    "RussoundError",
    "CommandError",
    "UnsupportedFeatureError",
    "UnsupportedRussoundVersionError",
    "UncachedVariableError",
    "RussoundTcpConnectionHandler",
]
