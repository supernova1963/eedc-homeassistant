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

