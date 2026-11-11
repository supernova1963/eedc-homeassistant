# kWh-Sensoren ohne Summen-Spalte — Tages- und Stundenwerte bleiben leer

## Was eedc sieht
Diese kWh-Sensoren stehen in der Langzeitstatistik von Home Assistant, aber mit `state_class: measurement` statt
`total_increasing`. Home Assistant führt dann nur Mittel-, Minimal- und Maximalwerte und keine Zählerstände — eedc kann
daraus keine Stunden- und Tagesmengen bilden. Die Live-Ansicht ist nicht betroffen, sie rechnet aus den Watt-Sensoren;
deshalb stehen dort Werte, während die Tagesansicht im Cockpit und die Stundenwerte 0 zeigen.

## Lösungsweg
1. In Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor anlegen,
   Zurücksetzen „nie“ (ohne Zyklus) — er führt die Summen-Spalte. Wer die YAML ohnehin pflegt, kann stattdessen
   `state_class: total_increasing` per `customize` setzen (Neustart von Home Assistant nötig).
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen.
3. Die Tage danach in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere
   Tage neu aggregieren» neu berechnen — Home Assistant sammelt die Summenwerte erst ab der Umstellung.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor eine
   Summen-Spalte hat.

## Was ohne Handlung gilt
Tagesansicht im Cockpit und Stundenwerte bleiben für diese Felder auf 0, die Live-Ansicht zeigt weiter Werte. Vergangenes
sammelt Home Assistant nicht nach.
