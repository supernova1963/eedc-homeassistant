# Strom der Wärmepumpe fehlt

## Was eedc sieht
Für die genannten Monate fehlt der Strom der Wärmepumpe — ohne getrennte Strommessung «Stromverbrauch», mit getrennter
Messung «Strom Heizen» und «Strom Warmwasser» (an einer Split-Klimaanlage nur «Strom Heizen»). Ohne ihn fehlen der
Verbrauch der Wärmepumpe und ihre Arbeitszahl in diesen Monaten.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Stromfeld
   der Wärmepumpe.
2. Den Wert eintragen und speichern, die übrigen Monate der Meldung ebenso. Mit zugeordnetem Sensor holt
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere Monate auf
   einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
Die Monate bleiben ohne Wärmepumpen-Strom; Verbrauch, Kosten und Arbeitszahl des Geräts rechnen für sie nicht.
