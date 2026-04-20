# GoodWe Poller – Architecture

## Overview

```
GoodWe Inverter(s)          Python Poller              MQTT Broker
  (Modbus TCP)                                         (Mosquitto …)
┌──────────────┐   Modbus   ┌─────────────────────┐   publish  ┌──────────┐
│ Master       │ ─────────▶ │ modbus_reader.py     │           │          │
│ 192.168.1.10 │            │   Block A: 35100-199 │           │  topics  │
└──────────────┘            │   Block B: 36000-049 │           │  under   │
                            └────────┬────────────┘           │ BASE_    │
┌──────────────┐   Modbus            │ raw dicts              │ TOPIC/   │
│ Slave        │ ─────────▶ ┌────────▼────────────┐           │ total/   │
│ 192.168.1.11 │  (optional)│ decoder.py           │           │ decoded/ │
└──────────────┘            │  scale + sanity check│           │          │
                            └────────┬────────────┘           └──────────┘
                                     │ decoded dicts                  ▲
                            ┌────────▼────────────┐                  │
                            │ combiner.py          │                  │
                            │  sum / avg / max     │                  │
                            │  + spike filter      │                  │
                            │  + deadband filter   │                  │
                            │  + monotonic guard   │                  │
                            └────────┬────────────┘                  │
                                     │ combined dict                  │
                            ┌────────▼────────────┐                  │
                            │ mqtt_publisher.py    │ ─────────────────┘
                            │  one topic per key   │
                            └─────────────────────┘
```

## Module Responsibilities

| File | Responsibility |
|------|---------------|
| `config.py` | Load all settings from environment / `.env` |
| `modbus_reader.py` | Open TCP connection, read holding registers, return raw `int` dict |
| `decoder.py` | Scale raw values to physical units, discard implausibly large readings |
| `filter.py` | `SpikeFilter`, `DeadbandFilter`, `MonotonicGuard` – independent, reusable |
| `combiner.py` | Merge master+slave data, run output-side filters, return single dict |
| `mqtt_publisher.py` | Publish each metric as a retained MQTT message |
| `main.py` | Wiring + polling loop + graceful shutdown |

## Register Map

### Block A – Inverter runtime (35100 … 35224)

| Register | Offset | Name | Type | Scale | Unit |
|----------|--------|------|------|-------|------|
| 35103 | +3 | Vpv1 | u16 | ×0.1 | V |
| 35104 | +4 | Ipv1 | u16 | ×0.1 | A |
| 35105–35106 | +5–6 | Ppv1 | u32 | ×1 | W |
| 35107 | +7 | Vpv2 | u16 | ×0.1 | V |
| 35108 | +8 | Ipv2 | u16 | ×0.1 | A |
| 35109–35110 | +9–10 | Ppv2 | u32 | ×1 | W |
| 35111 | +11 | Vpv3 | u16 | ×0.1 | V |
| 35112 | +12 | Ipv3 | u16 | ×0.1 | A |
| 35113–35114 | +13–14 | Ppv3 | u32 | ×1 | W |
| 35115 | +15 | Vpv4 | u16 | ×0.1 | V |
| 35116 | +16 | Ipv4 | u16 | ×0.1 | A |
| 35117–35118 | +17–18 | Ppv4 | u32 | ×1 | W |
| 35121 | +21 | Vgrid R (L1) | u16 | ×0.1 | V |
| 35122 | +22 | Igrid R | u16 | ×0.1 | A |
| 35123 | +23 | Fgrid R | u16 | ×0.01 | Hz |
| 35125 | +25 | Pgrid R | s16 | ×1, + = export | W |
| 35130 | +30 | Pgrid S (L2) | s16 | ×1, + = export | W |
| 35135 | +35 | Pgrid T (L3) | s16 | ×1, + = export | W |
| 35140 | +40 | Active Power Total | s16 | ×1, + = export | W |
| 35172 | +72 | Load Power Total | s16 | ×1 | W |
| 35176 | +76 | Temperature (Radiator) | s16 | ×0.1 | °C |
| 35182–35183 | +82–83 | Battery Power | s32 | ×1, + = discharge | W |
| 35187 | +87 | Work Mode | u16 | – | – |
| 35191–35192 | +91–92 | E_total PV | u32 | ÷10 | kWh |
| 35193–35194 | +93–94 | E_day PV | u32 | ÷10 | kWh |
| 35195–35196 | +95–96 | E_total Export | u32 | ÷10 | kWh |
| 35200–35201 | +100–101 | E_total Import | u32 | ÷10 | kWh |
| 35206–35207 | +106–107 | E_bat Charge Total | u32 | ÷10 | kWh |
| 35208 | +108 | E_bat Charge Today | u16 | ÷10 | kWh |
| 35209–35210 | +109–110 | E_bat Discharge Total | u32 | ÷10 | kWh |
| 35211 | +111 | E_bat Discharge Today | u16 | ÷10 | kWh |

### Block B – ARM external CT meter (36000 … 36049)

