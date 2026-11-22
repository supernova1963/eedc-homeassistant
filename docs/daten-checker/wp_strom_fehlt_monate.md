# Strom der Wärmepumpe fehlt

## Was eedc sieht
Für die genannten Monate fehlt der Strom der Wärmepumpe — ohne getrennte Strommessung «Stromverbrauch», mit getrennter
Messung «Strom Heizen» und «Strom Warmwasser» (an einer Split-Klimaanlage nur «Strom Heizen»). Ohne ihn fehlen der
Verbrauch der Wärmepumpe und ihre Arbeitszahl in diesen Monaten.

Genannt wird auch ein Monat, in dem der Strom mit **0 kWh** eingetragen ist, obwohl die Wärmepumpe in diesem Monat Wärme
abgegeben hat (die Meldung sagt dann „fehlt oder ist 0 kWh bei erfasster Wärme“ und nennt diese Monate getrennt). Wärme
ohne Strom gibt es nicht — meist hat der Stromzähler in diesem Monat nicht gezählt oder der Wert wurde nicht übernommen.
Ein Monat mit Strom und Wärme 0 (die Wärmepumpe lief nicht) und ein Monat nur mit Strom (Bereitschaft) sind kein Befund.
Sind ohne «Getrennte Strommessung» nur «Strom Heizen»/«Strom Warmwasser» zugeordnet, nennt das der Befund
„Strom Heizen/Warmwasser zugeordnet, aber „Getrennte Strommessung“ ist aus“.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Stromfeld
   der Wärmepumpe.
2. Den gemessenen Wert eintragen (statt der 0, wo die Meldung sie nennt) und speichern, die übrigen Monate der Meldung
   ebenso. Liegt der Fehler am Zähler oder Sensor in Home Assistant, dort zuerst berichtigen. Mit zugeordnetem Sensor holt
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere Monate auf
   einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
Die Monate bleiben ohne Wärmepumpen-Strom; Verbrauch, Kosten und Arbeitszahl des Geräts rechnen für sie nicht. Trägt ein solcher Monat Wärme, zählt er so lange auch keine Ersparnis gegenüber der alten Heizung (ohne Strom ist sie nicht bestimmbar).
