# Ein Gerät weicht an Tagen von Home Assistant ab

## Was eedc sieht
Für eine Komponente (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung oder Netzbezug) steht in eedc an einem oder
mehreren Tagen ein anderer Wert als in der Langzeitstatistik von Home Assistant — mindestens 2 kWh und 5 % Unterschied.
Es gibt eine Zeile je Gerät, nicht je Tag; sie nennt den Tag mit der größten Abweichung und beide Zahlen. Diese Werte
tragen Wirtschaftlichkeit und CO₂-Bilanz mit — eine Abweichung an der Wallbox kostet genauso wie eine an der PV.

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Entwicklerwerkzeuge → Statistik* beim Sensor mit „Wert anpassen“ berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**.
   Liest eedc deine Anlage aus der Statistik von Home Assistant, übernimmt der Knopf die Statistik dieses Zählers neu
   (das wirkt auf alle seine Tage) und baut den genannten Tag danach auf. Sonst heißt er «Tag neu aufbauen» und baut nur
   den genannten Tag neu; für alle Tage des Geräts auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — das Gerät ist aus der Liste verschwunden oder nennt weniger Tage.

Bleibt der Befund danach: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Kopieren»** und mit deiner Frage
melden (Forum oder GitHub); «Als Datei herunterladen» ist der zweite Weg.

## Was ohne Handlung gilt
Die Tage behalten ihren Wert in eedc; Tagesansicht, Monat, Wirtschaftlichkeit und CO₂-Bilanz rechnen damit. Hast du in
Home Assistant korrigiert und liest eedc die Anlage aus dessen Statistik, verschwindet die Zeile nach dem nächtlichen
Abgleich um 02:45 von selbst.
