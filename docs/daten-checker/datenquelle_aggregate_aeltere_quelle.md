# Tageswerte stammen noch aus einer älteren Quelle

## Was eedc sieht
Die Langzeitstatistik von Home Assistant ist erreichbar, die jüngste Tageszeile wurde aber noch auf einem anderen Weg
geschrieben, etwa beim Monatsabschluss. Die Meldung nennt das Datum und die Quelle. Sobald diese Tage neu aus der Statistik
aufgebaut sind, gilt sie als Quelle.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc baut die jüngsten Tage bis zum
   genannten Tag (höchstens 31 Tage, höchstens bis gestern) aus der Statistik neu auf; Tage, die eedc schon direkt aus Home
   Assistant führt, fasst der Knopf nicht an.
2. Steht am Befund kein solcher Knopf, gibt es in diesem Fenster keinen Tag, den eedc neu aufbauen müsste. Einen einzelnen
   Tag baut in der [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Tag neu
   aggregieren» neu auf.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — statt dieser Zeile nennt die Kategorie die Statistik von Home
   Assistant als aktive Quelle.

## Was ohne Handlung gilt
Die Tage behalten ihre Werte aus der älteren Quelle. Der nächste Monatsabschluss oder eine Tag-Reparatur baut sie aus der
Statistik neu auf.
