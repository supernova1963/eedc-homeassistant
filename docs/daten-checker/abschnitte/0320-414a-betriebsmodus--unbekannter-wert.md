<!-- anker: 414a-betriebsmodus--unbekannter-wert -->
### 4.14a Betriebsmodus – unbekannter Wert <a name="414a-betriebsmodus--unbekannter-wert"></a>

**Was wird geprüft:** Liefert der zugeordnete Betriebsmodus-Sensor einer Wärmepumpe oder Klimaanlage gerade einen Wert, den eedc kennt?

**Warum das zählt:** eedc versteht eine feste Liste von Texten (Werte-Tabelle im Handbuch [Wärme & Klima](HANDBUCH_WAERME_KLIMA.md#welchen-sensor-eedc-lesen-kann); dieselbe Liste steht in der Datenquellen-Zuordnung am Feld „Betriebsmodus"). Ein anderer Wert — etwa `heating`, `standby` oder `pool` aus einem eigenen Prioritäts-Sensor — zählt als *unbestimmt*: Der Strom dieser Stunden steht unter „nicht aufgeteilt", ohne dass es sonst jemand sagt.

> **Wann die Meldung schweigt:** ohne Verbindung zu Home Assistant, wenn der Sensor gerade `unknown` oder `unavailable` meldet (kein Wert ist kein falscher Wert), bei `auto`, `heat_cool` und `automatik` (eedc kennt sie und zählt sie bewusst als unbestimmt — das Gerät entscheidet dort selbst) und wenn das Gerät mehrere verschiedene Modus-Quellen hat (dann nennt §4.14 den Fall). Geprüft wird der Wert, den der Sensor **jetzt** meldet: Ein Wert, der nur zeitweise auftaucht, fällt auf, wenn er beim Prüfen ansteht.

---
