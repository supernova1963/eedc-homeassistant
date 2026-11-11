# PV-Erzeugung nur teilweise erfasst

## Was eedc sieht
In diesen Monaten hat nur ein Teil der PV-Module (Strings) einen Wert, und es gibt keinen Gesamtwert der Anlage, den eedc
auf die übrigen verteilen könnte. Die Monatssichten zeigen die Summe der erfassten Strings (und des Balkonkraftwerks);
die Monats- und die Jahresansicht im Cockpit sagen dazu, dass es eine Teilsumme ist. Die Prüfungen des Daten-Checkers
rechnen mit einer Teilsumme nicht — sonst meldeten sie Abweichungen, die es nicht gibt.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — der Monatsabschluss des ersten betroffenen Monats öffnet sich beim Feld
   «PV-Erzeugung» eines PV-Moduls.
2. Entweder für die fehlenden Module den Wert eintragen **oder** den Gesamtwert der Anlage — eedc verteilt ihn dann nach
   kWp auf die Module ohne eigenen Wert. Speichern; die übrigen Monate der Meldung ebenso. Mit zugeordneten Sensoren
   holt [«Monatsdaten aus HA-Statistik laden»](eedc:/einstellungen/integration?block=ha-statistik-import) mehrere
   Monate auf einmal.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die vervollständigten Monate sind aus der Zeile verschwunden.

## Was ohne Handlung gilt
Die Sichten zeigen die Teilsumme. Sie ist zu niedrig, wenn dem fehlenden String Erzeugung fehlt; war er wirklich aus,
stimmt sie.
