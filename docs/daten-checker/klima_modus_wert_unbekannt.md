# Betriebsmodus-Sensor liefert einen Wert, den eedc nicht kennt

## Was eedc sieht
Der zugeordnete Betriebsmodus-Sensor einer Wärmepumpe oder Klimaanlage meldet beim Prüfen einen Wert, den eedc nicht
versteht — etwa „heating“, „standby“ oder „pool“ aus einem eigenen Prioritäts-Sensor. Die Meldung nennt den Sensor und die
Liste der Werte, die eedc versteht; Groß-/Kleinschreibung ist egal. Stunden mit einem unbekannten Wert zählen als
unbestimmt: Ihr Strom steht unter „nicht aufgeteilt“.

## Lösungsweg
1. In eedc ist dafür nichts umzustellen — der Wert kommt aus Home Assistant. Dort einen Template-Sensor anlegen, der aus
   deinen Werten einen der Texte macht, die eedc versteht (Vorlage und Werte-Tabelle im Handbuch «Wärme & Klima»,
   Schritt 4, Weg B).
2. Den neuen Sensor in der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim Gerät im Feld «Betriebsmodus»
   zuordnen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald der zugeordnete Sensor einen
   bekannten Wert meldet. Geprüft wird der Wert von jetzt: Ein Wert, der nur zeitweise auftaucht, fällt auf, wenn er beim
   Prüfen ansteht.

## Was ohne Handlung gilt
Der Stromverbrauch zählt weiter vollständig; nur die Stunden mit dem unbekannten Wert stehen unter „nicht aufgeteilt“. Die
Aufteilung beginnt mit dem neuen Sensor — Stunden davor bleiben, wie sie sind.
