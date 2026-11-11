# Mehrere verschiedene Modus-Quellen an einem Gerät

## Was eedc sieht
Der Betriebsmodus ist an mehreren Innengeräten zugeordnet, und sie zeigen auf verschiedene Entitäten. Der Stromzähler des
Geräts ist aber einer — für die Aufteilung braucht eedc genau eine Aussage darüber, was die Anlage gerade tut. Aus mehreren
Innengeräte-Zuständen einen Anlagen-Zustand zu bilden, hängt an deiner Anlage (kann ein Innengerät lüften, während ein
anderes heizt? meldet das Außengerät beim Enteisen etwas?). Das weiß eedc nicht, und es rät nicht: Der Strom wird nicht
aufgeteilt.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld «Betriebsmodus».
2. Einen der zwei Wege wählen: bei allen Innengeräten **dieselbe** climate-Entität zuordnen — dann ist es eine Quelle (bei
   einer Ein-Kreis-Anlage gibt ohnehin das Außengerät die Richtung vor). Oder in Home Assistant einen Template-Sensor bauen,
   der deine Innengeräte zu einer Aussage zusammenfasst, und dessen Ergebnis zuordnen (Vorlage im Handbuch «Wärme & Klima»).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, die Prüfung meldet die Aufteilung als
   eingerichtet.

## Was ohne Handlung gilt
Alles bleibt wie bisher: Der Stromverbrauch zählt vollständig, nur die Aufteilung in Heizen und Kühlen fehlt. Sie beginnt
mit der eindeutigen Zuordnung und lässt sich nicht rückwirkend nachtragen.
