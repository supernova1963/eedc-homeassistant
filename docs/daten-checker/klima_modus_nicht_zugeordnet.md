# Betriebsmodus nicht zugeordnet — Heiz- und Kühlstrom bleiben zusammen

## Was eedc sieht
Dieses Gerät heizt und kühlt über denselben Stromzähler, und es gibt keinen der beiden Wege zur Aufteilung — weder eigene
Zähler je Betriebsart noch einen zugeordneten Betriebsmodus. eedc sieht deshalb nur eine Zahl und kann nicht sagen, welcher
Teil ins Heizen ging und welcher ins Kühlen. Den Hinweis bekommen Split-Klimaanlagen (Wärmepumpenart Luft/Luft) und jede
Wärmepumpe, an der eine Kühl-Größe zugeordnet oder gepflegt ist (Kühl-Leistung, Kältemenge, Kühl-Betriebsart).

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät am Feld «Betriebsmodus».
2. Dort die climate-Entität des Geräts zuordnen (in Home Assistant meist `climate.…`, sie zeigt Heizen/Kühlen/Aus). Ohne
   Home Assistant geht der Modus auch über MQTT mit der Quelle «Inbound» (Handbuch «Wärme & Klima»). Wer eigene Stromzähler
   je Betriebsart hat, ordnet stattdessen diese zu — liegen gemessene Werte vor, gelten sie, und der Betriebsmodus wird für
   dieses Gerät nicht gebraucht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, die Prüfung meldet die Aufteilung als
   eingerichtet.

## Was ohne Handlung gilt
Die Zuordnung ist freiwillig: Der Stromverbrauch zählt vollständig und richtig, es fehlt nur die Aufteilung. Sie beginnt mit
der Zuordnung und lässt sich nicht rückwirkend nachtragen — Home Assistant bewahrt Zustände wie „Heizen“ nur wenige Tage auf.
