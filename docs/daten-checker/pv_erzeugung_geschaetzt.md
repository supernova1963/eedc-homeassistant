# PV-Erzeugung über den kWp-Anteil verteilt

## Was eedc sieht
In diesen Monaten hat mindestens ein PV-Modul keinen eigenen Wert, die Anlage aber einen Gesamtwert. eedc verteilt den
Rest (Gesamtwert minus die gemessenen Module) nach Nennleistung auf die Module ohne Wert; gemessene Module behalten ihren
Wert. Die Summe stimmt, nur die Aufteilung je String ist geschätzt — deshalb nennen die String-Sichten in diesen Monaten
keinen besten oder schwächsten String. Ein Balkonkraftwerk mit zugeordneten PV-Modulen ist selbst ein Gesamtwert für
seine Module: hat es einen Wert und eines seiner Module nicht, gilt der Monat ebenso als abgedeckt.

## Lösungsweg
1. Am Befund **«Was gilt»** klicken — dieser Text. Das ist kein Mangel; wenn dir die Summe genügt, ist nichts zu tun.
2. Wer echte Werte je String will, ordnet jedem PV-Modul einen eigenen Erzeugungs-Zähler zu, in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) beim jeweiligen Modul. Vergangene Monate füllt danach
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import).
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein Modul in diesen Monaten keinen
   eigenen Wert hat.

## Was ohne Handlung gilt
Die PV-Erzeugung der Anlage stimmt; die Werte je String sind in diesen Monaten nach kWp verteilt und keine Messung.
