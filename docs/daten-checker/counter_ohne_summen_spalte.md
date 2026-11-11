# Zähler-Sensoren ohne Summen-Spalte — Reparatur-Werkzeuge wirken nicht

## Was eedc sieht
Diese Zähler-Felder liest eedc stündlich mit, und der laufende Betrieb funktioniert. Ihr `state_class` ist aber
`measurement` statt `total_increasing`, deshalb führt Home Assistant für sie keine Summen-Spalte — und alle
Reparatur-Werkzeuge der Reparatur-Werkbank lesen genau die. Ein Aussetzer lässt sich damit nicht nachholen. Die Details
nennen die betroffenen Sensoren.

## Lösungsweg
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus) — er führt die Summen-Spalte und behält seinen Namen auch nach einem Gerätetausch. Wer
   die YAML ohnehin pflegt, kann stattdessen `state_class: total_increasing` per `customize` setzen (Neustart von Home
   Assistant nötig).
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor eine
   Summen-Spalte hat.

## Was ohne Handlung gilt
Der laufende Betrieb erfasst die Zähler weiter; Aussetzer bleiben verloren. Die Historie des Helfers beginnt bei null —
Vergangenes sammelt Home Assistant nicht nach.
