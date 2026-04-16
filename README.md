# GoodWe Poller (Modbus → MQTT → Home Assistant)

## Overview

This project reads data from GoodWe hybrid inverters (ET/EH/BT/BH series) via Modbus TCP and publishes structured metrics to MQTT.

It is designed for:

* Home Assistant integration
* Multi-inverter setups (master + slave)
* Reliable energy monitoring with filtering and validation

## Features

* Reads Modbus registers (35100 / 36000 blocks)
* Supports master + slave inverter aggregation
* Publishes clean MQTT topics
* Built-in spike filtering (PV, battery, grid)
* Handles invalid / corrupted register values
* Grid import/export energy via external meter (ARM registers)

## Supported Data

* PV power and energy
* Battery power, charge/discharge energy
* Grid power (filtered)
* Grid import/export energy
* Load calculation

## Requirements

* Python 3.10+
* MQTT broker (e.g. Mosquitto)
* GoodWe inverter with Modbus TCP enabled

## Installation

```bash
git clone https://github.com/YOURNAME/goodwe-poller.git
cd goodwe-poller
pip install -r requirements.txt
```

## Configuration

Create a `.env` file:

```env
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=

MASTER_HOST=192.168.1.10
SLAVE_HOST=192.168.1.11

MODBUS_UNIT_ID=247
POLL_INTERVAL=10
BASE_TOPIC=goodwe_direct
```

## Run

```bash
python main.py
```

## MQTT Topics

Base topic:

```
goodwe_direct/total/decoded/
```

Examples:

* `pv_power_total_w`
* `battery_power_total_w`
* `grid_power_total_w`
* `grid_import_energy_total_kwh`
* `grid_export_energy_total_kwh`

## Register Mapping

Main sources:

* 35100 → inverter runtime data
* 36000 → external meter (ARM communication)

Grid energy:

* 36015 → total export (kWh)
* 36017 → total import (kWh)

## Filtering Logic

To improve stability:

* Spike filtering for PV, battery and grid
* Deadband around 0W for grid
* Maximum limits to avoid corrupted values
* Monotonic validation for energy counters

## Known Issues

* External meter values may be unavailable depending on inverter setup
* Some installations require fallback to inverter-based energy counters
* Modbus responses can contain spikes or invalid data

## Disclaimer

This project is not affiliated with GoodWe.
Use at your own risk.

## License

MIT License
