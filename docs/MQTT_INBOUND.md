# MQTT-Inbound: Universelle Datenbruecke

MQTT-Inbound ermoeglicht es, Live-Leistungsdaten und Monatswerte von **jedem Smarthome-System** an EEDC zu senden. Es wird nur ein MQTT-Broker benoetigt (z.B. Mosquitto).

## Unterstuetzte Systeme

- Home Assistant (Automation oder Node-RED Add-on)
- Node-RED (standalone oder als Add-on)
- ioBroker (JavaScript-Adapter)
- FHEM (MQTT2-Modul)
- openHAB (MQTT Binding)
- Jedes System mit MQTT-Publish-Faehigkeit

## Einrichtung

1. **MQTT-Broker installieren** (z.B. Mosquitto)
2. In EEDC unter *Einstellungen > Einrichtung > MQTT-Inbound*:
   - Broker-Adresse und Port eintragen
   - Optional: Benutzername/Passwort
   - "Speichern & Verbinden" klicken
3. Die generierten Topics im Smarthome-System befuellen

## Topic-Struktur

EEDC generiert die Topics automatisch aus den angelegten Anlagen und Investitionen. Das Format ist:

```
eedc/{anlage_id}_{name}/
├── live/                              # Echtzeit-Leistung (Watt)
│   ├── einspeisung_w                  → 1100
│   ├── netzbezug_w                    → 0
│   └── inv/{inv_id}_{name}/
│       ├── leistung_w                 → 4200
│       └── soc                        → 72       (nur Speicher/E-Auto)
│
└── energy/                            # Monatswerte (kWh, kumuliert)
    ├── einspeisung_kwh                → 397.2
    ├── netzbezug_kwh                  → 182.5
    └── inv/{inv_id}_{name}/
        └── {key}                      → Wert     (siehe Felder-Referenz)
```

### Energy-Felder Referenz (Investitions-Topics)

Die Felder unter `energy/inv/{id}_{name}/` entsprechen den Monatsdaten-Feldern der jeweiligen Investition. EEDC erkennt alle Felder automatisch — es muss kein Mapping konfiguriert werden.

| Investitionstyp | Key | Einheit | Beschreibung |
|---|---|---|---|
| **PV-Module** | `pv_erzeugung_kwh` | kWh | PV-Erzeugung |
| **Speicher** | `ladung_kwh` | kWh | Batterie-Ladung |
| **Speicher** | `entladung_kwh` | kWh | Batterie-Entladung |
| **Waermepumpe** | `stromverbrauch_kwh` | kWh | Stromverbrauch |
| **Waermepumpe** | `heizenergie_kwh` | kWh | Erzeugte Heizenergie |
| **Waermepumpe** | `warmwasser_kwh` | kWh | Warmwasser-Erzeugung |
| **E-Auto** | `km_gefahren` | km | Gefahrene Kilometer (Odometer-Differenz) |
| **E-Auto** | `v2h_entladung_kwh` | kWh | Vehicle-to-Home Entladung |
| **Wallbox** | `ladung_kwh` | kWh | Ladung gesamt |
| **Wallbox** | `ladevorgaenge` | Anzahl | Anzahl Ladevorgaenge |
| **BKW** | `pv_erzeugung_kwh` | kWh | BKW-Erzeugung |
| **BKW** | `eigenverbrauch_kwh` | kWh | Eigenverbrauch |
| **BKW** | `speicher_ladung_kwh` | kWh | BKW-Speicher Ladung |
| **BKW** | `speicher_entladung_kwh` | kWh | BKW-Speicher Entladung |
| **Sonstiges** | `erzeugung_kwh` | kWh | Erzeugung (Erzeuger/Speicher) |
| **Sonstiges** | `verbrauch_sonstig_kwh` | kWh | Verbrauch (Verbraucher/Speicher) |

**Nicht per MQTT lieferbar** (werden im Monatsabschluss manuell eingegeben oder berechnet):
- `ladung_pv_kwh` / `ladung_netz_kwh` (PV/Netz-Aufteilung bei Speicher, E-Auto, Wallbox)
- `batterie_ladung_netz_kwh` (Arbitrage-Anteil)
- `ladung_extern_kwh` / `ladung_extern_euro` (externe Ladung E-Auto)
- Wetterdaten (`globalstrahlung`, `sonnenstunden`, `temperatur`)
- `sonderkosten_euro`, `notizen`

### Beispiel

Fuer eine Anlage "Meine PV" (ID 1) mit Speicher "BYD HVS" (ID 3):

```
eedc/1_Meine_PV/live/einspeisung_w          → 1100
eedc/1_Meine_PV/live/inv/3_BYD_HVS/leistung_w → -500
eedc/1_Meine_PV/live/inv/3_BYD_HVS/soc      → 72
eedc/1_Meine_PV/energy/pv_gesamt_kwh         → 627.0
eedc/1_Meine_PV/energy/inv/3_BYD_HVS/ladung_kwh → 128.6
```

**Hinweis:** Die numerische ID am Anfang (`1_`, `3_`) ist die DB-ID. Der Name danach ist optional und dient nur der Lesbarkeit. EEDC extrahiert nur die ID.

## Datenquellen-Prioritaet

