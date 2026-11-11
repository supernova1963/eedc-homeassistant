# Auffällige PV-Tage mit Zählersprung — kein Doppelerfassungs-Verdacht

## Was eedc sieht
Einige Tage liegen über dem physikalisch Möglichen, aber jeder davon trägt einen unmöglichen Stundenwert — typisch nach
einer Verbindungsunterbrechung, wenn ein Zähler den Zuwachs nachliefert und Home Assistant ihn in eine Stunde bucht. Die
übrigen Tage sind unauffällig; eine doppelt zugeordnete Erzeugung passt deshalb nicht zum Bild. Die Details nennen die
Tage.

## Lösungsweg
1. In der Zuordnung ist hier nichts zu suchen. Die Ursache ist der Zählersprung: in der Kategorie «Energieprofil –
   Plausibilität» den Befund «Counter-Spike am …» des Tages öffnen und dessen Weg gehen (dort **«Tag neu aufbauen»**).
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Sprünge behoben sind.

## Was ohne Handlung gilt
Die Tage behalten den Sprung: Tagesansicht und Monat zeigen an ihnen zu viel Erzeugung. Ein Verdacht auf
Doppelerfassung entsteht daraus nicht.
