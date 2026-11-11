# Tage kennen nur den Ladestand eines Speichers

## Was eedc sieht
Die Anlage hat mehrere Speicher mit eigenem Ladestand-Sensor. An diesen Tagen hat eedc nur den Ladestand eines Geräts
gespeichert — welches, entschied die Reihenfolge der Zuordnung — und ihn behandelt, als gälte er für die ganze Anlage.
Die Tage stammen aus der Zeit vor der Korrektur dieser Rechnung. Betroffen sind Vollzyklen, Ladestand-Hübe und die
Speicher-Auswertungen; Erzeugung, Verbrauch und Netzbezug sind es nicht.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»**. Ein Lauf baut höchstens 31 Tage
   neu auf, die jüngsten zuerst.
2. Nennen die Details ältere Tage außerhalb dieses Fensters: nach dem Lauf erneut prüfen und den Knopf noch einmal nutzen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden oder nennt nur noch ältere Tage.

## Was ohne Handlung gilt
Für diese Tage rechnen Vollzyklen, Ladestand-Hübe und Speicher-Auswertungen mit dem Ladestand eines einzelnen Speichers,
als wäre es der der ganzen Anlage.
