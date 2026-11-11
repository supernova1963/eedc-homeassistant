# Netzladung übersteigt die Gesamtladung

## Was eedc sieht
Über die ganze Geschichte des Speichers steht mehr Netzladung als Ladung. «Ladung» ist die gesamte Ladung (PV und Netz),
«Netzladung» ein Teil davon. In einem einzelnen Monat darf die Netzladung vorn liegen — ein Ladevorgang über die
Monatsgrenze landet beim einen Zähler noch im alten, beim anderen schon im neuen Monat —, in der Summe nicht. Mögliche
Ursachen: der Netz-Zähler ist bei «Ladung» zugeordnet, oder «Ladung» wurde als reine PV-Ladung gepflegt.

## Lösungsweg
1. Am Befund **«Jahresbilanz prüfen»** klicken — die Speicher-Seite öffnet sich mit der Jahresbilanz dieses Speichers;
   dort siehst du, in welchen Jahren Ladung und Netzladung auseinanderlaufen.
2. In der [Datenquellen-Zuordnung](eedc:/einstellungen/datenquellen) bei diesem Speicher prüfen, dass bei «Ladung» der
   Zähler der gesamten Ladung liegt und bei «Netzladung» nur der Netz-Anteil.
3. Von Hand gepflegte Monate unter *Einstellungen → Daten → Monatsdaten* berichtigen: «Ladung» enthält die gesamte
   Ladung, die Netzladung ist ein Teil davon.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald die Summe der Netzladung
   nicht mehr über der Summe der Ladung liegt.

## Was ohne Handlung gilt
Die Speicher-Auswertungen rechnen mit den widersprüchlichen Mengen; der PV-Anteil der Ladung stimmt nicht.
