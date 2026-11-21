# Abweichung zu Home Assistant an einem Tag (PV)

## Was eedc sieht
Für diesen Tag steht in eedc eine andere PV-Erzeugung als in der Langzeitstatistik von Home Assistant (mindestens 2 kWh und
5 % Unterschied). Mehrere solche Tage stehen als eine Zeile «n Tage weichen von Home Assistant ab» mit einem Glied je Tag,
die größten Abweichungen vorn. **Benannte Grenze — der erste Tag einer Statistik:** an dem Tag, an dem die Statistik eines
Sensors in Home Assistant beginnt, zählt eedc den Kalendertag ab der ersten Stunde wie Home Assistant; der Vergleichswert, den
die Prüfung aus Home Assistant liest, reicht für diesen Tag aber nur bis 23 Uhr (die Stunde 23–24 Uhr zählt er zum Folgetag).
Trägt diese letzte Stunde mindestens 2 kWh und 5 %, nennt die Prüfung den Tag, obwohl Tagesansicht und Home Assistant
dieselbe Zahl zeigen; «Aus Home Assistant neu übernehmen» ändert daran nichts. Am Folgetag tritt das nicht auf.

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Einstellungen → Werkzeuge → Statistik* (in älteren Home-Assistant-Versionen: *Entwicklerwerkzeuge → Statistik*) beim Sensor mit „Summe anpassen“ für diesen Tag berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken (ohne Spiegel heißt der Knopf «Tag neu
   aufbauen»), die Vorschau lesen und **«Anwenden»**. Für viele Tage auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Der Tag behält seinen Wert in eedc; Tagesansicht, Monat und alles, was daraus rechnet, nutzen ihn. Home Assistant und
eedc zeigen für diesen Tag verschiedene Zahlen, bis einer der beiden berichtigt ist.
