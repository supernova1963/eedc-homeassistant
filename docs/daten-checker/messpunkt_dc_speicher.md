# DC-Speicher: der AC-Zähler misst die Batterie mit

## Was eedc sieht
Bei einem DC-gekoppelten Speicher misst der Anlagenzähler (nach dem Wechselrichter) Ladung und Entladung der Batterie
mit — die Differenz zu den String-Zählern ist dann nicht nur Wandlungsverlust. Ist die Kopplung am Speicher nicht
eingetragen, nimmt eedc DC an, sobald der Speicher einem Wechselrichter zugeordnet ist; die Meldung sagt dann dazu, dass
die Kopplung fehlt.

## Lösungsweg
1. Am Befund **«Gerät bearbeiten»** klicken — das Formular des Speichers öffnet sich.
2. Im Feld «Kopplung» eintragen, wie dein Speicher angeschlossen ist: «AC-gekoppelt» oder «DC-gekoppelt». Speichern.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — mit «AC-gekoppelt» verschwindet die Zeile; mit «DC-gekoppelt»
   bleibt sie als Auskunft stehen.

## Was ohne Handlung gilt
eedc zeigt die Differenz als Verluste an, bewertet sie aber nicht: Ersparnis, Umsatzsteuer und CO₂ rechnen ohne Abzug.
