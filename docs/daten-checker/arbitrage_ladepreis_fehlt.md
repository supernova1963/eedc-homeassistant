# Arbitrage aktiv, Ø Ladepreis fehlt

## Was eedc sieht
Am Speicher ist «Arbitrage-fähig» eingeschaltet, aber der erwartete Ø Ladepreis fehlt. Gemeint ist der Erwartungswert in
den Stammdaten des Speichers — aus ihm rechnen Prognose und Wirtschaftlichkeit in die Zukunft. Der gemessene Monatswert
«Ø Ladepreis» im Monatsabschluss und ein zugeordneter Preis-Sensor ersetzen ihn nicht: sie messen, was war, dieser
schätzt, was kommt.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich im Abschnitt
   «Netzladung & Arbitrage» beim Feld «Ø Ladepreis (ct/kWh)».
2. Den Preis eintragen, zu dem der Speicher im Niedrigtarif-Fenster lädt (etwa bei negativen Börsenpreisen), und
   speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
eedc rechnet die Arbitrage mit 12 ct/kWh als Ladepreis.
