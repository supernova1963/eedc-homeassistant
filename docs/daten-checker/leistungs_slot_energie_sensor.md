# Energie-Sensor in einem Leistungs-Feld

## Was eedc sieht
In einem Feld, das eine Momentanleistung erwartet, steht ein kWh-Zähler; verglichen wird die in Home Assistant hinterlegte
Einheit. Der Zählerstand wird dann als Leistung gelesen (aus 7130 kWh werden 7130 W), und im Live-Energiefluss klemmt der
berechnete Restverbrauch auf 0. Die Meldung nennt das Feld, die Details die zugeordnete Entität.

## Lösungsweg
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich an diesem Feld.
2. Dort einen Leistungssensor (W oder kW) wählen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Der Live-Energiefluss rechnet mit dem Zählerstand als Leistung weiter falsch.
