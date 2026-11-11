# PV-Zähler steht, obwohl erzeugt wird

## Was eedc sieht
Der Anlagenzähler (Feld „PV gesamt“) hat sich mindestens drei volle Tage nicht bewegt, während im selben Zeitraum erzeugt
wurde: die Einspeisung wuchs um mehr als die Entladung deiner Speicher und die Erzeugung der Balkonkraftwerke mit eigenem
Zähler, oder die String-Zähler, die er mitmisst, erzeugten im Mittel mehr als 0,5 kWh am Tag. Ohne Erzeugung kann das
nicht sein — meist liefert der Sensor einen eingefrorenen Wert (Integration hängt, Gerät nicht erreichbar, Zähler
zurückgesetzt). Geprüft werden die letzten 31 abgeschlossenen Tage.

## Lösungsweg
1. Den Sensor in Home Assistant prüfen (im Standalone-Betrieb das MQTT-Topic): Hängt die Integration, ist das Gerät
   erreichbar, wurde der Zähler zurückgesetzt? Der Knopf **«Was gilt»** am Befund öffnet diesen Text.
2. Liefert der Sensor wieder Werte, zählen die folgenden Tage richtig. Die Tage, an denen er stand, berichtigst du bei
   Bedarf in Home Assistant unter *Entwicklerwerkzeuge → Statistik* mit „Wert anpassen“.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange der Stillstand in den geprüften
   31 Tagen liegt.

## Was ohne Handlung gilt
eedc rechnet an diesen Tagen mit „keine Erzeugung“ und biegt nichts zurecht; Tages- und Monatsansicht im Cockpit zeigen
deshalb unplausible Werte, etwa eine negative Autarkie. Nulleinspeisung, autarke Tage, Schnee auf den Modulen oder ein
einzelner stehender String lösen diese Meldung nicht aus.
