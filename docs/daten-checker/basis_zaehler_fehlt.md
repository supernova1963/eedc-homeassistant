# Kein Basis-Zähler für Einspeisung oder Netzbezug

## Was eedc sieht
In der Datenquellen-Zuordnung fehlt der kumulative kWh-Zähler für Einspeisung, Netzbezug oder beide. Ohne ihn bleibt der
bilanzielle Gesamtverbrauch im Energieprofil leer — und damit auch die Grundlast, die als Median der Nachtstunden daraus
gebildet wird (Monatsansicht im Cockpit, Monatsbericht, HA-Sensor `eedc_grundlast_kw`). Als zugeordnet gilt ein Feld mit
einem Sensor aus Home Assistant oder mit Zählerständen, die in der letzten Woche per MQTT angekommen sind.

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim fehlenden Zähler.
2. Den kumulativen kWh-Zähler zuordnen, nicht den Leistungs-Sensor in Watt. Schickst du die Werte per MQTT, den
   Publisher prüfen: auf dem Topic kam seit über sieben Tagen nichts an.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — an der Stelle steht «Basis-Zähler (Einspeisung + Netzbezug)
   gemappt».

## Was ohne Handlung gilt
Gesamtverbrauch und Grundlast bleiben im Energieprofil leer. Die Monatswerte kannst du weiter im Monatsabschluss von Hand
pflegen.
