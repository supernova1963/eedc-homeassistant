# Gesamtzähler kleiner als Strom Heizen und Strom Warmwasser

## Was eedc sieht
Bei getrennter Strommessung mit zusätzlichem Gesamtzähler sind «Strom Heizen» und «Strom Warmwasser» Teile des
Gesamtverbrauchs und können zusammen nicht mehr sein. In diesen Monaten sind sie es. Meist misst der Gesamtzähler nur
einen Teil des Geräts (nur das Außengerät, nur einen Stromkreis), oder eine der Achsen zählt fremden Verbrauch mit.
Nur diese Richtung ist ein Fehler; ein höherer Gesamtzähler ist der Normalfall (Standby, Steuerung, Umwälzpumpen).

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «Stromverbrauch» der Wärmepumpe.
2. Prüfen, welcher Zähler welchen Wert liefert, und den falschen berichtigen. Kommt er aus Home Assistant, die Zuordnung
   in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=stromverbrauch_kwh) prüfen.
3. Sagt die Meldung, dass der Gesamtwert aus dem Monatsformular stammt, kann er ein stehen gebliebener alter Stand sein:
   das Feld «Stromverbrauch» leeren und speichern — eedc rechnet ihn dann aus Heizen und Warmwasser. Ist er der Wert
   eines eigenen Gesamtzählers, lass ihn stehen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc rechnet in diesen Monaten mit der Summe der beiden Achsen, damit nichts verloren geht.
