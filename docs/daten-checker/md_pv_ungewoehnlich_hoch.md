# PV-Erzeugung ungewöhnlich hoch

## Was eedc sieht
Die PV-Erzeugung des Monats liegt über der Obergrenze. Liegt eine PVGIS-Prognose vor, ist das
PVGIS × Performance Ratio × 1,45 (ab sechs Monaten Historie), mindestens aber PVGIS × 1,5; ohne PVGIS-Prognose gilt ein
festes Maximum je Monat und kWp. Die Details nennen die verwendete Schwelle. Häufigste echte Ursache ist eine
Doppelerfassung: dieselbe Erzeugung an zwei Stellen zugeordnet.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monat öffnet sich bei der PV-Erzeugung. Wert prüfen: Eingabefehler,
   falscher Faktor (etwa Wh statt kWh)?
2. Stimmt der Monatswert, die Zuordnung prüfen: steht dieselbe Erzeugung an zwei Stellen (Anlagenzähler und Modul, oder
   zwei Module mit demselben Sensor)? Das meldet auch die Prüfung «PV – Doppelerfassungs-Verdacht».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach einer Berichtigung ist der Monat aus der Zeile
   verschwunden. War es ein strahlungsreicher Monat, bleibt der Hinweis als Auskunft stehen und sagt, mit welcher Zahl
   eedc rechnet.

## Was ohne Handlung gilt
eedc rechnet mit dem erfassten Wert — Ersparnis, Autarkie und Vergleiche des Monats folgen ihm.
