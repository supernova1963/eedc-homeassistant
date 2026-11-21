<!-- anker: 48i-zaehlerstaende--zeit-verworfen -->
### 4.8i Zählerstände – Zeit verworfen <a name="48i-zaehlerstaende--zeit-verworfen"></a>

Hat eine Korrektur («Grund nachtragen» mit der Antwort «Bisherige Werte verwerfen» oder die Korrektur über einen versetzten
Abschnitt) die Zählerstände einer Zeit verworfen und füllt nichts sie wieder auf — ohne
Verbindung zu Home Assistant, bei einer MQTT-Quelle, oder weil Home Assistant für diese Zeit keine Geschichte des richtigen
Sensors führt —, bleibt diese Zeit endgültig leer. Diese Kategorie nennt je solcher Zeit eine Auskunft: Feld, Beginn und Ende,
und was dafür gilt — dieselbe Angabe, die die Vorschau beim Eintragen gemacht hat.

**Zwei Lagen.** Gilt davor, in dieser Zeit und danach dieselbe Quelle und ist dazwischen kein Zählertausch eingetragen, rechnet
eedc über die Zeit wie über jede Zählerlücke: die Menge der ganzen Zeit steht am Tag des ersten Zählerstands danach. Sonst
bildet eedc über die Zeit keine Differenz: die Tage darin zeigen für dieses Feld keinen Wert, die Tage an ihrem Rand nur ihren
Teil, und die Menge fehlt in Tag, Monat und Jahr. Dazu nennt die Auskunft die betroffenen Monate, für die ein Monatswert
gespeichert ist — er bleibt, wie er ist.

Eine solche Zeit nennt die Kategorie «Stunden ohne Stundenwerte» ([§4.7](#47-energieprofil--plausibilitaet)) nicht noch
einmal. Die Zeile verschwindet erst, wenn eine spätere Korrektur die ganze Zeit aus Home Assistant füllt.

---
