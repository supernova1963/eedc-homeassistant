<!-- anker: 415a-sensor-ohne-langzeitstatistik -->
### 4.15a Sensor ohne Langzeitstatistik <a name="415a-sensor-ohne-langzeitstatistik"></a>

**Was wird geprüft:** Trägt ein zugeordneter **Vorlauf-**, **Rücklauf-** oder **Zusatzheizungs-Sensor** einer Wärmepumpe in Home Assistant `state_class: measurement`? Gelesen wird der aktuelle Zustand des Sensors, je aktiver Wärmepumpe.

**Warum das zählt:** Den aktuellen Wert zeigt eedc aus dem Sensor-Zustand — live und im Überblick des Wärmepumpen-Hubs. **Stündliche Mittelwerte** übernimmt eedc dagegen aus der Langzeitstatistik von Home Assistant (rückwirkend, so weit sie zurückreicht), und die führt HA nur für Sensoren mit `state_class: measurement`. Ohne sie bleibt der Tagesverlauf dieser Werte leer, ohne dass es sonst jemand sagt.

> **Wann die Meldung schweigt:** ohne Verbindung zu Home Assistant, wenn HA den Sensor gerade nicht liefert, an stillgelegten Geräten und für Felder, deren Quelle MQTT ist — dort schreibt eedc die Stundenmittel selbst aus seiner 5-Minuten-Mitschrift, eine Langzeitstatistik braucht es nicht ([Wärme & Klima, Schritt 6](HANDBUCH_WAERME_KLIMA.md#schritt-6--live-werte-optional)). Ist einem Feld ein HA-Sensor **und** dasselbe MQTT-Topic zugeordnet, gilt der HA-Sensor — fehlt ihm die Langzeitstatistik, bleibt die Meldung, und eedc schreibt das Topic nicht stattdessen mit. Die Warmwasser-Temperatur prüft diese Kategorie nicht.

---
