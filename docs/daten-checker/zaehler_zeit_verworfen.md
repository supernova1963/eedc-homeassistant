# Zählerstände einer Zeit verworfen

## Was eedc sieht
Eine Korrektur hat für dieses Feld die Zählerstände einer Zeit verworfen, und nichts füllt sie wieder auf: Home Assistant war
nicht verbunden, die Quelle ist MQTT (sie hat keine Geschichte, die eedc nachholen könnte), oder Home Assistant führt für diese
Zeit keine Werte des richtigen Sensors. Das bleibt so — eedc liest diese Zeit auch später nicht noch einmal aus Home Assistant.
Die Meldung nennt das Feld, Beginn und Ende der Zeit. Die Details sagen, was dafür gilt: Gilt davor, in dieser Zeit und danach
dieselbe Quelle und ist dazwischen kein Zählertausch eingetragen, steht die Menge der ganzen Zeit am Tag des ersten
Zählerstands danach (wie bei jeder Zählerlücke). Sonst bildet eedc über diese Zeit keine Differenz — die Tage darin zeigen für
dieses Feld keinen Wert, die Tage an ihrem Rand nur ihren Teil, und die Menge fehlt in Tag, Monat und Jahr. Dazu nennen die
Details die Monate mit gespeichertem Monatswert, die die Zeit berührt.

## Lösungsweg
1. Die Angabe lesen. Stimmt sie, ist nichts zu tun: die Auskunft beschreibt, was die Korrektur festgelegt hat.
2. Soll ein gespeicherter Monatswert eines genannten Monats geändert werden: unter
   [«Monatsdaten»](eedc:/einstellungen/daten?block=monatsdaten) den Monat öffnen, den Wert des Felds eintragen und
   **«Speichern & abschließen»** klicken.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange die Zeit verworfen ist.

## Was ohne Handlung gilt
Die verworfene Zeit bleibt leer. eedc schätzt, verteilt und überbrückt nichts: Steht die Menge an einem Tag danach, ist es die
Differenz der Zählerstände, die die Quelle geliefert hat; sonst fehlt sie. Gespeicherte Monatswerte bleiben, wie sie sind.
Die Kategorie «Stunden ohne Stundenwerte» nennt diese Zeit nicht noch einmal. Die Zeile verschwindet, wenn eine spätere
Korrektur dieselbe Zeit ganz aus Home Assistant füllt.
