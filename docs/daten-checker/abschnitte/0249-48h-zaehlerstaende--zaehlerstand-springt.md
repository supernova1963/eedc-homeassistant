<!-- anker: 48h-zaehlerstaende--zaehlerstand-springt -->
### 4.8h Zählerstände – Zählerstand springt <a name="48h-zaehlerstaende--zaehlerstand-springt"></a>

Wird das Gerät hinter einem Zähler getauscht und Home Assistant führt **denselben Sensor** weiter, springt sein Stand: Zeigt
der neue Zähler mehr als der alte, zählt Home Assistant den Unterschied als Verbrauch bzw. Erzeugung der Stunde des Tauschs;
beginnt der neue Zähler nicht bei 0, hält Home Assistant das für einen neuen Zählerlauf und zählt seinen ganzen Stand. eedc
übernimmt die Statistik so, wie das Energie-Dashboard von Home Assistant sie zeigt, und berichtigt nichts — der Sprung steht in
Tag, Monat und Jahr. Diese Kategorie nennt bis zu fünf solche Stunden mit Feld, Sensor, Stunde und Menge; weitere zählt die letzte Zeile. Geprüft wird die ganze
übernommene Statistik.

**Woran eedc einen Sprung erkennt.** Die Menge der Stunde wird mit dem größten Tagesverbrauch des Zählers im Jahr davor
verglichen und durch die Tage seit seinem letzten Zuwachs geteilt (mindestens 1). Ein Sprung nach oben ist ein Befund ab dem
Zehnfachen — wenn der Zähler schon ein Jahr mit gewöhnlichem Betrieb kennt (ein Jahr Statistik, an mindestens 14 Tagen etwas
gezählt, an einem davon mindestens 1 kWh) oder die Menge mehr ist, als eine Anlage in einer Stunde leisten kann (100 kWh oder
1,5 × die Anlagenleistung in kWp, was größer ist; nur bei kWh). Ein Neubeginn, der nicht bei 0 liegt, ist ein Befund ab dem
Dreifachen. Verglichen werden nur Stunden desselben Sensors.

**Was kein Befund ist.** Eine Stunde, die nach einer Lücke die Menge mehrerer Stunden nachträgt; ein großer Verbrauch nach
langer Ruhe (Wallbox nach Wochen, Wärmepumpe im ersten kalten Monat, PV nach Schnee); die erste gewöhnliche Stunde eines
Zählers, der bisher nur Standby kannte; ein Zähler, der in den Tagen davor an weniger als 14 Tagen etwas gezählt hat
(Neubeginn); ein Zähler, der bei 0 neu beginnt; ein Sensor, der kurz 0 gemeldet hat und
zurückkehrt ([§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant)); der Wechsel zwischen zwei Sensoren
([Handbuch Einstellungen §7.7a](HANDBUCH_EINSTELLUNGEN.md#77a-die-frage-beim-wechsel-zwei-antworten)); die erste Stunde einer
neuen Statistik, auch mit einem großen Wert (eine importierte Statistik, ein Zähler, der beim ersten Wert springt — eedc zeigt
sie wie Home Assistant, [Handbuch Einstellungen §7.7c](HANDBUCH_EINSTELLUNGEN.md#77c-was-passiert-wenn)). Ein gefallener Zählerstand steht in
[§4.8c](#48c-zaehlerstaende--rueckgang-in-home-assistant) bzw. bei Verbrauchszählern in [§4.23](#423-verbrauchszaehler-zaehlerstaende).

**Zählerstände** (Gas, Wasser, Öl, Kilometerstand): eedc rechnet dort mit dem Stand, den der Sensor anzeigt, nicht mit der
Summe der Statistik — „Summe anpassen“ in Home Assistant ändert dort nichts. Der Befund ist dann eine Auskunft: er nennt den
Weg, den getauschten Zähler als eigenes Gerät zu führen, und wie ein späterer Tausch ohne Sprung bleibt.

---
