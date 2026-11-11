# Aufteilung nach Betriebsart nicht gespeichert

## Was eedc sieht
Die gemessenen Stunden ergeben für Heizen, Kühlen und Warmwasser zusammen mehr Strom, als im Monatsabschluss für das
ganze Gerät eingetragen ist — oder für den Monat ist gar kein Stromverbrauch eingetragen. Eine Teilmenge kann nicht
größer sein als das Ganze; deshalb hat eedc die Aufteilung beim Abschluss nicht gespeichert, und die Auswertungen zeigen
den Monat als „nicht aufgeteilt“. Die Meldung nennt den Monat und beide Mengen.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss dieses Monats öffnet sich bei der Wärmepumpe.
2. Den Stromverbrauch prüfen: Stimmt er, oder fehlt ein Zähler? Fehlt der Wert, eintragen.
3. Oder in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) prüfen, ob die Leistung des Geräts richtig
   zugeordnet ist.
4. Nach dem Berichtigen den Monat erneut speichern — eedc rechnet die Aufteilung dann neu.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Der Monat bleibt „nicht aufgeteilt“: die Sichten der Wärmepumpe zeigen für ihn keinen Heiz-, Kühl- oder
Warmwasserstrom.
