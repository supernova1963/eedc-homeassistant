# Energiebilanz ergibt negativen Gesamtverbrauch

## Was eedc sieht
PV − Einspeisung + Netzbezug + Batterie-Entladung − Batterie-Ladung ergibt für den Monat deutlich weniger als 0 (unter
−0,5 kWh). Das ist unmöglich. Die Details listen alle Summanden auf. Häufige Ursachen: vertauschte Einspeisungs- und
Netzbezugs-Sensoren oder fehlende Batterie-Daten.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich beim Netzbezug.
2. Zuerst die Batterie-Werte vervollständigen (beim Speicher «Ladung» und «Entladung»), dann Einspeisung und Netzbezug
   gegeneinander prüfen. Speichern.
3. Ist die Bilanz weiter negativ, enthält PV-Erzeugung oder Einspeisung einen Eingabefehler; bei Werten aus Home
   Assistant die Zuordnung von Einspeisung und Netzbezug in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) prüfen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
Gesamtverbrauch, Eigenverbrauch und Autarkie des Monats stehen falsch.
