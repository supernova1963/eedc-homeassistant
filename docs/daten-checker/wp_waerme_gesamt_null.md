# Wärme gesamt ist 0, die Einzelwerte nicht

## Was eedc sieht
In diesen Monaten steht unter «Wärme gesamt» eine 0, während «Heizwärme» und «Warmwasser-Wärme» zusammen mehr als
0,5 kWh tragen. eedc rechnet hier mit den beiden Einzelwerten. Häufigster Grund: Der Wärmemengenzähler hat im Monat
keinen neuen Stand geliefert — keine Statistik in Home Assistant, eingefroren oder erst seit kurzem zugeordnet.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich bei den
   Wärmewerten der Wärmepumpe.
2. Prüfen, ob der Zähler Werte liefert. Misst **ein** Zähler Heizung und Warmwasser zusammen, gehört sein Monatswert
   unter «Wärme gesamt». Mit getrennten Zählern bleibt das Feld leer — die 0 löschen.
3. Speichern, die übrigen Monate der Meldung ebenso.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc rechnet mit Heizwärme und Warmwasser-Wärme; die 0 unter «Wärme gesamt» bleibt gespeichert.
