# Keine Abweichung zu Home Assistant

## Was eedc sieht
In den letzten 90 Tagen stimmt, was eedc gespeichert hat, mit der Langzeitstatistik von Home Assistant überein: die
PV-Tagessumme und jede andere zugeordnete Komponente einzeln (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung,
Netzbezug). Kein Tag weicht um mindestens 2 kWh und 5 % zugleich ab. Der Speicher ist hier nicht dabei — sein
Vorzeichen hat eine eigene Prüfung.

## Lösungsweg
1. Nichts zu tun — die Prüfung ist bestanden.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange eedc und Home Assistant übereinstimmen.

## Was ohne Handlung gilt
eedc und Home Assistant zeigen für diese Tage dieselben Zahlen.
