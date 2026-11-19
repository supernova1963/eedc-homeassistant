# Zählerstände liegen für einen Abschnitt versetzt

## Was eedc sieht
In den gespeicherten Zählerständen eines Felds springt der Stand an einem Tag um einen festen Betrag nach oben, läuft
auf dieser Höhe weiter und fällt später um etwa denselben Betrag zurück — so sieht es aus, wenn eine Zeit lang die
Stände eines anderen Sensors gespeichert wurden, etwa nach einem Wechsel der Zuordnung. eedc bildet einen Tageswert aus
zwei Zählerständen; an den Rändern des Abschnitts ist er deshalb falsch: am Sprung zu hoch, am Rückgang fehlt er
(„Zähler zurückgesprungen“) — auch an einem Tag, an dem im selben Tagesfenster ein Sprung liegt. Die Meldung nennt Gerät
und Feld, den Abschnitt von bis und die Höhe des Versatzes; die Details nennen die Tage, deren Wert zu hoch ist oder
fehlt — nur die Tage, die eedc wirklich aus diesen Zählerständen bildet. Gespeicherte Monatswerte ändert das nicht.

## Lösungsweg
1. Am Befund **«Grund nachtragen»** klicken — die Datenquellen-Zuordnung öffnet sich beim Feld mit der Frage
   **„Warum wechselte die Quelle?"**; oben stehen der Abschnitt mit Beginn und Ende und die Quelle, die davor und danach
   gilt.
2. **„Bisher war der falsche Sensor zugeordnet"** wählen. Die Zeit der Korrektur steht fest: genau der Abschnitt.
3. Die Vorschau unter **„Was danach geschieht"** lesen. eedc verwirft die Zählerstände des Abschnitts. Passen die Stände
   davor und danach zu dem, was Home Assistant für diese Quelle führt, liest eedc die Zählerstände des Abschnitts danach aus
   Home Assistant neu und speichert sie — die Tageswerte stimmen dann an jedem Tag; bis das gelungen ist (etwa weil Home
   Assistant zwischendurch nicht erreichbar ist), zeigen die Tage am Rand des Abschnitts nur ihren Teil, und eedc holt das
   Lesen jede Stunde und nach jedem Start nach. Ohne Verbindung zu Home Assistant, oder führt Home Assistant die Quelle auf
   einer anderen Höhe oder für diese Zeit nichts, bleibt der Abschnitt leer, und eedc rechnet über ihn wie über jede
   Zählerlücke (davor und danach gilt dieselbe Quelle): die Menge des Abschnitts steht an dem Tag, an dem er endet, die Tage
   davor zeigen für diese Zeit keinen Wert; ist zwischen den Ständen davor und danach ein Zählertausch eingetragen, bildet
   eedc über den Abschnitt keine Differenz — die Tage darin zeigen keinen Wert, die Tage an seinem Rand nur ihren Teil (der
   Befund sagt es). Die Vorschau nennt die Tage.
4. **„Übernehmen"** klicken. Die Korrektur lässt sich in eedc nicht rückgängig machen.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Befund steht danach unter den bestandenen Prüfungen
   («Kein versetzter Abschnitt in den gespeicherten Zählerständen»).

In zwei Lagen trägt der Befund statt «Grund nachtragen» den Knopf «Was gilt»: Gelten vor und nach dem Abschnitt
verschiedene Quellen, nennt er beide — eedc weiß dann nicht, welche die richtige ist, und korrigiert den Abschnitt nicht. Ist Home Assistant
eingerichtet, aber gerade nicht erreichbar, sagt er es; sobald eedc die Langzeitstatistik wieder lesen kann, steht beim
nächsten **«Aktualisieren»** wieder **«Grund nachtragen»** am Befund.

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
