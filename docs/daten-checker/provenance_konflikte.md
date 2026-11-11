# Felder mit Werten aus mehreren Quellen

## Was eedc sieht
Für einige Felder haben in den letzten Tagen zwei oder mehr Quellen einen Wert geliefert — etwa ein Home-Assistant-Sensor und
zusätzlich ein MQTT-Topic. Die Details nennen je Treffer den Ort (Monatsdaten, Tagesdaten oder die Komponente), das Feld, den
Zeitraum und die beteiligten Quellen. Das ist kein Fehler: Bei mehreren Quellen für dasselbe Feld gewinnt die höherwertige,
und der angezeigte Wert stammt von ihr.

## Lösungsweg
1. Nichts zu tun — eedc hat bereits entschieden. Der Hinweis ist nützlich, wenn eine Zahl anders aussieht als erwartet: Die
   Details sagen, welche Quellen am Feld konkurriert haben.
2. Willst du die zweite Quelle nicht, entfernst du sie in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen)
   am genannten Feld.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange im Prüfzeitraum mehr als eine Quelle an
   einem Feld geschrieben hat; nach dem Entfernen einer Quelle verschwindet sie, wenn der Zeitraum ohne Konkurrenz ist.

## Was ohne Handlung gilt
Der angezeigte Wert kommt weiter aus der höchstprioren Quelle. Der Hinweis ist kein Auftrag und hat keinen
„Akzeptiert“-Knopf.
