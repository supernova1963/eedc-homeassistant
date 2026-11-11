# Verbrauchszähler ohne Zählerstand

## Was eedc sieht
Für diesen Gas-, Wasser- oder Ölzähler liegt kein einziger Stand vor — weder aus einem Sensor noch von Hand. In
Cockpit, Komponenten und Tabellen steht deshalb überall „—“. Weil ein Verbrauchszähler in keine Bewertung eingeht,
fällt das sonst nirgends auf.

## Lösungsweg
1. Am Befund **«Zählerstand erfassen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Zähler am Feld
   «Zählerstand». Einen Sensor zuordnen, der den fortlaufenden Stand liefert; eedc schreibt ihn dann stündlich mit.
2. Oder, gleichwertig: den Stand beim Monatsabschluss ablesen und im Feld «Zählerstand» eintragen
   ([Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)). Für einen Gas- oder Wasserzähler ohne Fernauslesung
   ist das der vorgesehene Weg.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald ein Stand vorliegt.

## Was ohne Handlung gilt
eedc zeigt für diesen Zähler überall „—“. Andere Zahlen sind nicht berührt — der Zähler geht in keine Bewertung ein.
