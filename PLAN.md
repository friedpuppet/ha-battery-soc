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

## ⏳ Verification on a real outage

- SoC drops by about `Ah_out / 200` (the 2026-10-07 outage would have been ~17 %).
- `Energy discharged` grows roughly like the Atorch meter (~1 kWh per 3 h).
- At the float edge SoC = 100 % and `Charge efficiency` moves from 95 % toward ~86–90 %.
- Capacity is only learned after a discharge to zero (the inverter switching itself off).

## ⏳ Removing the old helpers (after verification, with the user's go-ahead)

Before any change, back up `.storage/core.config_entries`, `core.entity_registry`, `energy`,
`lovelace.dashboard_nvertor` as `.bak-<timestamp>`.

1. Energy dashboard: battery source → `sensor.batareia_energy_discharged` / `_energy_charged` and
   `_discharge_power` / `_charge_power` via WS `energy/save_prefs`. The old battery history in Energy will not be
   joined to the new one.
2. `lovelace.dashboard_nvertor`: swap references to the new entities via WS `lovelace/config` +
   `lovelace/config/save`.
3. Delete the old config entries via `DELETE /api/config/config_entries/entry/<id>`:
   - SoC chain: `01KJDZD426Z63X7X633QQGCDFE` (Батарея відсоток заряду), `01KJDZ6MK6NRC21Z0JDCBQ9G95`
     (Батарея інтегрований струм), `01KJE2VKCP1B7YF033GSTHP7AJ` (Батарея фактичний струм)
   - Power/energy: `01KHYR62V75P4XG19ZNYGQ5JBX` (Інвертор потужність батареї),
     `01KJE42SEM090E1PHP6GWFMCPD` / `01KJE45CWJW6XY918YKBS5PH01` (Батарея потужність заряду/розряду),
     `01KJF0Y7EZWXNKRYZZBHGXKNMJ` / `01KJF0ZV5G77M6RTGESFNE99W1` (Батарея видана/спожита енергія),
     `01KJYFF35MXCGFB68DC9SNFBXS` (Інвертор мінус батарея)
   - Atorch-based, with "батарея" in the name: `01KH01G2DXX51B0ZQ45JJ4N90J` (Живлення від батареї),
     `01KGTKSW07WBC2HK8RC7P1B292` (Енергія від батареї). These are really the load's consumption during an
     outage, not battery parameters. **Ask the user again before deleting these two.**
4. Before deleting, grep `automations.yaml`, `scripts.yaml`, `.storage/lovelace*` and `custom_components` once
   more. As of 2026-10-07 only `lovelace.dashboard_nvertor` used the old entities.
5. Update docs: this file, `AGENTS.md`, the battery section in `../AGENTS.md`, `../electricity.md`.
