# Modulleistung weit über der Wechselrichter-Leistung

## Was eedc sieht
An diesem Wechselrichter hängen mehr als doppelt so viele kWp Module, wie er Leistung hat. Überbelegung ist normal
(üblich 1,1 bis 1,3, bei Ost/West bis etwa 1,5) und wird nicht gemeldet — über 2 ist ein Eingabefehler
wahrscheinlicher als eine Auslegung, etwa die Wechselrichter-Leistung im kWp-Feld eines Strings.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Wechselrichters öffnet sich am Feld «Max. Leistung (kW)».
2. Dort gehört die Geräteleistung hin. Dann unter [Komponenten](eedc:/einstellungen/komponenten) die PV-Module an
   diesem Wechselrichter prüfen: in «Leistung (kWp)» gehört die Modulleistung (Anzahl × Wp).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden. Ist die Auslegung wirklich so,
   bleibt sie stehen.

## Was ohne Handlung gilt
Die Zeile ändert keine Berechnung; eedc rechnet mit den eingetragenen Werten.
