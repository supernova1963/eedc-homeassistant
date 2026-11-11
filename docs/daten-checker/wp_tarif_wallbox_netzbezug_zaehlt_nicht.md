# Netzbezug zum Wallbox-Tarif zählt unter dem gemeinsamen Tarif nicht

## Was eedc sieht
Für Wärmepumpe und Wallbox gilt ein gemeinsamer Tarif (ein Zähler vor beiden Geräten). Den gemeinsamen Netzbezug trägt
das Feld «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)» an der Wärmepumpe. An der Wallbox ist zusätzlich
«Netzbezug zum Wallbox-Tarif» zugeordnet oder in einer Monatszeile der letzten zwölf abgeschlossenen Monate gefüllt —
dieser Wert zählt in der Stromrechnung nicht, er stünde sonst doppelt.

## Lösungsweg
1. Am Befund **«Tarif bearbeiten»** klicken — der gemeinsame Tarif öffnet sich. Prüfen, ob er stimmt: Haben die Geräte
   getrennte Zähler, ist die Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)» falsch.
2. Stimmt der gemeinsame Tarif: in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) die Zuordnung
   «Netzbezug zum Wallbox-Tarif» an der Wallbox lösen und den gemeinsamen Zähler an der Wärmepumpe zuordnen (Handbuch
   «Wärme & Klima», Schritt 6b).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald weder eine Zuordnung noch
   ein Monatswert der letzten zwölf abgeschlossenen Monate das Feld an der Wallbox trägt.

## Was ohne Handlung gilt
eedc rechnet den gemeinsamen Netzbezug von der Wärmepumpe; der Wert an der Wallbox bleibt in der Stromrechnung
unberücksichtigt.
