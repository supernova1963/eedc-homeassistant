# Eigener Tarif ohne gemessenen Netzbezug zum Tarif

## Was eedc sieht
Für Wärmepumpe oder Wallbox gilt ein eigener Tarif mit anderem Arbeitspreis als der Haushaltstarif, aber in Monaten der
letzten zwölf fehlt das Feld «Netzbezug zum WP-Tarif» bzw. «Netzbezug zum Wallbox-Tarif» (beim gemeinsamen Zähler
«Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)»). Ohne diese Menge bewertet eedc den Strom des Geräts zum
Haushaltstarif. Die Zeile nennt die Obergrenze, um die Ersparnis und Stromrechnung zusammen daneben liegen können:
Gerätemenge dieser Monate × Tarifdifferenz.

## Lösungsweg
1. Der Knopf **«Was gilt»** am Befund öffnet diesen Abschnitt: eedc rechnet ohne das Feld mit dem Haushaltstarif; die genannte
   Summe ist eine Obergrenze, keine gemessene Abweichung.
2. Misst dein Versorger den Tarif-Strom über einen Zähler, ihn in der
   [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen?feld=netzbezug_eigener_tarif_kwh) beim Gerät im Block
   «Gerät gesamt» zuordnen — gemeint ist der Zähler des Versorgers: Zähler vor dem Gerät minus Zähler nach dem Gerät.
   Mehr dazu im Handbuch «Wärme & Klima», Schritt 6b.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald das Feld in allen Monaten
   mit Gerätestrom einen Wert hat; ohne Zähler bleibt sie als Auskunft stehen.

## Was ohne Handlung gilt
Ersparnis und Stromrechnung rechnen den Strom des Geräts zum Haushaltstarif und liegen zusammen höchstens um die
genannte Summe daneben.