| Register | Offset | Name | Type | Scale | Unit |
|----------|--------|------|------|-------|------|
| 36005 | +5 | Meter active power L1 | s16 | ×1 | W |
| 36006 | +6 | Meter active power L2 | s16 | ×1 | W |
| 36007 | +7 | Meter active power L3 | s16 | ×1 | W |
| 36008 | +8 | Meter active power total | s16 | ×1 | W |
| 36009 | +9 | Meter reactive power total | s16 | ×1 | var |
| 36013 | +13 | Meter power factor | s16 | ×0.001 | – |
| 36014 | +14 | Meter frequency | u16 | ×0.01 | Hz |
| 36015–36016 | +15–16 | E_total export (float32) | float32 | ÷1000 | kWh |
| 36017–36018 | +17–18 | E_total import (float32) | float32 | ÷1000 | kWh |
| 36025–36026 | +25–26 | Meter active power total (32-bit) | s32 | ×1 | W |

> **Grid sign convention (Blocks A & B):** GoodWe reports positive = export to grid.
> The integration **negates** all grid-power values so HA convention applies:
> **positive = import from grid, negative = export to grid.**

> **Battery sign convention (Block A pbattery / Block C):** positive = discharging
> (contributing to house load), negative = charging. No negation is applied.

### Block C – BMS / battery pack data (37000 … 37007)

| Register | Offset | Name | Type | Scale | Unit |
|----------|--------|------|------|-------|------|
| 37007 | +7 | Battery SOC | u16 | ×1 | % |

## MQTT Topics

All topics are published under `{BASE_TOPIC}/total/decoded/`.

Examples with `BASE_TOPIC=goodwe_direct`:

```
goodwe_direct/total/decoded/pv_power_w
goodwe_direct/total/decoded/battery_power_w
goodwe_direct/total/decoded/battery_soc_pct
goodwe_direct/total/decoded/grid_power_w
goodwe_direct/total/decoded/load_power_w
goodwe_direct/total/decoded/pv_energy_today_kwh
goodwe_direct/total/decoded/pv_energy_total_kwh
goodwe_direct/total/decoded/grid_export_total_kwh
goodwe_direct/total/decoded/grid_import_total_kwh
goodwe_direct/total/decoded/inverter_temp_c
```

## Filtering Strategy

1. **SpikeFilter** (sliding median, per channel)  
   Rejects samples that deviate more than `max_delta` from the recent median.  
   Previous accepted value is returned instead.

2. **DailyEnergyFilter** (daily energy counters: PV today, battery charge/discharge today)  
   One-sided spike filter for counters that reset to zero at midnight.  
   - Upward spikes (`value >= median + max_up_delta`, with `max_up_delta = 3.0 kWh`)
     are suppressed — catches u16 register-corruption glitches (e.g. a 10 kWh
     jump in a single poll cycle).  
   - A significant *drop* (`value < median − max_up_delta`) is treated as a
     midnight counter reset: history is cleared and the new low value is accepted
     immediately so the filter does not freeze at the previous day's final value.

3. **DeadbandFilter** (grid power)  
   Values with |P| < 30 W are mapped to 0 to suppress jitter at standby.

4. **MonotonicGuard** (cumulative energy counters)  
   Rejects counter decreases for total-energy registers (not daily counters).  
   Applied *after* spike filtering.

5. **Meter-priority overrides (SEMS+ alignment)**  
   When the external CT meter (Block B) is available its values are used as the
   single source of truth for grid energy and power, matching the SEMS+ portal:
   - `grid_export_total_kwh` ← `meter_export_total_kwh` (Block B float32 kWh)
   - `grid_import_total_kwh` ← `meter_import_total_kwh` (Block B float32 kWh)
   - `grid_power_w`          ← `meter_power_total_w`    (Block B s32, W)

   The Block A inverter-side values are still exposed as separate sensors for
   diagnostics but are **not** used for the primary grid energy / power readings.
   When Block B is absent the integration falls back to Block A values.

   In a **master+slave** setup the coordinator first checks whether the master
   has Block B data.  If the master has no external meter but the slave does,
   the slave's Block B values are promoted to the combined grid/meter sensors
   automatically.  This ensures the correct meter source is always used
   regardless of which inverter the CT meter is physically connected to.

6. **Per-cycle debug logging**  
   Every coordinator update emits a `DEBUG`-level log line with the key power
   and energy values (PV, battery, grid, meter export/import totals). Enable
   debug logging for `custom_components.goodwe_modbus` in HA to inspect each
   poll cycle.

## Home Assistant Devices (HA custom integration)

Each config entry represents **one inverter** (or a master+slave pair) and creates
a single HA device with all inverter and external meter sensors.

### Single-inverter setup

To monitor a single GoodWe inverter, add this integration once via
**Settings → Devices & Services → Add Integration** and enter the master
inverter's IP address.  Leave the *Slave Host* field blank.

### Parallel/multi-inverter (master+slave) setup

GoodWe ET/EH/BT/BH inverters can be connected in parallel.  In such a setup
the external CT meter is physically wired to **only one** inverter (usually the
master).  Both inverters have Block B registers, but only the one with the meter
returns valid data.

To poll a master+slave pair as a single combined device, fill in the
**Slave Host** field when adding the integration.  The coordinator will then:

1. Poll **both** inverters on every scan cycle.
2. **Sum** PV generation and battery charge/discharge values across both units.
3. Use the external CT meter (Block B) from **whichever inverter has it**
   (master preferred; slave used automatically if master has no meter).
4. Log an `INFO` message whenever the slave meter is chosen, so the source is
   always transparent in the HA logs.

If only the master is reachable on a given cycle, the coordinator logs a warning
and continues with master-only data.

External meter (Block B) sensors are included on each device and are **enabled
by default**. If your inverter does not have an external CT meter connected,
the meter sensors will simply report no data and can be disabled manually in
the HA entity settings.
