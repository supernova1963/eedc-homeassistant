# Tage mit vertauschtem Batterie-Vorzeichen

## Was eedc sieht
An diesen gespeicherten Tagen stehen Laden und Entladen des Speichers vertauscht — sie wurden mit einer älteren
eedc-Version berechnet, die das Speicher-Netto in umgekehrter Richtung schrieb. Erkannt wird das am Vergleich mit einem
frischen Abruf aus Home Assistant: beide zeigen in entgegengesetzte Richtungen. Betroffen sind Energieprofil und
Tages-Historie, nicht die Live-Ansicht. Die Zeile nennt Zahl und Zeitraum der Tage.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut das jüngste Fenster
   von höchstens 31 Tagen neu auf — jeden Tag darin, auch die ohne Befund.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal
   nutzen, oder einen einzelnen Tag in der Zeile «… Tage mit vertauschtem Batterie-Vorzeichen» anklicken.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

## Was ohne Handlung gilt
Die Tage behalten die vertauschte Richtung: Energieprofil und Tagesansicht zeigen dort Laden als Entladen und umgekehrt.
Die Live-Ansicht ist davon nicht betroffen.
