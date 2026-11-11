# Netzbezug zum Tarif größer als der Verbrauch des Geräts

## Was eedc sieht
In den genannten Monaten ist «Netzbezug zum WP-Tarif» bzw. «Netzbezug zum Wallbox-Tarif» größer als der Stromverbrauch
bzw. die Ladung des Geräts (Toleranz 2 %). Beim gemeinsamen Zähler ist die Vergleichsmenge WP-Strom und Ladung
zusammen. Mehr, als das Gerät verbraucht, kann der Versorger nicht zum eigenen Tarif abgerechnet haben — eedc begrenzt
den Monat auf den Verbrauch; die Herleitung zeigt es als «begrenzt».

## Lösungsweg
1. Am Befund **«Zuordnung prüfen»** klicken — die Datenquellen-Zuordnung öffnet sich beim betroffenen Gerät
   (Wärmepumpe bzw. Wallbox; beim gemeinsamen Zähler die Wärmepumpe) am Feld für den Netzbezug zum Tarif; ist nicht
   eindeutig, welches Gerät es trägt, öffnet sie sich ohne Feld.
2. Prüfen, ob dort der richtige Sensor steht: der Zähler des Versorgers, also Zähler vor dem Gerät minus Zähler nach dem
   Gerät — und ob der Verbrauch des Geräts vollständig zugeordnet ist.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Monate neu erfasst sind.

## Was ohne Handlung gilt
eedc rechnet in diesen Monaten mit dem Verbrauch des Geräts als Netzbezug zum Tarif, nicht mit dem höheren Wert.
