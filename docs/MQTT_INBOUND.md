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
    ├── pv_gesamt_kwh                  → 627.0
    ├── einspeisung_kwh                → 397.2
    ├── netzbezug_kwh                  → 182.5
    └── inv/{inv_id}_{name}/
        ├── pv_erzeugung_kwh           → 627.0    (PV-Module)
        ├── ladung_kwh                 → 128.6    (Speicher/E-Auto/Wallbox)
        ├── entladung_kwh              → 85.3     (Speicher)
        └── stromverbrauch_kwh         → 450.0    (Waermepumpe)
```

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

## Beispiel-Flows

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
