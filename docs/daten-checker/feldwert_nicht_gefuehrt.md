# Wert in einem Feld, das das Gerät nicht führt

## Was eedc sieht
In den genannten Monaten steht ein Wert (nicht 0) in einem Feld, das dieses Gerät nach seinen Einstellungen nicht führt:
Netzladung an einem Speicher ohne «Lädt aus dem Netz», V2H-Entladung an einem E-Auto ohne «V2H-fähig», Speicherwerte an
einem Balkonkraftwerk ohne «Mit Speicher», getrennte Ströme Heizen/Warmwasser nach Abschalten der getrennten
Strommessung, Warmwasser-Wärme an einer Split-Klimaanlage — oder unter Sonstiges ein Feld, das die gewählte «Kategorie»
nicht liest. Das Feld fehlt deshalb im Monatsabschluss, der Wert ist dort nicht erreichbar und zählt in keiner Bilanz.
Eine Meldung je Feld, nicht je Monat.

## Lösungsweg
1. Prüfen, ob die Einstellung am Gerät stimmt.
2. Stimmt sie: am Befund **«Wert entfernen»** klicken, die Vorschau lesen, **«Anwenden»** — der Wert verschwindet aus
   allen genannten Monaten. Das ist endgültig.
3. Soll der Wert weiter zählen: stattdessen die Einstellung am Gerät zurückstellen (*Einstellungen → Komponenten*, das
   Gerät bearbeiten; unter Sonstiges die «Kategorie») — dann erscheint das Feld wieder im Monatsabschluss.
4. Vorher umtragen, wo der Wert woanders hingehört: Warmwasser-Wärme einer Split-Klimaanlage, die aus dem Kühlbetrieb
   stammt, im Monatsabschluss unter «Nutzenergie Kühlbetrieb» — daraus rechnet eedc die Arbeitszahl Kühlen. Ein Gerät,
   das von «Erzeuger» auf «Abgabe an Dritte» umgestellt wurde: die alte Menge aus «Erzeugung» oder «Verbrauch» unter
   *Einstellungen → Daten → Monatsdaten* ins Feld «Abgabe» eintragen. Danach Schritt 2.
5. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden.

## Was ohne Handlung gilt
Der Wert bleibt gespeichert, zählt aber nirgends mit. eedc löscht und verschiebt nichts von allein.
