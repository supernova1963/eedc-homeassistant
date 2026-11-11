# Wärmepumpen-Sensor ohne Langzeitstatistik — Live ja, Tagesverlauf nein

## Was eedc sieht
Ein zugeordneter Vorlauf-, Rücklauf- oder Zusatzheizungs-Sensor einer Wärmepumpe trägt in Home Assistant kein
`state_class: measurement`; die Meldung nennt je Sensor das Feld und die Entität. Den aktuellen Wert zeigt eedc trotzdem
(Live, Überblick der Wärmepumpe). Stündliche Mittelwerte für den Tagesverlauf übernimmt eedc aber aus der Langzeitstatistik
von Home Assistant, und die führt Home Assistant nur mit diesem `state_class` — ohne ihn bleibt der Tagesverlauf leer.

## Lösungsweg
1. In eedc ist dafür nichts umzustellen — der Weg liegt in Home Assistant: dort `state_class: measurement` ergänzen (per
   `customize`, Neustart von Home Assistant nötig) oder einen Template-Sensor anlegen, der es mitbringt.
2. Einen neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät zuordnen. Ab dann übernimmt
   eedc die Stundenmittel aus der Statistik, so weit sie zurückreicht; Stunden, für die Home Assistant keine geführt hat,
   bleiben leer.
3. Anderer Weg: den Wert über MQTT liefern (Quelle «Inbound» statt des Home-Assistant-Sensors) — dann entstehen die
   Stundenmittel aus der 5-Minuten-Mitschrift von eedc, ab der Zuordnung, nicht rückwirkend. Ist einem Feld ein
   Home-Assistant-Sensor **und** dasselbe MQTT-Topic zugeordnet, gilt der Home-Assistant-Sensor.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange einer der genannten Sensoren ohne
   Langzeitstatistik zugeordnet ist.

## Was ohne Handlung gilt
Live-Wert und Überblick funktionieren weiter; der Tagesverlauf dieser Werte bleibt leer.
