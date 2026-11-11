# Abweichung zu Home Assistant an einem Tag (PV)

## Was eedc sieht
Für diesen Tag steht in eedc eine andere PV-Erzeugung als in der Langzeitstatistik von Home Assistant (mindestens 2 kWh und
5 % Unterschied). Mehrere solche Tage stehen als eine Zeile «n Tage weichen von Home Assistant ab» mit einem Glied je Tag,
die größten Abweichungen vorn.

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ für diesen Tag berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken (ohne Spiegel heißt der Knopf «Tag neu
   aufbauen»), die Vorschau lesen und **«Anwenden»**. Für viele Tage auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Der Tag behält seinen Wert in eedc; Tagesansicht, Monat und alles, was daraus rechnet, nutzen ihn. Home Assistant und
eedc zeigen für diesen Tag verschiedene Zahlen, bis einer der beiden berichtigt ist.