MQTT-Inbound hat Konfidenz 91% und liegt zwischen Connector (90%) und HA Statistics (92%):

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%)
```

Hoehere Konfidenz ueberschreibt niedrigere. Wer also HA Statistics hat, dessen Werte haben Vorrang vor MQTT-Inbound.

## Home Assistant Blueprint (empfohlen)

Fuer Home Assistant Nutzer gibt es ein fertiges Blueprint, das die Einrichtung vereinfacht. Statt manuell YAML-Automationen zu schreiben, genuegt ein Import per URL:

1. In Home Assistant: **Einstellungen → Automatisierungen → Blueprints → Blueprint importieren**
2. URL eingeben:
   ```
   https://github.com/supernova1963/eedc-homeassistant/blob/main/blueprints/eedc_sensor_to_mqtt.yaml
   ```
3. Pro Sensor eine Automation erstellen:
   - **Sensor** auswaehlen (z.B. `sensor.pv_power`)
   - **MQTT Topic** aus EEDC kopieren (Einstellungen → MQTT-Inbound → Beispiel-Flows)
   - **Sende-Modus** waehlen (bei Aenderung oder Intervall)
4. Fertig — das Blueprint filtert automatisch `unavailable`/`unknown` Werte heraus

**Tipp:** Erstelle eine Automation pro Sensor/Topic-Paar. Die passenden Topics zeigt EEDC personalisiert fuer deine Anlage an.

## Beispiel-Flows (manuell)

Die folgenden Beispiele zeigen die manuelle Konfiguration ohne Blueprint — nuetzlich fuer andere Smarthome-Systeme oder wenn du volle Kontrolle ueber die Automation haben moechtest.

### Home Assistant Automation

```yaml
automation:
  - alias: "EEDC PV-Leistung senden"
    trigger:
      - platform: state
        entity_id: sensor.pv_power
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA_Tripower/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
```

Mehrere Sensoren:

```yaml
automation:
  - alias: "EEDC Live-Daten senden"
    trigger:
      - platform: time_pattern
        seconds: "/5"
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/einspeisung_w"
          payload: "{{ states('sensor.grid_export_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/netzbezug_w"
          payload: "{{ states('sensor.grid_import_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/leistung_w"
          payload: "{{ states('sensor.battery_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/soc"
          payload: "{{ states('sensor.battery_soc') }}"
```

### Node-RED

Einfacher Flow: Sensor-Node → MQTT-Out-Node

```json
[
  {
    "id": "eedc_pv",
    "type": "mqtt out",
    "topic": "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w",
    "broker": "localhost",
    "name": "EEDC PV-Leistung"
  }
]
```

Fuer mehrere Werte einen Function-Node verwenden, der die Sensor-Werte auf die passenden Topics mappt.

### ioBroker (JavaScript-Adapter)

```javascript
// Live-Leistung senden
on('sourceDP.pv_power', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/2_SMA/leistung_w',
        message: String(obj.state.val)
    });
});

// Batterie SoC senden
on('sourceDP.battery_soc', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/3_BYD/soc',
        message: String(obj.state.val)
    });
});

// Netz-Werte senden
on('sourceDP.grid_export', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/einspeisung_w',
        message: String(obj.state.val)
    });
});
```

### FHEM

```perl
# MQTT2-Geraet fuer EEDC anlegen
define eedc_mqtt MQTT2_DEVICE

# PV-Leistung bei Aenderung senden
define eedc_pv notify pv_power:.* {\
  fhem("set mqtt2 publish eedc/1_Meine_PV/live/inv/2_SMA/leistung_w " . ReadingsVal("pv_power","state","0"))\
}
```

### openHAB

```java
rule "EEDC PV-Leistung senden"
when
    Item PV_Power changed
then
    val mqttActions = getActions("mqtt", "mqtt:broker:myBroker")
    mqttActions.publishMQTT("eedc/1_Meine_PV/live/inv/2_SMA/leistung_w", PV_Power.state.toString)
end
```

## Testen

### Kommandozeile (mosquitto_pub)

```bash
# Einzelnen Wert senden
mosquitto_pub -h localhost -t "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w" -m "4200"

# Alle Topics subscriben (Monitoring)
mosquitto_sub -h localhost -t "eedc/#" -v
```

### In EEDC pruefen

1. In der MQTT-Einrichtung unter "Empfangene Werte" auf "Aktualisieren" klicken
2. Im Live-Dashboard pruefen ob die Werte angezeigt werden

## Hinweise

- **Payload-Format:** Nur numerische Werte (z.B. `4200`, `72.5`). Kein JSON.
- **Einheiten:** Live-Topics in **Watt** (nicht kW). Energy-Topics in **kWh**.
- **Batterie:** Positive Werte = Ladung, negative = Entladung
- **Retained Messages:** EEDC publisht beim Speichern Initialwerte (0) als Retained, damit Topics am Broker sichtbar sind.
- **Reconnect:** Bei Verbindungsverlust verbindet sich der Subscriber automatisch nach 10 Sekunden neu.
- **Monatsabschluss:** Energy-Topics erscheinen automatisch als Vorschlaege im Monatsabschluss-Wizard (Konfidenz 91%). Kein zusaetzliches Mapping noetig.
