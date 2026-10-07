"""Button to anchor the battery at 100 % by hand."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BatterySocConfigEntry
from .entity import BatteryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatterySocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MarkFullButton(entry, entry.runtime_data, "mark_full")])


class MarkFullButton(BatteryEntity, ButtonEntity):
    """Set the state of charge to 100 % and start a new cycle from "full"."""

    _attr_icon = "mdi:battery-check"

    async def async_press(self) -> None:
        self._tracker.async_mark_full()
