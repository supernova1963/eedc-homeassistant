# Verdacht auf PV-Doppelerfassung

## Was eedc sieht
An mindestens drei der letzten 30 Tage liefert die Anlage mehr, als physikalisch plausibel ist: eine Performance Ratio
über 1,05 oder ein Tagesertrag über 7 kWh je kWp. Der häufigste Grund ist dieselbe Erzeugung zweimal gezählt — etwa ein
String-Sensor und der Summenzähler der Anlage, beide zugeordnet, oder ein Wechselrichter-Zähler, der ein Balkonkraftwerk
schon mitmisst, das zusätzlich zugeordnet ist. Die Performance Ratio steigt aber auch, wenn der Vergleichsmaßstab zu
klein ist: die eingetragene kWp oder die Einstrahlung. Tage mit bekanntem Zählersprung sind schon herausgerechnet.

## Lösungsweg
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich bei der PV-Erzeugung. Prüfen, ob
   dieselbe Erzeugung an zwei Stellen zugeordnet ist, auch beim Balkonkraftwerk. Regel: entweder je Erzeuger ein eigener
   Zähler oder ein Summenzähler der Anlage — nicht beides.
2. Findet sich dort nichts: unter *Einstellungen → Komponenten → PV-Module* je Modul «Leistung (kWp)», «Ausrichtung»
   und «Neigung (Grad)» prüfen, unter *Einstellungen → Stammdaten → Anlage* den Standort. Ohne passende Ausrichtung und
   Neigung rechnet eedc mit einer Einstrahlung, die nicht zu deinem Dach passt.
3. Liegen die auffälligen Tage alle in den letzten fünf Tagen und sind es trübe Tage: abwarten. Die Einstrahlung dieser
   Tage ist noch vorläufig und an bewölkten Tagen zu klein; eedc holt den endgültigen Wert selbst nach.
4. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald weniger als drei Tage
   auffallen.

## Was ohne Handlung gilt
eedc kürzt nichts: welche Zuordnung richtig ist, entscheidest du. Ist die Erzeugung tatsächlich doppelt gezählt, fallen
Eigenverbrauch, Autarkie, Ersparnis und CO₂-Bilanz zu gut aus.
