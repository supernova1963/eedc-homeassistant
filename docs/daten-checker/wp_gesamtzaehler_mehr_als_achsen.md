# Gesamtzähler misst deutlich mehr als die Achsen

## Was eedc sieht
Mehr als ein Viertel des Wärmepumpen-Stroms liegt weder auf «Strom Heizen» noch auf «Strom Warmwasser»; eedc führt diese
Menge als „nicht aufgeteilt“. Das ist oft richtig — Standby, Steuerung und Umwälzpumpen laufen auf keiner der beiden
Achsen. Es kann aber auch heißen, dass am Gesamtzähler noch etwas anderes hängt als die Wärmepumpe. Eine Frage, kein
Fehler: eedc weiß nicht, was am Zähler hängt, und behauptet es nicht.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gesamtzähler
   («Stromverbrauch») dieser Wärmepumpe.
2. Prüfen, ob der zugeordnete Sensor nur die Wärmepumpe misst. Stimmt er, ist nichts zu tun.
3. Sagt die Meldung, dass der Gesamtwert aus dem Monatsformular stammt, kann er ein stehen gebliebener alter Stand sein:
   im Monatsabschluss das Feld «Stromverbrauch» leeren und speichern — eedc rechnet ihn dann aus Heizen und Warmwasser.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — stimmt der Zähler, bleibt die Zeile als Auskunft stehen.

## Was ohne Handlung gilt
Der Rest steht weiter als „nicht aufgeteilt“; Verbrauch, Kosten und CO₂ rechnen mit dem vollen Gesamtzähler.
