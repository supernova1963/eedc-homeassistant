# Keine PV-Module angelegt

## Was eedc sieht
Die Anlage hat weder PV-Module noch ein Balkonkraftwerk als Komponente. Ohne Erzeuger fehlt die Erzeugung in der
Aufschlüsselung, es gibt keinen String-Vergleich und keine Prognose je Dachfläche. Ein Balkonkraftwerk allein genügt —
dann erscheint diese Zeile nicht.

## Lösungsweg
1. Am Befund **«Komponente anlegen»** klicken — das Formular für eine neue Komponente vom Typ PV-Module öffnet sich.
2. Je Dachfläche (String) eine Komponente mit «Leistung (kWp)», Ausrichtung und Neigung anlegen und **«Erstellen»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile steht mit der Summe der Module unter den bestandenen
   Prüfungen.

## Was ohne Handlung gilt
eedc wertet die Gesamterzeugung aus, ohne sie auf Dachflächen aufzuteilen; Prognose und String-Vergleich bleiben leer.
