"""Battery SoC: state of charge of an inverter battery by coulomb counting with anchors."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_SOC, CONF_INITIAL_SOC, DOMAIN, SERVICE_SET_SOC
from .tracker import BatteryTracker

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type BatterySocConfigEntry = ConfigEntry[BatteryTracker]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register domain services (they act on every loaded entry)."""

    async def set_soc(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            entry.runtime_data.async_set_soc(call.data[ATTR_SOC])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SOC,
        set_soc,
        schema=vol.Schema({vol.Required(ATTR_SOC): vol.All(vol.Coerce(float), vol.Range(min=0, max=100))}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BatterySocConfigEntry) -> bool:
    tracker = BatteryTracker(hass, entry.entry_id, entry.options, entry.data.get(CONF_INITIAL_SOC, 100))
    await tracker.async_load()
    entry.runtime_data = tracker
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    tracker.async_start()
    entry.async_on_unload(tracker.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BatterySocConfigEntry) -> bool:
    await entry.runtime_data.async_flush()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_entry_updated(hass: HomeAssistant, entry: BatterySocConfigEntry) -> None:
    """Options changed: reload (the counter state is saved on unload)."""
    await hass.config_entries.async_reload(entry.entry_id)
