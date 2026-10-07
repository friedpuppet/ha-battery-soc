"""Fixtures for Battery SoC tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import (
    CONF_CURRENT_ENTITY,
    CONF_FULL_ENTITY,
    CONF_GRID_ENTITY,
    CONF_INITIAL_SOC,
    CONF_VOLTAGE_ENTITY,
    DEFAULTS,
    DOMAIN,
)

CURRENT = "sensor.inverter_battery_current"
VOLTAGE = "sensor.inverter_battery_voltage"
FULL = "binary_sensor.inverter_float_charging"
GRID = "binary_sensor.grid"

SOC = "sensor.battery_state_of_charge"
REMAINING = "sensor.battery_remaining_charge"
CAPACITY = "sensor.battery_capacity"
EFFICIENCY = "sensor.battery_charge_efficiency"
POWER = "sensor.battery_power"
DISCHARGE_POWER = "sensor.battery_discharge_power"
CHARGED = "sensor.battery_energy_charged"
DISCHARGED = "sensor.battery_energy_discharged"
STATUS = "sensor.battery_status"
MARK_FULL = "button.battery_mark_full"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_entry(options: dict[str, Any] | None = None, initial_soc: float = 100) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Battery",
        data={CONF_INITIAL_SOC: initial_soc},
        options={
            **DEFAULTS,
            CONF_CURRENT_ENTITY: CURRENT,
            CONF_VOLTAGE_ENTITY: VOLTAGE,
            CONF_FULL_ENTITY: FULL,
            CONF_GRID_ENTITY: GRID,
            **(options or {}),
        },
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def start_full(hass: HomeAssistant, options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Battery on float with the grid present (anchored full at startup)."""
    hass.states.async_set(CURRENT, "-1.6")
    hass.states.async_set(VOLTAGE, "27.2")
    hass.states.async_set(FULL, STATE_ON)
    hass.states.async_set(GRID, STATE_ON)
    entry = make_entry(options)
    await setup_entry(hass, entry)
    return entry


async def outage(hass: HomeAssistant, current: float = -20, voltage: float = 26.0) -> None:
    """Grid lost: float ends and the battery starts discharging."""
    hass.states.async_set(GRID, STATE_OFF)
    hass.states.async_set(FULL, STATE_OFF)
    hass.states.async_set(VOLTAGE, str(voltage))
    hass.states.async_set(CURRENT, str(current))
    await hass.async_block_till_done()


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float, step: float = 60) -> None:
    """Move time forward in steps, letting the integration tick run."""
    while seconds > 0:
        delta = min(step, seconds)
        freezer.tick(timedelta(seconds=delta))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        seconds -= delta


def value(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)
