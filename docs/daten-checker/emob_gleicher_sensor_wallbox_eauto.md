# Gleicher Sensor an Wallbox und E-Auto

## Was eedc sieht
Derselbe Sensor ist der Wallbox und dem E-Auto zugeordnet; die Zeile nennt Sensor und Geräte. Beide messen damit
denselben Ladestrom. In Monat und Jahr zählt eedc die Ladung einmal (das E-Auto trägt seine Messung, für die Wallbox
bleibt kein Rest) — die Zuordnung ist trotzdem falsch.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim E-Auto am Feld der Ladung.
2. Die Zuordnung an einem der beiden Geräte lösen. Faustregel: Die Wallbox misst den Stromfluss, das E-Auto trägt
   Nutzung und Kilometer — meist bleibt der Sensor an der Wallbox.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Ein weiteres Auto ohne eigene Messung bekommt von dieser Wallbox keine Heimladung, und die Sichten je Gerät zeigen
denselben Ladestrom an Wallbox und E-Auto.
