class CommandException(Exception):
    """A command sent to the controller caused an error."""


class UncachedVariable(Exception):
    """A variable was not found in the cache."""


class UnsupportedFeature(Exception):
    """A requested command is not supported on this controller"""


class UnsupportedRussoundVersion(Exception):
    """The client implements an unsupported version of the Russound RIO API"""
