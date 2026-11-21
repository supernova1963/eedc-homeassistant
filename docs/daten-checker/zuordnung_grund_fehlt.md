# Zuordnung eines Zählers geändert, Grund fehlt

## Was eedc sieht
Die Quelle eines Zählerfelds wurde gewechselt, als das Feld schon eigene Werte hatte — aber nicht verzeichnet ist, warum:
der Wechsel stammt aus der Zeit, bevor eedc beim Wechsel nach dem Grund gefragt hat, oder aus einem Hinweis
„Zuordnung geändert“, der noch offen war. eedc weiß deshalb nicht, ob die bisherigen Werte bleiben (der neue Sensor setzt
fort, etwa nach einem Zählertausch) oder verworfen werden (bisher war der falsche Sensor zugeordnet). Die Meldung nennt Gerät, Feld und den Tag des
Wechsels; Uhrzeit und beide Quellen stehen in den Details. Gemeldet wird nur ein Wechsel, nach dem eedc heute fragen
würde — nicht ein Wechsel auf „Keine“, nicht die Rückkehr von „Keine“ zur letzten Quelle mit Werten und nicht ein Feld,
das vorher noch keine Werte hatte.

## Lösungsweg
1. Am Befund **«Grund nachtragen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Feld mit der Frage
   **„Warum wechselte die Quelle?"**; der Zeitpunkt und beide Quellen stehen oben.
2. Misst der neue Sensor dasselbe Gerät weiter: **„Bisherige Werte bleiben — der neue Sensor setzt fort (Zähler oder Gerät getauscht, anderer Sensor für dasselbe Gerät)"** wählen. Sind beide Quellen Sensoren
   aus Home Assistant, rechnet eedc wie Home Assistant mit beiden: den bisherigen bis zu seinem letzten Wert, den neuen ab
   seinem ersten. Unter **„Was danach geschieht"** steht, seit wann Home Assistant den neuen Sensor führt und wie viele
   Stunden eedc neu liest und Tage neu bildet — auch den Tag des Wechsels. Haben beide Sensoren eine Zeit lang gleichzeitig
   gezählt, erscheint das Feld **„Der neue Sensor zählt ab"**, vorbelegt mit der Stunde des Wechsels; eine frühere Stunde
   nimmst du, wenn der neue Sensor schon ab dann die Werte des Geräts gemessen hat. Bei jeder anderen Quelle (etwa MQTT)
   bleiben die bisherigen Werte, und der Unterschied zwischen altem und neuem Zählerstand zählt nicht als Menge. Zwischen zwei
   MQTT-Quellen zählt die Stunde des Wechsels, was die bisherige Quelle bis zu ihrem letzten und die neue ab ihrem ersten
   Zählerstand gemeldet hat (aus den gespeicherten Zählerständen der letzten 31 Tage); sonst zählt sie dort keinen Zuwachs, wo
   eedc aus den gespeicherten Zählerständen rechnet. Für den Tag des Wechsels gilt
   dort: bildet eedc ihn aus seinen gespeicherten Stundenwerten, zählt der Unterschied danach nicht mehr; hat eedc für diesen
   Tag schon einen festen Tageswert gespeichert, bleibt der, wie er ist, und kann den Unterschied weiter enthalten.
3. Waren die Werte vor dem Wechsel falsch: **„Bisherige Werte verwerfen — bisher war der falsche Sensor zugeordnet"** wählen, unter
   **„Falsch seit"** angeben, ab wann (vorbelegt ist der Beginn der Quelle vor dem Wechsel), und die Vorschau unter
   **„Was danach geschieht"** lesen. eedc verwirft die Werte dieses Felds von „Falsch seit“ bis zum Wechsel und baut sie,
   soweit Home Assistant die Geschichte des richtigen Sensors führt und die Zählerstände davor und danach zu ihr passen, aus
   ihm neu auf; wo nichts sie füllt, rechnet eedc über die leere Zeit wie über jede Zählerlücke, wenn davor, in dieser Zeit
   und danach dieselbe Quelle gilt und kein Zählertausch dazwischen eingetragen ist (die Höhe der Zählerstände prüft eedc
   dabei nicht), sonst bildet eedc über sie keine Differenz und die Zeit bleibt ohne Wert. Das geht für den jüngsten Wechsel eines Felds, solange seine
   neue Quelle noch zugeordnet ist — auch, wenn mit ihm die Quelle zur vorigen zurückkehrte —, und für einen früheren
   Wechsel, mit dem die Quelle zur vorigen zurückkehrte: dort steht die Zeit fest — vom Wechsel davor bis zu diesem; der
   Dialog nennt sie. Die Korrektur lässt sich in eedc nicht rückgängig machen.
4. **„Übernehmen"** klicken. Die Datenquellen-Fläche zeigt oben, wie weit eedc die Tage neu bildet. Kann eedc einen
   Wechsel zwischen zwei Sensoren aus Home Assistant noch nicht wie Home Assistant rechnen (etwa weil Home Assistant den
   neuen Sensor noch nicht mit Stundenwerten führt), steht dort der Grund; eedc holt es jede Stunde von selbst nach.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Befund verschwindet, sobald der Grund eingetragen ist.

Nennt der Daten-Checker **zwei Wechsel desselben Felds** (etwa vom richtigen Sensor zu einem falschen und wieder zurück),
beginne beim jüngeren. Wählst du dort **„Bisherige Werte verwerfen — bisher war der falsche Sensor zugeordnet"**, ist **„Falsch seit"** mit dem älteren
Wechsel vorbelegt. War vor dem älteren Wechsel schon der richtige Sensor zugeordnet, oder legst du „Falsch seit“ vor den
älteren Wechsel, erledigt die Korrektur den älteren mit — der Daten-Checker nennt danach keinen der beiden mehr.

## Was ohne Handlung gilt
eedc rechnet über den Wechsel hinweg wie bisher: wo ein Wert aus den gespeicherten Zählerständen entsteht (etwa ein
Tageswert, der nicht aus der Statistik von Home Assistant kommt), kann der Unterschied zwischen altem und neuem
Zählerstand als Menge zählen, und Werte des falschen Sensors bleiben stehen. Tage, die eedc aus der Statistik von Home
Assistant rechnet, sind davon nicht betroffen. Gespeicherte Monatswerte ändern sich weder durch den Wechsel noch durch einen
nachgetragenen Grund; nach einer Korrektur folgt, was eedc im Monat aus den Tagen rechnet (etwa der PV-Anteil einer Ladung),
den neu gebildeten Tagen — die Vorschau nennt die Monate. Ein schon fest gespeicherter Tageswert vom Tag des Wechsels bleibt
auch nach „Bisherige Werte bleiben“, wie er ist — außer zwischen zwei Sensoren aus Home Assistant: dort bildet eedc die Tage
ab dem Wechsel neu.
