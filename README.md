# Battery SoC

> Personal project, published only so it can be installed through HACS as a custom repository.
> Use it if it's useful to you, but there's no support and no promise of stability.

A Home Assistant integration that tracks the state of charge of an inverter battery (LiFePO4 and
similar, whose voltage is too flat to read the charge from) by counting the battery current, and
re-anchors the count at the two moments it can actually detect: **full** and **empty**.

## Inputs

- **Battery current** (required): signed, positive while charging.
- **Battery voltage** (required): for power/energy and the voltage rules below.
- **Battery full** (optional binary sensor): on when the battery is full, e.g. the inverter's
  *float charging* flag.
- **Grid** (optional binary sensor): on while utility power is present.
- **Nominal capacity** (Ah) and **nominal voltage**.

## How it counts

- The current is integrated every 10 s and on every change. Charging current is multiplied by the
  charge efficiency.
- **Dropouts**: while the current sensor is unavailable, its last value is used for at most
  *max gap* seconds (default 300), then nothing is counted.
- **Float**: while the full sensor is on, the current is taken as 0. Chargers in float hold the
  voltage, and the shunt mostly shows its own offset, which would otherwise look like a slow
  discharge. If the full sensor drops to `unavailable`, the hold continues; only `off` ends it.
- The state of charge is clamped to 0–100 %. Whatever was clipped since the last anchor is in the
  `drift_ah` attribute.

## Anchors

**Full** (→ 100 %):
- the full sensor turns on;
- without a full sensor: voltage ≥ *full voltage* with |current| ≤ *tail current* for *full delay*.

**Empty** (→ 0 %):
- **Inverter shutdown.** An inverter powered from its own battery switches itself off at cut-off,
  and its telemetry disappears with it (Home Assistant itself has to be on a separate UPS to see
  this). Empty when all of these hold: no grid (grid sensor `off`; without one, the last current was
  a discharge), the battery was already low (last voltage ≤ *low voltage* or SoC ≤ *low SoC*),
  and the current sensor has been unavailable for *shutdown delay* (default 180 s). While the
  inverter is off, nothing is counted and Status is `off`. Once the telemetry is back, counting
  continues from 0 %.
- **Low voltage**: voltage ≤ *empty voltage* while discharging for *empty delay*.

## Learning

- **Capacity**: on *empty* after *full*, Ah out − (Ah in × efficiency) is the usable capacity.
- **Charge efficiency**: on *full* after *full*, Ah out / Ah in over the cycle; on *full* after
  *empty*, capacity / Ah in.

Both are smoothed (EMA, weight 0.3 per cycle). Cycles shorter than 10 % of the capacity are
skipped, and so are implausible results (capacity outside 50–120 % of nominal, efficiency outside
80–100 %). Changing the nominal capacity resets the learned capacity.

## Entities

On the battery's device: **State of charge** (%), **Remaining charge** (Ah), **Power** (W, signed),
**Charge power** / **Discharge power** (W) and **Energy charged** / **Energy discharged** (kWh,
`total_increasing`, ready for the Energy dashboard), **Status** (`charging`, `discharging`,
`idle`, `full`, `off`). Diagnostics: **Capacity**, **State of health**, **Charge efficiency**.
Button **Mark full**.

All three counted values (power, energy, SoC) use the same current, with the float hold applied.

## Services and events

- `battery_soc.set_soc` (`soc`: 0–100) sets the charge by hand. This is not an anchor, so nothing
  is learned from the next cycle.
- Events `battery_soc_full` and `battery_soc_empty` (`entry_id`, `reason`).

## Development

```
uv sync
uv run pytest
```
