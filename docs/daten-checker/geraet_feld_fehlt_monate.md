# Monatswert eines Geräts fehlt

## Was eedc sieht
Ein Pflichtfeld des Geräts ist in den genannten Monaten ab dem Anschaffungsdatum leer; die Meldung nennt Gerät und Feld.
Typische Fälle: «Speicher-Ladung» (ohne sie gibt es für diese Monate keine Vollzyklen und keinen Wirkungsgrad), «Ladung
gesamt» an der Wallbox, «Ladung PV» an einem E-Auto ohne Wallbox (der PV-Anteil der Ladung bleibt unbekannt) und
«PV-Erzeugung» am Balkonkraftwerk. Das Balkonkraftwerk wird nur gemeldet, wenn es weder einen eigenen Wert noch einen
Anteil am PV-Gesamtwert der Anlage hat — mit gespeichertem Gesamtwert bekommt es seinen kWp-Anteil, dann fehlt nichts.
E-Autos mit Wallbox und Dienstwagen werden nach «Ladung PV» nicht gefragt.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld des
   Geräts. Im Formular heißt es am Speicher «Ladung», am E-Auto «Heim: PV», am Balkonkraftwerk «Erzeugung».
2. Den Wert eintragen (auch 0 ist ein Wert) und speichern, die übrigen Monate der Meldung ebenso. Ist am Gerät ein Sensor
   zugeordnet, holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import)
   mehrere Monate auf einmal. Am Balkonkraftwerk genügt auch der PV-Gesamtwert der Anlage im selben Monat.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
Die Monate bleiben ohne diesen Wert; die Auswertungen des Geräts rechnen für sie nicht oder unvollständig. eedc setzt
keine 0.
