# Zählerstand eines Verbrauchszählers ist gefallen

## Was eedc sieht
Ein Zählerstand läuft nicht rückwärts — in dieser Reihe fällt er an einer oder mehreren Stellen (die Details nennen
sie). Für einen Zeitraum über eine solche Stelle hinweg zeigt eedc deshalb keine Differenz statt einer negativen Menge.
eedc heilt den Bruch nicht selbst: dafür müsste es raten, welcher der beiden Stände gilt.

## Lösungsweg
1. Am Befund zeigt **«Was gilt»** diesen Abschnitt. Die Ursache bestimmen — drei kommen in Frage, je mit eigenem Weg:
2. **Zähler gewechselt:** der neue Zähler beginnt niedriger. Unter *Einstellungen → Komponenten → Sonstiges* am alten
   Zähler ein «Stilllegungsdatum (optional)» setzen und den neuen als
   eigenes Gerät anlegen. Den Haken «Aktiv (in Berechnungen berücksichtigen)» am alten Gerät **stehen lassen** — ohne
   ihn verschwindet seine Historie aus allen Auswertungen. Der Verbrauch über den Wechsel ist danach die Summe beider
   Differenzen.
3. **Sensor getauscht oder Stand von Hand korrigiert,** und der neue Wert liegt unter dem alten. Kam der Stand von
   Hand, den Wert im Feld «Zählerstand» des betroffenen Monats prüfen
   ([Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten)); stimmt er, ist der Bruch echt und bleibt stehen.
4. **Umstieg auf eedc 4.0.25:** bis dahin schrieb eedc für Verbrauchszähler die Verbrauchssumme von Home Assistant statt
   des Zählerstands. Dann fällt die Reihe genau einmal, an der Umstellung, und es ist nichts kaputt. In der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) mit «Mehrere Tage neu aggregieren»
   zieht eedc die Historie nach, soweit Home Assistant sie noch hat.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt weniger Stellen; ein
   Bruch aus einem Zählerwechsel bleibt stehen, bis der alte Zähler stillgelegt ist.

## Was ohne Handlung gilt
Für Zeiträume über eine Bruchstelle zeigt eedc für diesen Zähler keine Differenz; Zeiträume davor und danach rechnen
normal. Andere Zahlen sind nicht berührt — der Zähler geht in keine Bewertung ein.
