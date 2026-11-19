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

**Ein Handgriff: «Grund nachtragen».** Er öffnet in den Datenquellen denselben Dialog wie beim Wechsel einer Quelle — nur
mit „Bisher war der falsche Sensor zugeordnet“ und mit der festen Zeit des Abschnitts. eedc verwirft die Zählerstände des
Abschnitts. Stimmen die Stände davor und danach mit dem überein, was Home Assistant für die Quelle davor und danach führt,
liest eedc den Abschnitt aus Home Assistant neu — auf derselben Höhe — und speichert ihn; die Tageswerte stimmen dann an jedem
Tag (bis das Neulesen gelungen ist, zeigen die Rand-Tage nur ihren Teil; eedc holt es jede Stunde und nach jedem Start nach).
Ohne Home Assistant, oder führt Home Assistant die Quelle auf einer anderen Höhe oder für diese Zeit nichts, bleibt der
Abschnitt leer, und eedc rechnet über ihn wie über jede Zählerlücke — davor und danach gilt dieselbe Quelle: die Menge des
Abschnitts steht an dem Tag, an dem er endet, die Tage davor zeigen für diese Zeit keinen Wert. Ist zwischen den Ständen
davor und danach ein Zählertausch eingetragen, bildet eedc über den Abschnitt keine Differenz: die Tage darin zeigen keinen
Wert, die Tage an seinem Rand nur ihren Teil — der Befund sagt es. Das geht auch, wenn der
Abschnitt heute endet. Gelten vor und nach dem Abschnitt verschiedene Quellen,
oder ist Home Assistant eingerichtet, aber gerade nicht erreichbar, trägt der Befund statt «Grund nachtragen» den Knopf
«Was gilt». Der Befund nennt nur die Tage, deren Wert eedc wirklich aus diesen Ständen bildet — liegt ein
Rückgang im Fenster eines Tages, fehlt dessen Wert, auch wenn im selben Fenster ein Sprung liegt.

---
