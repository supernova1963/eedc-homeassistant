# kWh-Sensoren nicht in der Langzeitstatistik von Home Assistant

## Was eedc sieht
Mindestens ein zugeordneter kWh-Sensor (etwa für Einspeisung, PV Erzeugung Gesamt oder den Stromverbrauch der Wärmepumpe)
hat in Home Assistant keine `state_class` — typisch bei Modbus-Rohwerten oder Hersteller-Integrationen ohne Angaben dazu.
Home Assistant führt für ihn keine Langzeitstatistik, und alle Reparatur-Werkzeuge der Reparatur-Werkbank lesen genau dort:
Für diese Felder wirken sie nicht. Jeder Aussetzer bleibt verloren. Die Details nennen die betroffenen Sensoren.

## Lösungsweg
1. Bevorzugt in Home Assistant unter *Einstellungen → Geräte & Dienste → Helfer* einen Verbrauchszähler auf diesen Sensor
   anlegen, Zurücksetzen „nie“ (ohne Zyklus). Der Helfer bringt die nötigen Statistik-Angaben mit und behält seinen Namen
   auch nach einem Gerätetausch.
2. Am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld; dort den
   Helfer zuordnen, oder einen anderen Sensor, der schon `state_class: total_increasing` trägt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

## Was ohne Handlung gilt
Live-Anzeigen funktionieren weiter. Die Reparatur-Werkzeuge wirken für diese Felder nicht, und eine Lücke bleibt eine Lücke.
Vergangenes sammelt Home Assistant auch nach der Umstellung nicht nach: Die Reihe beginnt ab der Umstellung.
