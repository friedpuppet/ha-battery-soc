"""Coulomb counter with full/empty anchors and capacity/efficiency learning.

The battery current (signed, + = charging) is integrated into the remaining charge (Ah).
Integration alone drifts, so it is re-anchored at the two points that can be detected:

- **Full**: the "full" binary sensor (e.g. the inverter's float-charging flag) turns on.
  While it stays on the current is taken as 0: chargers in float hold the voltage and the
  shunt mostly shows its own offset, which would otherwise count as a slow discharge.
  Without a full sensor: voltage >= full voltage with |current| <= tail current for a while.
- **Empty**: an inverter powered from its own battery switches itself off at cut-off, and
  its telemetry disappears with it. So: no grid, the battery was already low (voltage or
  SoC hint), and the current sensor has been unavailable for ``shutdown_delay`` seconds.
  Fallback: voltage <= empty voltage while discharging for ``empty_delay`` seconds.

Each anchor also teaches a parameter: empty after full gives the usable capacity, full
after full/empty gives the charge efficiency (Ah out / Ah in over the cycle). Both use an
EMA and ignore cycles that are too short or give implausible values.

Short sensor dropouts are bridged by extrapolating the last current for ``max_gap`` seconds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CAPACITY_RANGE,
    CONF_CURRENT_ENTITY,
    CONF_EMPTY_DELAY,
    CONF_EMPTY_VOLTAGE,
    CONF_FULL_DELAY,
    CONF_FULL_ENTITY,
    CONF_FULL_VOLTAGE,
    CONF_GRID_ENTITY,
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
    DEFAULT_EFFICIENCY,
    DEFAULTS,
    DOMAIN,
    EFFICIENCY_RANGE,
    EVENT_EMPTY,
    EVENT_FULL,
    IDLE_CURRENT,
    LEARN_ALPHA,
    LEARN_MIN_CYCLE,
    STORAGE_VERSION,
    TICK_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

ANCHOR_FULL = "full"
ANCHOR_EMPTY = "empty"


def _number(state: str | None) -> float | None:
    try:
        return float(state)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class BatteryTracker:
    """Track the remaining charge of one battery."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, options: Mapping[str, Any], initial_soc: float
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        opts = {**DEFAULTS, **options}
        self.current_entity: str = opts[CONF_CURRENT_ENTITY]
        self.voltage_entity: str = opts[CONF_VOLTAGE_ENTITY]
        self.full_entity: str | None = opts.get(CONF_FULL_ENTITY) or None
        self.grid_entity: str | None = opts.get(CONF_GRID_ENTITY) or None
        self.nominal_ah = float(opts[CONF_NOMINAL_CAPACITY])
        self.nominal_v = float(opts[CONF_NOMINAL_VOLTAGE])
        self.empty_voltage = float(opts[CONF_EMPTY_VOLTAGE])
        self.empty_delay = float(opts[CONF_EMPTY_DELAY])
        self.shutdown_delay = float(opts[CONF_SHUTDOWN_DELAY])
        self.low_voltage_hint = float(opts[CONF_LOW_VOLTAGE_HINT])
        self.low_soc_hint = float(opts[CONF_LOW_SOC_HINT])
        self.full_voltage = float(opts[CONF_FULL_VOLTAGE])
        self.tail_current = float(opts[CONF_TAIL_CURRENT])
        self.full_delay = float(opts[CONF_FULL_DELAY])
        self.max_gap = timedelta(seconds=float(opts[CONF_MAX_GAP]))
        self.learn_capacity = bool(opts[CONF_LEARN_CAPACITY])
        self.learn_efficiency = bool(opts[CONF_LEARN_EFFICIENCY])
        self.initial_soc = initial_soc

        # Persisted state
        self.capacity_ah = self.nominal_ah
        self.remaining_ah = self.nominal_ah * initial_soc / 100
        self.efficiency = DEFAULT_EFFICIENCY
        self.energy_in_kwh = 0.0
        self.energy_out_kwh = 0.0
        self.anchor: str | None = None  # last anchor: "full", "empty" or None (manual)
        self.cycle_in_ah = 0.0  # raw Ah charged since the last anchor
        self.cycle_out_ah = 0.0  # Ah discharged since the last anchor
        self.drift_ah = 0.0  # counted beyond 0/capacity since the last anchor
        self.last_full: datetime | None = None
        self.last_empty: datetime | None = None
        self.holding = False  # full sensor on: current is taken as 0
        self.off = False  # inverter switched off at empty; nothing flows until it is back

        # Live inputs
        self.current: float | None = None
        self.voltage: float | None = None
        self._last_current: float | None = None
        self._last_voltage: float | None = None
        self._gap_until: datetime | None = None  # extrapolate the last current until then
        self._last_ts: datetime = dt_util.utcnow()

        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._timers: dict[str, CALLBACK_TYPE] = {}

    # ----- derived values -------------------------------------------------

    @property
    def soc(self) -> float:
        return 100 * self.remaining_ah / self.capacity_ah if self.capacity_ah else 0.0

    @property
    def state_of_health(self) -> float:
        return 100 * self.capacity_ah / self.nominal_ah

    @property
    def effective_current(self) -> float | None:
        """Current the counter uses right now (0 while full or switched off)."""
        if self.off or self.holding:
            return 0.0
        return self.current

    @property
    def power(self) -> float | None:
        current = self.effective_current
        if current is None:
            return None
        return current * self._volts()

    @property
    def status(self) -> str | None:
        if self.off:
            return "off"
        if self.holding:
            return "full"
        current = self.current
        if current is None:
            return None
        if current > IDLE_CURRENT:
            return "charging"
        if current < -IDLE_CURRENT:
            return "discharging"
        return "idle"

    def _volts(self) -> float:
        if self.voltage is not None:
            return self.voltage
        return self._last_voltage if self._last_voltage is not None else self.nominal_v

    # ----- lifecycle ------------------------------------------------------

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        self.remaining_ah = data["remaining_ah"]
        self.capacity_ah = data["capacity_ah"]
        self.efficiency = data["efficiency"]
        self.energy_in_kwh = data["energy_in_kwh"]
        self.energy_out_kwh = data["energy_out_kwh"]
        self.anchor = data["anchor"]
        self.cycle_in_ah = data["cycle_in_ah"]
        self.cycle_out_ah = data["cycle_out_ah"]
        self.drift_ah = data["drift_ah"]
        self.last_full = dt_util.parse_datetime(data["last_full"]) if data["last_full"] else None
        self.last_empty = dt_util.parse_datetime(data["last_empty"]) if data["last_empty"] else None
        self.holding = data["holding"]
        self.off = data["off"]
        if data["nominal_ah"] != self.nominal_ah:
            # A different battery (or a corrected rating): start learning from the new nominal.
            soc = self.soc
            self.capacity_ah = self.nominal_ah
            self.remaining_ah = self.nominal_ah * soc / 100
            _LOGGER.info("Nominal capacity changed to %s Ah, learned capacity reset", self.nominal_ah)

    def _data(self) -> dict[str, Any]:
        return {
            "remaining_ah": self.remaining_ah,
            "capacity_ah": self.capacity_ah,
            "nominal_ah": self.nominal_ah,
            "efficiency": self.efficiency,
            "energy_in_kwh": self.energy_in_kwh,
            "energy_out_kwh": self.energy_out_kwh,
            "anchor": self.anchor,
            "cycle_in_ah": self.cycle_in_ah,
            "cycle_out_ah": self.cycle_out_ah,
            "drift_ah": self.drift_ah,
            "last_full": _iso(self.last_full),
            "last_empty": _iso(self.last_empty),
            "holding": self.holding,
            "off": self.off,
        }

    @callback
    def async_start(self) -> None:
        """Read the sources, subscribe to them and start the integration tick."""
        self._last_ts = dt_util.utcnow()
        self.current = _number(self._state(self.current_entity))
        self._last_current = self.current
        self.voltage = _number(self._state(self.voltage_entity))
        self._last_voltage = self.voltage
        if self.current is not None:
            self.off = False

        if self.full_entity:
            full = self._state(self.full_entity)
            if full == STATE_ON and not self.holding:
                self._full_event("full sensor already on at startup")
            elif full == STATE_OFF:
                self.holding = False

        entities = [self.current_entity, self.voltage_entity]
        entities += [e for e in (self.full_entity, self.grid_entity) if e]
        self._unsubs.append(async_track_state_change_event(self.hass, entities, self._async_on_change))
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_tick, timedelta(seconds=TICK_SECONDS))
        )
        self._changed()

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for name in list(self._timers):
            self._cancel(name)

    async def async_flush(self) -> None:
        self._accrue(dt_util.utcnow())
        await self._store.async_save(self._data())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    # ----- manual calibration ---------------------------------------------

    @callback
    def async_set_soc(self, soc: float) -> None:
        """Set the state of charge by hand; this is not an anchor, nothing is learned."""
        self._accrue(dt_util.utcnow())
        self.remaining_ah = self.capacity_ah * soc / 100
        self.anchor = None
        self._reset_cycle()
        self._changed()

    @callback
    def async_mark_full(self) -> None:
        """Anchor at 100 % by hand (counts as "full" for the next capacity measurement)."""
        self._accrue(dt_util.utcnow())
        self.remaining_ah = self.capacity_ah
        self.anchor = ANCHOR_FULL
        self.last_full = dt_util.utcnow()
        self._reset_cycle()
        self._changed()

    # ----- inputs ---------------------------------------------------------

    @callback
    def _async_tick(self, now: datetime) -> None:
        self._accrue(dt_util.utcnow())
        self._changed()

    @callback
    def _async_on_change(self, event: Event[EventStateChangedData]) -> None:
        now = dt_util.utcnow()
        self._accrue(now)  # everything up to now used the old values
        entity_id = event.data["entity_id"]
        new = event.data["new_state"]
        state = new.state if new else None

        if entity_id == self.current_entity:
            self._on_current(_number(state), now)
        elif entity_id == self.voltage_entity:
            self._on_voltage(_number(state))
        elif entity_id == self.full_entity:
            if state == STATE_ON and not self.holding:
                self._full_event("full sensor turned on")
            elif state == STATE_OFF:
                self.holding = False
            # unavailable: keep holding, the sensor shares the flaky bridge with the current
        elif entity_id == self.grid_entity and state == STATE_ON:
            self._cancel("shutdown")
        self._check_voltage_rules()
        self._changed()

    @callback
    def _on_current(self, value: float | None, now: datetime) -> None:
        if value is not None:
            self.current = self._last_current = value
            self._gap_until = None
            self._cancel("shutdown")
            if self.off:
                _LOGGER.info("Battery telemetry is back after the shutdown")
                self.off = False
            return
        if self.current is None:
            return
        # The source just went away: bridge the gap, and maybe the inverter shut down.
        self.current = None
        self._gap_until = now + self.max_gap
        if not self.off and self._grid_absent() and self._was_low():
            self._start("shutdown", self.shutdown_delay, self._async_shutdown_expired)

    @callback
    def _on_voltage(self, value: float | None) -> None:
        self.voltage = value
        if value is not None:
            self._last_voltage = value

    def _grid_absent(self) -> bool:
        if self.grid_entity:
            grid = self._state(self.grid_entity)
            if grid in (STATE_ON, STATE_OFF):
                return grid == STATE_OFF
        return self._last_current is not None and self._last_current < -IDLE_CURRENT

    def _was_low(self) -> bool:
        low_v = self._last_voltage is not None and self._last_voltage <= self.low_voltage_hint
        return low_v or self.soc <= self.low_soc_hint

    @callback
    def _async_shutdown_expired(self, _now: datetime) -> None:
        self._timers.pop("shutdown", None)
        self._accrue(dt_util.utcnow())
        if self.current is None and self._state(self.grid_entity) != STATE_ON:
            self.off = True
            self._empty_event("inverter shut down (telemetry gone while low, no grid)")
            self._changed()

    @callback
    def _check_voltage_rules(self) -> None:
        v, i = self.voltage, self.current
        empty = (
            v is not None
            and v <= self.empty_voltage
            and (i is None or i < 0)
            and not self.off
            and not (self.anchor == ANCHOR_EMPTY and self.remaining_ah == 0)
        )
        if not empty:
            self._cancel("empty")
        elif "empty" not in self._timers:
            self._start("empty", self.empty_delay, self._async_empty_expired)

        full = (
            not self.full_entity
            and v is not None
            and i is not None
            and v >= self.full_voltage
            and abs(i) <= self.tail_current
        )
        if not full:
            self._cancel("full")
        elif "full" not in self._timers:
            self._start("full", self.full_delay, self._async_full_expired)

    @callback
    def _async_empty_expired(self, _now: datetime) -> None:
        self._timers.pop("empty", None)
        self._accrue(dt_util.utcnow())
        self._empty_event(f"voltage <= {self.empty_voltage} V for {self.empty_delay:g} s")
        self._changed()

    @callback
    def _async_full_expired(self, _now: datetime) -> None:
        self._timers.pop("full", None)
        self._accrue(dt_util.utcnow())
        self._full_event(f"voltage >= {self.full_voltage} V at tail current for {self.full_delay:g} s")
        self._changed()

    # ----- counting -------------------------------------------------------

    @callback
    def _accrue(self, now: datetime) -> None:
        start, self._last_ts = self._last_ts, now
        if self.off or self.holding:
            return
        if self.current is not None:
            current, end = self.current, now
        elif self._last_current is not None and self._gap_until is not None:
            current, end = self._last_current, min(now, self._gap_until)
        else:
            return
        seconds = (end - start).total_seconds()
        if seconds <= 0 or current == 0:
            return
        ah = current * seconds / 3600
        kwh = abs(ah) * self._volts() / 1000
        if ah > 0:
            self.cycle_in_ah += ah
            self.energy_in_kwh += kwh
            self._add(ah * self.efficiency)
        else:
            self.cycle_out_ah -= ah
            self.energy_out_kwh += kwh
            self._add(ah)

    def _add(self, delta_ah: float) -> None:
        value = self.remaining_ah + delta_ah
        clamped = min(max(value, 0.0), self.capacity_ah)
        self.drift_ah += value - clamped
        self.remaining_ah = clamped

    def _reset_cycle(self) -> None:
        self.cycle_in_ah = self.cycle_out_ah = self.drift_ah = 0.0

    @callback
    def _full_event(self, reason: str) -> None:
        if self.learn_efficiency and self.cycle_in_ah >= LEARN_MIN_CYCLE * self.capacity_ah:
            sample = None
            if self.anchor == ANCHOR_FULL and self.cycle_out_ah >= LEARN_MIN_CYCLE * self.capacity_ah:
                sample = self.cycle_out_ah / self.cycle_in_ah  # back where it started
            elif self.anchor == ANCHOR_EMPTY:
                sample = self.capacity_ah / self.cycle_in_ah
            if sample is not None:
                self.efficiency = self._learn("charge efficiency", self.efficiency, sample, EFFICIENCY_RANGE)
        _LOGGER.info("Battery full (%s); drift %.1f Ah", reason, self.drift_ah)
        self.remaining_ah = self.capacity_ah
        self.anchor = ANCHOR_FULL
        self.last_full = dt_util.utcnow()
        self.holding = bool(self.full_entity)
        self.off = False
        self._reset_cycle()
        self.hass.bus.async_fire(EVENT_FULL, {"entry_id": self.entry_id, "reason": reason})

    @callback
    def _empty_event(self, reason: str) -> None:
        if self.learn_capacity and self.anchor == ANCHOR_FULL:
            sample = self.cycle_out_ah - self.cycle_in_ah * self.efficiency
            low, high = CAPACITY_RANGE
            self.capacity_ah = self._learn(
                "capacity", self.capacity_ah, sample, (low * self.nominal_ah, high * self.nominal_ah)
            )
        _LOGGER.info("Battery empty (%s); drift %.1f Ah", reason, self.drift_ah)
        self.remaining_ah = 0.0
        self.anchor = ANCHOR_EMPTY
        self.last_empty = dt_util.utcnow()
        self._reset_cycle()
        self.hass.bus.async_fire(EVENT_EMPTY, {"entry_id": self.entry_id, "reason": reason})

    @staticmethod
    def _learn(name: str, old: float, sample: float, bounds: tuple[float, float]) -> float:
        low, high = bounds
        if not low <= sample <= high:
            _LOGGER.warning("Ignoring implausible %s sample %.3f (allowed %.3f-%.3f)", name, sample, low, high)
            return old
        new = old + LEARN_ALPHA * (sample - old)
        _LOGGER.info("Learned %s: sample %.3f, %.3f -> %.3f", name, sample, old, new)
        return new

    # ----- helpers --------------------------------------------------------

    def _state(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    def _start(self, name: str, delay: float, action: Callable[[datetime], None]) -> None:
        self._timers[name] = async_call_later(self.hass, delay, action)

    def _cancel(self, name: str) -> None:
        if (cancel := self._timers.pop(name, None)) is not None:
            cancel()

    @callback
    def _changed(self) -> None:
        self._store.async_delay_save(self._data, 10)
        for listener in list(self._listeners):
            listener()
