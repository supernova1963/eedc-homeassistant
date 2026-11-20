# Zählerstand springt in einer MQTT-Reihe

## Was eedc sieht
Bei MQTT ist der Zählerstand, den der Publisher sendet, die Quelle; eedc bildet daraus je Stunde die Menge nach der Regel von
Home Assistant. In der genannten Stunde wechselt der Stand die Höhe: er springt nach oben, beginnt neu, aber nicht bei 0, oder
fällt um weniger als ein Zehntel. eedc zählt den Unterschied als Menge dieser Stunde — in Tag, Monat und Jahr. So sieht es aus,
wenn der Zähler oder das Gerät getauscht wurde oder ein anderes Gerät auf demselben Topic sendet. Die Meldung nennt Feld, Tag
und Uhrzeit, die Details den Stand davor und danach und die Menge, die eedc für die Stunde zählt.

## Lösungsweg
1. Am Befund **«Zähler getauscht»** klicken — in den Datenquellen öffnet sich beim Feld der Dialog **«Zähler getauscht (gleiche
   Quelle)»**; **«Getauscht am»** steht auf der Zeit, zu der der Zählerstand springt.
2. Die Sätze im Dialog lesen: Sie nennen die Zeit des Sprungs, den Stand davor und danach und — ist die Stunde schon
   gespeichert — was sie danach zählt.
3. **«Eintragen»** klicken. Darunter steht «Ein Eintrag lässt sich nicht zurücknehmen.»
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Stunde ist aus der Liste verschwunden.

Stimmt der Sprung (der Zähler hat wirklich so viel gezählt), ist nichts zu tun. Sendet der Publisher den Tageswert statt des
fortlaufenden Stands, gilt [Zählerstand springt zwischendurch zurück](#zaehler_ruecksprung).

## Was ohne Handlung gilt
Die Stunde zählt den Unterschied der Zählerstände als Menge, und Tag, Monat und Jahr enthalten ihn. Nach dem Eintrag zählt die
Stunde nur, was der alte Zähler bis zu seinem letzten und der neue ab seinem ersten Stand gezählt hat (aus den gespeicherten
Zählerständen der letzten 31 Tage; ältere sind nicht mehr gespeichert — dann zählt die Stunde des Tauschs keinen Zuwachs). Die
Live-Anzeige rechnet direkt aus den Zählerständen: sie zeigt den Sprung am Tag des Sprungs unter „heute“ und am Tag danach
unter „gestern“, auch nach dem Eintrag.
