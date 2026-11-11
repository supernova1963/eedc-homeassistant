# Monat fehlt

## Was eedc sieht
Für einen abgeschlossenen Monat ab der Inbetriebnahme gibt es keinen Monatsabschluss — Einspeisung und Netzbezug fehlen.
Ohne sie gibt es keine Bilanz: eedc kann nicht sagen, woher der Strom eines Geräts kam, und rechnet den Monat weder in den
Jahreswert noch in den Community-Vergleich. Mehrere fehlende Monate stehen als eine Zeile «n Monate fehlen» mit einem
Glied je Monat; über zwölf hinaus nennt die Zeile die Zahl der weiteren.

## Lösungsweg
1. Am Befund ein Glied (den Monat) oder **«Monat erfassen»** klicken — der Monatsabschluss dieses Monats öffnet sich.
2. Einspeisung und Netzbezug eintragen (auch 0 ist ein Wert) und speichern. Mit zugeordneten Zählern in Home Assistant
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere Monate
   auf einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
Der Monat bleibt leer: Jahreswerte, Amortisation und Community-Vergleich rechnen ohne ihn und sind entsprechend
unvollständig. eedc setzt keine 0 und schätzt nichts.
