# Gerät älter als die Anlage

## Was eedc sieht
Ein Gerät, das kein PV-Erzeuger ist (E-Auto, Wallbox, Wärmepumpe, Speicher, Wechselrichter, Sonstiges), wurde vor der
Inbetriebnahme der Anlage angeschafft. Das ist normal und kein Fehler — man hatte das Auto vor der PV-Anlage. Die Zeile
meldet die Datenlage: Für die Monate davor gibt es keine Einspeisungs- und Netzbezugswerte und damit keine Bilanz; eedc
kann dort nicht sagen, ob der Strom gekauft oder selbst erzeugt war.

## Lösungsweg
1. Hast du Zählerwerte aus dieser Zeit: unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) die Monate nachtragen.
2. Stimmt das Datum der Anlage nicht: am Befund **«Anlage bearbeiten»** klicken, im Feld «Inbetriebnahme (Anlage)»
   korrigieren und **«Speichern»**.
3. Sonst nichts — die Zeile ist eine Auskunft. Das Gerät nie umdatieren: seine Anschaffungshistorie ginge verloren.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Hinweis stehen, solange das Gerät älter
   ist als die Anlage; das ist der richtige Zustand.

## Was ohne Handlung gilt
Das Gerät rechnet ab seinem eigenen Anschaffungsdatum mit. Für die Monate vor der Anlage fehlt die Bilanz; Monate davor
fordert eedc nicht ein.
