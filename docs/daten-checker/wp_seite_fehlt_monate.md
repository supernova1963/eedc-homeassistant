# Eine Stromseite der Wärmepumpe fehlt

## Was eedc sieht
Bei getrennter Strommessung ist in diesen Monaten die Wärme einer Seite erfasst, der Strom dafür nicht: «Strom Heizen»
neben einer erfassten «Heizwärme» oder «Strom Warmwasser» neben einer erfassten «Warmwasser-Wärme». eedc bildet jede
Arbeitszahl aus abgegebener Wärme ÷ eingesetztem Strom und setzt dafür beide Seiten voraus. Die Zeile dieser Funktion
sagt es bereits („kein Stromverbrauch erfasst“); die Gesamt-Arbeitszahl rechnet dann die Wärme beider Seiten über dem
Strom einer und fällt zu hoch aus.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim fehlenden
   Feld.
2. Den Wert eintragen und speichern, die übrigen Monate der Meldung ebenso.
3. Soll dieser Zähler künftig von allein mitlaufen, ihn zusätzlich in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei dieser Wärmepumpe zuordnen. Die Zuordnung wirkt nach
   vorn; vergangene Monate füllt nur der Monatsabschluss.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
Die Gesamt-Arbeitszahl dieser Monate rechnet mit einem unvollständigen Nenner und fällt zu hoch aus.
