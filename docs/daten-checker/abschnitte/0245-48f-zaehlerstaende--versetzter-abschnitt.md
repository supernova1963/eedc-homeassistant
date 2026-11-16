<!-- anker: 48f-zaehlerstaende--versetzter-abschnitt -->
### 4.8f Zählerstände – versetzter Abschnitt <a name="48f-zaehlerstaende--versetzter-abschnitt"></a>

eedc merkt sich je Stunde den Stand jedes zugeordneten Zählers und bildet einen Tageswert aus zwei solchen Ständen — dem
am Tagesbeginn und dem am Tagesende. Gespeichert wird immer der Stand des Sensors, der **in dem Moment** zugeordnet ist.
Waren eine Zeit lang die Stände eines anderen Sensors in der Reihe (etwa nach einem Wechsel der Zuordnung), liegt ein
Abschnitt um einen festen Betrag versetzt: am Anfang springt der Stand nach oben, am Ende fällt er um etwa denselben
Betrag zurück. An diesen Rändern stimmt der Tageswert nicht — am Sprung ist er zu hoch, am Rückgang fehlt er
(„Zähler zurückgesprungen“). Geprüft wird die ganze gespeicherte Reihe jedes Zählers, dessen Stände aus Home Assistant
kommen.

**Gemeldet wird nur, was sich auswirkt.** Geprüft werden die Felder, deren Tageswert die Tagesansicht aus diesen
gespeicherten Ständen bildet: PV- und Netz-Ladung von Wallbox und E-Auto, die Netzladung des Speichers, die Zähler der
Wärmepumpe und der Netzbezug zum eigenen Tarif. Die übrigen Felder (etwa die Gesamt-Ladung der Wallbox oder die Zähler von
PV, Netz und Speicher) zeigt eedc aus der gespeicherten Tageszeile oder der Statistik von Home Assistant — dort wirkt ein
solcher Abschnitt nicht. Rechnet eedc die Rand-Tage eines Felds ohnehin aus der Statistik von Home Assistant (an einem Tag,
an dem alle Zähler seiner Gruppe dort lückenlos vorliegen), schweigt die Prüfung ebenfalls.

**Was kein Befund ist:** ein Zähler, der auf null oder fast null zurückgesetzt wird (das meldet
[§4.8a](#48a-zaehlerstaende--ruecksprung) für MQTT); ein einzelner Rückgang ohne vorangehenden Sprung ähnlicher Größe;
ein großer Zuwachs ohne späteren Rückgang — ein langer Ladevorgang, eine Datenlücke von Tagen oder ein Sensorwechsel,
nach dem der neue Sensor einfach weiterläuft.

**Zwei Lagen.** Stimmen die Stände vor und nach dem Abschnitt mit dem überein, was Home Assistant für den heute
zugeordneten Sensor führt, holt «Tage neu aufbauen» die Stände des Abschnitts neu und baut die Tage neu auf — höchstens
31 Tage je Lauf; ein längerer Abschnitt braucht mehrere Klicks. Sonst — ohne Home Assistant, oder wenn auch die Stände
außerhalb nicht zum heutigen Sensor passen — nennt der Befund nur die betroffenen Tage: neu geholt, entstünde der
Versatz an anderer Stelle.

---
