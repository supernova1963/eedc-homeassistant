# Zählerstand springt zwischendurch zurück

## Was eedc sieht
Ein Zählerstand muss fortlaufend steigen. Bei den genannten Feldern fällt der per MQTT gelieferte Stand in den letzten
30 Tagen mindestens einmal auf einen niedrigeren Wert zurück — fällt er immer wieder zurück, typisch für ein Feld, das
„heute“ oder „diesen Monat“ meint statt des Gesamtstands; fällt er einmal, kann auch ein neuer Zähler begonnen oder die
Quelle eine Zeit lang einen anderen Stand gesendet haben (dann nennt oft auch „Zählerstand springt (MQTT)“ den Sprung). eedc bildet eine Menge aus zwei Ständen; liegt dazwischen ein Neubeginn, ist ihre
Differenz keine Menge. Die Meldung nennt die Felder, wie oft es passiert ist, und belegt den jüngsten Fall mit beiden
Ständen. Ein Rückgang an einem Wechsel, den eedc als Fortsetzung kennt (Zähler getauscht oder neuer Sensor für dasselbe
Gerät, Handbuch Einstellungen §7.7), zählt nicht — dort ist der neue Stand der Beginn des neuen Zählers.

## Lösungsweg
1. Am Befund **«Sensor wechseln»** klicken — die Datenquellen-Zuordnung öffnet sich beim betroffenen Feld. Dort siehst
   du, woher der Wert kommt. Wählst du dort eine andere Quelle und hat das Feld schon eigene Werte, fragt eedc vor dem
   Speichern **„Warum wechselt die Quelle?"** (Handbuch Einstellungen §7.7).
2. Den fortlaufenden Stand schicken statt des Tageswerts: Kommt der Wert aus einem Helfer von Home Assistant, unter
   *Einstellungen → Geräte & Dienste → Helfer* den Verbrauchszähler öffnen und das Zurücksetzen auf „nie“ (ohne Zyklus)
   stellen. Kommt er aus einer eigenen App oder einem Skript, dort den Lebenszählerstand senden. Wurde der Zähler
   getauscht, in den [Datenquellen](eedc:/einstellungen/datenquellen) am Feld das Symbol „Zähler getauscht (gleiche
   Quelle)“ öffnen und den Tausch eintragen; hat die Quelle eine Zeit lang einen falschen Stand gesendet, liegt der Fehler
   dort.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Befund verschwindet von selbst, sobald in den letzten
   30 Tagen kein Rücksprung mehr liegt; es gibt nichts zu quittieren.

## Was ohne Handlung gilt
Für ein solches Feld liefert eedc keinen Wert: im Monatsabschluss steht kein Vorschlag, in der Monatsansicht im Cockpit
bleibt der gespeicherte Wert stehen. Rechnet eedc das Feld über eine eigene Summe (die Meldung sagt das), stimmen Tag,
Monat und Jahr trotzdem; nicht verlässlich bleiben dann „heute“ und „gestern“ im Live-Bereich sowie die Tageswerte
der Geräte aus der Zeit, bevor eedc diese eigene Summe führte. eedc rechnet den
fehlenden Teil nicht hoch — er steht in keinem Stand.
