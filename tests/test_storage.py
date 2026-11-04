"""The state is written while it keeps changing, not only once updates pause."""

from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant

from custom_components.battery_soc.const import DOMAIN

from .conftest import CURRENT, REMAINING, advance, outage, start_full, value


async def test_state_saved_during_steady_updates(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    entry = await start_full(hass)
    await outage(hass, current=-20)
    for i in range(60):  # the ESP reports every few seconds, so a 10 s debounce never fires
        hass.states.async_set(CURRENT, str(-20 - (i % 2) * 0.1))
        await advance(hass, freezer, 5, step=5)
    saved = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["remaining_ah"]
    # 5 min at 20 A is ~1.7 Ah; what is on disk may lag by at most about a minute (~0.4 Ah).
    assert saved == pytest.approx(value(hass, REMAINING), abs=0.5)
    assert saved < 200 - 1.0
