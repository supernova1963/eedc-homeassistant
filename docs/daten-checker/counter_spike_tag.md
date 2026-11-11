# Unmöglicher Stundenwert an einem Tag

## Was eedc sieht
Dieser Tag enthält mindestens eine Stunde, in der PV oder Einspeisung über der Schwelle liegt (Anlagenleistung × 1,5 je
Stunde; trägt die Stunde die Energie einer Lücke von n Stunden, gilt die n-fache Schwelle) — so viel erzeugt keine Anlage
in dieser Zeit. Häufige Ursache ist ein Neustart während des Tages, bei dem ein verzerrter
Zählerstand gespeichert wurde. Die Details nennen Stunde und Wert. Geprüft werden die letzten 30 Tage, und nur Tage aus
eigenen Stundenwerten.

## Lösungsweg
1. Am Befund **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Zählerstände des Tages
   neu und rechnet den Tag in einem Schritt neu.
2. Sind mehrere Tage betroffen, in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren» mit
   dem passenden Von-/Bis-Bereich nutzen; das reicht auch für Tage, die älter als 30 Tage sind.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist verschwunden, oder an der Stelle steht «Keine
   Counter-Spikes in den letzten 30 Tagen».

## Was ohne Handlung gilt
Die überhöhte Stunde bleibt im Tag stehen und zählt im Tag und im Lernfaktor mit; in den Monat geht sie nur ein, wenn der
Monat keinen eigenen Monatswert hat.
