# Entladung an einem Speicher nicht erfasst

## Was eedc sieht
Für den genannten Speicher steht im Monat eine Ladung, aber keine Entladung. Ohne Entladung gibt es keinen gemessenen
Wirkungsgrad und keine Speicher-Ersparnis — der HA-Sensor meldet dann `wirkungsgrad_messung: keine-entladung`. Eine
erfasste 0 ist ein Wert: ein Monat, in dem der Speicher nichts abgegeben hat, wird nicht gemeldet.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim genannten Speicher.
2. Im Feld «Entladung» den gemessenen Wert eintragen (auch 0, wenn der Speicher nichts abgegeben hat) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
Für diesen Speicher und Monat gibt es keinen gemessenen Wirkungsgrad und keine Speicher-Ersparnis.
