"""Full/empty anchors and what they teach."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import CONF_FULL_ENTITY, EVENT_EMPTY, EVENT_FULL

from .conftest import (
    CAPACITY,
    CURRENT,
    EFFICIENCY,
    FULL,
    GRID,
    LOAD,
    OFFSET,
    REMAINING,
    SOC,
    STATUS,
    VOLTAGE,
    advance,
    make_entry,
    outage,
    setup_entry,
    start_full,
    telemetry_gone,
    value,
)


async def test_full_sensor_anchors_and_learns_efficiency(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_FULL)
    await outage(hass, current=-20)
    await advance(hass, freezer, 7200)  # 40 Ah out

    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(CURRENT, "50")
    await hass.async_block_till_done()
    await advance(hass, freezer, 3240)  # 45 Ah in
    hass.states.async_set(FULL, STATE_ON)
    await hass.async_block_till_done()

    assert value(hass, SOC) == 100
    assert hass.states.get(STATUS).state == "full"
    # sample 40/45 = 0.889; EMA from 0.95 with alpha 0.3
    assert value(hass, EFFICIENCY) == pytest.approx(93.2, abs=0.1)
    assert len(events) == 1


async def test_short_cycle_teaches_nothing(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-20)
    await advance(hass, freezer, 1800)  # 10 Ah out, 5 % of capacity
    hass.states.async_set(CURRENT, "50")
    await hass.async_block_till_done()
    await advance(hass, freezer, 900)
    hass.states.async_set(FULL, STATE_ON)
    await hass.async_block_till_done()
    assert value(hass, EFFICIENCY) == 95


async def discharge_to_low(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """From full: 170 Ah out at 20 A, SoC 15 %."""
    await outage(hass, current=-20, voltage=25.6)
    await advance(hass, freezer, 8.5 * 3600, step=600)
    assert value(hass, SOC) == pytest.approx(15, abs=0.1)


async def test_inverter_shutdown_is_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await discharge_to_low(hass, freezer)
    await telemetry_gone(hass)

    await advance(hass, freezer, 170, step=10)
    assert events == []
    await advance(hass, freezer, 20, step=10)
    assert len(events) == 1
    assert value(hass, SOC) == 0
    assert hass.states.get(STATUS).state == "off"
    assert hass.states.get(SOC).attributes["anchor"] == "empty"
    # Discharged since full: 170 Ah + 180 s bridged at 20 A = 171 Ah; EMA from 200
    assert value(hass, CAPACITY) == pytest.approx(191.3, abs=0.05)

    # Nothing accrues while the inverter is off.
    await advance(hass, freezer, 3600, step=600)
    assert value(hass, SOC) == 0

    # Grid back: the inverter starts and charges from zero.
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(VOLTAGE, "27.0")
    hass.states.async_set(CURRENT, "50")
    hass.states.async_set(FULL, STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "charging"
    await advance(hass, freezer, 3600, step=600)
    assert value(hass, REMAINING) == pytest.approx(47.5, abs=0.1)


async def test_dropout_at_high_soc_is_not_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await outage(hass, current=-20, voltage=26.3)
    await telemetry_gone(hass)
    await advance(hass, freezer, 600, step=10)
    assert events == []
    assert value(hass, REMAINING) == pytest.approx(198.33, abs=0.05)  # 300 s bridged


async def test_dropout_with_grid_is_not_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await discharge_to_low(hass, freezer)
    hass.states.async_set(GRID, STATE_ON)
    await telemetry_gone(hass)
    await advance(hass, freezer, 600, step=10)
    assert events == []


async def test_grid_return_cancels_shutdown(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await discharge_to_low(hass, freezer)
    await telemetry_gone(hass)
    await advance(hass, freezer, 60, step=10)
    hass.states.async_set(GRID, STATE_ON)
    await hass.async_block_till_done()
    await advance(hass, freezer, 600, step=10)
    assert events == []


async def test_low_voltage_is_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await outage(hass, current=-20, voltage=26.0)
    await advance(hass, freezer, 3600)

    hass.states.async_set(VOLTAGE, "23.9")
    await hass.async_block_till_done()
    await advance(hass, freezer, 5, step=5)
    hass.states.async_set(VOLTAGE, "24.3")  # a dip under load, not empty
    await hass.async_block_till_done()
    await advance(hass, freezer, 20, step=5)
    assert events == []

    hass.states.async_set(VOLTAGE, "23.8")
    await hass.async_block_till_done()
    await advance(hass, freezer, 15, step=5)
    assert len(events) == 1
    assert value(hass, SOC) == 0
    # A capacity of ~20 Ah is implausible for a 200 Ah battery: not learned.
    assert value(hass, CAPACITY) == 200


async def test_charge_from_empty_learns_efficiency(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await discharge_to_low(hass, freezer)
    await telemetry_gone(hass)
    await advance(hass, freezer, 200, step=10)  # empty, capacity 191.3

    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(VOLTAGE, "27.0")
    hass.states.async_set(FULL, STATE_OFF)
    hass.states.async_set(CURRENT, "50")
    await hass.async_block_till_done()
    await advance(hass, freezer, 4.4 * 3600, step=600)  # 220 Ah in
    hass.states.async_set(FULL, STATE_ON)
    await hass.async_block_till_done()
    # sample 191.3 / 220 = 0.8695; EMA from 0.95
    assert value(hass, EFFICIENCY) == pytest.approx(92.6, abs=0.1)
    assert value(hass, SOC) == 100


async def test_full_by_voltage_without_full_sensor(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(CURRENT, "-20")
    hass.states.async_set(VOLTAGE, "26.0")
    hass.states.async_set(GRID, STATE_OFF)
    await setup_entry(hass, make_entry({CONF_FULL_ENTITY: None}, initial_soc=50))
    assert value(hass, SOC) == 50

    hass.states.async_set(CURRENT, "50")
    hass.states.async_set(VOLTAGE, "28.0")
    await hass.async_block_till_done()
    await advance(hass, freezer, 600)
    hass.states.async_set(CURRENT, "8")
    hass.states.async_set(VOLTAGE, "28.3")
    await hass.async_block_till_done()
    await advance(hass, freezer, 30, step=10)
    assert value(hass, SOC) < 100
    await advance(hass, freezer, 40, step=10)
    assert value(hass, SOC) == 100
    assert hass.states.get(STATUS).state == "charging"  # no hold without a full sensor


async def test_long_dropout_ends_at_shutdown_once_load_is_dark(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(LOAD, "500")
    await start_full(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await outage(hass, current=-20, voltage=26.0)
    await advance(hass, freezer, 3600)  # 180 Ah left

    # The ESP drops off while the inverter keeps feeding 500 W: counted from the load.
    await telemetry_gone(hass)
    await advance(hass, freezer, 8 * 3600, step=600)
    # 300 s bridged at 20 A (1.67 Ah) + 28500 s at 500 W / 26 V (152.24 Ah)
    assert value(hass, REMAINING) == pytest.approx(26.09, abs=0.05)
    assert events == []  # low, but the load still runs: not a shutdown

    hass.states.async_set(LOAD, STATE_UNAVAILABLE)  # the inverter switched off
    await hass.async_block_till_done()
    await advance(hass, freezer, 20, step=10)
    assert len(events) == 1
    assert value(hass, SOC) == 0
    assert hass.states.get(STATUS).state == "off"
    # 173.91 Ah out since full; EMA from 200
    assert value(hass, CAPACITY) == pytest.approx(192.2, abs=0.05)


async def test_shunt_offset_is_learned_and_efficiency_stays_plausible(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    # The shunt reads 1 A low. On float that is all it shows; 10 hourly samples learn it.
    await start_full(hass, float_current=-1.0)
    await advance(hass, freezer, 10 * 3600, step=600)
    assert value(hass, OFFSET) == pytest.approx(-0.97, abs=0.005)

    await outage(hass, current=-21)  # really 20 A
    await advance(hass, freezer, 3 * 3600, step=600)
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(CURRENT, "50")  # really 51 A
    await hass.async_block_till_done()
    await advance(hass, freezer, 1.2 * 3600, step=600)
    hass.states.async_set(FULL, STATE_ON)
    await hass.async_block_till_done()
    # 60.08 Ah out / 61.17 Ah in = 0.982 (uncorrected: 63 / 60 = 1.05, rejected); EMA from 0.95
    assert value(hass, EFFICIENCY) == pytest.approx(96.0, abs=0.05)
