---
name: Live Dashboard - fehlende Heute/Gestern-kWh im Standalone-MQTT-Modus
description: Heute/Gestern-kWh im Live Dashboard fehlen ohne HA History API — MQTT-Cache speichert nur letzten Wert, keine History für Trapezregel-Integration
type: project
---

Live Dashboard zeigt heute_pv_kwh, heute_einspeisung_kwh etc. nur im HA-Modus (braucht HA History API für Leistungskurven-Integration via Trapezregel). Im Standalone-MQTT-Modus sind alle Heute/Gestern-Werte `None`.

**Why:** Der MQTT-Inbound-Cache speichert nur den letzten Wert pro Topic, keine zeitliche History. Die `_get_tages_kwh()`-Methode bricht bei `HA_INTEGRATION_AVAILABLE = False` sofort ab.

**How to apply:** Für MQTT-Inbound eine leichtgewichtige Tages-History im Cache aufbauen (z.B. Ring-Buffer mit 5-Min-Samples) und daraus Tages-kWh per Trapezregel berechnen. Alternativ: MQTT Energy Topics (monatliche kWh) nutzen, um zumindest Monats-Fortschritt anzuzeigen. User empfindet den Zustand als "unbefriedigend" — hat Priorität für eine spätere Iteration.
