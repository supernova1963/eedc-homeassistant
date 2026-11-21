# Daten vor der Änderung gelöscht

## Was eedc sieht
Beim Wechsel der Quelle dieses Felds wurde «Daten vor der Änderung löschen» gewählt. Die Daten dieses Felds aus der Zeit vor
der Änderung sind gelöscht; seitdem verhält sich das Feld, als wäre der neue Sensor von Anfang an zugeordnet: Was Home
Assistant für ihn führt, übernimmt eedc, für die Zeit davor zeigt das Feld «—». Die Meldung nennt das Feld und den Zeitpunkt
der Änderung. Die Details sagen, seit wann Home Assistant den neuen Sensor führt (bei einer MQTT-Quelle: seit wann eedc ihren
ersten Wert hat) und — beginnt er mitten an einem Tag — dass dieser Tag für das Feld nicht vollständig ist: eedc zählt ihn wie
Home Assistant erst ab dieser Stunde. Dazu nennen die Details die Monate mit gespeichertem Monatswert; die bleiben, wie sie sind.

## Lösungsweg
1. Die Angabe lesen. Stimmt sie, ist nichts zu tun: die Auskunft beschreibt, was beim Wechsel gewählt wurde.
2. Soll ein gespeicherter Monatswert eines genannten Monats zum neuen Sensor passen: unter
   [«Monatsdaten»](eedc:/einstellungen/daten?block=monatsdaten) am Monat den Stift wählen und den Wert des Felds überschreiben,
   oder den Monat mit **«Aus HA laden»** aus Home Assistant holen. Führt Home Assistant den neuen Sensor nur für einen Teil des
   Monats, schlägt «Aus HA laden» nur diesen Teil vor.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt; sie sagt, was für dieses Feld gilt.

## Was ohne Handlung gilt
Die gelöschten Daten kommen nicht zurück. Was Home Assistant für den neuen Sensor führt, zeigt eedc wie Home Assistant; davor
zeigt das Feld «—». eedc schätzt, verteilt und überbrückt nichts. Gespeicherte Monatswerte bleiben, wie sie sind.
