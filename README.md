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
| Battery Power | W | Batterieladeleistung (+ = Entladen, − = Laden) |
| Battery SOC | % | Ladestand (Durchschnitt bei 2 WR) |
| Battery Charged/Discharged Today | kWh | Tagesenergie Batterie |
| Battery Charged/Discharged Total | kWh | Lebenszeit-Energiezähler Batterie |
| Grid Power | W | Netzleistung (+ = Netzbezug, − = Einspeisung) |
| Grid Voltage / Frequency | V / Hz | Netzspannung und -frequenz |
| Grid Export / Import Total | kWh | Gesamte Netzenergie |
| Load Power | W | Hausverbrauch |
| PV Energy Today / Total | kWh | PV-Energie |
| Inverter Temperature | °C | Wechselrichter-Temperatur (Maximum) |

### Externe Zähler-Sensoren (standardmäßig aktiviert)

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| Meter Active Power | W | Gesamtleistung ext. Zähler (int16) |
| Meter Active Power L1/L2/L3 | W | Phasenleistung ext. Zähler |
| Meter Active Power Total (32-bit) | W | Gesamtleistung ext. Zähler (int32, höherer Messbereich) |
| Meter Frequency | Hz | Netzfrequenz am ext. Zähler |
| Meter Power Factor | – | Leistungsfaktor ext. Zähler |
| Meter Export / Import Total | kWh | Gesamte Netzenergie (float32-Darstellung des WR) |

> Hinweis: Ist kein externer CT-Zähler angeschlossen, liefern diese Sensoren keine Daten und können in den HA-Entitätseinstellungen deaktiviert werden.

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
- **Tagesenergie-Filter**: Für tägliche Energiezähler (PV heute, Batterie Laden/Entladen heute) wird ein einseitiger Spike-Filter verwendet. Nur unplausibel hohe Sprünge (≥ 3 kWh über dem Median in einem Abfragezyklus) werden verworfen. Ein Abfall auf nahezu 0 (Mitternachts-Reset) wird erkannt und die Filterhistorie automatisch zurückgesetzt.
- **Deadband**: Netzleistung < 30 W wird auf 0 gesetzt (verhindert Jitter im Leerlauf)
- **Monotonie-Guard**: Gesamtenergiezähler werden bei unplausiblen Rücksprüngen eingefroren

## Unterstützte Register

Die Integration liest drei Holding-Register-Blöcke via Modbus TCP aus
(Protokoll: GoodWe ET/EH/BT/BH ARM205 v1.7).

### Block A – Wechselrichter Laufzeitdaten (35100 … 35224)

