"""RIO response parsing helpers."""

from __future__ import annotations

import logging

from aiorussound.const import RESPONSE_REGEX
from aiorussound.rio.models import (
    MediaManagementMenuPage,
    MessageType,
    RussoundMessage,
)

_LOGGER = logging.getLogger(__package__)


def process_response(res: bytes) -> RussoundMessage | None:
    """Process an incoming RIO response into a structured message."""
    try:
        # Decode via Latin-1 first to preserve the protocol's extended characters.
        str_res = (
            res.decode(encoding="iso-8859-1")
            .encode(encoding="utf-8")
            .decode(encoding="utf-8")
            .strip()
        )
    except UnicodeDecodeError as err:
        _LOGGER.warning("Failed to decode Russound response %s: %s", res, err)
        return None

    if not str_res:
        return None
    if str_res.startswith("{"):
        return _media_management_message(MessageType.NOTIFICATION, str_res)

    tag = str_res[0].upper()
    payload = str_res[1:].lstrip()
    if tag == MessageType.ERROR:
        _LOGGER.debug("Device responded with error: %s", payload)
        return RussoundMessage(tag, value=payload)
    if payload.startswith("{"):
        return _media_management_message(tag, payload)
    if tag == MessageType.STATE and not payload:
        return RussoundMessage(MessageType.STATE)

    match = RESPONSE_REGEX.match(payload)
    if not match:
        return RussoundMessage(tag)
    value = match.group(3)
    value = None if not value or value == "------" else value
    return RussoundMessage(tag, match.group(1) or None, match.group(2), value)


def _media_management_message(tag: str, payload: str) -> RussoundMessage:
    """Create a message containing a parsed Media Management page."""
    try:
        page = MediaManagementMenuPage.from_json(payload)
    except (TypeError, ValueError):
        _LOGGER.warning("Failed to parse Media Management JSON notification")
        return RussoundMessage(tag)
    return RussoundMessage(tag, media_management_page=page)
