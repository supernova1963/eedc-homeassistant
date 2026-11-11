# Noch keine Tageswerte

## Was eedc sieht
Home Assistant ist erreichbar, aber es gibt noch keine Tageszeile mit Stundenwerten. Direkt nach der Einrichtung ist das
normal — die ersten Werte entstehen mit dem nächsten Lauf. Bleibt es dabei, fehlt meist die Zuordnung der kWh-Zähler: Es
müssen die kWh-Zeilen belegt sein, nicht nur die Watt-Zeilen.

## Lösungsweg
1. Nach der Einrichtung zuerst den nächsten Lauf abwarten.
2. Bleibt die Zeile: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) die kWh-Zähler zuordnen
   (Einspeisung, Netzbezug, PV und die Komponenten).
3. Zurückliegende Tage holt in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die
   Operation «Lücken aus HA-LTS nachfüllen».
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — statt dieser Zeile nennt die Kategorie die aktive Quelle als
   bestanden.

## Was ohne Handlung gilt
Ohne Tageszeilen bleiben die Tagesansicht im Cockpit, die Stundenwerte und das Energieprofil leer.
