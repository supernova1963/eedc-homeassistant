# Einspeisung wird mit 0 ct/kWh gerechnet

## Was eedc sieht
Mindestens ein Tarif der Verwendung «Standard (allgemein)», bei dem «Einspeisevergütung wechselt monatlich» nicht
eingeschaltet ist, trägt 0 ct/kWh Einspeisevergütung, und in seinem Zeitraum ist Einspeisung erfasst (auf ein Jahr
hochgerechnet ab 50 kWh). eedc rechnet den Einspeise-Erlös so, wie es im Tarif steht — in Cockpit, Amortisation und
Jahresbericht bleibt er 0 €. Ein neuer Tarif startet mit 0; eedc rät den Satz bewusst nicht.

## Lösungsweg
1. Ist deine Einspeisung wirklich unvergütet (Nulleinspeisung, Volleinspeisung ohne Vergütung, ausgelaufene
   EEG-Förderung): nichts zu tun — 0 ist dann richtig.
2. Bekommst du eine Vergütung: am Befund **«Tarif bearbeiten»** klicken — der Tarif öffnet sich am Feld
   «Einspeisevergütung (ct/kWh)». Den Satz aus deinem Vergütungsbescheid eintragen; bei gestaffelter Vergütung den nach
   kWp gewichteten Mischsatz, denn eedc rechnet mit einem Satz. **«Speichern»**.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — nach Schritt 2 ist die Zeile verschwunden; nach Schritt 1
   bleibt sie als Auskunft stehen.

## Was ohne Handlung gilt
Der Einspeise-Erlös dieser Zeiträume bleibt 0 €; alles andere rechnet unverändert.
