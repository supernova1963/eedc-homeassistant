# Fahrzeug der Steuerung unbekannt

## Was eedc sieht
Die Steuerung (evcc, openWB) meldet am Ladepunkt einen Fahrzeugnamen, den kein E-Auto der Anlage als „Kennung in der
Steuerung“ trägt. Die Wallbox-Karte zeigt dann nur „Fahrzeug der Steuerung unbekannt“. Die Zeile nennt den gemeldeten
Namen.

## Lösungsweg
1. Am Befund **«Kennung eintragen»** klicken — mit genau einem E-Auto öffnet sich sein Formular am Feld
   «Kennung in der Steuerung (evcc vehicleName, openWB Fahrzeug)»; mit mehreren E-Autos öffnet sich die Seite
   «Komponenten» — dort beim passenden E-Auto das Stift-Symbol «Bearbeiten» klicken.
2. Am E-Auto den Namen genau so eintragen, wie die Steuerung das Fahrzeug nennt (Groß-/Kleinschreibung ist
   egal), und speichern. Ist es ein fremdes Fahrzeug, ist nichts zu tun.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; bei einem fremden Fahrzeug bleibt
   sie, solange es am Ladepunkt steht.

## Was ohne Handlung gilt
Die Wallbox-Karte zeigt „Fahrzeug der Steuerung unbekannt“, statt den Ladevorgang einem deiner E-Autos zuzuordnen.
