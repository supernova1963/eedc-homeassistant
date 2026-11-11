# Zählersprung in der Statistik von Home Assistant

## Was eedc sieht
Ein Sensor hat kurz 0 gemeldet (etwa ein Wechselrichter, der nachts „nicht verfügbar“ ist, oder ein Neustart) und ist
danach auf seinen alten Stand zurückgekehrt. Home Assistant hält das für einen neuen Zähler und bucht beim Zurückkehren
den ganzen Zählerstand als Zuwachs dieser einen Stunde. eedc übernimmt die Langzeitstatistik so, wie das Energie-Dashboard
von Home Assistant sie zeigt — der Sprung steht deshalb in Tag, Monat und Jahr. Die Meldung nennt je Fund der letzten
30 Tage Sensor, Tag, Stunde und die Menge des Sprungs.

## Lösungsweg
1. In Home Assistant unter *Entwicklerwerkzeuge → Statistik* den genannten Sensor suchen, beim Symbol „Wert anpassen“
   die genannte Stunde wählen und den Zuwachs auf die echte Menge setzen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»** —
   eedc holt die berichtigte Statistik und baut den Tag des ersten Funds neu auf. Ohne Klick gleicht eedc die
   Statistik beim nächtlichen Abgleich von selbst ab.
3. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Sprung ist aus der Liste verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Der Sprung bleibt in Tag, Monat und Jahr stehen — in eedc wie im Energie-Dashboard von Home Assistant. eedc schneidet
ihn nicht selbst ab: die Quelle ist die Statistik in Home Assistant.
