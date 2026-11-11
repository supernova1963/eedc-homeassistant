# Tage mit Mengen aus den gespeicherten Stundenwerten

## Was eedc sieht
An diesen Tagen kommen PV, Netz und Speicher weder aus der Langzeitstatistik von Home Assistant noch aus eigenen
Zählerständen. eedc liest ihre Mengen deshalb aus den gespeicherten Stunden- und Tageswerten — so wie vor der Umstellung.
Typisch sind Tage vor dem ersten gespeicherten Zählerstand. Die Details nennen auch die Zahl der Tage mit der neuen
Deckung.

## Lösungsweg
1. Nichts zu tun — das ist kein Fehler. Der Knopf **«Was gilt»** am Befund öffnet diesen Text.
2. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange es solche Tage gibt; sie macht nur
   sichtbar, welche Tage noch aus den gespeicherten Werten rechnen.

## Was ohne Handlung gilt
Diese Tage rechnen weiter mit den gespeicherten Stunden- und Tageswerten.
