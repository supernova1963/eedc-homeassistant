<!-- anker: 416-quellen-konflikte -->
### 4.16 Quellen-Konflikte <a name="416-quellen-konflikte"></a>

**Was wird geprüft:** Gab es in den letzten Tagen Felder, für die **mehr als eine** Quelle einen Wert geliefert hat — etwa ein HA-Sensor und zusätzlich ein MQTT-Topic?

**Warum das zählt:** Es ist kein Fehler. eedc hat sich bereits entschieden: Bei mehreren Quellen für dasselbe Feld gewinnt die höherwertige, und der angezeigte Wert stammt von ihr. Der Hinweis sagt nur, dass es die Konkurrenz gibt — nützlich, wenn eine Zahl anders aussieht als erwartet.

---
