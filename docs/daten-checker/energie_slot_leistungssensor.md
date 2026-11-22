# Leistungssensor in einem Energie-Feld

## Was eedc sieht
In einem Feld, das eine Energiemenge erwartet, steht ein Leistungssensor (W oder kW); verglichen wird die in Home Assistant
hinterlegte Einheit. Aus einem Leistungssensor lässt sich die Energie nur näherungsweise über die Zeit ableiten — ungenauer
und anfällig für Lücken. Die Meldung nennt das Feld, die Details die zugeordnete Entität.

## Lösungsweg
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich an diesem Feld.
2. Dort einen fortlaufenden kWh-Zähler wählen. Hat das Feld schon eigene Werte, fragt eedc vor dem Speichern
   **„Warum wechselt die Quelle?"** — hier passt meist **„Daten vor der Änderung löschen — das Feld beginnt mit dem neuen
   Sensor neu"**: die Werte dieses Felds aus der Zeit davor gehen weg, und eedc übernimmt, was Home Assistant für den neuen
   Zähler führt. Unter **„Was danach geschieht"** steht vorher, welche gespeicherten Monatswerte bleiben; das Löschen lässt
   sich nicht rückgängig machen (Handbuch Einstellungen, Abschnitt „Sensorwechsel“).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Aus dem Leistungssensor in diesem Feld entsteht kein Stunden- und kein Tageswert; nur wo eine Watt-Zeile mit einem
Leistungssensor belegt ist, schätzt eedc die Tagesenergie aus dessen Verlauf.
