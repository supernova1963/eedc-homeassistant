# Tage mit mehr Einspeisung als Erzeugung

## Was eedc sieht
An diesen Tagen wurde mehr ins Netz eingespeist, als PV und Speicher-Entladung zusammen geliefert haben (Toleranz
0,5 kWh; Entladung ins Netz ist erlaubt). Eigenverbrauch und Autarkie stehen dort auf 0 bzw. „—“. Die Details listen die
Tage mit allen drei Mengen. Häufige Ursachen: der PV-Zähler liefert nicht (steht auf 0), Einspeisung und Netzbezug sind
vertauscht, oder das Vorzeichen eines kombinierten Netz-Sensors ist umgekehrt.

## Lösungsweg
1. Zuerst die Zuordnung prüfen: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) nachsehen, ob der
   PV-Zähler liefert und ob Einspeisung und Netzbezug richtig herum zugeordnet sind; Fehler dort berichtigen.
2. Danach am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** (höchstens 31 Tage je Lauf).
   Kommen die Tage aus der Statistik von Home Assistant, heißt der Knopf **«Aus Home Assistant neu übernehmen»** — dann
   vorher die Statistik in Home Assistant unter *Entwicklerwerkzeuge → Statistik* berichtigen. Steht am Befund nur
   **«Was gilt»**, kommen die Mengen aus eedcs eigenen Zählerständen; dann wirkt die berichtigte Zuordnung auf die
   folgenden Tage.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die berichtigten Tage sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
An diesen Tagen stehen Eigenverbrauch und Autarkie auf 0 bzw. „—“; Tag und Monat rechnen mit den Mengen, wie sie gemessen
sind.
