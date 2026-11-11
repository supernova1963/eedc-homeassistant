# Keine Monatsdaten vorhanden

## Was eedc sieht
Es gibt keinen einzigen Monat mit Einspeisung und Netzbezug. Cockpit, Aussicht, Amortisation und Community-Vergleich
bleiben leer.

## Lösungsweg
1. Am Befund **«Monat erfassen»** klicken — der Monatsabschluss des ersten Monats ab der «Inbetriebnahme (Anlage)»
   öffnet sich; ohne dieses Datum der Monat des ältesten Anschaffungsdatums eines PV-Moduls oder Balkonkraftwerks, sonst
   die Monatsdaten-Liste.
2. Einspeisung und Netzbezug eintragen (auch 0 ist ein Wert) und speichern. Mit zugeordneten Zählern in Home Assistant
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) viele Monate
   auf einmal; vorhandene Daten liest unter [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)
   **«CSV importieren»** ein.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden; fehlen noch Monate, nennt der
   Daten-Checker sie einzeln.

## Was ohne Handlung gilt
Ohne Monate gibt es keine Bilanz, keine Jahreswerte und keinen Vergleich; eedc schätzt nichts.
