"""Per-mode corrections of the current sensor (charge, discharge with a temperature term)."""

import json

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import (
    CONF_BOOT_ENTITY,
    CONF_CHARGE_CORRECTION,
    CONF_CORRECTION_REF_TEMP,
    CONF_COUNTERS_ENTITY,
    CONF_DISCHARGE_CORRECTION,
    CONF_DISCHARGE_TEMP_COEFF,
    CONF_LEARN_OFFSET,
    CONF_TEMPERATURE_ENTITY,
)

from .conftest import (
    BOOT,
    COUNTERS,
    CURRENT,
    FULL,
    GRID,
    OFFSET,
    POWER,
    REMAINING,
    SOC,
    VOLTAGE,
    advance,
    make_entry,
    outage,
    setup_entry,
    start_full,
    value,
)
from .test_counters import set_counters, totals

TEMP = "sensor.inverter_ntc2_temperature"
CORRECTIONS = {
    CONF_LEARN_OFFSET: False,
    CONF_CHARGE_CORRECTION: 2.7,
    CONF_DISCHARGE_CORRECTION: 2.5,
    CONF_DISCHARGE_TEMP_COEFF: 0.3,
    CONF_CORRECTION_REF_TEMP: 40.0,
    CONF_TEMPERATURE_ENTITY: TEMP,
}


async def test_discharge_and_charge_are_corrected(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(TEMP, "45")
    await start_full(hass, CORRECTIONS)
    await advance(hass, freezer, 3600)  # an hour of float at -1.6 A
    assert value(hass, OFFSET) == pytest.approx(-0.48, abs=0.005)  # tracked, not subtracted
    assert value(hass, SOC) == 100

    await outage(hass, current=-20, voltage=25.0)
    assert value(hass, POWER) == pytest.approx(-24 * 25.0)  # 2.5 + 0.3 * 5 more discharge
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(176, abs=0.05)

    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(CURRENT, "40")
    await hass.async_block_till_done()
    await advance(hass, freezer, 1800)
    assert value(hass, REMAINING) == pytest.approx(176 + 42.7 * 0.5 * 0.95, abs=0.05)


async def test_temperature_term_is_clamped(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(TEMP, "10")  # 2.5 - 9 would read the discharge as less than the sensor
    await start_full(hass, CORRECTIONS)
    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(180, abs=0.05)

    hass.states.async_set(TEMP, "80")  # 2.5 + 12 is capped at 10 A
    await hass.async_block_till_done()
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(150, abs=0.05)


async def test_without_temperature_the_base_applies(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass, {**CORRECTIONS, CONF_TEMPERATURE_ENTITY: None})
    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(177.5, abs=0.05)


async def start_counting_corrected(hass: HomeAssistant) -> None:
    hass.states.async_set(CURRENT, "-1.6")
    hass.states.async_set(VOLTAGE, "27.2")
    hass.states.async_set(FULL, STATE_ON)
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(COUNTERS, json.dumps(totals()))
    hass.states.async_set(BOOT, json.dumps({**totals(), "pon": 1}))
    options = {**CORRECTIONS, CONF_TEMPERATURE_ENTITY: None, CONF_COUNTERS_ENTITY: COUNTERS, CONF_BOOT_ENTITY: BOOT}
    await setup_entry(hass, make_entry(options))


async def test_counter_steps_follow_the_grid(hass: HomeAssistant) -> None:
    await start_counting_corrected(hass)
    await outage(hass, current=-20)
    await set_counters(hass, ao=3, so=600)  # 10 min: still follows the grid by direction
    await set_counters(hass, ao=3.3, so=660)
    assert value(hass, REMAINING) == pytest.approx(200 - 3.3 - 2.5 * 660 / 3600, abs=0.05)

    hass.states.async_set(GRID, STATE_ON)
    await hass.async_block_till_done()
    # grid back but the sensor still shows a small discharge: the charge correction applies
    await set_counters(hass, ao=3.8, so=720)
    assert value(hass, REMAINING) == pytest.approx(200 - 3.8 - 2.5 * 660 / 3600 + 2.7 / 60 * 0.95, abs=0.05)


async def test_long_counter_catch_up_splits_by_direction(hass: HomeAssistant) -> None:
    await start_counting_corrected(hass)
    hass.states.async_set(GRID, STATE_OFF)
    hass.states.async_set(FULL, STATE_OFF)
    await hass.async_block_till_done()
    # Home Assistant missed an outage and part of the recharge
    await set_counters(hass, ao=40, so=7200)
    assert value(hass, REMAINING) == pytest.approx(200 - 40 - 2.5 * 2, abs=0.05)
    await set_counters(hass, ao=41, so=7500, ai=10, si=1800)  # discharge, then part of the recharge
    assert value(hass, REMAINING) == pytest.approx(155 - 1 - 2.5 * 300 / 3600 + (10 + 2.7 * 0.5) * 0.95, abs=0.05)
