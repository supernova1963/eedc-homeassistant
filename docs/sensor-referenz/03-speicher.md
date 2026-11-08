## 3. Speicher (Batterie)

### Monatserfassung

<!-- erzeugt: eingabefelder typ=speicher liste=monat -->

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=speicher liste=live -->

**Ladung und Entladung des Tages** sind keine eigenen Registry-Felder: Es sind die Monatsfelder `ladung_kwh`/`entladung_kwh` der Tabelle „Monatserfassung", hier mit einem Tagessensor zugeordnet.

| Feld | Label | Einheit | Sensortyp | Beschreibung | Ausgewertet in |
|------|-------|---------|-----------|-------------|-----------------|
| `ladung_kwh` | Ladung heute | kWh | Tagessensor | Tages-Ladeenergie. Optional — wenn vorhanden, wird für heute-kWh-Anzeige bevorzugt (genauer als Trapez-Integration aus W-Sensor). Wird täglich um 0:00 auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |
| `entladung_kwh` | Entladung heute | kWh | Tagessensor | Tages-Entladeenergie. Optional — wie `ladung_kwh`. Wird täglich auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

