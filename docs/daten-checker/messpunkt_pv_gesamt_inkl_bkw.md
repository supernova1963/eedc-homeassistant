# „PV gesamt“ gilt als Zähler einschließlich Balkonkraftwerk

## Was eedc sieht
Dem Anlagenzähler (Feld „PV gesamt“) ist ein Sensor zugeordnet, mindestens ein aktives PV-Modul hat keinen eigenen Zähler
und mindestens ein Balkonkraftwerk hat einen. eedc liest den Anlagenzähler dann als Zähler der ganzen Erzeugung
einschließlich Balkonkraftwerk und verteilt seinen Rest nach dem Zähler des Balkonkraftwerks auf die PV-Module ohne
Zähler. Die Meldung nennt beide. Ein Modul, das zum Balkonkraftwerk selbst gehört, zählt nicht als Modul ohne Zähler.

## Lösungsweg
1. Klären, was dein Anlagenzähler misst (der Knopf **«Was gilt»** am Befund öffnet diesen Text): Zählt er die ganze
   Erzeugung einschließlich Balkonkraftwerk, stimmt die Rechnung, und es ist nichts zu tun.
2. Misst er nur den Wechselrichter: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) denselben Sensor
   beim PV-Modul im Feld „PV-Erzeugung“ zuordnen. Sonst fehlt die Erzeugung der Balkonkraftwerke in PV gesamt.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein PV-Modul ohne eigenen Zähler neben
   dem Anlagenzähler steht.

## Was ohne Handlung gilt
eedc verteilt den Rest des Anlagenzählers nach dem Zähler des Balkonkraftwerks auf die Module ohne Zähler. Misst der
Anlagenzähler nur den Wechselrichter, fehlt die Erzeugung des Balkonkraftwerks in PV gesamt. Die Messpunkt-Prüfungen
schweigen in dieser Lage, weil der verteilte Rest die Differenz verdeckt.
