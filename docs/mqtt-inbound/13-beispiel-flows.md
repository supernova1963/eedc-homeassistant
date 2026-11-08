## Beispiel-Flows (andere Systeme)

Die folgenden Beispiele zeigen die manuelle Konfiguration fuer andere Smarthome-Systeme.

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

