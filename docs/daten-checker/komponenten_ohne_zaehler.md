# Komponenten ohne vollständige kWh-Zähler

## Was eedc sieht
Mindestens eine aktive Komponente hat nicht alle erwarteten kWh-Zähler zugeordnet; die Meldung nennt die Komponenten und
die fehlenden Felder. Für sie bleibt das Energieprofil leer — Prognose-IST, Lernfaktor und Monatsberichte fehlen. Bei
einem Speicher oder einer PV-Erzeugung kommt die teuerste Folge hinzu: der Gesamtverbrauch je Stunde
(PV + Netzbezug − Einspeisung − Speicher) rechnet den fehlenden Anteil als 0 und fällt zu niedrig aus — mit ihm die
Grundlast (Monatsansicht im Cockpit, Monatsbericht, HA-Sensor `eedc_grundlast_kw`). Diese Zahl sieht plausibel aus.
Wärmepumpe, Wallbox und E-Auto verfälschen Gesamtverbrauch und Grundlast nicht; bei ihnen bleiben nur die eigenen
Auswertungen leer.

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der ersten genannten Komponente.
2. Je Komponente die kWh-Zeilen belegen, nicht nur die Watt-Zeilen; ein Speicher braucht Ladung und Entladung. Liefert
   ein Gerät nur Leistung (W), baut Home Assistant unter *Helfer → „Integral-Sensor“* (Riemannsche Summe) einen
   kWh-Zähler daraus. Für die übrigen Komponenten der Liste diesen Schritt wiederholen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — an der Stelle steht «Alle … aktiven Komponenten haben
   kWh-Zähler gemappt».

## Was ohne Handlung gilt
Die Auswertungen dieser Komponenten bleiben leer; fehlt der Zähler an einem Speicher oder einer PV-Erzeugung, stehen
Gesamtverbrauch und Grundlast zu niedrig. Ein Feld, für das du «Keine» gewählt hast, zählt als ohne Zähler — die Zeile
bleibt dann stehen.
