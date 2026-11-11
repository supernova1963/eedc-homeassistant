# Felder mit Werten aus mehreren Quellen

## Was eedc sieht
Für einige Felder haben in den letzten 30 Tagen zwei oder mehr Quellen einen Wert geliefert — etwa eine Eingabe von Hand
und der Monatsabschluss, oder die HA-Statistik und eine Reparatur. Die Details nennen je Treffer den Ort (Monatsdaten,
Tagesdaten oder die Komponente), das Feld, den Zeitraum und die beteiligten Quellen. Das ist kein Fehler: Bei mehreren
Quellen für dasselbe Feld gewinnt die höherwertige, und der angezeigte Wert stammt von ihr.

## Lösungsweg
1. Nichts zu tun — eedc hat bereits entschieden. Der Hinweis ist nützlich, wenn eine Zahl anders aussieht als erwartet: Die
   Details sagen, welche Quellen am Feld konkurriert haben.
2. Zu entfernen gibt es nichts: Die Quellen sind die Wege, auf denen ein Wert geschrieben wurde (Eingabe von Hand,
   Monatsabschluss, HA-Statistik, Reparatur, Import) — keine Zuordnung. Der Hinweis zeigt nur, welche davon am Feld
   nacheinander geschrieben haben.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, bis in den letzten 30 Tagen keine zwei Quellen
   mehr an demselben Feld geschrieben haben.

## Was ohne Handlung gilt
Der angezeigte Wert kommt weiter aus der höchstprioren Quelle. Der Hinweis ist kein Auftrag und hat keinen
„Akzeptiert“-Knopf.
