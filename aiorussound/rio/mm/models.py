"""Models for Russound RIO Media Management."""

from dataclasses import dataclass, field

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass(frozen=True)
class MediaManagementMenuItem(DataClassORJSONMixin):
    """A menu item returned by a Russound Media Management session."""

    item_id: int = field(metadata=field_options(alias="id"))
    text: str
    is_first: bool | None = field(metadata=field_options(alias="isFirst"), default=None)
    is_last: bool | None = field(metadata=field_options(alias="isLast"), default=None)
    is_menu: bool | None = field(metadata=field_options(alias="isMenu"), default=None)
    beginning_of_transmission: bool | None = field(
        metadata=field_options(alias="BOT"), default=None
    )
    end_of_transmission: bool | None = field(
        metadata=field_options(alias="EOT"), default=None
    )
    value: str | None = None
    image_url: str | None = field(metadata=field_options(alias="imgURL"), default=None)
    uri: str | None = None
    attributes: str | None = None


@dataclass(frozen=True)
class MediaManagementMenuPage(DataClassORJSONMixin):
    """A JSON-formatted page of Media Management menu items."""

    total_items: int = field(metadata=field_options(alias="totalItems"))
    num_items: int = field(metadata=field_options(alias="numItems"))
    menu_items: tuple[MediaManagementMenuItem, ...] = field(
        metadata=field_options(alias="menuItems")
    )
