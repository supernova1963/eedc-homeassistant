# Zählerstand springt in der Statistik von Home Assistant

## Was eedc sieht
In einer Stunde ist der Zählerstand eines Sensors gesprungen — meist, weil das Gerät dahinter getauscht wurde und Home
Assistant denselben Sensor weiterführt. Zeigt der neue Zähler mehr als der alte, zählt Home Assistant den Unterschied als
Verbrauch bzw. Erzeugung dieser Stunde; beginnt der neue Zähler nicht bei 0, zählt es seinen ganzen Stand. eedc übernimmt die
Statistik so, wie das Energie-Dashboard von Home Assistant sie zeigt, und berichtigt nichts — der Sprung steht deshalb in Tag,
Monat und Jahr. Die Meldung nennt je Fund Feld, Sensor, Tag, Stunde und die Menge, die eedc wie Home Assistant dafür zählt.

## Lösungsweg
1. In Home Assistant unter *Entwicklerwerkzeuge → Statistik* den genannten Sensor suchen, beim Symbol „Wert anpassen“
   die genannte Stunde wählen und den Zuwachs auf die echte Menge setzen.
2. Zurück in eedc am Befund **«Aus Home Assistant neu übernehmen»** klicken, die Vorschau lesen und **«Anwenden»** —
   eedc holt die berichtigte Statistik und baut den Tag des größten Funds neu auf. Ohne Klick gleicht eedc die
   Statistik beim nächtlichen Abgleich von selbst ab.
3. Hast du einen betroffenen Monat schon gespeichert (mit «Aus HA laden» oder per Import), den Monat unter
   [Monatsdaten](eedc:/einstellungen/daten?block=monatsdaten) öffnen und mit «Aus HA laden» neu übernehmen — ein
   gespeicherter Monat ändert sich nicht von allein.
4. **Zählerstand** (Gas, Wasser, Öl, Kilometerstand; die Meldung sagt es): hier rechnet eedc mit dem Stand, den der Sensor
   anzeigt, und „Wert anpassen“ wirkt nicht. Wurde der Zähler getauscht, führe den neuen als eigenes Gerät: unter
   *Einstellungen → Komponenten* am alten Gerät ein «Stilllegungsdatum (optional)» setzen, den Haken «Aktiv (in
   Berechnungen berücksichtigen)» stehen lassen und den neuen Zähler als eigenes Gerät anlegen (Handbuch Einstellungen,
   Verbrauchszähler). Beim nächsten Tausch zählt kein Sprung, wenn du in Home Assistant für den neuen Zähler einen eigenen
   Sensor oder Helfer anlegst, ihn in eedc unter [Datenquellen](eedc:/einstellungen/datenquellen) dem Feld zuordnest
   und im Dialog «Bisherige Werte bleiben» wählst.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach den Schritten 1 und 2 ist der Sprung aus der Liste
   verschwunden. Ein Sprung an einem Zählerstand bleibt stehen; die Zeile erklärt ihn weiterhin.

Bleibt der Befund danach: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das Diagnose-Paket:
im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei
an die Adresse aus unserer Antwort schicken.

## Was ohne Handlung gilt
Der Sprung bleibt in Tag, Monat und Jahr stehen — in eedc wie im Energie-Dashboard von Home Assistant. eedc schneidet ihn
nicht selbst ab: die Quelle ist die Statistik in Home Assistant.
