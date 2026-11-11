# Einspeisung größer als PV-Erzeugung

## Was eedc sieht
Für den Monat ist mehr Einspeisung erfasst als PV-Erzeugung — du kannst nicht mehr einspeisen, als du erzeugst. Häufigste
Ursache: Einspeisungs- und Netzbezugs-Sensor sind vertauscht, oder das Vorzeichen eines kombinierten Netz-Sensors ist
umgekehrt. Ebenso häufig ist die Erzeugung nur teilweise erfasst (ein String fehlt in den Komponenten). Liegen die
Tageswerte zusammen um mehr als 20 % und zugleich mehr als 20 kWh (die größere der beiden Grenzen) über dem
Monatswert, sagen das die Details zuerst: dann wurde der Monat nach einer Reparatur der Tage nie nachgezogen.

## Lösungsweg
1. Nennen die Details höhere Tageswerte: im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) «Vorschau laden» — bereits belegte
   Monate stehen dort unter «Konflikte» und sind zum Überschreiben vorausgewählt; vor dem Import einmal durchsehen.
2. Sonst am Befund **«Monat öffnen»** klicken — der Monat öffnet sich bei der Einspeisung. Einspeisung und PV-Erzeugung
   prüfen und berichtigen; bei vertauschten Sensoren die Zuordnung in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) richtigstellen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
Eigenverbrauch und Autarkie des Monats stehen falsch, solange einer der beiden Werte nicht stimmt.
