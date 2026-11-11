# Netzladung der Wallbox größer als der gemeinsame Netzbezug

## Was eedc sieht
Beim gemeinsamen Zähler für Wärmepumpe und Wallbox ist in den genannten Monaten die Netzladung der Wallbox (Wert aus
evcc bzw. Tagesquote) größer als «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)». eedc setzt den Wallbox-Teil
auf den gemeinsamen Netzbezug; der Wärmepumpe bleibt dann kein Netzanteil.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der Wärmepumpe am Feld
   «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)»; ist nicht eindeutig, welche Wärmepumpe den gemeinsamen Zähler
   trägt, öffnet sie sich ohne Feld.
2. Den gemeinsamen Zähler prüfen (Zähler vor beiden Geräten minus Zähler danach) und die Netzladung der Wallbox: misst
   ihr Sensor wirklich nur Netzstrom dieser Wallbox?
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind.

## Was ohne Handlung gilt
Der gemeinsame Netzbezug geht ganz an die Wallbox; die Wärmepumpe rechnet in diesen Monaten ohne Netzanteil zum Tarif.
