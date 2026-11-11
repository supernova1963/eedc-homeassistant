# Ein Tag ohne Tageswerte, Home Assistant hat Werte

## Was eedc sieht
Für diesen Tag ist die gespeicherte Tageszeile leer, die Langzeitstatistik von Home Assistant hat aber Werte — die Meldung
nennt sie je Komponente. Mehrere solche Tage stehen als eine Zeile «n Tage ohne Tageswerte, Home Assistant hat Werte» mit
einem Glied je Tag; jedes Glied baut genau diesen Tag neu auf.

## Lösungsweg
1. Am Befund (oder am Glied des Tages) **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt
   Tages- und Stundenwerte dieses Tages aus der Statistik von Home Assistant nach.
2. Die Monatswerte schreibt der Knopf nicht. Ist der Monat schon abgeschlossen, ihn danach im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) mit **«Vorschau laden»** neu übernehmen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Der Tag bleibt in eedc leer; Tagesansicht im Cockpit, Stundenwerte und Energieprofil zeigen für ihn nichts, obwohl Home
Assistant Werte hat.
