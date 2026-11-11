# Zähler-Sensoren ohne state_class — Reparatur-Werkzeuge wirken nicht

## Was eedc sieht
Zähler-Felder wie die Kompressor-Starts einer Wärmepumpe liest eedc stündlich mit, und das funktioniert live. Ohne
`state_class` führt Home Assistant für sie aber keine Langzeitstatistik — die Reparatur-Werkzeuge der Reparatur-Werkbank
lesen genau dort und greifen nicht. Jeder Aussetzer (Neustart, hängende Abfrage) bleibt verloren; im Normalbetrieb fehlt
zusätzlich häufig die letzte Stunde des Tages (23–24 Uhr). Die Details nennen die betroffenen Sensoren.

## Lösungsweg
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus). Wer die YAML ohnehin pflegt, kann `state_class` stattdessen per `customize` ergänzen.
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

## Was ohne Handlung gilt
Die Zähler laufen live weiter; Aussetzer lassen sich nicht nachholen. Die Historie des Helfers beginnt bei null —
Vergangenes sammelt Home Assistant nicht nach.