| Register | Offset | Name | Typ | Skalierung | Einheit |
|----------|--------|------|-----|------------|---------|
| 35103 | +3 | Vpv1 | u16 | ×0,1 | V |
| 35104 | +4 | Ipv1 | u16 | ×0,1 | A |
| 35105–35106 | +5–6 | Ppv1 | u32 | ×1 | W |
| 35107 | +7 | Vpv2 | u16 | ×0,1 | V |
| 35108 | +8 | Ipv2 | u16 | ×0,1 | A |
| 35109–35110 | +9–10 | Ppv2 | u32 | ×1 | W |
| 35111 | +11 | Vpv3 | u16 | ×0,1 | V |
| 35112 | +12 | Ipv3 | u16 | ×0,1 | A |
| 35113–35114 | +13–14 | Ppv3 | u32 | ×1 | W |
| 35115 | +15 | Vpv4 | u16 | ×0,1 | V |
| 35116 | +16 | Ipv4 | u16 | ×0,1 | A |
| 35117–35118 | +17–18 | Ppv4 | u32 | ×1 | W |
| 35121 | +21 | Vgrid R (L1) | u16 | ×0,1 | V |
| 35122 | +22 | Igrid R (L1) | u16 | ×0,1 | A |
| 35123 | +23 | Fgrid R (L1) | u16 | ×0,01 | Hz |
| 35125 | +25 | Pgrid R (L1) | s16 | ×1, + = Einspeisung | W |
| 35130 | +30 | Pgrid S (L2) | s16 | ×1, + = Einspeisung | W |
| 35135 | +35 | Pgrid T (L3) | s16 | ×1, + = Einspeisung | W |
| 35140 | +40 | Netzleistung Gesamt | s16 | ×1, + = Einspeisung | W |
| 35172 | +72 | Lastleistung Gesamt | s16 | ×1 | W |
| 35176 | +76 | Temperatur (Kühlkörper) | s16 | ×0,1 | °C |
| 35182–35183 | +82–83 | Batterieleistung | s32 | ×1, + = Entladen | W |
| 35187 | +87 | Arbeitsmodus | u16 | – | – |
| 35191–35192 | +91–92 | PV-Energie Gesamt | u32 | ÷10 | kWh |
| 35193–35194 | +93–94 | PV-Energie Heute | u32 | ÷10 | kWh |
| 35195–35196 | +95–96 | Einspeisung Gesamt | u32 | ÷10 | kWh |
| 35200–35201 | +100–101 | Netzbezug Gesamt | u32 | ÷10 | kWh |
| 35206–35207 | +106–107 | Batterie Laden Gesamt | u32 | ÷10 | kWh |
| 35208 | +108 | Batterie Laden Heute | u16 | ÷10 | kWh |
| 35209–35210 | +109–110 | Batterie Entladen Gesamt | u32 | ÷10 | kWh |
| 35211 | +111 | Batterie Entladen Heute | u16 | ÷10 | kWh |

### Block B – Externer CT-Zähler (36000 … 36049)

| Register | Offset | Name | Typ | Skalierung | Einheit |
|----------|--------|------|-----|------------|---------|
| 36005 | +5 | Zähler Wirkleistung L1 | s16 | ×1 | W |
| 36006 | +6 | Zähler Wirkleistung L2 | s16 | ×1 | W |
| 36007 | +7 | Zähler Wirkleistung L3 | s16 | ×1 | W |
| 36008 | +8 | Zähler Wirkleistung Gesamt | s16 | ×1 | W |
| 36009 | +9 | Zähler Blindleistung Gesamt | s16 | ×1 | var |
| 36013 | +13 | Leistungsfaktor | s16 | ×0,001 | – |
| 36014 | +14 | Frequenz | u16 | ×0,01 | Hz |
| 36015–36016 | +15–16 | Einspeisung Gesamt (float32) | float32 | bereits kWh | kWh |
| 36017–36018 | +17–18 | Netzbezug Gesamt (float32) | float32 | bereits kWh | kWh |
| 36025–36026 | +25–26 | Zähler Wirkleistung Gesamt (32-bit) | s32 | ×1 | W |

> Hinweis: Block B ist optional. Ist kein externer CT-Zähler angeschlossen, liefert dieser Block keine Daten.

### Block C – BMS / Batterie-Daten (37000 … 37007)

| Register | Offset | Name | Typ | Skalierung | Einheit |
|----------|--------|------|-----|------------|---------|
| 37007 | +7 | Batterie-Ladezustand (SOC) | u16 | ×1 | % |

> Hinweis: Block C ist optional. Falls dieser Block nicht verfügbar ist, liefert der SOC-Sensor keinen Wert.

> **Vorzeichenkonvention:** GoodWe meldet Netzleistung mit positivem Vorzeichen = Einspeisung ins Netz.
> Die Integration **kehrt dieses Vorzeichen um**, damit die HA-Konvention gilt: **positiv = Netzbezug, negativ = Einspeisung**.

Weitere Details zur Architektur und Filterlogik: [docs/architecture.md](docs/architecture.md)

## Disclaimer

Dieses Projekt steht in keiner Verbindung mit GoodWe. Verwendung auf eigene Gefahr.

## Lizenz

MIT License

