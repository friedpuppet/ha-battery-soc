"""Config and options flows."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import CURRENT, FULL, GRID, SOC, VOLTAGE, make_entry, setup_entry, value
from custom_components.battery_soc.const import (
    CONF_CURRENT_ENTITY,
    CONF_EMPTY_VOLTAGE,
    CONF_FULL_ENTITY,
    CONF_GRID_ENTITY,
    CONF_INITIAL_SOC,
    CONF_NOMINAL_CAPACITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_VOLTAGE_ENTITY,
    DOMAIN,
)

USER_INPUT = {
    CONF_NAME: "Battery",
    CONF_CURRENT_ENTITY: CURRENT,
    CONF_VOLTAGE_ENTITY: VOLTAGE,
    CONF_FULL_ENTITY: FULL,
    CONF_GRID_ENTITY: GRID,
    CONF_NOMINAL_CAPACITY: 200,
    CONF_NOMINAL_VOLTAGE: 25.6,
    CONF_INITIAL_SOC: 80,
}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    hass.states.async_set(CURRENT, "-5")
    hass.states.async_set(VOLTAGE, "26")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Battery"
    assert result["data"] == {CONF_INITIAL_SOC: 80}
    assert result["options"][CONF_EMPTY_VOLTAGE] == 24.0  # defaults filled in
    await hass.async_block_till_done()
    assert value(hass, SOC) == 80


async def test_same_current_sensor_aborts(hass: HomeAssistant) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_reloads_and_keeps_state(hass: HomeAssistant) -> None:
    hass.states.async_set(CURRENT, "-5")
    hass.states.async_set(VOLTAGE, "26")
    entry = make_entry(initial_soc=70)
    await setup_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    options = {**entry.options, CONF_EMPTY_VOLTAGE: 23.8}
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_EMPTY_VOLTAGE] == 23.8
    assert value(hass, SOC) == 70


async def test_nominal_change_resets_capacity(hass: HomeAssistant) -> None:
    hass.states.async_set(CURRENT, "-5")
    hass.states.async_set(VOLTAGE, "26")
    entry = make_entry(initial_soc=50)
    await setup_entry(hass, entry)
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_NOMINAL_CAPACITY: 100})
    await hass.async_block_till_done()
    assert value(hass, SOC) == 50
    assert value(hass, "sensor.battery_capacity") == 100
