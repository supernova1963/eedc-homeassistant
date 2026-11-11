# PV-Zuordnung am Wechselrichter wird nicht ausgewertet

## Was eedc sieht
Am Wechselrichter hängt ein PV-Zähler, oder dort ist ein PV-Monatswert von Hand gepflegt. Beides zählt nirgends mit:
eedc führt die PV-Erzeugung an den PV-Modulen und, für die ganze Anlage, in der Gruppe «Anlage (Basis)» der
Datenquellen. Solange die alte Zuordnung hängt, gilt die PV in der Zuordnung als abgedeckt, obwohl niemand den Sensor
liest — die Live-Anzeige rechnet dann aus der Leistung hoch und kann deutlich danebenliegen.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim PV-Feld des Wechselrichters.
2. Den Zähler dort zuordnen, wo eedc ihn liest: Misst du je String, beim jeweiligen PV-Modul. Hast du nur einen Zähler
   für die ganze Anlage, in der Gruppe «Anlage (Basis)» — eedc verteilt die Menge dann nach kWp auf deine Module.
3. Danach die alte Zuordnung am Wechselrichter entfernen (Quelle «Keine»); sie bleibt sichtbar, bis du sie löschst.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange am Wechselrichter eine Zuordnung oder
   ein gepflegter PV-Monatswert steht.

## Was ohne Handlung gilt
Der Sensor am Wechselrichter und sein Monatswert zählen nirgends; die PV-Erzeugung kommt allein aus Modulen und
Anlagenzähler.
