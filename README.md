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
- **Load power** (optional sensor, W): what the load draws from the inverter output, e.g. a meter
  on the inverter's AC output. Used while the battery telemetry is gone during an outage.
- **Battery counters** and **boot snapshot** (optional text sensors, JSON): totals kept by the
  inverter's own ESP. See *Counter mode*.
- **Nominal capacity** (Ah) and **nominal voltage**.

## How it counts

- The current is integrated every 10 s and on every change. Charging current is multiplied by the
  charge efficiency.
- **Dropouts**: while the current sensor is unavailable, its last value is used for at most
  *max gap* seconds (default 300). After that, during an outage (grid `off`) the discharge is
  counted from the load power sensor: load W × *load ratio* / last battery voltage. Status stays
  `discharging` with the attribute `estimated: true`. Without a load sensor, or with the grid
  present, nothing is counted.
- **Float**: while the full sensor is on, the current is taken as 0. Chargers in float hold the
  voltage, and the shunt mostly shows its own offset, which would otherwise look like a slow
  discharge. If the full sensor drops to `unavailable`, the hold continues; it ends when the
  full sensor turns `off` or when the grid goes `off` (there is no float without the grid).
- **Current offset**: what the current sensor reads on float is taken as its zero offset and
  subtracted from every reading outside float.
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
  a discharge), the battery is low (last voltage ≤ *low voltage* or SoC ≤ *low SoC*), the load
  sensor (if configured) shows no load (unavailable or under 10 W), and the current sensor has
  been unavailable for at least *shutdown delay* (default 180 s). This is checked every 10 s, so a
  long dropout that was counted from the load still ends here once the battery runs low. While the
  inverter is off, nothing is counted and Status is `off`. Once the telemetry is back, counting
  continues from 0 %.
- **Low voltage**: voltage ≤ *empty voltage* while discharging for *empty delay*.

## Counter mode

When the counters entity is set, the battery is not counted from the current sensor. The device
that reads the inverter (here an ESPHome ESP8266, config in the author's `esp-inverter`) integrates
the current itself into monotonic totals that survive its reboots:

```
{"n": 12, "ai": …, "ao": …, "si": …, "so": …, "fa": …, "fs": …, "wi": …, "wo": …}
```

`n` is the boot number. `ai`/`ao` are Ah charged/discharged and `si`/`so` the seconds of each, all
off float. `fa`/`fs` are raw Ah and seconds on float. `wi`/`wo` are Wh. The boot snapshot has the
same fields as they were at boot, plus `pon: 1` for a power-on boot.

- The tracker applies the differences from the totals it last saw (persisted). Whatever happened
  while Home Assistant was down or could not see the ESP is caught up on the next update.
- The current offset is subtracted using the seconds (`offset × si` / `so`) and learned from
  `fa`/`fs`.
- **Empty**: a power-on boot of the ESP while the battery was low (last voltage ≤ *low voltage* or
  SoC ≤ *low SoC*). The ESP is powered by the inverter, so a power-on means the inverter had been
  off. Telemetry disappearing alone never means empty in this mode, and there is no load-power
  fallback. The low-voltage rule and the full sensor still apply.
- Totals that go back (the ESP restored an older copy after a crash or a power loss) are taken as
  the new starting point; the lost part is not counted.
- Power and Status still come from the live current and voltage.

## Learning

- **Capacity**: on *empty* after *full*, Ah out − (Ah in × efficiency) is the usable capacity.
- **Charge efficiency**: on *full* after *full*, Ah out / Ah in over the cycle; on *full* after
  *empty*, capacity / Ah in.

- **Current offset**: the mean current on float, once per hour of float (or when a float of at
  least 30 min ends); ±5 A at most. Can be turned off in the options.
- **Load ratio** (battery W per load W, covers the inverter's losses): on every grid return, battery
  Ah out / load Ah over the outage, if at least 10 Ah came out while both sensors reported;
  0.8–1.5, starts at 1.0.

All are smoothed (EMA, weight 0.3 per sample). Cycles shorter than 10 % of the capacity are
skipped, and so are implausible results (capacity outside 50–120 % of nominal, efficiency outside
80–100 %). Changing the nominal capacity resets the learned capacity.

## Entities

On the battery's device: **State of charge** (%), **Remaining charge** (Ah), **Power** (W, signed),
**Charge power** / **Discharge power** (W) and **Energy charged** / **Energy discharged** (kWh,
`total_increasing`, ready for the Energy dashboard), **Status** (`charging`, `discharging`,
`idle`, `full`, `off`). Diagnostics: **Capacity**, **State of health**, **Charge efficiency**, **Current offset**. The
learned load ratio is the `load_ratio` attribute of State of charge.
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
