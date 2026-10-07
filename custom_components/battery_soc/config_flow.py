"""Config and options flows."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CURRENT_ENTITY,
    CONF_EMPTY_DELAY,
    CONF_EMPTY_VOLTAGE,
    CONF_FULL_DELAY,
    CONF_FULL_ENTITY,
    CONF_FULL_VOLTAGE,
    CONF_GRID_ENTITY,
    CONF_INITIAL_SOC,
    CONF_LEARN_CAPACITY,
    CONF_LEARN_EFFICIENCY,
    CONF_LOW_SOC_HINT,
    CONF_LOW_VOLTAGE_HINT,
    CONF_MAX_GAP,
    CONF_NOMINAL_CAPACITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_SHUTDOWN_DELAY,
    CONF_TAIL_CURRENT,
    CONF_VOLTAGE_ENTITY,
    DEFAULTS,
    DOMAIN,
)


def _number(unit: str, max_value: float, step: float = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=max_value, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _optional_entity(key: str, defaults: dict[str, Any]) -> vol.Optional:
    value = defaults.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value else None)


def _sources_schema(defaults: dict[str, Any]) -> dict:
    def d(key: str) -> Any:
        return defaults.get(key, DEFAULTS.get(key, vol.UNDEFINED))

    return {
        vol.Required(CONF_CURRENT_ENTITY, default=d(CONF_CURRENT_ENTITY)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.CURRENT)
        ),
        vol.Required(CONF_VOLTAGE_ENTITY, default=d(CONF_VOLTAGE_ENTITY)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.VOLTAGE)
        ),
        _optional_entity(CONF_FULL_ENTITY, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN)
        ),
        _optional_entity(CONF_GRID_ENTITY, defaults): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=BINARY_SENSOR_DOMAIN)
        ),
        vol.Required(CONF_NOMINAL_CAPACITY, default=d(CONF_NOMINAL_CAPACITY)): _number("Ah", 10000, 0.1),
        vol.Required(CONF_NOMINAL_VOLTAGE, default=d(CONF_NOMINAL_VOLTAGE)): _number("V", 1000, 0.1),
    }


def _tuning_schema(defaults: dict[str, Any]) -> dict:
    def d(key: str) -> Any:
        return defaults.get(key, DEFAULTS[key])

    return {
        vol.Required(CONF_EMPTY_VOLTAGE, default=d(CONF_EMPTY_VOLTAGE)): _number("V", 1000, 0.1),
        vol.Required(CONF_EMPTY_DELAY, default=d(CONF_EMPTY_DELAY)): _number("s", 3600),
        vol.Required(CONF_SHUTDOWN_DELAY, default=d(CONF_SHUTDOWN_DELAY)): _number("s", 3600),
        vol.Required(CONF_LOW_VOLTAGE_HINT, default=d(CONF_LOW_VOLTAGE_HINT)): _number("V", 1000, 0.1),
        vol.Required(CONF_LOW_SOC_HINT, default=d(CONF_LOW_SOC_HINT)): _number("%", 100),
        vol.Required(CONF_FULL_VOLTAGE, default=d(CONF_FULL_VOLTAGE)): _number("V", 1000, 0.1),
        vol.Required(CONF_TAIL_CURRENT, default=d(CONF_TAIL_CURRENT)): _number("A", 1000, 0.1),
        vol.Required(CONF_FULL_DELAY, default=d(CONF_FULL_DELAY)): _number("s", 3600),
        vol.Required(CONF_MAX_GAP, default=d(CONF_MAX_GAP)): _number("s", 3600),
        vol.Required(CONF_LEARN_CAPACITY, default=d(CONF_LEARN_CAPACITY)): selector.BooleanSelector(),
        vol.Required(CONF_LEARN_EFFICIENCY, default=d(CONF_LEARN_EFFICIENCY)): selector.BooleanSelector(),
    }


class BatterySocConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one entry per battery."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._async_abort_entries_match({CONF_CURRENT_ENTITY: user_input[CONF_CURRENT_ENTITY]})
            name = user_input.pop(CONF_NAME)
            initial_soc = user_input.pop(CONF_INITIAL_SOC)
            return self.async_create_entry(
                title=name, data={CONF_INITIAL_SOC: initial_soc}, options={**DEFAULTS, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Battery"): selector.TextSelector(),
                **_sources_schema({}),
                vol.Required(CONF_INITIAL_SOC, default=100): _number("%", 100),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BatterySocOptionsFlow()


class BatterySocOptionsFlow(OptionsFlow):
    """Change sources and tuning (the entry reloads; the counter state is kept)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({**_sources_schema(options), **_tuning_schema(options)})
        )
