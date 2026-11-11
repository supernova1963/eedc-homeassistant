# Tage zählen dieselbe Ladung doppelt

## Was eedc sieht
An diesen gespeicherten Tagen der letzten 180 tragen Wallbox und E-Auto beide eine Ladung von mindestens 1 kWh, die
Ladung steht also zweimal in der Bilanz. eedc zählt eine Ladung inzwischen nur noch einmal (trägt die Wallbox die Ladeenergie, ist sie die Quelle) —
diese Tage wurden aber vorher geschrieben und bleiben so, bis sie neu berechnet werden. Die Details nennen die Menge und
die größten Fälle mit beiden Beträgen.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut das jüngste Fenster
   von höchstens 31 Tagen neu auf — jeden Tag darin, auch die ohne Befund; er berichtigt Tages- und Stundenwerte, nicht
   die Monatswerte. Werte, die nur per MQTT ankamen, und Strompreis-Sensordaten ohne Gegenstück in Home Assistant gehen
   dabei verloren — die Vorschau nennt es. Ist der jüngste betroffene Tag heute, lehnt die Vorschau ab («Der laufende
   Tag lässt sich erst morgen neu aufbauen.») — dann morgen erneut.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal nutzen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

## Was ohne Handlung gilt
Die Tage behalten die doppelte Ladung; Tagesansicht und Energieprofil zeigen dort zu viel Ladeenergie. eedc überschreibt
gespeicherte Werte nie ungefragt — deshalb läuft die Berichtigung nicht von selbst.
