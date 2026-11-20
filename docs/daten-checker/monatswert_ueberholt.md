# Gespeicherter Monatswert passt nicht mehr zur Quelle

## Was eedc sieht
Für diesen Monat ist ein Monatswert gespeichert, und ein Wechsel der Quelle («Bisherige Werte bleiben»), ein eingetragener
Zählertausch oder eine Korrektur hat seither geändert, was die Quelle für diesen Monat ergibt — um mindestens 1 kWh. eedc prüft
nur Monate bis zu dem Monat, in dem der Wechsel eingetragen wurde; einen späteren Monat hast du schon mit dem Wechsel gespeichert. Die
Meldung nennt Feld und Monat, die Details den gespeicherten Wert, den Wert der Quelle und seit wann er gilt. Alles, was eedc für
diesen Monat zeigt, rechnet mit dem gespeicherten Wert.

## Lösungsweg
1. Am Befund **«Monat öffnen»** klicken — das Formular des Monats öffnet sich: bei Einspeisung oder Netzbezug der Anlage beim
   Feld, bei einem Gerät beim Gerät; dort das Feld aus der Meldung suchen.
2. Den Wert der Quelle aus den Details in das Feld eintragen. Steht unter dem Feld «Sensor meldet …», genügt
   **«Sensorwert übernehmen»**, wenn dort derselbe Wert steht.
3. **«Speichern & abschließen»** klicken.
4. Soll der gespeicherte Wert bleiben (etwa, weil er von einem geeichten Zähler abgelesen ist): im Formular beim Feld
   **«gespeicherten behalten»** wählen und speichern — dann nennt eedc den Monat nicht mehr.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Liste verschwunden.

## Was ohne Handlung gilt
Der gespeicherte Monatswert bleibt, und eedc rechnet den Monat weiter mit ihm. Tageswerte und die Tagesansicht folgen der
Quelle; Monat und Tage dieses Monats passen dann um die genannte Abweichung nicht zueinander. eedc ändert keinen gespeicherten
Wert von selbst.
