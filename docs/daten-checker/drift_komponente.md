# Ein Gerät weicht an Tagen von Home Assistant ab

## Was eedc sieht
Für eine Komponente (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung oder Netzbezug) steht in eedc an einem oder
mehreren Tagen ein anderer Wert als in der Langzeitstatistik von Home Assistant — mindestens 2 kWh und 5 % Unterschied.
Es gibt eine Zeile je Gerät, nicht je Tag; sie nennt den Tag mit der größten Abweichung und beide Zahlen. Diese Werte
tragen Wirtschaftlichkeit und CO₂-Bilanz mit — eine Abweichung an der Wallbox kostet genauso wie eine an der PV. Geprüft werden
die Tage der letzten 90 Tage bis gestern.

**Benannte Grenze — die Stunde 23–24 Uhr:** die Prüfung kann einen Tag nennen, obwohl eedc und Home Assistant für ihn
dieselbe Zahl zeigen. Der Grund: eedc zeigt den Kalendertag wie Home Assistant; der Vergleichswert der Prüfung reicht aber von
23 Uhr des Vortags bis 23 Uhr. Lief das Gerät in der Stunde 23–24 Uhr an zwei aufeinanderfolgenden Tagen deutlich verschieden
— mindestens 2 kWh und 5 % des Tages, typisch eine Wärmepumpe oder Wallbox nachts —, weicht nur dieser Vergleichswert ab
(gemessen: «67,5 → 60,0 kWh», Tagesansicht und Home Assistant 67,5). Ein Fall derselben Grenze ist der erste Tag einer
Statistik: beginnt sie an diesem Tag, fehlt dem Vergleichswert die Stunde 23–24 Uhr (gemessen: «12,5 → 10,0 kWh»,
Tagesansicht und Home Assistant 12,5). Erkennen: zeigen die Tagesansicht in eedc und Home Assistant für den genannten Tag
dieselbe Zahl, ist die gezeigte Zahl die von Home Assistant und ungenau allein der Vergleichswert. Dann ist nichts zu tun;
«Aus Home Assistant neu übernehmen» ändert daran nichts.

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Einstellungen → Werkzeuge → Statistik* (in älteren Home-Assistant-Versionen: *Entwicklerwerkzeuge → Statistik*) beim Sensor mit „Summe anpassen“ berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**.
   Liest eedc deine Anlage aus der Statistik von Home Assistant, übernimmt der Knopf die Statistik aller gespiegelten
   Zähler der Anlage neu (ab der ersten abweichenden Stunde) und baut den genannten Tag danach auf. Sonst heißt er «Tag neu aufbauen» und baut nur
   den genannten Tag neu; für alle Tage des Geräts auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — das Gerät ist aus der Liste verschwunden oder nennt weniger Tage.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Die Tage behalten ihren Wert in eedc; Tagesansicht, Monat, Wirtschaftlichkeit und CO₂-Bilanz rechnen damit. Hast du in
Home Assistant korrigiert und liest eedc die Anlage aus dessen Statistik, verschwindet die Zeile an Tagen, die eedc für
dieses Gerät aus der Statistik liest, nach dem nächtlichen Abgleich um 02:45 von selbst; an älteren Tagen (Gerätewert aus
der gespeicherten Tageszeile) erst nach **«Aus Home Assistant neu übernehmen»**.
