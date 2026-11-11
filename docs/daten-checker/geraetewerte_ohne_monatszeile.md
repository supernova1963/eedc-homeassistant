# Messwerte ohne Monatszeile

## Was eedc sieht
Für den Monat liegen Messwerte einzelner Geräte vor (die Zeile nennt sie), aber keine Zählerzeile mit Einspeisung und
Netzbezug. Die Werte zählen in Cockpit und Auswertungen mit, der Monat erscheint aber in keiner Monatsliste, fehlt in
Autarkie und Community-Vergleich und weist einen erneuten Import ab. Der Zustand entsteht auf mehreren Wegen
(Statistik-Import ohne Zähler-Sensoren, Cloud-Import ohne Smartmeter, ein früher gelöschter Monat); nachträglich sind
sie nicht zu unterscheiden.

Nennt der Befund einen Zählerstand (Gas, Wasser, Öl — Sonstiges der Kategorie Zähler), ist Nachtragen der einzige
unschädliche Weg: Ein Stand ist kein Monatswert, sondern der Anfangswert des Folgemonats. Entfernst du ihn, rechnet der
nächste Monat gegen den vorletzten Stand und weist zwei Monate als einen aus — ohne Hinweis.

## Lösungsweg
1. Am Befund **«Monat erfassen»** klicken — der Monatsabschluss dieses Monats öffnet sich.
2. Einspeisung und Netzbezug eintragen und speichern — die Messwerte gehören dann wieder dazu. Das ist der Regelfall.
3. Nur wenn die Werte wirklich weg sollen: in der
   [Reparatur-Werkbank](eedc:/einstellungen/daten?block=energieprofil&karte=werkbank) die Operation «Messwerte ohne
   Monatszeile entfernen» wählen, den Monat wählen, **«Plan erstellen»**, die Vorschau lesen und anwenden — das ist
   endgültig.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Monat ist aus der Liste verschwunden.

## Was ohne Handlung gilt
Die Gerätewerte rechnen weiter mit, der Monat bleibt aber ohne Bilanz und unsichtbar, und ein Import dieses Monats wird
abgewiesen.
