# Kühlanteil wird geschätzt — Stromzähler für den Kühlbetrieb fehlt

## Was eedc sieht
Die Wärmepumpe misst Heizen und Warmwasser mit eigenen Zählern und teilt zusätzlich nach dem Betriebsmodus auf. Für den
Kühlbetrieb gibt es aber keinen eigenen Stromzähler — eedc schätzt den Kühlanteil deshalb aus der Summe der beiden anderen.
Verbrauch, Kosten und CO₂ rechnen weiter mit dem vollen Strom. Nur die Aufteilung nach Betriebsart ist eine Verteilung statt
einer Messung, und deshalb kürzt sie die Arbeitszahl nicht.

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld
   «Strom Kühlbetrieb (kWh)».
2. Dort den Stromzähler des Kühlbetriebs zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; eedc liest den Kühlstrom ab, statt ihn
   zu verteilen.

## Was ohne Handlung gilt
Die Zuordnung ist freiwillig — ohne sie bleibt alles wie bisher: Die Mengen stimmen, der Kühlanteil bleibt geschätzt.
