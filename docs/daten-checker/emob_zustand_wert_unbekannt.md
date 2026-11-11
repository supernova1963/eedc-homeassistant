# Zustand der E-Mobilität mit unbekanntem Wert

## Was eedc sieht
Ein zugeordneter Zustand der E-Mobilität («Ladezustand», «Lademodus», «Ladezustand (Fahrzeug)», «Zu Hause» oder eines
der Felder «evcc: Fahrzeug verbunden», «evcc: lädt», «evcc: Laden freigegeben») liefert gerade einen Wert, den eedc nicht
kennt. eedc zeigt dann keinen Zustand an. Die Details nennen den gelieferten Wert und die
Wörter, die eedc versteht; Groß-/Kleinschreibung ist egal.

## Lösungsweg
1. In eedc ist dafür nichts umzustellen — der Wert kommt von deinem Gerät. In Home Assistant unter
   *Einstellungen → Geräte & Dienste → Helfer* einen Template-Sensor anlegen, der aus deinen Werten eines der Wörter
   macht, die eedc versteht (Werte-Tabelle im Handbuch «Einstellungen»,
   [Abschnitt 7.10](HANDBUCH_EINSTELLUNGEN.md#710-zustand-und-sitzung-e-mobilität)).
2. Den neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät an diesem Zustand
   zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald der neue Sensor einen
   bekannten Wert liefert; mit dem alten Sensor bleibt sie stehen.

## Was ohne Handlung gilt
eedc zeigt für diesen Zustand nichts an, solange der Sensor den unbekannten Wert liefert. Mit einem bekannten Wert
erscheint der Zustand wieder.
