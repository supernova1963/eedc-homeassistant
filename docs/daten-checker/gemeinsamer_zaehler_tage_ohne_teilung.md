# Gemeinsamer Zähler: Tage teilen die Ersparnis nicht

## Was eedc sieht
Beim gemeinsamen Zähler für Wärmepumpe und Wallbox rechnet die Stromrechnung je Tag mit den Stunden des gemeinsamen
Netzbezugs. Die Eigenverbrauchs-Ersparnis teilt der einzelne Tag aber nicht in Wärmepumpe und Wallbox, weil Stundenwerte
der Netzladung der Wallbox fehlen. Der Monat trägt den genauen Wert; die Summe der Tage weicht bei der Ersparnis davon
ab. Das ist eine bekannte Grenze, kein Fehler deiner Daten.

## Lösungsweg
1. Der Knopf **«Was gilt»** am Befund öffnet diesen Abschnitt: Für Monat und Jahr gilt der Monatswert; die Tagesansicht im Cockpit
   rechnet die Ersparnis ohne die Teilung.
2. Nichts zu tun.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Auskunft stehen, solange der gemeinsame
   Tarif gilt.

## Was ohne Handlung gilt
Monats- und Jahreswerte stimmen; einzelne Tage zeigen die Ersparnis ohne Teilung zwischen Wärmepumpe und Wallbox.
