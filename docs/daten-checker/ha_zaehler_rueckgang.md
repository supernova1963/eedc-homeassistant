# Zählerstand in der Statistik von Home Assistant gefallen

## Was eedc sieht
Die Summe eines Sensors in der Langzeitstatistik von Home Assistant ist in einer Stunde gefallen, statt zu steigen — meist,
weil der Wert in Home Assistant nachträglich zu weit nach unten angepasst wurde, oder weil der Sensor einen kleineren
Zählerstand gemeldet hat (typisch nach dem Neustart einer Integration, die ihren Zähler selbst hochrechnet). eedc
übernimmt die Statistik so, wie das Energie-Dashboard sie zeigt: der Rückgang steht als Abzug in Tag, Monat und Jahr, und
«Aus HA laden» schlägt für den Monat einen zu kleinen oder negativen Wert vor. Das ist kein Vorzeichen für Entladen oder
Einspeisen — jede Richtung hat ihr eigenes Feld. Die Meldung nennt je Sensor und Tag die Menge und die Stunde; geprüft
wird die ganze übernommene Statistik, nicht nur die letzten 30 Tage.

## Lösungsweg
1. In Home Assistant unter *Entwicklerwerkzeuge → Statistik* den genannten Sensor suchen, beim Symbol „Wert anpassen“
   die genannte Stunde wählen und die Menge auf den echten Wert setzen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**. Ohne
   Klick gleicht eedc die berichtigte Statistik beim nächtlichen Abgleich von selbst ab.
3. Stammt der Rückgang von einem Sensor, den du inzwischen ersetzt hast (die Meldung sagt „Vorgänger-Sensor, zugeordnet
   bis …“): statt in Home Assistant zu berichtigen, in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Werte vor dem
   Sensorbeginn verwerfen» ausführen.
4. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Liste verschwunden.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Der Rückgang zieht Tag, Monat und Jahr nach unten. eedc verwirft ihn nicht selbst: die Quelle ist die Statistik in Home
Assistant, und übernommen wird nur, was Home Assistant hat.
