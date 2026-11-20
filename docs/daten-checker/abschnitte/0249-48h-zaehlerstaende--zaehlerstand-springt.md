<!-- anker: 48h-zaehlerstaende--zaehlerstand-springt -->
### 4.8h Zählerstände – Zählerstand springt <a name="48h-zaehlerstaende--zaehlerstand-springt"></a>

Wird das Gerät hinter einem Zähler getauscht und Home Assistant führt **denselben Sensor** weiter, springt sein Stand: Zeigt
der neue Zähler mehr als der alte, zählt Home Assistant den Unterschied als Verbrauch bzw. Erzeugung der Stunde des Tauschs;
beginnt der neue Zähler nicht bei 0, hält Home Assistant das für einen neuen Zählerlauf und zählt seinen ganzen Stand. eedc
übernimmt die Statistik so, wie das Energie-Dashboard von Home Assistant sie zeigt, und berichtigt nichts — der Sprung steht in
Tag, Monat und Jahr. Diese Kategorie nennt jede solche Stunde mit Feld, Sensor, Stunde und Menge. Geprüft wird die ganze
übernommene Statistik.

**Woran eedc einen Sprung erkennt.** Die Menge der Stunde wird mit dem größten Tagesverbrauch des Zählers im Jahr davor
verglichen und durch die Tage seit seinem letzten Zuwachs geteilt (mindestens 1). Ein Sprung nach oben ist ein Befund ab dem
Zehnfachen, ein Neubeginn, der nicht bei 0 liegt, ab dem Dreifachen. Verglichen werden nur Stunden desselben Sensors.

**Was kein Befund ist.** Eine Stunde, die nach einer Lücke die Menge mehrerer Stunden nachträgt; ein großer Verbrauch nach
langer Ruhe (Wallbox nach Wochen, Wärmepumpe im ersten kalten Monat, PV nach Schnee); ein Zähler, der in den Tagen davor an
weniger als 14 Tagen etwas gezählt hat; ein Zähler, der bei 0 neu beginnt; ein Sensor, der kurz 0 gemeldet hat und
zurückkehrt ([§4.8b](#48b-zaehlerstaende--sprung-in-home-assistant)); der Wechsel zwischen zwei Sensoren
([Handbuch Einstellungen §7.7](HANDBUCH_EINSTELLUNGEN.md)). Ein gefallener Zählerstand steht in
[§4.8c](#48c-zaehlerstaende--rueckgang-in-home-assistant) bzw. bei Verbrauchszählern in [§4.23](#423-verbrauchszaehler-zaehlerstaende).

**Zählerstände** (Gas, Wasser, Öl, Kilometerstand): eedc rechnet dort mit dem Stand, den der Sensor anzeigt, nicht mit der
Summe der Statistik — „Summe anpassen“ in Home Assistant ändert dort nichts. Der Befund ist dann eine Auskunft: er nennt den
Weg, den getauschten Zähler als eigenes Gerät zu führen, und wie ein späterer Tausch ohne Sprung bleibt.

---
