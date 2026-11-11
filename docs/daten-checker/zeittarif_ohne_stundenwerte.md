# Zeittarif ohne Stundenwerte

## Was eedc sieht
Ein Tarif hat Zeitfenster (etwa Hoch- und Niedertarif), aber es gibt keine gemessenen Stundenwerte des Netzbezugs. Die
Fenster gewichtet eedc über diese Stundenwerte — die gibt es nur, wo der Netzbezug über einen zugeordneten Sensor läuft.
Ohne sie rechnet eedc mit dem Arbeitspreis des Tarifs, also dem Hochtarif: deine Stromkosten stehen zu hoch, Ersparnis
und Amortisation zu niedrig.

## Lösungsweg
1. Am Befund **«Sensor zuordnen»** klicken — die Datenquellen-Zuordnung öffnet sich am Feld für den Netzbezug. Den
   Sensor deines Netzbezugszählers zuordnen.
2. Ohne Sensor: Steht der Tarif auf der Vertragsart «Dynamischer Tarif», zeigt der Monatsabschluss das Feld
   «Ø Strompreis (dynamisch)» — dort den Durchschnittspreis aus deiner Abrechnung eintragen; er gilt vor dem Tarif.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald Stundenwerte vorliegen.

## Was ohne Handlung gilt
Der Netzbezug wird zum Arbeitspreis des Tarifs bewertet; die günstigeren Zeitfenster bleiben unberücksichtigt.
