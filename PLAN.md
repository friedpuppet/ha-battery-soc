# Inverter battery: the `battery_soc` integration

Restored from the plan approved on 2026-10-07. Status markers: ✅ done, ⏳ pending.

## Context

The "battery" used to be 11 hand-made UI helpers (template + integration) from February 2026. The main bug:
`sensor.batareia_vidsotok_zariadu` = `integrated_current / 200 × 100`, and `sensor.batareia_integrovanii_strum`
(a Riemann sum of `batareia_faktichnii_strum`) **never resets**. Errors had piled up since February:
−7471 Ah, −3735 %. Nothing anchored it to full or empty, and nothing clamped it to 0–100 %.

What HA data showed (outage 2026-10-07 06:01–09:06 UTC): see "Why it works the way it does" in `AGENTS.md`.

Decision: an own integration in the style of `grid_load_shedding`. After it is verified, delete **all** the old
battery helpers.

## ✅ Subproject and repository

`battery-soc/`, the same layout as `../grid-load-shedding/`; repo `friedpuppet/ha-battery-soc`; HACS custom
repository. Details in `AGENTS.md`.

## ✅ The integration (v0.1.0)

- **Config flow** (one entry per battery): current sensor (signed, + = charging), voltage sensor, optional
  "full" binary sensor (`binary_sensor.inverter_float_charging`), optional grid binary sensor
  (`binary_sensor.e_elektrika`), nominal capacity 200 Ah, nominal voltage 25.6 V, initial SoC.
- **Options**: empty voltage 24.0 V / 10 s; shutdown detection 180 s with low-voltage hint 25.0 V or low-SoC hint
  20 %; full by voltage 28.2 V with tail current 10 A for 60 s (only without a full sensor); max gap 300 s;
  learn capacity / efficiency.
- **Core (`tracker.py`)**: coulomb counter (left Riemann, every 10 s and on each change); dropouts bridged with the
  last current for up to `max_gap`; charging current × efficiency; hold at 100 % while the full sensor is on.
  - **Full**: full sensor off→on (or the voltage rule) → 100 %. Learns efficiency (Ah out / Ah in for a full→full
    cycle, capacity / Ah in for empty→full); EMA α = 0.3, 0.80–1.00, cycle ≥ 10 % of capacity.
  - **Empty**: (1) **inverter shutdown**: the inverter runs from its own battery and switches off at cut-off
    together with its ESP, while HA and the router stay up on their own small UPS. No grid, battery already low,
    current sensor unavailable for 180 s → 0 %, Status `off`, nothing counted until the telemetry returns.
    (2) Voltage ≤ empty voltage while discharging for 10 s. Learns capacity after a full anchor (EMA, 50–120 %
    of nominal; implausible samples are rejected, not clamped).
  - SoC clamped to 0–100 %; the clipped amount is the `drift_ah` attribute. State persisted with `Store`.
- **Entities**, see `README.md`. Service `battery_soc.set_soc`, button "Mark full", events
  `battery_soc_full` / `battery_soc_empty`.
- **Tests**: 21, all green; CI (hassfest + pytest) green.

## ✅ Deployment

Released v0.1.0, installed via HACS, entry «Батарея» created, running **in parallel** with the old helpers.
Live check done: SoC 100 % on float, Status `full`, power 0; `set_soc 50` → 50 %, "Mark full" → 100 %.

## ✅ Verification on a real outage (2026-10-07 18:23–21:17)

SoC 100 → 53.4 %, back to 100 % on float at 23:12. Two flaws found and fixed in v0.2.0:
- Charge efficiency was not learned: Ah out / Ah in = 94.5 / 91.4 > 1, so the sample was rejected. The float
  current (mean −1.0…−1.2 A) is a shunt offset; v0.2.0 learns it on float and subtracts it everywhere.
- Night of 2026-10-08: the ESP was gone 02:17–05:48 during an outage, the load ran on (Atorch 170–190 W), and
  ~28 Ah went uncounted. The float hold also survived the unavailable float flag. v0.2.0: grid loss ends the hold,
  the discharge is counted from `sensor.atorch_lichilnik_zhivlennia` × learned load ratio after `max_gap`, and
  shutdown detection runs every tick and needs the load to be dark.

## ✅ v0.2.0 (2026-10-08)

Released, installed via HACS, option load power = `sensor.atorch_lichilnik_zhivlennia`. The SoC after that night
is overstated by ~14 %; the next float anchor fixes it (no manual correction).

## ✅ Old helpers removed (2026-10-08)

Backups `.storage/{core.config_entries,core.entity_registry,energy,lovelace.dashboard_nvertor,lovelace.potochna_energ_ia}.bak-20261008-083204`.
- Energy battery source → `sensor.batareia_energy_discharged` / `_energy_charged`, power `_discharge_power` /
  `_charge_power` (net-power entity `sensor.energy_battery_batareia_discharge_power_batareia_charge_power_net_power`
  is made by HA). The old battery history in Energy is not joined to the new one.
- `lovelace.dashboard_nvertor`: tiles → `sensor.batareia_power`, `_remaining_charge`, `_state_of_charge`; the
  «Інвертор мінус батарея» tile is removed.
- `lovelace.potochna_energ_ia`: the «Енергія від батареї» statistics graph → `sensor.batareia_energy_discharged`.
- All 11 old config entries deleted (the user chose to delete the two Atorch-based ones and «Інвертор мінус
  батарея» too): `01KJDZD426Z63X7X633QQGCDFE`, `01KJDZ6MK6NRC21Z0JDCBQ9G95`, `01KJE2VKCP1B7YF033GSTHP7AJ`,
  `01KHYR62V75P4XG19ZNYGQ5JBX`, `01KJE42SEM090E1PHP6GWFMCPD`, `01KJE45CWJW6XY918YKBS5PH01`,
  `01KJF0Y7EZWXNKRYZZBHGXKNMJ`, `01KJF0ZV5G77M6RTGESFNE99W1`, `01KJYFF35MXCGFB68DC9SNFBXS`,
  `01KH01G2DXX51B0ZQ45JJ4N90J`, `01KGTKSW07WBC2HK8RC7P1B292`. The orphaned old Energy net-power entity was removed
  from the registry.

## ⏳ Still to confirm on live data

- After the next float: `Current offset` ≈ −1 A.
- Next full→full cycle: `Charge efficiency` moves off 95 % (expected ~0.97–0.99) instead of being rejected.
- Next outage: `load_ratio` (State of charge attribute) moves off 1.0.
- An ESP dropout during an outage: Status `discharging` with `estimated: true`, SoC keeps falling.
- Capacity: only after a discharge to zero (the inverter switching itself off).
