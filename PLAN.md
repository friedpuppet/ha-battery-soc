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
- Night of 2026-10-08: all telemetry was gone 02:17–05:47, and nothing was counted. v0.2.0: grid loss ends the
  hold, the discharge is counted from `sensor.atorch_lichilnik_zhivlennia` × learned load ratio after `max_gap`,
  and shutdown detection runs every tick and needs the load to be dark.
  **Correction (later investigation):** the cause was the HA box losing Ethernet, not the ESP. The grid was on
  until ~03:20:45, so only ~03:20–05:47 ran from the battery, ~12–25 Ah. Atorch was unavailable too, so even
  v0.2.0 would not have counted that night. The fallback still helps when only the ESP drops off.

## ✅ v0.2.0 (2026-10-08)

Released, installed via HACS, option load power = `sensor.atorch_lichilnik_zhivlennia`. The SoC after that night
is overstated by ~6–12 %; the next float anchor fixes it (no manual correction).

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
- Missed by the pre-delete grep (it skipped `core.config_entries`): template «Споживання інвертором»
  `01KJJGTD2XB8GWWP1AHYBDC911` (`sensor.spozhivannia_invertorom`) used `sensor.batareia_potuzhnist_zariadu`.
  It now uses `sensor.batareia_charge_power`. Next time also grep the options of other config entries.

## ⏳ Still to confirm on live data

- ✅ After the next float: `Current offset` ≈ −1 A (−1.03 A on 2026-10-09).
- ✅ Next full→full cycle: `Charge efficiency` moved off 95 %: 96.0 % on 2026-10-08 23:07 UTC (cycle 11:43→23:07,
  discharged to 33 %; sample ≈ 0.98, EMA α 0.3). Earlier samples 1.034 and 0.662 were rejected as implausible.
- Next outage: `load_ratio` (State of charge attribute) moves off 1.0.
- An ESP dropout during an outage: Status `discharging` with `estimated: true`, SoC keeps falling.
- Capacity: only after a discharge to zero (the inverter switching itself off).

## Hybrid: counters on the inverter's ESP (2026-10-08)

Why: everything HA doesn't see is lost when it integrates the current itself (HA down, LAN lost like the night of
2026-10-08, ESP Wi-Fi drop). Also, losing the LAN while the battery is low could fake "empty".

- ✅ ESP firmware with the totals, flashed by OTA 2026-10-08 10:38 UTC (details: `../esp-inverter/AGENTS.md`).
  Soft reboot via `button.inverter_restart` kept every total (boot 2, `pon` 0).
- ✅ `sensor.inverter_battery_counters` / `_boot` excluded from the recorder (`configuration.yaml`, backup `.bak-<ts>`).
- ✅ v0.3.0 released and installed. Counter mode is implemented and tested, but the live entry **still uses the current
  sensor**.
- ⏳ Compare for about a day. Δ(ai − ao) from the counters should match `battery_soc`'s own count
  (`cycle_in_ah` / `cycle_out_ah`, Energy charged/discharged) within ~2 %.
- ⏳ Then set the options of «Батарея»: counters = `sensor.inverter_battery_counters`, boot =
  `sensor.inverter_battery_boot`. The first sight only sets the baseline, so the SoC does not jump.
- ⏳ Cold start check: the user briefly cuts the D1 mini's power. Expect `pon` 1 and `r` 0 or 6, and no empty anchor
  at a high SoC.
- ⏳ Later: a real discharge to cut-off. Empty must appear only after the ESP comes back with `pon` 1.

## Investigation: the current offset (2026-10-09)

Question: is the −1 A on float a sensor offset, or does the inverter really draw ~1 A from the battery while the
grid is on (and if so, does it hold during charge/discharge, where v0.2.0 also subtracts it)? Nothing was changed
on HA or in the code; this is data only.

### Findings

- **Literature.** Cheap high-frequency all-in-one inverters (Growatt SPF, PowMr) have a battery↔HV-bus LLC
  converter; forum reports say some of them draw ~25 W from the battery even on grid, others (PowMr in SBU) cover
  self-consumption from the grid. Not starting without a battery is normal for the class (CPU/aux supply start
  from the battery). Nothing model-specific found for this unit.
