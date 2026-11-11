# Alle kWh- und Zählerstand-Sensoren in der Langzeitstatistik

## Was eedc sieht
Jeder zugeordnete kWh-Sensor und jeder Zählerstand-Sensor steht in der Langzeitstatistik von Home Assistant; die Zeile nennt
die Zahlen. Für die kWh-Sensoren wirken damit die Reparatur-Werkzeuge auf alle Felder. Für einen Zählerstand wird bewusst keine Summen-Spalte verlangt
— er kommt aus dem Sensor-Zustand, nicht aus einer Verbrauchssumme.

## Lösungsweg
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Prüfung steht weiter als bestanden im Kopf ihrer Kategorie.

## Was ohne Handlung gilt
eedc liest Zählerstände und Mengen weiter aus der Statistik von Home Assistant; Lücken lassen sich von dort nachholen.
