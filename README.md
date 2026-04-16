# GoodWe Modbus – Home Assistant Custom Integration

## Overview

Liest Daten von GoodWe Hybrid-Wechselrichtern (ET/EH/BT/BH-Serie) direkt via
**Modbus TCP** und stellt alle Werte als native **Home Assistant Sensoren** bereit.

Kein MQTT-Broker, kein externer Dienst – der Wechselrichter wird direkt aus HA heraus abgefragt.

## Unterstützte Sensoren

### Kombinierte Sensoren (Gesamtsystem)

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| PV Power Total | W | Gesamte PV-Leistung (alle Wechselrichter) |
| PV1–4 Power / Voltage / Current | W / V / A | Einzelne PV-Strings |
| Battery Power | W | Ladeleistung (+ = laden, − = entladen) |
| Battery SOC | % | Ladestand (Durchschnitt bei 2 WR) |
| Battery Charged/Discharged Today | kWh | Tagesenergie Batterie |
| Grid Power | W | Netzleistung (+ = Einspeisung, − = Bezug) |
| Grid Voltage / Frequency | V / Hz | Netzspannung und -frequenz |
| Grid Export / Import Total | kWh | Gesamte Netzenergie |
| Load Power | W | Hausverbrauch |
| PV Energy Today / Total | kWh | PV-Energie |
| Inverter Temperature | °C | Wechselrichter-Temperatur (Maximum) |

### Externe Zähler-Sensoren (standardmäßig deaktiviert)

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| Meter Active Power | W | Gesamtleistung ext. Zähler (int16) |
| Meter Active Power L1/L2/L3 | W | Phasenleistung ext. Zähler |
| Meter Active Power Total (32-bit) | W | Gesamtleistung ext. Zähler (int32, höherer Messbereich) |
| Meter Frequency | Hz | Netzfrequenz am ext. Zähler |
| Meter Power Factor | – | Leistungsfaktor ext. Zähler |
| Meter Export / Import Total | kWh | Gesamte Netzenergie (float32-Darstellung des WR) |

### Einzelne Wechselrichter (Geräte „Inverter 1" / „Inverter 2")

Bei Konfiguration eines Slave-Wechselrichters werden zwei zusätzliche
HA-Geräte angelegt. Jeder dieser Geräte stellt alle oben genannten
Leistungs- und Energiesensoren für den jeweiligen Wechselrichter einzeln bereit.

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

Wenn ein zweiter Wechselrichter (Slave IP) angegeben wird, werden:

- **Leistungswerte** aufsummiert (kombiniertes Gerät)
- **Energiezähler** aufsummiert (kombiniertes Gerät)
- **SOC** gemittelt (kombiniertes Gerät)
- **Temperatur** als Maximum angezeigt (kombiniertes Gerät)
- **Spannung / Frequenz** vom Master übernommen (kombiniertes Gerät)

Zusätzlich werden automatisch zwei Untergeräte angelegt:

| Gerät | Name | Inhalt |
|-------|------|--------|
| Inverter 1 | `<Name> – Inverter 1` | Alle Werte nur für Wechselrichter 1 |
| Inverter 2 | `<Name> – Inverter 2` | Alle Werte nur für Wechselrichter 2 |

So sind die Daten beider Wechselrichter einzeln sichtbar.

## Filterlogik

- **Spike-Filter**: Ausreißer werden anhand des gleitenden Medians erkannt und verworfen
- **Deadband**: Netzleistung < 30 W wird auf 0 gesetzt (verhindert Jitter im Leerlauf)
- **Monotonie-Guard**: Energiezähler werden bei unplausiblen Rücksprüngen eingefroren

## Unterstützte Register

- Block 35100–35199: Laufzeitdaten (PV, Batterie, Netz, Last)
- Block 36000–36049: ARM-Kommunikation (Netz-Energiezähler + ext. Zähler)

## Disclaimer

Dieses Projekt steht in keiner Verbindung mit GoodWe. Verwendung auf eigene Gefahr.

## Lizenz

MIT License