- **LLC state on float** (`sensor.inverter_llc_topology`, history 2026-10-06…09): it flips `charge`/`discharge`
  150–670 times per float period, ~75–85 % of the time `discharge`, `charge` runs ~10 s (one sample). In
  `charge` the sensor reads ~0…+0.2 A, in `discharge` −0.5…−1.3 A (median). Turned out to be a regulation-mode
  flag, not the energy direction (see the clamp below).
- **Float current vs load:** r = 0.06 over 486 five-minute bins (load 0–2 kW). The load goes through bypass.
- **Battery voltage on float** stays at 27.175 V for 12–13 h (no trend). A real −1.1…−1.3 A would remove 14–16 Ah
  (7–8 %), which LiFePO4 near full would show as ~0.3 V lower. So the net current on float is ~0.
- **Three meters** (Zigbee meter before the inverter, inverter `load_power`, Atorch after):
  - grid mode: Zigbee = 1.02 × Atorch + 34 W (r 0.99). The two independent AC meters agree, so Atorch is good to a
    few %; inverter `load_power` reads 4–8 % below Atorch. **~34 W self-consumption comes from the grid.**
  - outage: battery power (raw current × V) = 1.08 × Atorch − 39 W. The negative intercept looked like the raw
    discharge current being low already, but it is an extrapolation; the clamp below outweighs it.
  - bulk charge (~48 A): battery power / (Zigbee − Atorch − 34 W) = 0.86, plausible for the charger.
