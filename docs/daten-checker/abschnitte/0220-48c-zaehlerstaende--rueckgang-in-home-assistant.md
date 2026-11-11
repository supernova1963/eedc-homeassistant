<!-- anker: 48c-zaehlerstaende--rueckgang-in-home-assistant -->
### 4.8c Zählerstände – Rückgang in Home Assistant <a name="48c-zaehlerstaende--rueckgang-in-home-assistant"></a>

Das Gegenstück zum Sprung: Die Summe eines Sensors in der Langzeitstatistik von Home Assistant **fällt** in einer
Stunde, statt zu steigen. Meist wurde der Wert in Home Assistant nachträglich nach unten angepasst (unter
*Entwicklerwerkzeuge → Statistik* mit „Wert anpassen“, mit einer zu großen Korrektur oder an der falschen Stunde), oder
ein Sensor hat einen kleineren Zählerstand gemeldet. Home Assistant bucht das als negative Menge, und eedc übernimmt die
Statistik so, wie das Energie-Dashboard sie zeigt — der Rückgang steht als Abzug in Tag, Monat und Jahr, und
«Aus HA laden» schlägt für den Monat einen zu kleinen oder negativen Wert vor.

Das ist **kein Vorzeichen** für Entladen oder Einspeisen: Lade-, Entlade- und Einspeisezähler laufen nur nach oben, jede
Richtung hat ihr eigenes Feld. Fällt ein Entlade-Zähler, ist das kein Entladen, sondern ein gesunkener Zählerstand —
typisch nach dem Neustart einer Integration, die den Zähler selbst hochrechnet und mit der Zustandsklasse `total` statt
`total_increasing` meldet.

Geprüft wird die **ganze** übernommene Statistik, nicht nur die letzten 30 Tage: ein Rückgang aus einem alten Monat trifft
jede Sicht und «Aus HA laden» genauso wie ein frischer. Der Tag eines Funds ist der Kalendertag, wie im
Energie-Dashboard von Home Assistant: auch die Stunde ab 23:00 gehört zu ihrem eigenen Tag (in der Tagesansicht im
Cockpit die Stunde 23–24 Uhr). Ein täglich zurückgesetzter Helfer ist kein Befund (sein Stand fällt jede Nacht, die
Summe in Home Assistant zählt weiter), ein Zählersprung ([§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant)) auch
nicht — dort steigt die Summe.

Lädst du einen betroffenen Monat mit «Aus HA laden» in einen Monat, der schon Daten hat, nennt der Vergleichsdialog die
Felder mit negativem Wert unter „Rückgang in Home Assistant“ und denselben Weg.

> **Stunden ohne Langzeitstatistik.** Wo die Langzeitstatistik von Home Assistant für eine Stunde nichts hat, nimmt eedc
> seine eigenen gespeicherten Stundenstände dieses Zählers — aber nur für die Zeit vor dem ersten Wert aus Home
> Assistant, nicht für Lücken mittendrin, und ein späterer Abgleich mit Home Assistant ersetzt diese Stunden nicht.
> Liegen von einem Zähler nur Stände um Mitternacht vor, stimmen die Tagesmengen; die Stundenansicht zeigt den Tag als
> eine Spanne ohne Verteilung auf die Stunden.

---
