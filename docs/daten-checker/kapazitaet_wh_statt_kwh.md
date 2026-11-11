# Speicher-Kapazität vermutlich in Wh statt kWh

## Was eedc sieht
Das Balkonkraftwerk, zu dem dieser Speicher gehört, nennt seine Akku-Kapazität in Wh, dieser Speicher seine in kWh — und
beide tragen denselben Zahlenwert. Dann ist die Kapazität tausendfach zu groß, und Vollzyklen, Auslastung und
Wirtschaftlichkeit des Speichers rechnen gegen einen Nenner, den es nicht gibt. Geprüft wird nur dieser Widerspruch der
beiden Felder, keine Obergrenze — ein großer Speicher wird nicht gemeldet.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich beim Feld «Kapazität (kWh)».
2. Die Kapazität in kWh eintragen (die Meldung nennt die Zahl; 5.376 Wh sind 5,376 kWh) und speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Vollzyklen, Auslastung und Wirtschaftlichkeit des Speichers bleiben um den Faktor 1000 verzerrt.
