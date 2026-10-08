"""Battery sensors: state of charge, learned parameters, power and energy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BatterySocConfigEntry
from .entity import BatteryEntity
from .tracker import BatteryTracker

AMPERE_HOUR = "Ah"


@dataclass(frozen=True, kw_only=True)
class BatterySensorDescription(SensorEntityDescription):
    value_fn: Callable[[BatteryTracker], float | str | None]
    attrs_fn: Callable[[BatteryTracker], dict[str, Any]] | None = None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value)


def _clip(value: float | None, sign: int) -> float | None:
    return None if value is None else max(sign * round(value), 0)


SENSORS: tuple[BatterySensorDescription, ...] = (
    BatterySensorDescription(
        key="state_of_charge",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda t: round(t.soc, 1),
        attrs_fn=lambda t: {
            "anchor": t.anchor,
            "last_full": t.last_full,
            "last_empty": t.last_empty,
            "drift_ah": round(t.drift_ah, 2),
            "cycle_in_ah": round(t.cycle_in_ah, 2),
            "cycle_out_ah": round(t.cycle_out_ah, 2),
            "load_ratio": round(t.load_ratio, 3),
        },
    ),
    BatterySensorDescription(
        key="remaining_charge",
        icon="mdi:battery-arrow-down-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=AMPERE_HOUR,
        suggested_display_precision=1,
        value_fn=lambda t: round(t.remaining_ah, 1),
    ),
    BatterySensorDescription(
        key="capacity",
        icon="mdi:battery-high",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=AMPERE_HOUR,
        suggested_display_precision=1,
        value_fn=lambda t: round(t.capacity_ah, 1),
    ),
    BatterySensorDescription(
        key="state_of_health",
        icon="mdi:battery-heart-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda t: round(t.state_of_health, 1),
    ),
    BatterySensorDescription(
        key="charge_efficiency",
        icon="mdi:battery-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda t: round(100 * t.efficiency, 1),
    ),
    BatterySensorDescription(
        key="current_offset",
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        value_fn=lambda t: round(t.current_offset, 2),
    ),
    BatterySensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda t: _round(t.power),
    ),
    BatterySensorDescription(
        key="charge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda t: _clip(t.power, 1),
    ),
    BatterySensorDescription(
        key="discharge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda t: _clip(t.power, -1),
    ),
    BatterySensorDescription(
        key="energy_charged",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda t: round(t.energy_in_kwh, 3),
    ),
    BatterySensorDescription(
        key="energy_discharged",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda t: round(t.energy_out_kwh, 3),
    ),
    BatterySensorDescription(
        key="status",
        icon="mdi:battery-sync-outline",
        device_class=SensorDeviceClass.ENUM,
        options=["charging", "discharging", "idle", "full", "off"],
        value_fn=lambda t: t.status,
        attrs_fn=lambda t: {"estimated": t.estimating},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatterySocConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(BatterySensor(entry, entry.runtime_data, description) for description in SENSORS)


class BatterySensor(BatteryEntity, SensorEntity):
    """A value computed by the tracker."""

    entity_description: BatterySensorDescription

    def __init__(
        self, entry: BatterySocConfigEntry, tracker: BatteryTracker, description: BatterySensorDescription
    ) -> None:
        super().__init__(entry, tracker, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value_fn(self._tracker)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self._tracker)
