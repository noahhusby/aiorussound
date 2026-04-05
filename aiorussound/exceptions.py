"""Asynchronous Python client for Russound RIO."""


class RussoundError(Exception):
    """A generic error."""


class CommandError(RussoundError):
    """A command sent to the controller caused an error."""


class UncachedVariableError(RussoundError):
    """A variable was not found in the cache."""


class UnsupportedFeatureError(RussoundError):
    """A requested command is not supported on this controller."""


class UnsupportedRussoundVersionError(RussoundError):
    """The client implements an unsupported version of the Russound RIO API."""
