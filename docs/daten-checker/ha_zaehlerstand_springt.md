# Zählerstand springt in der Statistik von Home Assistant

## Was eedc sieht
In einer Stunde ist der Zählerstand eines Sensors gesprungen — meist, weil das Gerät dahinter getauscht wurde und Home
Assistant denselben Sensor weiterführt. Zeigt der neue Zähler mehr als der alte, zählt Home Assistant den Unterschied als
Verbrauch bzw. Erzeugung dieser Stunde; beginnt der neue Zähler nicht bei 0, zählt es seinen ganzen Stand. eedc übernimmt die
Statistik so, wie das Energie-Dashboard von Home Assistant sie zeigt, und berichtigt nichts — der Sprung steht deshalb in Tag,
Monat und Jahr. Die Meldung nennt je Fund Feld, Sensor, Tag, Stunde und die Menge, die eedc wie Home Assistant dafür zählt.

Dasselbe gilt, wenn die Statistik eines Sensors in Home Assistant gar nicht bei 0 beginnt, sondern mit einem großen Stand —
etwa, weil sie importiert wurde: Home Assistant zählt diesen Stand als Menge der ersten Stunde, eedc ebenso. Die Meldung sagt
dann „die Statistik beginnt mit diesem Stand statt bei 0“. eedc nennt das nur, wenn der Stand mehr
ist, als eine Anlage in einer Stunde erzeugen oder verbrauchen kann.

Ein dritter Fall betrifft die **gefahrenen Kilometer**: Tag und Tabelle zählen die Zunahme des Kilometerstands, der Monatswert
(Vorschlag im Monatsabschluss, „Aus HA laden“) die Summe der Statistik. Beginnt Home Assistant die Summe mitten in der Reihe
neu — meist nach einer Lücke in der Statistik —, während der Stand weiterläuft, stehen für denselben Monat zwei Zahlen. Die
Meldung sagt dann „die Summe beginnt neu, der Stand läuft weiter“ und nennt den Tag mit beiden Tageszahlen.

## Lösungsweg
1. In Home Assistant unter *Einstellungen → Werkzeuge → Statistik* (in älteren Home-Assistant-Versionen: *Entwicklerwerkzeuge → Statistik*) den genannten Sensor suchen und beim Symbol „Summe anpassen“ den Dialog
   „Eine Statistik anpassen“ öffnen: unter „Zeitpunkt auswählen“ die Zeit des Sprungs in der genannten Stunde wählen, bei
   „Neuer Wert“ die echte Menge eintragen und „Anpassen“ drücken. Beginnt die Statistik mit einem großen Stand, ist das
   die erste Stunde der Statistik, und die echte Menge ist das, was in dieser ersten Stunde wirklich gezählt wurde.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»** —
   eedc holt die berichtigte Statistik und baut den Tag des größten Funds neu auf. Ohne Klick gleicht eedc die
   Statistik beim nächtlichen Abgleich von selbst ab.
3. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
4. **Zählerstand** (Gas, Wasser, Öl, Kilometerstand; die Meldung sagt es): hier rechnet eedc mit dem Stand, den der Sensor
   anzeigt, und „Summe anpassen“ wirkt nicht. Wurde der Zähler getauscht, führe den neuen als eigenes Gerät: unter
   *Einstellungen → Komponenten* am alten Gerät ein «Stilllegungsdatum (optional)» setzen, den Haken «Aktiv (in
   Berechnungen berücksichtigen)» stehen lassen und den neuen Zähler als eigenes Gerät anlegen (Handbuch Einstellungen,
   Verbrauchszähler). Beim nächsten Tausch zählt kein Sprung, wenn du in Home Assistant für den neuen Zähler einen eigenen
   Sensor oder Helfer anlegst, ihn in eedc unter [Datenquellen](eedc:/einstellungen/datenquellen) dem Feld zuordnest
   und im Dialog «Bisherige Werte bleiben» wählst.
5. **Summe beginnt neu, der Stand läuft weiter** (gefahrene Kilometer; die Meldung sagt es): wie in Schritt 1 „Summe
   anpassen“ öffnen, unter „Zeitpunkt auswählen“ die genannte Stunde wählen und bei „Neuer Wert“ die Zunahme des Stands in
   dieser Stunde eintragen (der Unterschied der beiden Stände, die die Meldung in Klammern nennt), dann „Anpassen“. Danach
   Schritt 2 und, für gespeicherte Monate, Schritt 3 — oder den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) von Hand berichtigen. Damit zählen Tag, Tabelle und Monatswert
   dieselbe Zahl; die Kilometer der Lücke stehen dann im Tag des Neubeginns, wie der Stand sie zeigt.
6. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach den Schritten 1 und 2 (bzw. 5) ist der Befund aus der Liste
   verschwunden. Ein Sprung an einem Zählerstand (Schritt 4) bleibt stehen; die Zeile erklärt ihn weiterhin.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Der Sprung bleibt in Tag, Monat und Jahr stehen — in eedc wie im Energie-Dashboard von Home Assistant. eedc schneidet ihn
nicht selbst ab: die Quelle ist die Statistik in Home Assistant.
