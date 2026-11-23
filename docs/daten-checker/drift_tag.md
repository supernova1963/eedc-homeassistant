# Abweichung zu Home Assistant an einem Tag (PV)

## Was eedc sieht
Für diesen Tag steht in eedc eine andere PV-Erzeugung als in der Langzeitstatistik von Home Assistant (mindestens 2 kWh und
5 % Unterschied). Mehrere solche Tage stehen als eine Zeile «n Tage weichen von Home Assistant ab» mit einem Glied je Tag,
die größten Abweichungen vorn. Geprüft werden die Tage der letzten 90 Tage bis gestern.

**Benannte Grenze — die Stunde 23–24 Uhr:** die Prüfung der PV liest den Vergleichswert aus Home Assistant von 23 Uhr des
Vortags bis 23 Uhr; eedc zeigt an Tagen aus dem Home-Assistant-Spiegel den Kalendertag (0 bis 24 Uhr). Weil PV zwischen 23 und
24 Uhr praktisch nichts erzeugt, ändert das den Vergleich nicht. Am **ersten Tag einer Statistik** gibt es zwei Fälle, in
denen ein Tag erscheint, obwohl eedc und Home Assistant dieselbe Zahl zeigen: dem Vergleichswert fehlt die Stunde 23–24 Uhr
(nur wenn sie mindestens 2 kWh und 5 % trägt); und beginnt die Statistik mit einem großen ersten Wert (etwa eine importierte
Statistik), lässt der Vergleichswert diese Stunde als unplausibel aus, Tagesansicht und Home Assistant zählen sie. Im zweiten
Fall zeigt der Tag den großen ersten Wert wie Home Assistant, und „Zählerstand springt“ nennt diese erste Stunde — ist er dort
falsch, berichtige ihn dort (Schritt 1). Erkennen: zeigen die Tagesansicht in eedc und Home Assistant für den genannten Tag
dieselbe Zahl, ist ungenau allein der Vergleichswert; dann ist nichts zu tun. Wallbox, E-Auto, Wärmepumpe, Sonstiges,
Einspeisung und Netzbezug vergleicht der Daten-Checker an solchen Tagen mit dem Kalendertag von Home Assistant (Befund „Ein
Gerät weicht an Tagen von Home Assistant ab“).

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Einstellungen → Werkzeuge → Statistik* (in älteren Home-Assistant-Versionen: *Entwicklerwerkzeuge → Statistik*) beim Sensor mit „Summe anpassen“ für diesen Tag berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken (ohne Spiegel heißt der Knopf «Tag neu
   aufbauen»), die Vorschau lesen und **«Anwenden»**. Für viele Tage auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) (*Einstellungen → Daten → Energieprofil-Pflege*) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Der Tag behält seinen Wert in eedc; Tagesansicht, Monat und alles, was daraus rechnet, nutzen ihn. Home Assistant und
eedc zeigen für diesen Tag verschiedene Zahlen, bis einer der beiden berichtigt ist.
