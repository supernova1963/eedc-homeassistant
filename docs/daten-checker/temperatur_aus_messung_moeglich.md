# Ø Temperatur fehlt — eigene Messwerte reichen

## Was eedc sieht
In einigen erfassten Monaten ist das Feld «Ø Temperatur» leer; für einen Teil davon liegen eigene Messwerte der
Außentemperatur vor. Betroffen sind vor allem Monate, die zwischen Juli und September 2026 abgeschlossen wurden — da
füllte eedc das Feld nicht selbst. eedc rechnet mit diesem Feld heute keine Kennzahl aus (Außentemperatur-Linie und
Vergleich je Heizgradtag lesen die Tagesreihe); es ist die Rückfallebene für Zeiten ohne diese Reihe. Die Zeile nennt
beide Zahlen.

## Lösungsweg
1. Am Befund **«Temperatur aus Messung übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**. eedc trägt die
   erreichbaren Monate aus deinen Messwerten nach (Stundenmittel, sonst Tages-Min/Max); bereits gepflegte Werte bleiben
   unberührt, mehrfaches Ausführen ist gefahrlos.
2. Für die übrigen Monate (die Details nennen sie): den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen, im Abschnitt «Wetterdaten (optional)» auf
   «Auto-Fill» klicken und speichern — eedc holt den Wert dann aus dem Wetter-Archiv.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; bleiben Monate ohne
   eigene Messwerte, steht statt ihrer die Zeile «Ø Temperatur fehlt in n Monat(en)» mit dem Knopf «Monat öffnen».

## Was ohne Handlung gilt
Einmal täglich füllt eedc leere Ø Temperaturen abgeschlossener Monate von selbst — zuerst aus deinen Messwerten, sonst
aus dem Archiv der an der Anlage gewählten Quelle; Voraussetzung sind hinterlegte Koordinaten der Anlage. Der Knopf
erledigt es sofort. Keine Kennzahl rechnet heute mit dem Feld.
