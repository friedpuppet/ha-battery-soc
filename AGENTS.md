# battery-soc — Home Assistant integration

Subproject of `homeassistant`. This is the HA custom integration **`battery_soc`** ("Battery SoC"): the state
of charge of the inverter battery, counted from its current and re-anchored at full/empty, with
capacity/efficiency learning. Behaviour is in `README.md`; the plan and what is still pending are in `PLAN.md`.

## Shared Home Assistant context (read before touching the live instance)

This directory only holds the battery work. Everything about the HA host itself lives one level up. Read it
first, even when the session was started here:

- `../AGENTS.md`: host, SSH (`ssh root@homeassistant`), Supervised install, `ha core check` / `ha core restart`,
  REST/WS API at `https://ha.yells.kyiv.ua/api/` with the token in `~/.config/homeassistant/token` (HA user
  "Claude"), `.bak-<timestamp>` backup convention, the Atorch meter.
- `../electricity.md`: the power setup (inverter, grid sensor `binary_sensor.e_elektrika`, load shedding,
  dashboards).
- `../grid-load-shedding/AGENTS.md`: the sibling integration this one mirrors (layout, release, HACS update via WS).
- `../esp-inverter/AGENTS.md`: the inverter's ESP, the source of `sensor.inverter_battery_*` and
  `binary_sensor.inverter_float_charging` (it drops off Wi-Fi now and then).

Keep battery details here and in `PLAN.md`; the battery section in `../AGENTS.md` stays a short pointer.

It replaces the hand-made UI helpers from February 2026, where `sensor.batareia_vidsotok_zariadu` =
the never-reset Riemann sum `sensor.batareia_integrovanii_strum` / 200 × 100 and had drifted to −3735 %.

## Why it works the way it does (live data, outage 2026-10-07 06:01–09:06 UTC)

- `sensor.inverter_battery_charge_current` is signed: +48 A charging, −3…−23 A discharging. That outage took
  35.0 Ah out; recharging took 40.6 Ah in.
- `binary_sensor.inverter_float_charging` goes off when the outage starts and on when the battery is full
  (~50 min after the grid returns). This flag is the full anchor.
- On float, the current sensor reads −0.4…−3.3 A (mean −1.0…−1.2 A). Counting that would add a phantom discharge
  of ~1 kWh/day, so the current is held at 0 while float is on. The first full→full cycle (2026-10-07 evening)
  gave Ah out / Ah in = 94.5 / 91.4 > 1. Treating the float mean as a shunt offset gives ~0.976, so v0.2.0 learns
  the offset on float and subtracts it everywhere.
- The inverter's ESP can drop off during an outage while the inverter keeps running (night of 2026-10-08,
  02:17–05:48, Atorch showed 170–190 W the whole time). v0.2.0 counts such gaps from the Atorch load power, and
  only treats telemetry loss as a shutdown when the load is dark too.
- The battery is LiFePO4 24 V (8S), 200 Ah. Inverter settings: bulk 28.4 V, float 27.2 V, cut-off 23.2 V.
  Under load the voltage is flat (26.2–26.5 V).
- **The inverter runs from its own battery and shuts off at cut-off, taking its ESP with it. HA and the router
  are on a small separate UPS and keep running.** So "empty" is detected mostly as the telemetry
  disappearing while there is no grid and the battery was already low (see README).

## Status

- Code and tests are done (`uv run pytest`: 27 green against HA 2026.8.3). CI (hassfest + pytest) green.
  Latest release **v0.2.0** (2026-10-08: load-power fallback, grid loss ends the float hold, learned shunt offset).
  Release via the GitHub API with the PAT below; `target_commitish` must be the full SHA. No `gh` CLI here. Bump `manifest.json` `version` (and `pyproject.toml`) with each release.
- Repo: **[friedpuppet/ha-battery-soc](https://github.com/friedpuppet/ha-battery-soc)** (public, for HACS only;
  same "personal project" rules as `../grid-load-shedding/AGENTS.md`). The token is the **same** fine-grained PAT
  as for grid-load-shedding: `~/.config/github/token-grid-load-shedding` (the user added this repo to it).
  Push: `git -c http.https://github.com/.extraheader="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$(cat ~/.config/github/token-grid-load-shedding)" | base64 -w0)" push`
- **Installed on the live HA (2026-10-07)** via HACS custom repository (HACS repo id `1408776912`), entry
  «Батарея» `01M4B7472BRYY2NS0XTGE77E6A`. Sources: `sensor.inverter_battery_charge_current`,
  `sensor.inverter_battery_voltage`, full = `binary_sensor.inverter_float_charging`, grid =
  `binary_sensor.e_elektrika`, load power = `sensor.atorch_lichilnik_zhivlennia` (since v0.2.0); 200 Ah / 25.6 V;
  started at 100 % on float.
  - Entity ids: `sensor.batareia_{state_of_charge,remaining_charge,capacity,state_of_health,charge_efficiency,
    current_offset,power,charge_power,discharge_power,energy_charged,energy_discharged,status}`, `button.batareia_mark_full`.
  - **Updating**: release, then WS `hacs/repository/download` with `repository: "1408776912"`,
    `version: "vX.Y.Z"`, then `ha core check` + `ha core restart`.
  - **The only battery source since 2026-10-08.** The Energy dashboard, `lovelace.dashboard_nvertor` and
    `lovelace.potochna_energ_ia` use `sensor.batareia_*`. The 11 old helpers are deleted (list in `PLAN.md`; backups
    `.storage/*.bak-20261008-083204`).
