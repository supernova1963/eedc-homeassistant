# Tage ohne Werte trotz zugeordnetem Zähler

## Was eedc sieht
In den letzten 90 Tagen gibt es Tage, an denen ein Zähler zugeordnet ist und die Langzeitstatistik von Home Assistant
für ihn mindestens 1 kWh hat, die gespeicherte Tageszeile in eedc aber leer ist. Das ist der typische Fall nach einer
nachträglich korrigierten Zuordnung: Die Zuordnung steht heute, für die Tage davor hat sie nie jemand aufgeschrieben.
Die Meldung nennt den Zeitraum, die Details die betroffenen Komponenten.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Tage aus der Statistik
   von Home Assistant nach, höchstens 31 Tage je Lauf; ältere Tage bleiben für einen zweiten Lauf stehen. Einzelne Tage baut
   die Zeile «… Tage ohne Tageswerte, Home Assistant hat Werte» mit einem Glied je Tag neu auf.
2. Steht am Befund stattdessen **«Sensor zuordnen»**, kann eedc die Tage noch nicht nachholen: Der Tages-Lauf braucht
   zusätzlich eine Leistungs-Zuordnung (W). Der Knopf öffnet die
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=netzbezug_w) am Feld «Netzbezug» — dort einen
   Leistungssensor zuordnen; danach erscheint am Befund der Knopf aus Schritt 1.
3. Die Tagesreparatur heilt Tages- und Stundenwerte, nicht die Monatswerte. Für abgeschlossene Monate danach im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) **«Vorschau laden»** — bereits belegte
   Monate stehen dort unter «Konflikte» und sind zum Überschreiben vorausgewählt, also vor dem Import einmal durchsehen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgeholten Tage sind aus der Zeile verschwunden; nennt die
   Meldung ältere oder noch nicht geprüfte Tage, den Knopf ein weiteres Mal anwenden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Die Tage bleiben in eedc leer: Tagesansicht im Cockpit, Stundenwerte und Energieprofil zeigen für sie nichts, obwohl Home
Assistant Werte hat. Die Monatswerte sind davon nicht berührt.
