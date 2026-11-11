# PV-Ladung größer als Gesamtladung

## Was eedc sieht
An einer Wallbox oder einem E-Auto ist für den Monat die aus PV geladene Menge größer als die gesamte Ladung. Die
PV-Ladung ist ein Teil der Gesamtladung und kann nicht größer sein. eedc rechnet in dieser Lage mit PV + Netz weiter und
legt den eingetragenen Gesamtwert beiseite — die Ladung, die du siehst, ist dann nicht die, die du erfasst hast. Welcher
der beiden Werte stimmt, kann eedc nicht wissen.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss dieses Monats öffnet sich beim genannten Gerät.
2. Beide Werte prüfen und berichtigen: an der Wallbox «Ladung gesamt» und «Ladung PV», am E-Auto «Heim: gesamt» und
   «Heim: PV». Häufige Ursachen: ein Import hat nur eines der beiden Felder aktualisiert, oder Gesamt- und PV-Wert stammen
   aus zwei verschiedenen Quellen (Wallbox-Sicht gegen Fahrzeug-Sicht). Speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
In deinen Auswertungen steht keine falsche Zahl: eedc rechnet mit PV + Netz. Der eingetragene Gesamtwert bleibt aber
beiseitegelegt, bis einer der beiden Werte berichtigt ist.
