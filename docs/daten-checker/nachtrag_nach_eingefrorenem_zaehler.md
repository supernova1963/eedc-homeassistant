# Nachtrag nach eingefrorenem Zähler

## Was eedc sieht
An diesen Tagen stand ein Zähler (PV oder Einspeisung) mehrere Stunden still und lieferte die Menge danach in einer
einzigen Stunde nach — mehr, als in einer Stunde erzeugt werden kann. Sie zählt im Tag und im Monat mit, wie in Home
Assistant. Die Details nennen je Tag die Mengen und sagen, ob der Tag aus der Langzeitstatistik von Home Assistant oder
aus Zählerständen gerechnet ist. Dieselbe Form hat ein Zählersprung nach einer Nacht ohne Erzeugung.

## Lösungsweg
1. Die genannten Mengen prüfen (der Knopf **«Was gilt»** am Befund öffnet diesen Text). Stimmen sie, ist nichts zu tun.
2. Stimmt eine nicht, liegt der Fehler in der Zähler-Historie der Quelle: in Home Assistant unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ berichtigen. Danach den Tag in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) neu holen: «Aus Home Assistant
   neu übernehmen» für einen Tag aus der Statistik von Home Assistant, sonst «Tag neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein solcher Nachtrag in den Tagen steht.

## Was ohne Handlung gilt
Der Nachtrag zählt im Tag und im Monat mit, wie in Home Assistant. Die Menge geht nicht verloren, sie steht nur gebündelt
in einer Stunde.
