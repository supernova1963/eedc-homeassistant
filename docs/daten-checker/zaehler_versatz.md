# Zählerstände liegen für einen Abschnitt versetzt

## Was eedc sieht
In den gespeicherten Zählerständen eines Felds springt der Stand an einem Tag um einen festen Betrag nach oben, läuft
auf dieser Höhe weiter und fällt später um etwa denselben Betrag zurück — so sieht es aus, wenn eine Zeit lang die
Stände eines anderen Sensors gespeichert wurden, etwa nach einem Wechsel der Zuordnung. eedc bildet einen Tageswert aus
zwei Zählerständen; an den Rändern des Abschnitts ist er deshalb falsch: am Sprung zu hoch, am Rückgang fehlt er
(„Zähler zurückgesprungen“). Die Meldung nennt Gerät und Feld, den Abschnitt von bis, die Höhe des Versatzes und die
Tage, die zu hoch sind oder fehlen. Gespeicherte Monatswerte ändert das nicht.

## Lösungsweg
1. Steht am Befund **«Tage neu aufbauen»**: klicken, die Vorschau lesen und **«Anwenden»** — eedc holt die Zählerstände
   der genannten Tage neu aus Home Assistant und baut diese Tage neu auf, höchstens 31 Tage je Lauf. Den Knopf gibt es
   nur, wenn die Stände vor und nach dem Abschnitt mit dem übereinstimmen, was Home Assistant für den heute zugeordneten
   Sensor führt — dann heilt der Lauf den Abschnitt. Der Lauf übernimmt für diese Tage die Stände **aller** Zähler der
   Anlage neu aus Home Assistant und holt Wetter- und Börsenpreis-Werte der Tage neu ab; dafür braucht eedc eine
   Internetverbindung.
2. Ist der Abschnitt länger als 31 Tage, nennt der Befund nach dem ersten Lauf den Rest: noch einmal
   **«Tage neu aufbauen»** und **«Anwenden»**.
3. Steht am Befund nur **«Was gilt»**: eedc kann den Abschnitt nicht selbst richtigstellen — ohne Verbindung zu Home
   Assistant nicht, und wenn die Stände vor oder nach dem Abschnitt nicht zum heute zugeordneten Sensor passen, auch
   nicht, weil neu geholte Stände den Versatz nur an eine andere Stelle schöben. Endet der Abschnitt heute, steht der
   Knopf ab morgen da.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach dem letzten Lauf steht der Befund unter den bestandenen
   Prüfungen («Kein versetzter Abschnitt in den gespeicherten Zählerständen»).

Bleibt der Befund nach dem Klick stehen: stell deine Frage im Forum oder auf GitHub. Bitten wir dich dort um das
Diagnose-Paket: im Kopf des Daten-Checkers **«Diagnose-Paket»** öffnen, **«Herunterladen»** und die Datei an die Adresse
aus unserer Antwort schicken.

## Was ohne Handlung gilt
Die Tageswerte an den genannten Tagen bleiben falsch: am Sprung zu hoch, am Rückgang ohne Wert. eedc stellt sie nicht
von selbst richtig. Tage, die eedc aus der Statistik von Home Assistant rechnet, und gespeicherte Monatswerte sind nicht
betroffen.

Was dieser Befund nicht erkennt oder nicht abdeckt:
- Ein einzelner alter Wechsel, nach dem die Stände nicht wieder zurückgehen, wird nicht erkannt — der Befund braucht den
  Sprung und den Rückgang um etwa denselben Betrag.
- Die Netzladung des Speichers liest eedc für jeden Monat, für den keine Monatswerte des Speichers gespeichert sind, aus
  den gespeicherten Zählerständen; ein versetzter Abschnitt geht dort ungekürzt in den Monatswert ein.
- Ohne Stundenwerte aus Home Assistant (eedc ohne Home Assistant, Werte über MQTT) rechnet eedc jeden Tag aus den
  gespeicherten Zählerständen — dort sind an beiden Rändern des Abschnitts die Tageswerte dieses Felds falsch.
