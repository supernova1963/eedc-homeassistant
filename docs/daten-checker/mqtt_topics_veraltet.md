# MQTT-Topics mit veralteten Werten

## Was eedc sieht
Die genannten Topics wurden schon empfangen, aber ihr letzter Wert ist älter als erlaubt: Live-Topics sollten innerhalb von
2 Minuten, Energie-Topics innerhalb von 10 Minuten neu kommen. Die Meldung nennt je Topic das Alter in Minuten. Meist
läuft die Publisher-Automation nicht mehr oder hat ihre Quelle verloren (etwa ein Wechselrichter offline).

## Lösungsweg
1. Am Befund **«Topics prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim ersten betroffenen Gerät.
2. Die Publisher-Automation prüfen: Läuft sie noch, liefert ihre Quelle? Fehlt die Quelle dauerhaft, die Automation
   aufräumen oder in der Datenquellen-Zuordnung die Quelle des Felds ändern.
3. Brauchst du MQTT überhaupt nicht, in der
   [MQTT-Broker-Verbindung](eedc:/einstellungen/integration?block=mqtt-broker) «Daten über MQTT empfangen (Import)»
   ausschalten.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die wieder frischen Topics sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc nutzt nur, was ankommt: ab dem letzten Empfang fehlen die Werte dieser Topics, in der Live-Anzeige wie in den
Mengen von Tag und Monat.
