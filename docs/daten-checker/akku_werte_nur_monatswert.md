# Akku des Balkonkraftwerks nur als Monatswert erfasst

## Was eedc sieht
Lade- und Entlademengen stehen direkt am Balkonkraftwerk («Speicher Ladung», «Speicher Entladung»). In dieser Form gibt es
sie nur monatlich — im Live-Dashboard, im Tagesverlauf und im Energiefluss fehlt der Akku. Ein Akku mit allen Ansichten
ist eine eigene Komponente vom Typ Speicher, die zum Balkonkraftwerk gehört.

## Lösungsweg
1. Unter *Einstellungen → Komponenten → Speicher* mit «+» einen Speicher anlegen, bei «Gehört zu» dieses
   Balkonkraftwerk wählen und speichern.
2. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich; die Lade- und Entladesensoren beim
   neuen Speicher zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald ein Speicher zu diesem
   Balkonkraftwerk gehört.

## Was ohne Handlung gilt
Die gepflegten Monatswerte bleiben erhalten und werden weiter angezeigt; Live-Dashboard, Tagesverlauf und Energiefluss
zeigen den Akku nicht.
