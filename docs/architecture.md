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

### Block A – Inverter runtime (35100 … 35199)

| Offset | Name | Scale | Unit |
|--------|------|-------|------|
| +3 | Vpv1 | ×0.1 | V |
| +4 | Ipv1 | ×0.1 | A |
| +5 | Ppv1 | ×1 | W |
| +6–8 | PV2 (same pattern) | | |
| +9–11 | PV3 | | |
| +12–14 | PV4 | | |
| +16 | Vgrid R | ×0.1 | V |
| +18 | Fgrid R | ×0.01 | Hz |
| +19,23,27 | Pgrid R/S/T | ×1 signed | W |
| +28 | Pgrid total | ×1 signed | W (+ = export) |
| +40 | Pbattery | ×1 signed | W (+ = charging) |
| +41 | SOC | ×1 | % |
| +47 | Pload | ×1 | W |
| +54 | Temperature | ×0.1 | °C |
| +56–57 | E_day PV | ×0.1 (32-bit) | kWh |
| +60–61 | E_total PV | ×0.1 (32-bit) | kWh |
| +70–71 | E_day charge | ×0.1 (32-bit) | kWh |
| +74–75 | E_day discharge | ×0.1 (32-bit) | kWh |

### Block B – ARM external meter (36000 … 36049)

| Offset | Name | Scale / Type | Unit |
|--------|------|--------------|------|
| +5 | Meter active power L1 | int16 signed | W |
| +6 | Meter active power L2 | int16 signed | W |
| +7 | Meter active power L3 | int16 signed | W |
| +8 | Meter active power total | int16 signed | W |
| +9 | Meter reactive power total | int16 signed | var |
| +13 | Meter power factor | ×0.001 | – |
| +14 | Meter frequency | ×0.01 | Hz |
| +15–16 | E_total export (float32 hi+lo) | IEEE 754 float | kWh |
| +17–18 | E_total import (float32 hi+lo) | IEEE 754 float | kWh |
| +25–26 | Meter active power total (32-bit) | int32 signed | W |

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
   Rejects samples that deviate more than `max_delta` W from the recent median.  
   Previous accepted value is returned instead.

2. **DeadbandFilter** (grid power)  
   Values with |P| < 30 W are mapped to 0 to suppress jitter at standby.

3. **MonotonicGuard** (energy counters)  
   Rejects counter decreases that are not large enough to be a true rollover.  
   Applied per inverter *before* summation.

## Home Assistant Devices (HA custom integration)

Each config entry represents **one inverter** and creates a single HA device with
all inverter and external meter sensors.

To monitor multiple inverters, add this integration once per inverter via
**Settings → Devices & Services → Add Integration**.

External meter (Block B) sensors are included on each device and are **disabled
by default**; enable the ones you need in the HA entity settings.
