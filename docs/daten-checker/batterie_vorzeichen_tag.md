# Ein Tag mit vertauschtem Batterie-Vorzeichen

## Was eedc sieht
An diesem gespeicherten Tag stehen Laden und Entladen des Speichers vertauscht — er wurde mit einer älteren eedc-Version
berechnet. Gespeicherter Wert und ein frischer Abruf aus Home Assistant zeigen in entgegengesetzte Richtungen. Mehrere
solche Tage stehen als eine Zeile «n Tage mit vertauschtem Batterie-Vorzeichen» mit einem Glied je Tag.

## Lösungsweg
1. Am Befund einen Tag (ein Glied) bzw. **«Tag neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — genau
   dieser Tag wird neu aufgebaut, mit dem Speicher-Netto in der richtigen Richtung.
2. Für viele Tage auf einmal ist der Befund «… Tag(e) mit vertauschtem Batterie-Vorzeichen» mit seinem Knopf
   «Tage neu aufbauen» der kürzere Weg.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — der Tag ist aus der Zeile verschwunden.

## Was ohne Handlung gilt
Der Tag behält die vertauschte Richtung; Energieprofil und Tagesansicht zeigen dort Laden als Entladen und umgekehrt.
