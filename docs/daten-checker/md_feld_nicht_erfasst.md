# Einspeisung oder Netzbezug nicht erfasst

## Was eedc sieht
Für den Monat steht kein erfasster Wert für Einspeisung bzw. Netzbezug — auch 0 ist ein Wert, aber nur, wenn ihn jemand
geliefert hat (typisch nach einem Import, der nur Wallbox- oder PV-Werte enthielt). Ohne ihn lassen Übersicht,
Jahresbericht, HA-Sensoren, die Tabelle der Auswertungen und die Finanz-Aussicht den Monat aus Eigenverbrauch, Autarkie,
Ersparnis und CO₂ heraus (seine PV-Erzeugung zählen sie weiter), und der Community-Upload teilt ihn nicht. Die
Monatsansicht im Cockpit nimmt den Wert aus der HA-Statistik, sofern ein Zähler zugeordnet ist. Steht dahinter
„(Monat ohne Monatsabschluss)“, gibt es für den Monat keinen Monatsabschluss, und an keinem seiner Tage hat ein Zähler
das Feld gemessen — typisch bei einem Balkonkraftwerk ohne Einspeisungs- oder Netz-Zähler.

## Lösungsweg
1. Zuerst den Wert aus Home Assistant holen, wenn ein Zähler zugeordnet ist: im
   [Statistik-Import](eedc:/einstellungen/integration?block=ha-statistik-import) diesen Monat importieren — ohne
   „Überschreiben“ genügt, solange der Monat so gemeldet ist.
2. Sonst am Befund **«Monat öffnen»** klicken — der Monat öffnet sich zum Bearbeiten («Monatsdaten bearbeiten», für einen
   Monat ohne Monatsabschluss «Monatsdaten erfassen»). Den gemessenen Wert eintragen und speichern. Das Feld steht leer,
   nicht mit 0 — ein leeres Feld ist keine 0; steht schon ein Vorschlag darin, ihn prüfen und speichern.
3. Für einen Monat ohne Monatsabschluss gibt es auch den Weg über die
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen): den Zähler zuordnen. Er zählt ab dann; frühere Tage bleiben
   ohne Wert.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
eedc rechnet das Feld nicht als 0. Eigenverbrauch, Autarkie und Ersparnis des Monats bleiben in der Monats- und der
Jahresansicht im Cockpit leer („–“), sofern die HA-Statistik den Wert nicht liefert; die PV-Erzeugung bleibt.
