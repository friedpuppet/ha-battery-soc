# battery-soc — Home Assistant integration

Subproject of `homeassistant` (see `../AGENTS.md`). This is the HA custom integration
**`battery_soc`** ("Battery SoC"): the state of charge of the inverter battery, counted from its current
and re-anchored at full/empty, with capacity/efficiency learning. Behaviour is in `README.md`.
Implementation plan: `~/.claude/plans/proud-wiggling-shamir.md`.

It replaces the hand-made UI helpers from February 2026, where `sensor.batareia_vidsotok_zariadu` =
the never-reset Riemann sum `sensor.batareia_integrovanii_strum` / 200 × 100 and had drifted to −3735 %.

## Why it works the way it does (live data, outage 2026-10-07 06:01–09:06 UTC)

- `sensor.inverter_battery_charge_current` is signed: +48 A charging, −3…−23 A discharging. That outage took
  35.0 Ah out; recharging took 40.6 Ah in.
- `binary_sensor.inverter_float_charging` goes off when the outage starts and on when the battery is full
  (~50 min after the grid returns). This flag is the full anchor.
- On float, the current sensor reads −0.4…−3.3 A. Counting that would add a phantom discharge of ~1 kWh/day,
  so the current is held at 0 while float is on.
- The battery is LiFePO4 24 V (8S), 200 Ah. Inverter settings: bulk 28.4 V, float 27.2 V, cut-off 23.2 V.
  Under load the voltage is flat (26.2–26.5 V).
- **The inverter runs from its own battery and shuts off at cut-off, taking its ESP with it. HA and the router
  are on a small separate UPS and keep running.** So "empty" is detected mostly as the telemetry
  disappearing while there is no grid and the battery was already low (see README).

## Status

- Code and tests are done (`uv run pytest`: 21 green against HA 2026.8.3). Not yet released or installed.
