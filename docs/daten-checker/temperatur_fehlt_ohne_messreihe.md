# Ø Temperatur fehlt — keine eigene Messreihe

## Was eedc sieht
In einigen erfassten Monaten ist das Feld «Ø Temperatur» leer, und für keinen davon reicht deine eigene Messreihe der
Außentemperatur zurück. Betroffen sind vor allem Monate, die zwischen Juli und September 2026 abgeschlossen wurden — da
füllte eedc das Feld nicht selbst. eedc rechnet mit diesem Feld heute keine Kennzahl aus; es ist die Rückfallebene für
Zeiten ohne Tagesreihe. Die Details nennen die Monate.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der erste betroffene Monat öffnet sich zum Bearbeiten.
2. Im Abschnitt «Wetterdaten (optional)» auf «Auto-Fill» klicken und speichern — eedc holt den Wert aus dem
   Wetter-Archiv. Die übrigen Monate ebenso unter [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt weniger Monate.

## Was ohne Handlung gilt
Einmal täglich versucht eedc, leere Wetterfelder abgeschlossener Monate von der an der Anlage gewählten Quelle zu
füllen; ein Monat, für den sie an deinem Ort keinen gemessenen Wert liefert, bleibt ohne Ø Temperatur. Keine Kennzahl
rechnet heute mit dem Feld.
