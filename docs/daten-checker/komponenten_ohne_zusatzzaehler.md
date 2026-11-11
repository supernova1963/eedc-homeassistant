# Komponenten ohne Zusatz-Zähler für Tageswerte

## Was eedc sieht
Es geht um zusätzliche Messstellen: Wärmemengenzähler einer Wärmepumpe (Heizwärme, Warmwasser-Wärme) und die getrennte
PV-Ladung an Wallbox oder E-Auto. Diese Werte lassen sich nur aus einem eigenen kumulativen Zähler ableiten; ohne ihn
bleiben sie in der Tagesansicht im Cockpit auf „—“. Kein Fehler — solche Zähler hat längst nicht jede Anlage. Eine
Split-Klimaanlage wird nicht nach Wärme gefragt, eine Brauchwasser-Wärmepumpe nicht nach Heizwärme.

## Lösungsweg
1. Hast du einen solchen Zähler: am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der
   ersten genannten Komponente — und das kWh-Feld zuordnen.
2. Hast du keinen: nichts zu tun. Die Monatswerte pflegst du bei Bedarf im Monatsabschluss von Hand.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die zugeordneten Komponenten sind aus der Zeile verschwunden;
   ohne Zähler bleibt sie als Hinweis stehen.

## Was ohne Handlung gilt
Die Monatsauswertungen sind nicht betroffen. Nur die genannten Tageswerte bleiben in der Tagesansicht im Cockpit auf „—“.
