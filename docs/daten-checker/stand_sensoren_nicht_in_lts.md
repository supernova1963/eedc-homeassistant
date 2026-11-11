# Zählerstand-Sensoren nicht in der Langzeitstatistik von Home Assistant

## Was eedc sieht
Für diese Zählerstand-Sensoren führt Home Assistant keine Langzeitstatistik — meist fehlt `state_class`. eedc liest den
Zählerstand stündlich genau dort; deshalb wird für diese Zähler gar kein Stand mitgeschrieben: Anfang, Ende und Verbrauch des
Zeitraums bleiben leer, ohne dass sonst etwas darauf hinweist. Die Details nennen die betroffenen Sensoren.

## Lösungsweg
1. In Home Assistant für diesen Sensor `state_class` ergänzen (etwa per `customize`). Ein Zählerstand ist eine Bestandsgröße:
   `measurement` genügt — `total_increasing` oder ein Verbrauchszähler-Helfer sind dafür nicht nötig.
2. Oder am Befund **«Anderen Sensor wählen»** klicken — die Datenquellen-Zuordnung öffnet sich am ersten betroffenen Feld;
   dort einen Sensor wählen, der `state_class` mitbringt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder genannte Sensor in der
   Langzeitstatistik steht.

## Was ohne Handlung gilt
Für diese Zähler bleibt der Stand leer. Vergangenes sammelt Home Assistant nicht nach: Die Reihe beginnt ab der Umstellung.
