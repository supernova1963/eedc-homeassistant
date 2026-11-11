# MQTT-Topics erwartet, nie empfangen

## Was eedc sieht
Die Verbindung zum Broker steht, aber für die genannten Topics hat noch keine Quelle Daten geliefert. Die Zeile nennt
die Zahl, die Details bis zu sechs Topics mit vollem Pfad — erst der Pfad sagt, an welchem Gerät das Feld fehlt.
Erwartet werden nur Felder, die über MQTT kommen sollen: die Pflichtfelder eines Geräts (in den Datenquellen rot
markiert) und optionale Felder, denen du MQTT oder ein Gateway als Quelle zugeordnet hast. Felder mit gespeicherter
Quelle «Keine» oder einem Sensor aus Home Assistant zählen nicht.

## Lösungsweg
1. Am Befund **«Topics prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim ersten betroffenen Gerät.
2. Je Topic klären: Ist die Publisher-Automation (Home Assistant, ioBroker, Node-RED) noch nicht eingerichtet, sie
   einrichten. Hat sich nach einem neuen Import die Nummer des Geräts geändert, das Topic in der Automation nachziehen —
   der Pfad enthält sie.
3. Wird ein Feld gar nicht über MQTT geliefert: in der Datenquellen-Zuordnung dessen Quelle auf «Keine» stellen — einmal
   anklicken speichert die Wahl. Brauchst du MQTT überhaupt nicht, in der
   [MQTT-Broker-Verbindung](eedc:/einstellungen/integration?block=mqtt-broker) «Daten über MQTT empfangen (Import)»
   ausschalten.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die versorgten oder abbestellten Topics sind aus der Zeile
   verschwunden.

## Was ohne Handlung gilt
Die Felder dieser Topics bleiben leer; was aus ihnen rechnet, fehlt in Live-Anzeige, Tag und Monat.
