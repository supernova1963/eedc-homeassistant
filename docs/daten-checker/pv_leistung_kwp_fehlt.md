# Leistung der PV-Module fehlt

## Was eedc sieht
Diesen PV-Modulen fehlt die Leistung in kWp. Ohne sie greift die Prüfung der Anlagenleistung gegen die Module nicht, die
Verteilung eines Gesamtwerts nach kWp kennt den Anteil dieser Module nicht, und das PVGIS-Soll je String fehlt.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der PV-Module öffnet sich beim Feld «Leistung (kWp)».
2. Die Leistung eintragen und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Die kWp-Summe der Anlage ist unvollständig; Soll-Werte und Prognose je String fehlen für diese Module.
