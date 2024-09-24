"""Asynchronous Python client for Russound RIO."""


class RussoundError(Exception):
    """A generic error."""


class CommandError(Exception):
    """A command sent to the controller caused an error."""


class UncachedVariableError(Exception):
    """A variable was not found in the cache."""


class UnsupportedFeatureError(Exception):
    """A requested command is not supported on this controller."""


class UnsupportedRussoundVersionError(Exception):
    """The client implements an unsupported version of the Russound RIO API."""
