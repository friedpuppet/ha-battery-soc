"""Coulomb counting, float hold, dropouts, persistence and manual calibration."""

from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import DOMAIN

from .conftest import (
    CHARGED,
    CURRENT,
    DISCHARGE_POWER,
    DISCHARGED,
    FULL,
    GRID,
    LOAD,
    MARK_FULL,
    OFFSET,
    POWER,
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


async def test_float_holds_full(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    assert value(hass, SOC) == 100
    assert hass.states.get(STATUS).state == "full"

    # The shunt shows -1.6 A on float; that must not count as a discharge.
    await advance(hass, freezer, 3600)
    assert value(hass, SOC) == 100
    assert value(hass, POWER) == 0
    assert value(hass, DISCHARGED) == 0


async def test_discharge(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-20, voltage=26.0)
    assert hass.states.get(STATUS).state == "discharging"
    assert value(hass, POWER) == -520
    assert value(hass, DISCHARGE_POWER) == 520

    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(180, abs=0.1)
    assert value(hass, SOC) == pytest.approx(90, abs=0.1)
    assert value(hass, DISCHARGED) == pytest.approx(0.52, abs=0.002)
    assert value(hass, CHARGED) == 0


async def test_charge_uses_efficiency(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)  # 180 Ah left

    hass.states.async_set(CURRENT, "40")
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "charging"
    await advance(hass, freezer, 900)  # 10 Ah in, 9.5 Ah stored at the default 0.95
    assert value(hass, REMAINING) == pytest.approx(189.5, abs=0.1)


async def test_short_dropout_is_bridged(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-36)
    hass.states.async_set(CURRENT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    await advance(hass, freezer, 60)
    hass.states.async_set(CURRENT, "-36")
    await hass.async_block_till_done()
    assert value(hass, REMAINING) == pytest.approx(199.4, abs=0.05)  # 60 s at 36 A = 0.6 Ah


async def test_long_dropout_stops_after_max_gap(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-36)
    hass.states.async_set(GRID, STATE_ON)  # not a shutdown: grid is back
    hass.states.async_set(CURRENT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    await advance(hass, freezer, 1800)
    assert value(hass, REMAINING) == pytest.approx(197, abs=0.05)  # only 300 s counted
    assert hass.states.get(STATUS).state == "unknown"


async def test_full_sensor_unavailable_keeps_holding(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    hass.states.async_set(FULL, STATE_UNAVAILABLE)
    hass.states.async_set(CURRENT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    hass.states.async_set(CURRENT, "-1.6")
    await hass.async_block_till_done()
    await advance(hass, freezer, 600)
    assert value(hass, SOC) == 100

    hass.states.async_set(FULL, STATE_OFF)
    await hass.async_block_till_done()
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(198.4, abs=0.05)


async def test_state_survives_reload(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry = await start_full(hass)
    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert value(hass, SOC) == pytest.approx(90, abs=0.1)
    assert value(hass, DISCHARGED) == pytest.approx(0.52, abs=0.002)
    assert hass.states.get(SOC).attributes["anchor"] == "full"


async def test_set_soc_and_mark_full(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await outage(hass, current=-20)

    await hass.services.async_call(DOMAIN, "set_soc", {"soc": 50}, blocking=True)
    assert value(hass, SOC) == 50
    assert hass.states.get(SOC).attributes["anchor"] is None

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: MARK_FULL}, blocking=True)
    assert value(hass, SOC) == 100
    assert hass.states.get(SOC).attributes["anchor"] == "full"


async def test_grid_loss_ends_hold_and_counts_from_load(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    # The night of 2026-10-08: the ESP drops off on float, then the grid goes; the load runs on.
    hass.states.async_set(LOAD, "200")
    await start_full(hass)
    await telemetry_gone(hass)
    hass.states.async_set(GRID, STATE_OFF)
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "discharging"

    await advance(hass, freezer, 3600)
    # 300 s bridged at the last 1.6 A (0.13 Ah), then 3300 s at 200 W / 27.2 V (6.74 Ah)
    assert value(hass, REMAINING) == pytest.approx(193.13, abs=0.05)
    assert hass.states.get(STATUS).attributes["estimated"] is True
    assert value(hass, POWER) == -200


async def test_load_ratio_is_learned_per_outage(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    hass.states.async_set(LOAD, "480")
    await start_full(hass)
    await outage(hass, current=-20, voltage=25.0)
    await advance(hass, freezer, 3600)  # 20 Ah from the battery, 480 W / 25 V = 19.2 Ah to the load
    hass.states.async_set(GRID, STATE_ON)
    await hass.async_block_till_done()
    # sample 20 / 19.2 = 1.042; EMA from 1.0
    assert hass.states.get(SOC).attributes["load_ratio"] == pytest.approx(1.0125, abs=0.001)


async def test_offset_is_subtracted(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_full(hass)
    await advance(hass, freezer, 3600)  # one hour of float at -1.6 A
    assert value(hass, OFFSET) == pytest.approx(-0.48, abs=0.005)
    assert value(hass, SOC) == 100

    await outage(hass, current=-20)
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == pytest.approx(180.48, abs=0.05)


async def test_state_from_v0_1_0_is_kept(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    entry = make_entry()
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "remaining_ah": 150.0,
            "capacity_ah": 200.0,
            "nominal_ah": 200.0,
            "efficiency": 0.95,
            "energy_in_kwh": 2.5,
            "energy_out_kwh": 2.9,
            "anchor": "full",
            "cycle_in_ah": 0.0,
            "cycle_out_ah": 50.0,
            "drift_ah": 0.0,
            "last_full": "2026-10-07T23:12:18+00:00",
            "last_empty": None,
            "holding": False,
            "off": False,
        },
    }
    hass.states.async_set(CURRENT, "-20")
    hass.states.async_set(VOLTAGE, "26.0")
    hass.states.async_set(GRID, STATE_OFF)
    await setup_entry(hass, entry)
    assert value(hass, SOC) == 75
    assert value(hass, OFFSET) == 0
    assert hass.states.get(SOC).attributes["load_ratio"] == 1
