# Ein Gerät weicht an Tagen von Home Assistant ab

## Was eedc sieht
Für eine Komponente (Wallbox, E-Auto, Wärmepumpe, Sonstiges, Einspeisung oder Netzbezug) steht in eedc an einem oder
mehreren Tagen ein anderer Wert als in der Langzeitstatistik von Home Assistant — mindestens 2 kWh und 5 % Unterschied.
Es gibt eine Zeile je Gerät, nicht je Tag; sie nennt den Tag mit der größten Abweichung und beide Zahlen. Diese Werte
tragen Wirtschaftlichkeit und CO₂-Bilanz mit — eine Abweichung an der Wallbox kostet genauso wie eine an der PV. Geprüft werden
die Tage der letzten 90 Tage bis gestern.

**Welcher Tag verglichen wird:** zeigt eedc ein Gerät an einem Tag aus dem Home-Assistant-Spiegel (der Kalendertag, 0 bis
24 Uhr), vergleicht die Prüfung mit dem Kalendertag von Home Assistant; liest eedc den Tag aus den gespeicherten Werten,
vergleicht sie wie diese von 23 Uhr des Vortags bis 23 Uhr. Ein Gerät, das nachts an zwei Tagen verschieden läuft, und der
erste Tag einer Statistik erscheinen deshalb nicht mehr, wenn eedc und Home Assistant dieselbe Zahl zeigen.

**Benannte Grenze — eine fehlende Stunde in Home Assistant:** führt Home Assistant für ein Gerät die Stunde 23–24 Uhr nicht
(etwa weil der Sensor in dieser Stunde nicht lesbar war), obwohl seine Statistik davor läuft, prüft der Daten-Checker dieses
Gerät an den beiden Tagen um diese Stunde nicht — eedc setzt für die fehlende Stunde keinen Wert ein. Ebenso bleibt der
letzte geprüfte Tag (gestern) ungeprüft, solange Home Assistant die Stunde 23–24 Uhr von gestern noch nicht geschrieben hat.

## Lösungsweg
1. In Home Assistant prüfen, welcher Wert stimmt. Ist die Statistik dort falsch (etwa ein Zählersprung), sie unter
   *Einstellungen → Werkzeuge → Statistik* (in älteren Home-Assistant-Versionen: *Entwicklerwerkzeuge → Statistik*) beim Sensor mit „Summe anpassen“ berichtigen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»**.
   Liest eedc deine Anlage aus der Statistik von Home Assistant, übernimmt der Knopf die Statistik aller gespiegelten
   Zähler der Anlage neu (ab der ersten abweichenden Stunde) und baut den genannten Tag danach auf. Sonst heißt er «Tag neu aufbauen» und baut nur
   den genannten Tag neu; für alle Tage des Geräts auf einmal: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) (*Einstellungen → Daten → Energieprofil-Pflege*) «Mehrere Tage neu aggregieren».
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — das Gerät ist aus der Liste verschwunden oder nennt weniger Tage.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Die Tage behalten ihren Wert in eedc; Tagesansicht, Monat, Wirtschaftlichkeit und CO₂-Bilanz rechnen damit. Hast du in
Home Assistant korrigiert und liest eedc die Anlage aus dessen Statistik, verschwindet die Zeile an Tagen, die eedc für
dieses Gerät aus der Statistik liest, nach dem nächtlichen Abgleich um 02:45 von selbst; an älteren Tagen (Gerätewert aus
der gespeicherten Tageszeile) erst nach **«Aus Home Assistant neu übernehmen»**.
