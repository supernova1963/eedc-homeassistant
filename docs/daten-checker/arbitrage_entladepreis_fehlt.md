# Arbitrage aktiv, Ø Entladepreis fehlt

## Was eedc sieht
Am Speicher ist «Arbitrage-fähig» eingeschaltet, aber der erwartete Ø Entladepreis fehlt — der Preis, den eine entladene
Kilowattstunde vermeidet. Gemeint ist der Erwartungswert in den Stammdaten des Speichers; aus ihm rechnen Prognose und
Wirtschaftlichkeit in die Zukunft. Gemessene Monatswerte ersetzen ihn nicht.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich im Abschnitt
   «Netzladung & Arbitrage» beim Feld «Ø Entladepreis (ct/kWh)».
2. Den vermiedenen Preis zur Spitzenlastzeit eintragen und speichern. Trag einen Wert über 0 ct/kWh ein: 0 zählt hier
   als nicht eingetragen, die Zeile bliebe stehen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
eedc rechnet die Arbitrage mit 35 ct/kWh als Entladepreis.
