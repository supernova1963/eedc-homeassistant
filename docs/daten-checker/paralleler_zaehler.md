# Paralleler Zähler am Gerät

## Was eedc sieht
Das Gerät misst seinen Stromverbrauch (bzw. die Ladung) und den Netzbezug zum eigenen Tarif mit demselben Sensor: ein
eigener Zähler parallel zum Hauszähler, das Gerät bezieht keinen PV-Strom. Das ist zulässig — dann muss aber der
Netzbezug der Anlage diesen Zähler enthalten. Fehlt er dort, ist der Netzbezug zu klein, und eedc begrenzt den Anteil
zum eigenen Tarif auf den Netzbezug. Dasselbe gilt beim gemeinsamen Zähler für Wärmepumpe und Wallbox.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Gerät.
2. Prüfen, ob der [Netzbezug der Anlage](eedc:/einstellungen/datenquellen?feld=netzbezug_kwh) beide Zähler enthält:
   Netzbezug der Anlage = Hauszähler + Zähler des Geräts. Wenn nicht, dort einen Sensor zuordnen, der beide Zähler
   zusammen misst.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt als Hinweis, solange der parallele Zähler
   besteht; eine Warnung, der Netzbezug zum Tarif sei größer als der Netzbezug der Anlage, verschwindet, wenn der
   Netzbezug stimmt.

## Was ohne Handlung gilt
eedc rechnet mit dem zugeordneten Netzbezug; enthält er den Gerätezähler nicht, ist er zu klein und der Anteil zum
eigenen Tarif wird darauf begrenzt.
