# Volleinspeisung ohne AC-Ertragszähler

## Was eedc sieht
Es gibt keinen Anlagenzähler, und in den letzten drei abgeschlossenen Monaten ging fast die ganze Erzeugung der
String-Zähler ins Netz. Was dazwischen fehlt, sind bei einer Volleinspeisung vor allem die Verluste im Wechselrichter —
die kennt eedc nur mit einem Zähler nach dem Wechselrichter.

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Dort den AC-Ertragszähler deines Wechselrichters (Gesamtertrag nach dem Wechselrichter) zuordnen. Denselben Sensor
   zusätzlich als Einspeisung zuzuordnen ist nicht der Weg — das meldet die Datenquellen-Prüfung als Doppelzählung.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
eedc kennt die Wandlungsverluste nicht und rechnet deshalb auch aus ihnen eine Ersparnis — sie zählen, als wären sie
im Haus verbraucht worden.
