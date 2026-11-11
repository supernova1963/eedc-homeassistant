# Betrieb ohne Langzeitstatistik von Home Assistant

## Was eedc sieht
eedc erreicht keine Langzeitstatistik von Home Assistant — im Standalone-Betrieb ohne Home Assistant ist das der Normalfall,
im Add-on heißt es, dass die Verbindung gerade nicht steht. Tages- und Stundenwerte entstehen dann aus den
5-Minuten-Messungen von eedc. Die Prüfungen gegen Home Assistant (Sensoren in der Langzeitstatistik, Abweichung zu Home
Assistant) laufen deshalb nicht; der Kopf des Daten-Checkers zählt sie als nicht ausführbar.

## Lösungsweg
1. Standalone ohne Home Assistant: nichts zu tun — die Prüfungen gegen Home Assistant haben hier kein Gegenstück; die
   Kategorie «MQTT – Topic-Abdeckung» prüft dort die Zuordnung.
2. Im Add-on oder mit Zugriffstoken: unter [HA-Verbindung](eedc:/einstellungen/integration?block=ha-verbindung) prüfen, ob
   die Verbindung zu Home Assistant steht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange keine Langzeitstatistik erreichbar ist;
   mit erreichbarem Home Assistant nennt die Kategorie die aktive Quelle, und die übersprungenen Prüfungen laufen wieder.

## Was ohne Handlung gilt
eedc rechnet weiter aus seinen 5-Minuten-Messungen; mit der Langzeitstatistik von Home Assistant wäre die Summe der Stunden
genau der Tag. Die Prüfungen gegen Home Assistant bleiben übersprungen.
