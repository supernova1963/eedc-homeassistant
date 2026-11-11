# MQTT-Empfang eingeschaltet, aber nicht verbunden

## Was eedc sieht
Der Empfang über MQTT ist eingeschaltet, aber er läuft nicht — meist, weil eedc beim letzten Start keine Verbindung zum
Broker aufbauen konnte, etwa weil der Broker nicht erreichbar ist oder die Zugangsdaten nicht stimmen. Über MQTT kommen
dann keine Werte an.

## Lösungsweg
1. Am Befund **«Zur Verbindung»** klicken — die MQTT-Broker-Verbindung öffnet sich.
2. Broker-Adresse und Zugangsdaten prüfen und speichern. Brauchst du keine Daten über MQTT, dort den Schalter «Daten über
   MQTT empfangen (Import)» ausschalten.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; mit ausgeschaltetem Empfang
   zählt der Kopf des Daten-Checkers die Prüfung als «nicht ausführbar (MQTT-Import aus)».

## Was ohne Handlung gilt
Über MQTT kommen keine Live-Werte und keine Zählerstände an; Felder, die nur über MQTT versorgt werden, bleiben leer.
