# Zählerstand springt in einer MQTT-Reihe

## Was eedc sieht
Bei MQTT ist der Zählerstand, den der Publisher sendet, die Quelle; eedc bildet daraus je Stunde die Menge nach der Regel von
Home Assistant. In der genannten Stunde wechselt der Stand die Höhe: er springt nach oben, beginnt neu, aber nicht bei 0, oder
fällt um weniger als ein Zehntel — oder er zeigt innerhalb der Stunde kurz eine andere Höhe (etwa 0 oder den Stand eines anderen
Geräts) und steht danach wieder auf dem alten Zähler. eedc zählt den Unterschied bzw. den ganzen Stand als Menge dieser Stunde —
in Tag, Monat und Jahr. So sieht es aus, wenn der Zähler oder das Gerät getauscht wurde, das Gerät kurz 0 meldet oder ein anderes
Gerät auf demselben Topic sendet. Die Meldung nennt Feld, Tag und Uhrzeit, die Details den Stand davor und danach und die Menge,
die eedc für die Stunde zählt.

## Lösungsweg
1. Am Befund **«Zähler getauscht»** klicken — in den Datenquellen öffnet sich beim Feld der Dialog **«Zähler getauscht (gleiche
   Quelle)»**; **«Getauscht am»** steht auf der Zeit, zu der der Zählerstand springt bzw. zurückkehrt.
2. Die Sätze im Dialog lesen: Sie nennen die Zeit des Sprungs, den Stand davor und danach und — ist die Stunde schon
   gespeichert — was sie danach zählt. Ändert sich der Stand dort mit einem einzelnen Schritt, den eedc nicht von gezähltem
   Verbrauch unterscheiden kann (etwa nachdem er eine Zeit lang still stand), sagt der Dialog das und nennt die Menge, die nach
   dem Eintrag nicht zählt.
3. **«Eintragen»** klicken. Darunter steht «Ein Eintrag lässt sich nicht zurücknehmen.»
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach dem Eintrag ist die Stunde aus der Liste verschwunden. Steht im
   Dialog statt **«Eintragen»** ein Satz, dass dort kein Sprung zu sehen ist oder die Stunde danach weniger als nichts zählte,
   ist nichts eingetragen: die Zeit unter **«Getauscht am»** prüfen.

Stimmt der Sprung (der Zähler hat wirklich so viel gezählt), ist nichts zu tun. Für die letzten 31 Tage prüft eedc dazu die
gespeicherten Zählerstände: die Prüfung nennt eine Stunde nur, wenn der Stand dort die Höhe wechselt oder sich mit einem
einzelnen Schritt ändert, der fast die ganze Menge der Stunde trägt. Ändert er sich gleichmäßig (etwa beim Laden) oder in zwei
ähnlich großen Schritten, nennt sie die Stunde nicht, und der Dialog trägt dort nichts ein — die Menge zählt.
Sendet der Publisher den Tageswert statt des fortlaufenden Stands, gilt [Zählerstand springt zwischendurch zurück](#zaehler_ruecksprung).

## Was ohne Handlung gilt
Die Stunde zählt den Unterschied der Zählerstände als Menge, und Tag, Monat und Jahr enthalten ihn. Nach dem Eintrag zählt die
Stunde nur, was der alte Zähler bis zu seinem letzten und der neue ab seinem ersten Stand gezählt hat (aus den gespeicherten
Zählerständen der letzten 31 Tage; ältere sind nicht mehr gespeichert — dann zählt die Stunde des Tauschs keinen Zuwachs). Die
Live-Anzeige rechnet direkt aus den Zählerständen: sie zeigt den Sprung am Tag des Sprungs unter „heute“ und am Tag danach
unter „gestern“, auch nach dem Eintrag.
