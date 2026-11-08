## 6. Wallbox

> **Die Wallbox ist die Summe aller Ladungen an ihr** — privates Auto, Gast, Dienstwagen. So zählt sie in der Energiebilanz, am Tag, in der Stunde und in ihrer eigenen Anzeige. Mehrere Wallboxen werden summiert (jeder Ladepunkt zählt). Trägt ein Auto eine eigene Heim-Messung (siehe E-Auto), zählt sie für dieses Auto; der **Rest** der Wallbox geht nach Kilometern an die privaten Autos ohne eigene Messung, ohne solche bleibt er nicht zugeordnet (Gast, Verluste: nur Verbrauch, keine Ersparnis) — außer es ist gar kein Fahrzeug angelegt: dann ist die Wallbox selbst das private Auto. Ohne Messung am Auto ist das die bisherige km-anteilige Aufteilung. Ordne den Loadpoint-/Wallbox-Energiesensor hier zu.

### Monatserfassung

<!-- erzeugt: eingabefelder typ=wallbox liste=monat -->

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=wallbox liste=live -->

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

## 6a. Themen (frei gewählte Entitäten) — Wärmepumpe, Wallbox, E-Auto

*Seit der nächsten Version.* Kein eedc-Feld: ein **Themen-Eintrag** zeigt den Zustand einer Entität, die du selbst wählst,
wie Home Assistant ihn liefert — jede Domain, keine Einheit vorgeschrieben, keine Rechnung, keine Mitschrift
([Handbuch Einstellungen §7.11](HANDBUCH_EINSTELLUNGEN.md#711-themen-frei-gewählte-entitäten)).

| Weg | Form | Hinweis |
|-----|------|---------|
| HA-Sensor | jede Entität mit Zustand (`lock.…`, `binary_sensor.…`, `sensor.…`, `device_tracker.…`) | Wert = State, Einheit = `unit_of_measurement`; für Klartext einen Template-Helfer zuordnen |
| MQTT-Inbound | `eedc/{id}_{name}/live/inv/{id}_{name}/thema_e{n}` | Text, am besten `retained` ([MQTT-Inbound](MQTT_INBOUND.md)) |
| MQTT-Gateway | Fremd-Topic → `…/thema_e{n}` | als Text weitergereicht, ohne Faktor |

---

