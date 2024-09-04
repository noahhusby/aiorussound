"""Models for aiorussound."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RussoundMessage:
    """Incoming russound message."""
    tag: str
    variable: Optional[str] = None
    value: Optional[str] = None
    zone: Optional[str] = None
    controller: Optional[str] = None
    source: Optional[str] = None
