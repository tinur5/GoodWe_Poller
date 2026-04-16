# GoodWe Modbus – Home Assistant Custom Integration

## Overview

Liest Daten von GoodWe Hybrid-Wechselrichtern (ET/EH/BT/BH-Serie) direkt via
**Modbus TCP** und stellt alle Werte als native **Home Assistant Sensoren** bereit.

Kein MQTT-Broker, kein externer Dienst – der Wechselrichter wird direkt aus HA heraus abgefragt.

## Unterstützte Sensoren

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| PV Power Total | W | Gesamte PV-Leistung |
| PV1–4 Power / Voltage / Current | W / V / A | Einzelne PV-Strings |
| Battery Power | W | Ladeleistung (+ = laden, − = entladen) |
| Battery SOC | % | Ladestand |
| Battery Charged/Discharged Today | kWh | Tagesenergie Batterie |
| Grid Power | W | Netzleistung (+ = Einspeisung, − = Bezug) |
| Grid Voltage / Frequency | V / Hz | Netzspannung und -frequenz |
| Grid Export / Import Total | kWh | Gesamte Netzenergie |
| Load Power | W | Hausverbrauch |
| PV Energy Today / Total | kWh | PV-Energie |
| Inverter Temperature | °C | Wechselrichter-Temperatur |

## Voraussetzungen

* Home Assistant 2024.1 oder neuer
* GoodWe-Wechselrichter mit aktiviertem Modbus TCP
* Wechselrichter im gleichen Netzwerk wie Home Assistant erreichbar

## Installation

1. Ordner `custom_components/goodwe_modbus/` in dein HA-Konfigurationsverzeichnis kopieren:
   ```
   config/
   └── custom_components/
       └── goodwe_modbus/   ← diesen Ordner kopieren
   ```
2. Home Assistant neu starten.
3. In HA: **Einstellungen → Geräte & Dienste → Integration hinzufügen → GoodWe Modbus**
4. IP-Adresse des Wechselrichters eingeben, Verbindung wird automatisch geprüft.

## Konfigurationsoptionen

| Feld | Standard | Beschreibung |
|------|----------|--------------|
| Master IP | – | IP-Adresse des Haupt-Wechselrichters |
| Slave IP | (leer) | Zweiter Wechselrichter (optional, wird summiert) |
| Modbus Port | 502 | TCP-Port |
| Unit ID | 247 | Modbus Unit-ID (GoodWe-Standard: 247) |
| Abfrage-Intervall | 10 s | Wie oft HA die Daten aktualisiert |

## Multi-Wechselrichter

Wenn ein zweiter Wechselrichter angegeben wird, werden:
- **Leistungswerte** aufsummiert
- **Energiezähler** aufsummiert
- **SOC** gemittelt
- **Temperatur** als Maximum angezeigt
- **Spannung / Frequenz** vom Master übernommen

## Filterlogik

- **Spike-Filter**: Ausreißer werden anhand des gleitenden Medians erkannt und verworfen
- **Deadband**: Netzleistung < 30 W wird auf 0 gesetzt (verhindert Jitter im Leerlauf)
- **Monotonie-Guard**: Energiezähler werden bei unplausiblen Rücksprüngen eingefroren

## Unterstützte Register

- Block 35100–35199: Laufzeitdaten (PV, Batterie, Netz, Last)
- Block 36000–36049: ARM-Kommunikation (Netz-Energiezähler)

## Disclaimer

Dieses Projekt steht in keiner Verbindung mit GoodWe. Verwendung auf eigene Gefahr.

## Lizenz

MIT License

