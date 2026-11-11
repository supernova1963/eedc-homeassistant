# Tage vor dem Umbau gerechnet

## Was eedc sieht
eedc rechnet eine fehlende Stunde aus Home Assistant heute wie das Energie-Dashboard: ihre Energie steht in der Stunde
danach, und die Tagesansicht im Cockpit zeigt Eigenverbrauch, Autarkie und Gesamtverbrauch auch an solchen Tagen. Die
genannten Tage wurden vor dieser Umstellung gerechnet und zeigen dort noch „—“. Gezählt werden nur Tage mit eigenen
Stundenwerten; Tage, deren Mengen aus der Langzeitstatistik von Home Assistant kommen, brauchen das nicht.

## Lösungsweg
1. Am Befund **«Tage neu aufbauen»** klicken, die Vorschau lesen und **«Anwenden»** — eedc rechnet die jüngsten Tage neu,
   höchstens 31 je Lauf.
2. Bleiben ältere Tage übrig, erscheint die Zeile danach mit dem nächsten Zeitraum; den Knopf dann erneut nutzen.
3. Steht am Befund statt dessen **«Sensor zuordnen»**: der Anlage fehlt eine Leistungs- oder Zähler-Zuordnung. Der Knopf
   öffnet die Datenquellen-Zuordnung; nach der Zuordnung steht am Befund wieder «Tage neu aufbauen».
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, oder sie nennt den nächsten
   Zeitraum.

## Was ohne Handlung gilt
Die genannten Tage zeigen in der Tagesansicht im Cockpit bei Eigenverbrauch, Autarkie und Gesamtverbrauch weiter „—“.
Eine automatische Umrechnung beim Start gibt es bewusst nicht.
