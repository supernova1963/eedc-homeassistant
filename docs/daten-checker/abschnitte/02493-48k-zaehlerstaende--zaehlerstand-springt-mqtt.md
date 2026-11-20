<!-- anker: 48k-zaehlerstaende--zaehlerstand-springt-mqtt -->
### 4.8k Zählerstände – Zählerstand springt (MQTT) <a name="48k-zaehlerstaende--zaehlerstand-springt-mqtt"></a>

Bei MQTT ist der Zählerstand, den der Publisher sendet, die Quelle; eedc bildet daraus je Stunde die Menge nach der Regel von
Home Assistant und berichtigt nichts. Wechselt der Stand die Höhe — der Zähler oder das Gerät wurde getauscht, oder ein anderes
Gerät sendet auf demselben Topic —, zählt diese Regel den Unterschied als Menge der Stunde: einen Sprung nach oben ganz, einen
Neubeginn, der nicht bei 0 liegt, mit dem ganzen neuen Stand, einen Fall um weniger als ein Zehntel als negative Menge. Diese
Kategorie nennt jede solche Stunde mit Feld, Zeit und Menge; der Knopf «Zähler getauscht» öffnet in den Datenquellen den Dialog
mit der Zeit des Sprungs. Geprüft werden alle Stunden, die eedc für das Feld aus MQTT führt.

**Woran eedc einen Sprung erkennt.** Wie in [§4.8h](#48h-zaehlerstaende--zaehlerstand-springt): die Menge der Stunde wird mit
dem größten Tagesverbrauch des Zählers im Jahr davor verglichen und durch die Tage seit seinem letzten Zuwachs geteilt; ein
Sprung nach oben ist ein Befund ab dem Zehnfachen, ein Neubeginn ab dem Dreifachen. Ein Rückgang (die Stunde zählt weniger als
−0,01 kWh) ist immer ein Befund.

**Was kein Befund ist.** Ein Zähler, der täglich oder monatlich bei 0 neu beginnt
([§4.8a](#48a-zaehlerstaende--ruecksprung)); eine Stunde, die nach einer Lücke die Menge mehrerer Stunden nachträgt;
ein Zähler mit weniger als 14 Tagen mit Zuwachs (Sprung und Neubeginn); eine Stunde, an der ein Zählertausch schon eingetragen
ist; Sprung und Rückgang eines versetzten Abschnitts ([§4.8f](#48f-zaehlerstaende--versetzter-abschnitt)).

---
