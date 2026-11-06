"""The sensor's zero, re-measured on every float; only its drift from the reference is subtracted."""

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import (
    CONF_CHARGE_CORRECTION,
    CONF_CORRECTION_REF_TEMP,
    CONF_DISCHARGE_CORRECTION,
    CONF_DISCHARGE_TEMP_COEFF,
    CONF_LEARN_OFFSET,
    CONF_TEMPERATURE_ENTITY,
    CONF_ZERO_REFERENCE,
)

from .conftest import CURRENT, FULL, GRID, OFFSET, REMAINING, SOC, advance, outage, start_full, value

TEMP = "sensor.inverter_ntc2_temperature"
OPTIONS = {
    CONF_LEARN_OFFSET: True,
    CONF_ZERO_REFERENCE: -1.0,  # the zero the corrections below were fitted at
    CONF_CHARGE_CORRECTION: 2.7,
    CONF_DISCHARGE_CORRECTION: 2.5,
    CONF_DISCHARGE_TEMP_COEFF: 0.3,
    CONF_CORRECTION_REF_TEMP: 40.0,
    CONF_TEMPERATURE_ENTITY: TEMP,
}


async def test_only_the_drift_from_the_reference_is_subtracted(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(TEMP, "40")
    await start_full(hass, OPTIONS, float_current=-3.0)  # the zero moved from -1 A to -3 A
    await advance(hass, freezer, 3600)
    assert value(hass, OFFSET) == pytest.approx(-3.0, abs=0.005)
    assert value(hass, SOC) == 100

    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)
    # -20 read, +2 A of zero drift, -2.5 A discharge correction: 20.5 A for an hour
    assert value(hass, REMAINING) == pytest.approx(179.5, abs=0.05)


async def test_the_start_of_a_float_is_skipped(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(TEMP, "40")
    await start_full(hass, OPTIONS, float_current=-1.0)
    hass.states.async_set(CURRENT, "-6")  # the current still settling right after float starts
    await hass.async_block_till_done()
    await advance(hass, freezer, 1800)
    hass.states.async_set(CURRENT, "-2")
    await hass.async_block_till_done()
    await advance(hass, freezer, 1800)
    assert value(hass, OFFSET) == pytest.approx(-2.0, abs=0.005)


async def test_each_float_replaces_the_zero(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(TEMP, "40")
    await start_full(hass, OPTIONS, float_current=-3.0)
    await advance(hass, freezer, 3600)
    assert value(hass, OFFSET) == pytest.approx(-3.0, abs=0.005)

    await outage(hass, current=-20)
    await advance(hass, freezer, 1800)
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(CURRENT, "50")
    await hass.async_block_till_done()
    await advance(hass, freezer, 600)
    hass.states.async_set(FULL, STATE_ON)  # the inverter powered on in between: a new zero
    hass.states.async_set(CURRENT, "1.0")
    await hass.async_block_till_done()
    await advance(hass, freezer, 1200)
    assert value(hass, OFFSET) == pytest.approx(-3.0, abs=0.005)  # still settling: the old zero stays
    await advance(hass, freezer, 2400)
    assert value(hass, OFFSET) == pytest.approx(1.0, abs=0.005)  # replaced, not averaged with -3 A
