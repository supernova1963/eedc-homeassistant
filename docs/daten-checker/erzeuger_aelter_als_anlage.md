# Erzeuger älter als die Anlage

## Was eedc sieht
Ein PV-Modul oder Balkonkraftwerk wurde laut Anschaffungsdatum vor der Inbetriebnahme der Anlage angeschafft. Dann wurde
bereits Strom erzeugt, bevor die Anlage laut Stammdaten existierte — für die Monate dazwischen fragt eedc keine
Zählerwerte ab. Eines der beiden Daten stimmt nicht; der Befund nennt den ältesten Erzeuger und, wenn es mehrere sind,
ihre Zahl.

## Lösungsweg
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Inbetriebnahme (Anlage)».
2. Stimmt das Datum der Anlage nicht (der häufige Fall), es korrigieren und **«Speichern»**.
3. Stimmt stattdessen das «Anschaffungsdatum» des Erzeugers nicht, es unter
   [Komponenten](eedc:/einstellungen/komponenten) beim Gerät korrigieren. Andere Geräte (E-Auto, Wallbox, Wärmepumpe,
   Speicher) nie umdatieren, nur damit eine Zeile verschwindet — ihre echte Historie ginge verloren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Fehlen danach Monate ab dem neuen
   Datum, meldet sie der Daten-Checker einzeln.

## Was ohne Handlung gilt
Der erwartete Monatsbereich beginnt mit dem Datum der Anlage; für die Monate davor, in denen schon erzeugt wurde, gibt es
keine Bilanz und keine Meldung.
