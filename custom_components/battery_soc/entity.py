"""Base entity for the integration's "Battery" device."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .tracker import BatteryTracker


class BatteryEntity(Entity):
    """Entity on the per-entry "Battery" service device."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, tracker: BatteryTracker, key: str) -> None:
        self._tracker = tracker
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._tracker.async_add_listener(self._on_change))

    @callback
    def _on_change(self) -> None:
        self.async_write_ha_state()
