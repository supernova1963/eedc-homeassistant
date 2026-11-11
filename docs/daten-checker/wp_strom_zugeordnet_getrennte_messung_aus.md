# Strom Heizen/Warmwasser zugeordnet, getrennte Messung aus

## Was eedc sieht
An der Wärmepumpe ist «Strom Heizen» oder «Strom Warmwasser» zugeordnet (Home-Assistant-Sensor oder MQTT), der Schalter
«Getrennte Strommessung (Heizen / Warmwasser)» an der Komponente ist aber aus. Diese Zähler zählt eedc nur mit Schalter
als Teile des Wärmepumpen-Stroms; ohne ihn rechnet es den Strom allein aus dem Gesamtzähler — Heizen und Warmwasser
bleiben leer, der ganze Strom steht unter „nicht aufgeteilt“. eedc schaltet nicht selbst um: der Schalter sagt, wie du
misst.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular der Wärmepumpe öffnet sich beim Schalter
   «Getrennte Strommessung (Heizen / Warmwasser)».
2. Den Schalter einschalten und speichern.
3. Nutzt du bewusst nur den Gesamtzähler, stattdessen in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei «Strom Heizen» und «Strom Warmwasser» die Quelle
   «Keine» wählen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Heizen und Warmwasser bleiben leer, der ganze Strom der Wärmepumpe steht unter „nicht aufgeteilt“.
