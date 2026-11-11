<!-- anker: 49a-datenquellen--status -->
### 4.9a Datenquellen – Status (Kategorie „Datenquelle – aktiver Pfad“) <a name="49a-datenquellen--status"></a>

> **Variantenhinweis:** Die Kategorie meldet in beiden Varianten genau einen Befund: welcher Weg die Tages- und Stundenwerte zuletzt
> geschrieben hat. Im **HA Add-on** ist das die HA-Langzeitstatistik oder der HA-Spiegel (Kanal-Tag), im **Standalone-Betrieb** der
> Snapshot-Pfad. Ist keine Langzeitstatistik erreichbar, laufen auch die Prüfungen gegen Home Assistant nicht (Sensoren in der
> Langzeitstatistik, Abweichung zu Home Assistant) — der Kopf des Daten-Checkers zählt sie als nicht ausführbar.

**Was wird geprüft:** die Herkunft der jüngsten Tageszeile mit Stundenwerten (die häufigste Quelle ihrer Felder) und ob Home Assistant
erreichbar ist.

---
