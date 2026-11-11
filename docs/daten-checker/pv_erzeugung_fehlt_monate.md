# PV-Erzeugung fehlt in Monaten

## Was eedc sieht
Für diese Monate gibt es gar keine PV-Quelle — weder einen Wert je PV-Modul noch einen Gesamtwert der Anlage. Ohne
PV-Erzeugung fehlen Eigenverbrauch, Autarkie und Ersparnis dieser Monate. Geprüft wird anlagenweit, nicht je Modul: ein
einziger Gesamtwert deckt alle Strings ab. Bei Anlagen mit eigenem Zähler am Balkonkraftwerk kann ein Monat auch ohne
dein Zutun leer sein — eine frühere Start-Migration hat dort den Gesamtwert mitgeleert. Zurückholen kann eedc ihn nicht;
die Schritte unten füllen die Monate neu.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «PV-Erzeugung» eines PV-Moduls.
2. Ist ein PV-Sensor zugeordnet, holt
   [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) die Monate auf
   einmal; der Monatsabschluss tut es für seinen Monat. Beide schreiben die Werte je Modul.
3. Ohne zugeordneten Sensor die Werte von Hand eintragen — je Modul oder als Gesamtwert der Anlage — und speichern.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die nachgetragenen Monate sind aus der Zeile verschwunden.

Die Reparatur-Werkbank hilft hier nicht: «Tag neu aggregieren» und «Mehrere Tage neu aggregieren» bauen das stündliche
Energieprofil neu, nicht die Monatswerte.

## Was ohne Handlung gilt
Die Monate bleiben ohne PV-Erzeugung: Bilanz, Jahreswerte und Wirtschaftlichkeit rechnen ohne sie. eedc setzt keine 0
und schätzt nichts.
