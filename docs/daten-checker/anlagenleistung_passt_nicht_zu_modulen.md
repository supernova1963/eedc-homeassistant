# Anlagenleistung passt nicht zu den Modulen

## Was eedc sieht
Die «Leistung (kWp)» der Anlage weicht um mehr als 0,1 kWp von der Summe deiner aktiven PV-Module ab — sowohl ohne als
auch mit Balkonkraftwerk gerechnet. eedc rechnet spezifischen Ertrag, Performance Ratio und die Plausibilitätsprüfungen
mit der Modulsumme; die Anlagenleistung geht an den Community-Vergleich. Solange beide auseinanderliegen, vergleichst du
dich dort mit einer anderen Anlagengröße als der, die du auswertest.

## Lösungsweg
1. Am Befund **«Anlage bearbeiten»** klicken — das Anlagen-Formular öffnet sich am Feld «Leistung (kWp)».
2. Stimmt die Anlagenleistung nicht: korrigieren und **«Speichern»**.
3. Stimmt die Leistung eines Moduls nicht: unter [Komponenten](eedc:/einstellungen/komponenten) beim PV-Modul die
   «Leistung (kWp)» korrigieren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
eedc überschreibt keine der beiden Angaben: Die Auswertungen rechnen mit der Modulsumme, der Community-Vergleich mit der
Anlagenleistung.
