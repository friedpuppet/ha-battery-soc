"""Counter mode: the inverter's ESP keeps the totals, the tracker applies their differences."""

import json

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import CONF_BOOT_ENTITY, CONF_COUNTERS_ENTITY, EVENT_EMPTY

from .conftest import (
    BOOT,
    CAPACITY,
    COUNTERS,
    CURRENT,
    DISCHARGED,
    FULL,
    GRID,
    OFFSET,
    REMAINING,
    SOC,
    VOLTAGE,
    advance,
    make_entry,
    outage,
    setup_entry,
    telemetry_gone,
    value,
)

FIELDS = ("ai", "ao", "si", "so", "fa", "fs", "wi", "wo")


def totals(n: int = 1, **values: float) -> dict[str, float]:
    return {"n": n, **{k: values.get(k, 0.0) for k in FIELDS}}


async def set_counters(hass: HomeAssistant, n: int = 1, **values: float) -> None:
    hass.states.async_set(COUNTERS, json.dumps(totals(n, **values)))
    await hass.async_block_till_done()


async def set_boot(hass: HomeAssistant, n: int, pon: bool, **values: float) -> None:
    hass.states.async_set(BOOT, json.dumps({**totals(n, **values), "pon": int(pon)}))
    await hass.async_block_till_done()


async def start_counting(hass: HomeAssistant) -> MockConfigEntry:
    """On float with the grid present, ESP at boot 1 with all totals at zero."""
    hass.states.async_set(CURRENT, "-1.6")
    hass.states.async_set(VOLTAGE, "27.2")
    hass.states.async_set(FULL, STATE_ON)
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(COUNTERS, json.dumps(totals()))
    hass.states.async_set(BOOT, json.dumps({**totals(), "pon": 1}))
    entry = make_entry({CONF_COUNTERS_ENTITY: COUNTERS, CONF_BOOT_ENTITY: BOOT})
    await setup_entry(hass, entry)
    return entry


async def test_counted_from_totals_not_current(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    assert value(hass, SOC) == 100
    await outage(hass, current=-20, voltage=26.0)
    await advance(hass, freezer, 3600)
    assert value(hass, REMAINING) == 200  # the current sensor is not integrated

    await set_counters(hass, ao=20, so=3600, wo=520)
    assert value(hass, REMAINING) == pytest.approx(180, abs=0.01)
    assert value(hass, DISCHARGED) == pytest.approx(0.52, abs=0.001)


async def test_downtime_is_caught_up(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry = await start_counting(hass)
    await outage(hass, current=-20)
    await set_counters(hass, ao=20, so=3600)
    assert await hass.config_entries.async_unload(entry.entry_id)

    # Home Assistant away; the ESP keeps counting.
    await set_counters(hass, ao=50, so=9000)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert value(hass, REMAINING) == pytest.approx(150, abs=0.01)


async def test_soft_reboot_continues(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    await outage(hass, current=-20)
    await set_counters(hass, ao=20)
    await set_counters(hass, n=2, ao=25)  # waits for the boot snapshot
    assert value(hass, REMAINING) == pytest.approx(180, abs=0.01)
    await set_boot(hass, 2, pon=False, ao=22)
    assert value(hass, REMAINING) == pytest.approx(175, abs=0.01)
    assert hass.states.get(SOC).attributes["anchor"] == "full"


async def test_power_on_boot_when_low_is_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await outage(hass, current=-20, voltage=25.4)
    await set_counters(hass, ao=170)
    assert value(hass, SOC) == pytest.approx(15, abs=0.01)

    # The inverter switches off: telemetry gone, no false empty while it is away.
    await telemetry_gone(hass)
    await advance(hass, freezer, 3600, step=600)
    assert events == []

    # Grid back: the ESP boots from power-on (2 more Ah went out before the cut-off) and charges 10 Ah.
    hass.states.async_set(GRID, STATE_ON)
    hass.states.async_set(FULL, STATE_OFF)
    hass.states.async_set(CURRENT, "50")
    await set_counters(hass, n=2, ao=172, ai=10)
    await set_boot(hass, 2, pon=True, ao=172)
    assert len(events) == 1
    # 172 Ah out since full; EMA from 200
    assert value(hass, CAPACITY) == pytest.approx(191.6, abs=0.05)
    assert value(hass, REMAINING) == pytest.approx(9.5, abs=0.01)  # 10 Ah in at 0.95
    assert hass.states.get(SOC).attributes["anchor"] == "empty"


async def test_power_on_boot_when_high_is_not_empty(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    events = async_capture_events(hass, EVENT_EMPTY)
    await outage(hass, current=-20, voltage=26.2)
    await set_counters(hass, ao=20)
    await set_boot(hass, 2, pon=True, ao=21)
    await set_counters(hass, n=2, ao=21)
    assert events == []
    assert value(hass, REMAINING) == pytest.approx(179, abs=0.01)


async def test_totals_going_back_are_rebased(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    await outage(hass, current=-20)
    await set_counters(hass, ao=20)
    await set_counters(hass, ao=15)  # restored from an older flash copy
    assert value(hass, REMAINING) == pytest.approx(180, abs=0.01)
    await set_counters(hass, ao=18)
    assert value(hass, REMAINING) == pytest.approx(177, abs=0.01)


async def test_unavailable_totals_are_ignored(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    await outage(hass, current=-20)
    await set_counters(hass, ao=20)
    hass.states.async_set(COUNTERS, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    await set_counters(hass, ao=30)
    assert value(hass, REMAINING) == pytest.approx(170, abs=0.01)


async def test_offset_learned_from_float_totals(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await start_counting(hass)
    await set_counters(hass, fa=-1.0, fs=3600)  # an hour on float reading -1 A
    assert value(hass, OFFSET) == pytest.approx(-0.3, abs=0.005)
    assert value(hass, SOC) == 100

    await outage(hass, current=-21)
    await set_counters(hass, fa=-1.0, fs=3600, ao=21, so=3600)
    # 21 Ah read, 0.3 Ah of it is the offset
    assert value(hass, REMAINING) == pytest.approx(179.3, abs=0.01)
