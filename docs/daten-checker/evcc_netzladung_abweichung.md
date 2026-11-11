# Netzladung aus evcc weicht vom Netzbezug zum Wallbox-Tarif ab

## Was eedc sieht
Die Wallbox trägt in den genannten Monaten neben «Netzbezug zum Wallbox-Tarif» einen PV-/Netz-Anteil der Ladung (etwa
aus evcc), und beide nennen eine andere Netzladung (mehr als 0,5 kWh bzw. 2 % Unterschied). eedc rechnet mit dem
Zähler des Versorgers: Netzladung = Netzbezug zum Wallbox-Tarif, PV-Ladung = Ladung minus Netzladung — für Ersparnis,
Heimladekosten und Stromrechnung.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich bei der Wallbox am Feld für die
   Netzladung.
2. Prüfen, ob beide Sensoren dieselbe Wallbox messen. Misst einer ein anderes Gerät oder einen anderen Zeitraum, die
   Zuordnung berichtigen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind
   und beide Werte übereinstimmen.

## Was ohne Handlung gilt
eedc nimmt den Netzbezug zum Wallbox-Tarif als Netzladung; der PV-/Netz-Anteil aus der anderen Quelle bleibt für diese
Monate unberücksichtigt.
