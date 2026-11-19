# Zuordnung eines Zählers geändert, Grund fehlt

## Was eedc sieht
Die Quelle eines Zählerfelds wurde gewechselt, als das Feld schon eigene Werte hatte — aber nicht verzeichnet ist, warum:
der Wechsel stammt aus der Zeit, bevor eedc beim Wechsel nach dem Grund gefragt hat, oder aus einem Hinweis
„Zuordnung geändert“, der noch offen war. eedc weiß deshalb nicht, ob der neue Sensor dasselbe weiter misst (etwa nach
einem Zählertausch) oder ob bisher der falsche Sensor zugeordnet war. Die Meldung nennt Gerät, Feld und den Tag des
Wechsels; Uhrzeit und beide Quellen stehen in den Details. Gemeldet wird nur ein Wechsel, nach dem eedc heute fragen
würde — nicht ein Wechsel auf „Keine“, nicht die Rückkehr von „Keine“ zur letzten Quelle mit Werten und nicht ein Feld,
das vorher noch keine Werte hatte.

## Lösungsweg
1. Am Befund **«Grund nachtragen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Feld mit der Frage
   **„Warum wechselte die Quelle?"**; der Zeitpunkt und beide Quellen stehen oben.
2. Messen beide Sensoren dasselbe: **„Der neue Sensor misst dasselbe weiter (Zähler getauscht, anderer Sensor für
   dasselbe Gerät)"** wählen. Die bisherigen Werte bleiben, und der Unterschied zwischen altem und neuem Zählerstand zählt
   nicht als Menge; wo eedc aus den gespeicherten Zählerständen rechnet, zählt die Stunde des Wechsels keinen Zuwachs.
   Für den Tag des Wechsels gilt: bildet eedc ihn aus seinen gespeicherten Stundenwerten, zählt der Unterschied danach
   nicht mehr; hat eedc für diesen Tag schon einen festen Tageswert gespeichert, bleibt der, wie er ist, und kann den
   Unterschied weiter enthalten.
3. Waren die Werte vor dem Wechsel falsch: **„Bisher war der falsche Sensor zugeordnet"** wählen, unter
   **„Falsch seit"** angeben, ab wann (vorbelegt ist der Beginn der Quelle vor dem Wechsel), und die Vorschau unter
   **„Was danach geschieht"** lesen. eedc verwirft die Werte dieses Felds von „Falsch seit“ bis zum Wechsel und baut sie,
   soweit Home Assistant die Geschichte des richtigen Sensors führt und die Zählerstände davor und danach zu ihr passen, aus
   ihm neu auf; wo nichts sie füllt, rechnet eedc über die leere Zeit wie über jede Zählerlücke, wenn davor, in dieser Zeit
   und danach dieselbe Quelle gilt und kein Zählertausch dazwischen eingetragen ist (die Höhe der Zählerstände prüft eedc
   dabei nicht), sonst bildet eedc über sie keine Differenz und die Zeit bleibt ohne Wert. Das geht für den jüngsten Wechsel eines Felds, solange seine
   neue Quelle noch zugeordnet ist — auch, wenn mit ihm die Quelle zur vorigen zurückkehrte —, und für einen früheren
   Wechsel, mit dem die Quelle zur vorigen zurückkehrte: dort steht die Zeit fest — vom Wechsel davor bis zu diesem; der
   Dialog nennt sie. Die Korrektur lässt sich in eedc nicht rückgängig machen.
4. **„Übernehmen"** klicken. Bei einer Korrektur zeigt die Datenquellen-Fläche oben, wie weit die Tage neu gebildet
   sind.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Befund verschwindet, sobald der Grund eingetragen ist.

Nennt der Daten-Checker **zwei Wechsel desselben Felds** (etwa vom richtigen Sensor zu einem falschen und wieder zurück),
beginne beim jüngeren. Wählst du dort **„Bisher war der falsche Sensor zugeordnet"**, ist **„Falsch seit"** mit dem älteren
Wechsel vorbelegt. War vor dem älteren Wechsel schon der richtige Sensor zugeordnet, oder legst du „Falsch seit“ vor den
älteren Wechsel, erledigt die Korrektur den älteren mit — der Daten-Checker nennt danach keinen der beiden mehr.

## Was ohne Handlung gilt
eedc rechnet über den Wechsel hinweg wie bisher: wo ein Wert aus den gespeicherten Zählerständen entsteht (etwa ein
Tageswert, der nicht aus der Statistik von Home Assistant kommt), kann der Unterschied zwischen altem und neuem
Zählerstand als Menge zählen, und Werte des falschen Sensors bleiben stehen. Tage, die eedc aus der Statistik von Home
Assistant rechnet, sind davon nicht betroffen. Gespeicherte Monatswerte ändern sich weder durch den Wechsel noch durch einen
nachgetragenen Grund; nach einer Korrektur folgt, was eedc im Monat aus den Tagen rechnet (etwa der PV-Anteil einer Ladung),
den neu gebildeten Tagen — die Vorschau nennt die Monate. Ein schon fest gespeicherter Tageswert vom Tag des Wechsels bleibt
auch bei einer nachgetragenen Fortsetzung, wie er ist.
