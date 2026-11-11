# «Strom Heizbetrieb» und «Strom Heizen» beide belegt

## Was eedc sieht
An der Wärmepumpe sind der Betriebsart-Zähler «Strom Heizbetrieb» und der Zähler «Strom Heizen» zugeordnet
(Home-Assistant-Sensor oder MQTT). Der Betriebsart-Zähler hat Vorrang — «Strom Heizen» wird nicht gezählt. Misst er
wirklich den Heizbetrieb, ist das richtig; liegt dort ein anderer Zähler (etwa der Kühlbetrieb), zeigt eedc unter Heizen
dessen Wert. Nur Heizen ist betroffen: Warmwasser hat keinen Betriebsart-Zähler, Kühlen keinen eigenen Summanden.

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung dieser Wärmepumpe öffnet sich.
2. Prüfen, was der Sensor bei «Strom Heizbetrieb» misst. Misst er den Heizbetrieb, ist nichts zu tun.
3. Misst du Heizen und Warmwasser getrennt, bei «Strom Heizbetrieb» die Quelle «Keine» wählen.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald nur noch einer der beiden
   Zähler zugeordnet ist.

## Was ohne Handlung gilt
eedc zählt unter Heizen den Betriebsart-Zähler; der Wert von «Strom Heizen» bleibt unberücksichtigt.