- **Clamp meter** (ANENG ST212, DC A, REL zeroed ~0.5 m away, on the battery-minus → inverter-minus cable;
  the user provided two phone videos of the meter's display on float: 26 s from 07:47:28 UTC and 241 s from
  08:54:28 UTC; the phone's file name gives the start time, phone and HA clocks are both NTP-synced). Read once
  per second and matched to the 24 HA samples of the second video:
  - the clamp and the inverter sensor move together (r ≈ 0.8 with the clamp 1–3 s before the HA stamp), so the
    sign matches: clamp + = charging in that orientation;
  - **clamp − inverter = +0.98 A on average**; the inverter sensor mean was −0.51 A, the clamp +0.27…+0.40 A;
  - so near zero the inverter's sensor reads ~1 A low (matches the learned −1.03 A), and the real battery current on
    float is ~0 to slightly charging (≈ 7–11 W, within the clamp's zero accuracy of ±0.2–0.3 A), with slow
    swings of ±0.5–1 A (±15–25 W);
  - consistent with the user's hypothesis: the electronics run from rectified grid power (directly at the 27 V
    node or from the HV bus — the battery cable can't tell which); the battery only sees fluctuations.
  - **Artifact:** a ~1 A dip lasting ~2 s starts ~0.4 s after every HA update (every 10 s, smaller one 5 s later;
    the ESP polls every 5 s). Seen in both videos. Either Wi-Fi/RF from the ESP disturbing the clamp, or the
    inverter reacting to the poll. Not the inverter's own regulation cycle.

### Current conclusion

The −1 A is an additive offset of the inverter's current sensor, at least in the −1.3…0 A range. v0.2.0's model
(learn the offset on float, subtract it everywhere) is supported there. Whether it stays ~1 A at −10…−25 A and
+48 A, and whether there is also a scale error, is not known yet.

### Next steps

1. ⏳ Clamp on the same cable, same orientation, during an outage (battery mode, −10…−25 A), 3–5 min, with 2–3 load
   steps (kettle / microwave on-off) → offset and scale of the discharge reading.
2. ⏳ The same during the bulk charge after the grid returns (~48 A, ideally into the taper and the first minute of
   float).
3. ⏳ In each video, ~30 s with the clamp reversed on the cable: the reading must flip sign with the same magnitude;
   half the difference of |readings| is the clamp's own zero error.
4. ⏳ Optional: the source of the 5/10 s dips — move the clamp and phone away from the ESP, or briefly power the ESP
   off (only with the user's go-ahead: HA loses inverter telemetry meanwhile).
5. ⏳ Analysis per video: read the display once per second, align with HA by the file-name time, fit
   clamp = a + b × sensor per mode. Then decide in `battery_soc`: keep the single additive offset, or add a scale
   factor (charge and discharge may differ), and re-check the learned efficiency and `load_ratio` (0.993 looks
   low: with inverter losses the battery should give more than the load takes).
6. ⏳ Optional: energy balance over a full→full cycle (Zigbee energy in − Atorch energy out = all losses), as a check
   that doesn't depend on the battery current sensor at all.

### Clamp session 2 (2026-10-10): discharge, microwave, bulk charge

Five phone videos from the user (same clamp, REL zeroed away from cables): discharge on the minus cable (121 s from
08:05:04 UTC) and on the plus cable (61 s from 08:07:30), plus cable with a microwave on low power (60 s from
08:10:03; the magnetron cycles ~3 s on / ~27 s off), bulk charge on the plus cable (121 s from 19:05:04) and on the
minus cable (35 s from 19:07:19). The clamp flips sign between the two cables, as it should. Error of the inverter
sensor e = true − sensor, with the clamp's own zero z separated from the plus/minus pair:

| Mode | Sensor | Clamp (as charge current) | e | z |
|---|---|---|---|---|
| float (2026-10-09) | −0.5 A | +0.3…+0.4 A | ≈ +0.6…+1.0 A | (assumed ~0.4) |
| discharge, 8–14 A | −3.6…−9.8 A | −7.8…−13.5 A | **≈ −3.5…−4.1 A** | +0.37 |
| microwave pulse | −65 A | −69 A | ≈ −3.7 A | — |
| bulk charge | +48.3 A | +51.9 (minus) / +54.2 (plus) | **≈ +3.6…+5.9 A** | ? (see below) |

- Nothing but the inverter is connected to the battery (user, 2026-10-10), so the plus and minus cables carry the
  same current and the plus/minus difference is the clamp's error (≈ 2.4 A in the charge session). REL was not reset
  between the two cables, so the zero may have moved between the records (core remanence after 50+ A, the
  neighbouring cable's field, orientation in the Earth's field); then averaging does not cancel it. Charge error
  stays a range: +3.6 A (minus record) … +5.9 A (plus record, taken right after zeroing — the likelier one).
- Steps match: microwave on = +55.7 A by the clamp, +55.6 A by the sensor; a 92 W load step = +3.6 / +4.3 A. So the
  sensor's scale is right (slope ≈ 1) and the error is a mode-dependent zero: it shows too little discharge and too
  little charge (|I| low by ~4 A in both power-flow directions), and ~1 A of phantom discharge on float.
- Independent checks without the clamp:
  - at 08:05, before the load step, the raw sensor gave 95 W from the battery for 145–165 W of AC output — impossible;
  - absorb phase (28.4 V held for ~30 min before float) the sensor reads −1.6…−3 A, though a battery held at
    28.4 V can only be taking current;
  - bulk charge, energy: raw battery energy / (Zigbee − Atorch − 34 W) = 0.82–0.87; with +4.75 A 0.92–0.96.
- **Unresolved conflict:** with e = −4 A on discharge and +4.75 A on charge, full→full cycles give out/in = 1.06–1.11
  (impossible) for the long outages (2026-10-07 18:23–21:17, 2026-10-08 12:26–19:59; loads ~450 W, ~18 A), but
  1.00 for the short low-load cycle of 2026-10-09/10. Cycle balance plus the AC energy balance of those long
  outages fit e ≈ −1.5…−2.2 A on discharge. So the discharge error may depend on load, temperature or time. The
  clamp only saw low loads, ~10 min after warm-up.
- Self-consumption: grid mode ~34 W from the grid (battery ≈ 0); battery mode, from the clamp: battery power ≈
  1.07 × inverter `load_power` + 46 W (idle ~45 W plus ~7 %); charger efficiency ≈ 0.92–0.95 with the corrected current.
  The inverter's `load_power` reads 4–8 % below Atorch; Atorch and the Zigbee meter agree within ~2 %.

### Clamp session 3 (2026-10-10 19:56–19:59 UTC): clamp calibration in bulk charge

Two videos: REL in the air, red (plus) cable away from the black one, back to the air without REL, REL again, black
(minus) cable twice. The sensor read 48.0–48.8 A throughout.

- Clamp without REL in the air: −1.5…−1.8 A (so REL is essential). After removing it from 50 A: +0.2 A at most,
  back to ±0.05 within seconds. Remanence/zero drift is negligible.
- Plus 50.1 A; minus 51.5 and 51.45 A (repeatable). The same current in both, so ~1.4 A (2.7 %) is the clamp's own
  position/geometry error. The earlier plus reading of 54.2 A was taken next to the minus cable: the neighbouring
  field added ~3 A there. Clamp scale is not checked against a reference (could be done on AC against Atorch).
- **Charge error: e ≈ +2.5…+3.2 A** (true ≈ 50.8–51.5 A for a 48.3 A reading), not +4.75.

### Revised picture (2026-10-10)

- Implied discharge error per 30 min of each outage, taking battery power = 1.07 × `load_power` + 46 W (clamp fit of
  the morning): **−1.1…−1.5 A in every long outage** (07.10, 08.10, 10.10 evening; 300–1000 W), but −3.4…−5.8 A in
  the low-load morning outage of 10.10 (150–300 W), shrinking as the inverter cooled (NTC2 48 → 42 °C).
- Full→full balance with charge +3 A and discharge −1.2 A: out/in = 0.99 (08.10), 1.00–1.01 (07.10). Consistent.
- On float the sensor's reading moves with the inverter's temperature (+0.33 A/°C against NTC2, r 0.9, but only
  over 48–50 °C). So the zero error drifts with temperature. The NTCs are not at the current sensor, so this is a
  proxy only.
- Model now: float e ≈ +0.5…+1.0 A (true ≈ 0); charging e ≈ +3 A; discharging e ≈ −1.2 A typically, up to −4…−6 A
  at low load with a warm inverter. The scale is right (slope ≈ 1).
- What v0.2/0.3 do (subtract −1.03 A everywhere) under-counts the discharge by ~2.2 A, ~12 % at a typical 18 A,
  and the charge by ~2 A, ~4 %.
- Self-consumption: grid mode ~34 W from the grid; battery mode ~45 W + 5–7 %; charger efficiency ≈ 0.88–0.90 with
  the corrected charge current.

### Clamp scale check on AC (2026-10-10 20:13:27 UTC, 42 s)

The user clamped the live wire before the Zigbee meter (AC, true-RMS), during the absorb tail (grid input ~1.1–1.3 kW,
current falling). Clamp mean 6.01 A (5.46–6.64), Zigbee meter 5.77 A over the same seconds (5.6–5.7 A for most of
it), inverter `grid_current` 5.59 A. The clamp follows the meter's changes (e.g. the bump at +26 s). **The clamp reads
~4–5 % high** against the Zigbee meter (which agrees with Atorch within ~2 %). The ST212 accuracy spec was not found;
±2–3 % of reading plus digits is typical for the class, so this is at the edge of spec.

If the same scale error applies to DC (same Hall sensor, but REL/offset handling differs), the corrections shrink:
charge e ≈ +0.5…+1 A instead of +3 A, morning discharge ≈ −3 A, and the long-outage implied discharge error ≈ −0.5 A
(cycle balance would then also need only ~−0.1…−0.5 A). Against that: in the 28.4 V absorb phase the sensor reads
−1.6…−3 A, which needs a charge error of at least ~2 A. Not settled: one short check at 6 A with a changing current.
Better: a steady 10–20 A AC load (kettle(s)) for a minute, comparing clamp, Zigbee meter and Atorch.

### Clamp position check on AC (2026-10-11 10:19:59–10:22:24 UTC, 144 s, steady ~18 A)

The user clamped a live wire in the distribution board under a steady resistive load (Zigbee P ≈ 3.88 kW at
217 V, PF ≈ 1), on float. Moving the wire inside the jaws showed that the position matters.

References:
- Zigbee meter: 17.85–18.10 A (mean ≈ 17.95), consistent with its own P/V.
- Atorch after the inverter: 17.45–17.59 A. Plus ~0.2 A of inverter self-consumption, that gives ≈ 17.7 A at the input.
- inverter `grid_current`: 17.1–17.45 A (it reads ~4 % low again).

| Wire position (from the video) | Clamp, A | vs Zigbee |
|---|---|---|
| against the jaw tips (where the halves meet) | 18.03–18.25 (≈ 18.13) | +0.5…+1.7 % |
| middle of the window | 17.2–17.6 | −2…−4 % |
| against the body (bottom of the window) | 16.40–16.62 (≈ 16.5) | −8 % |

The total spread is 16.40–18.25 A, i.e. 11 % of the reading. This is an open-loop Hall clamp. Ampère's law makes
the reading position-independent only for an ideal closed core with high μ. Here the core has the Hall gap plus the
gap where the jaws meet. Near the gaps the sensor also picks up the wire's own field directly (∝ 1/r) and the flux
leaks. So a conductor near the gap reads high and one far from it reads low. The highest readings at the tips suggest
the Hall element sits at the tip junction.

Consequences:
- The jaw-tip position is the most accurate here (≈ +1 % vs Zigbee, ≈ +2 % vs Atorch-implied). It is also
  reproducible: the wire is pressed into the corner. Use it for all further clamp readings, with a factor of ≈ 0.99.
- Yesterday's +4 % at 6 A: the position was not recorded. Also, during charging the input current is not sinusoidal;
  a true-RMS clamp counts the harmonics, which the meter may not.
- All earlier DC clamp numbers carry this position uncertainty: up to ±5 %, i.e. ±2.5 A at 50 A and ±0.5 A at
  10 A. That is as large as the charge-mode error being measured, so the charge e ≈ +2.5…+3.2 A is not settled.
  A thick battery cable cannot sit right at the tips either, so expect ±1–2 % even when pressed there.
- Next DC clamp readings: the cable pressed against the jaw tips, the same orientation, REL in the air in the same
  pose. Note the position in the video.

### Clamp session 4 (2026-10-12 16:36:21–16:37:58 UTC): battery minus cable, outage, ~470 W

Setup: outage, steady load (Atorch 456–479 W, inverter `load_power` ~445 W), battery 26.43 V, NTC2 35–36 °C. REL
was zeroed in the air (it read −0.19 A before).
- 0:15–0:21: the cable was held by hand in some other position. Clamp −19.3…−19.7 A.
- 0:22–1:36: the clamp hung on the cable, pressed against the jaw tips. Clamp −17.60…−17.99 A (mean ≈ −17.70),
  stable.
- Sensor over the same 70 s: −18.6…−19.3 A, with one −20.9 at a load blip. Mean ≈ −19.0 (−18.9 without the blip).

**Energy bound.** At 26.43 V the inverter delivered ~470 W (Atorch), so the battery must supply at least
470 / 26.43 = 17.8 A even at 100 % efficiency. With ~45 W idle plus 5–7 % losses, expect ≈ 20–21 A.
- The jaw-tip clamp reading (17.7 A) is physically impossible here. On the thick battery cable the tip position reads
  low by at least ~1 % and probably ~15 %.
- The hand-held position (19.6 A) and the sensor (19.0 A) are both possible. They mean ~518 W and ~502 W from the
  battery, i.e. an inverter efficiency of 0.91–0.94 including idle.

Conclusion: the clamp's position error on the thick DC cable is ≈ ±10 %, and the AC check on a thin wire does not
carry over. The clamp can no longer resolve a 1–2 A sensor error. Only the energy bound against Atorch is solid. It
says the sensor does not over-read discharge by more than ~1.2 A at 470 W. It is consistent with the sensor reading
low (by ~1–2 A if efficiency is ~0.88–0.9). Better references:
- a DC shunt meter on the battery cable, a fixed position that does not depend on the conductor;
- the BMS current, if the battery's BMS exposes one;
- a full discharge to cut-off (capacity anchor) against the Atorch energy.

### Next steps (updated)

1. ✅ Per-30-min analysis of the outages against load and the NTCs (above).
2. ⏳ Clamp videos during an outage: ~10 min, ~1 h and 2–3 h in, each with load steps (~250 / ~700 / ~1500–2000 W,
   30–40 s each); REL in the air before each, the cable away from the other one and pressed against the jaw
   tips (see the position check). Optional: in bulk ~1–1.5 h in and
   in the 28.4 V absorb phase. Optional clamp scale check: AC mode on a single live wire of a kettle vs Atorch.
3. ⏳ Then change `battery_soc`: drop the single learned offset subtracted everywhere (it moves the discharge the wrong
   way: +1.03 A less discharge where ~2–4 A more is needed). Use per-mode corrections instead: float = hold 0
   (as now); charging = +c_chg; discharging = −c_dis (maybe load-dependent). Fixed options first, from the
   clamp; the cycle balance can tune c_dis afterwards. The ESP counters already keep the seconds of charge and
   discharge (`si`/`so`), so per-mode additive corrections also work in counter mode.
4. ⏳ After the change, re-check efficiency (should come out ~0.97–0.99), `load_ratio` (~1.15–1.25 expected for
   ~450 W) and, after the first discharge to cut-off, capacity.

## Meter-only analysis (2026-10-12): clamp readings discarded

The user decided to drop all clamp measurements (position error ±5–10 % on the battery cable). The reference is the
Zigbee meter before the inverter. Data: a snapshot of the HA recorder, 2026-10-02…10-12. It was resampled to 10 s and
binned at 5–10 min. Modes:
- float = grid on + float flag;
- charge = grid on, no float;
- battery = no grid.

Scripts are in the session scratchpad (not kept).

**Meters against each other (float, 165 h)**
- Zigbee − Atorch = inverter self-consumption on grid, 43.5 W (median 41.8). It does not depend on load
  (+1.3 % of load, which may also be a scale mismatch between the meters).
- Inverter `load_power` = 0.959 · Atorch − 12.7 W: it reads 4–8 % low, worst at low load.
- Inverter `grid_current` cannot be used as power: Ig = 1.10 · Iz − 1.42, with a load PF of ~0.74.

**Float: the sensor reading against temperature**
- True net current is ~0: the voltage sits at 27.17 V for days. The sensor reads −1.05 A on average.
- The reading drifts with NTC2 at **+0.35 A/°C**, r² 0.66: −1.6 A at 46 °C, −0.5 at 49, −0.24 at 50.
- It does not depend on load (r² 0.01) or on time since float started (after the first 30 min, which show a real
  relaxation discharge of −1.9 A).
- The LLC is in "discharge" 88 % of float time (sensor −1.23) and in "charge" 12 % (sensor +0.17). The duty
  correlates with T2 (−0.85), so float cannot separate a pure Hall temperature drift from a direction-dependent error.

**Battery mode: sensor power against Atorch (430 five-minute bins)**
- Raw sensor power minus Atorch output gives the inverter loss. Physically impossible values:
  - −40…−90 W below 300 W of load;
  - only +8…+20 W at 300–700 W.
- The loss also falls by 6.5 W per °C of T2 at a given load, i.e. **~−0.25 A/°C** in the reading. Low load comes with
  a hotter T2 (slower fans), so in this mode load and temperature are confounded.

**Full float→float cycles (7)**
- Raw out/in: 0.69–1.03. The worst cycles are the low-load warm-heatsink outages: 10-10 morning 0.69, 10-07 morning 0.85.
- Fit of per-mode offsets, I_true = I_sensor + u:
  - discharge u_d = −2.5 − 0.30 · (T2 − 40) A (k from −0.20 to −0.35 gives u_d0 −2.43…−2.62);
  - charge u_c = +2.5…+3.0 A.
- Corrected out/in: 0.975–1.03, residuals ≤ 2.5 Ah. The exception is the short odd 10-12 morning cycle with 1.5 h of
  low-current "charge", 0.85. That suggests the charge error scales with current (≈ 5 % of 48 A) rather than being a
  constant.
- Sanity with this model:
  - battery-mode loss ≈ 20–30 W at low load, ~60 W at 600 W, ~90 W at 1 kW;
  - bulk charger efficiency from Zigbee ≈ 0.91 (raw 0.86; the bound η ≤ 0.95 caps u_c at ~4.5 A).

**Conclusions**
- The sensor's scale cannot be told apart from inverter/charger efficiency with these meters. It does not matter for
  SoC % because it is absorbed into the learned capacity.
- The errors are offsets that depend on mode and temperature:
  - float: ≈ −1 A, hold at 0 (correct now);
  - discharge: reads 1–4 A too little, more at low load and a hot heatsink;
  - charge: reads ~2.5–3 A too little at 48 A.
- The current v0.2/0.3 handling (I + 1.03 everywhere) is right in sign for charge but too small. For discharge it goes
  the wrong way and adds 1 A of under-count to the existing 1–4 A.
- Candidate for `battery_soc`: float hold 0; charge I + 2.7 (or × 1.055); discharge I − 2.5 − 0.3 · (T2 − 40),
  with NTC2 as an optional input. Then cycle balance ≈ 1.00 ± 0.03.

**Applied (2026-10-12, v0.4.0).** Options on the live entry: charge correction +2.7 A; discharge correction 2.5 A
+ 0.3 A/°C × (`sensor.inverter_ntc2_temperature` − 40), clamped to 0–10 A; float-offset subtraction off (the float
reading is still tracked). First check at 34 °C: sensor −22.5 A → counted −23.2 A (612 W) vs Atorch 551 W.
To watch:
- the learned efficiency, 0.925 when this was applied; it came from uncorrected cycles, expect ~0.97–1.0;
- `load_ratio`;
- cycle drift at the next float anchors.
