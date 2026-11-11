# Energiemenge im Monat negativ

## Was eedc sieht
Einspeisung, Netzbezug, PV-Erzeugung oder ein Batteriewert ist für den Monat kleiner als 0. Energiemengen können nicht
negativ sein — meist ein Vorzeichen- oder Eingabefehler, seltener ein gesunkener Zählerstand in der Quelle.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim genannten Feld.
2. Den Wert berichtigen und speichern. Kam er aus Home Assistant, dort die Zählerstände prüfen: ein gefallener Stand
   meldet der Daten-Checker auch als «Zählerstände – Rückgang in Home Assistant».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc rechnet mit dem negativen Wert; Bilanz, Eigenverbrauch und alles, was daraus folgt, stehen für den Monat falsch.
