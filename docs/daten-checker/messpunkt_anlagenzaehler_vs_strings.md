# Anlagenzähler und String-Zähler messen verschiedene Dinge

## Was eedc sieht
In den genannten Monaten liegt die Summe der String-Zähler um mehr als 10 % über dem Anlagenzähler (Feld „PV gesamt“).
Wechselrichterverluste dieser Höhe sind nicht plausibel — meist misst der Anlagenzähler nicht dieselbe Anlage wie die
Strings: ein String fehlt in ihm, oder er misst nach dem Speicher. eedc zeigt die Differenz als Wandlungsverluste,
zieht sie in diesen Monaten aber nicht von Ersparnis, Umsatzsteuer und CO₂ ab.

## Lösungsweg
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Prüfen, welcher Sensor dort steht: Er soll den Gesamtertrag aller Strings nach dem Wechselrichter zählen, nicht einen
   Teil der Anlage und nicht den Ausgang nach dem Speicher. Passt er nicht, den richtigen Zähler zuordnen; passt er,
   die Zähler der einzelnen PV-Module auf derselben Seite prüfen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile nennt nur noch Monate, in denen die Zähler weiter so
   weit auseinanderliegen.

## Was ohne Handlung gilt
eedc zeigt die Differenz weiter als Wandlungsverluste an, bewertet sie in diesen Monaten aber nicht: Ersparnis,
Umsatzsteuer und CO₂ rechnen ohne Abzug. Bilanz, Autarkie und Eigenverbrauchsquote bleiben davon unberührt.
