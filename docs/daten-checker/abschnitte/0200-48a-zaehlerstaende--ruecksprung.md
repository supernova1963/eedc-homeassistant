<!-- anker: 48a-zaehlerstaende--ruecksprung -->
### 4.8a Zählerstände – Rücksprung <a name="48a-zaehlerstaende--ruecksprung"></a>

> **Variantenhinweis:** Diese Kategorie greift, sobald Zählerstände über MQTT ankommen. Über Home Assistant ist sie
> gegenstandslos — dort liefert die Langzeitstatistik einen bereits bereinigten Stand, ein Verbrauchszähler mit
> Tageszyklus ist also unschädlich.

**Was wird geprüft:** Steigt jeder per MQTT gelieferte Zählerstand fortlaufend, oder fällt er zwischendurch auf einen
niedrigeren Wert zurück? Geprüft werden die letzten **30 Tage** der mitgeschriebenen Stände.

**Warum das zählt.** eedc bildet aus zwei Ständen eine Menge — Anfang und Ende des Zeitraums, die Differenz dazwischen.
Springt der Zähler dazwischen auf null zurück, gehören die beiden Stände zu **verschiedenen Zählerläufen**, und ihre
Differenz ist keine Menge. Typisch ist das bei einem Feld, das „heute“ oder „diesen Monat“ meint statt des Gesamtstands.

**Was eedc dann tut:** Es liefert für dieses Feld **keinen Wert** — im Monatsabschluss steht kein Vorschlag, in der
Monatsansicht im Cockpit bleibt der gespeicherte Wert stehen. Das ist Absicht: eine Zahl aus zwei unzusammenhängenden
Zählerläufen sähe aus wie eine Messung und wäre keine.

**Mit eigener Summe.** Führt eedc für das Feld eine eigene Summe aus den MQTT-Ständen, rechnet es den Zähler wie Home
Assistant: ein Stand unter 90 % des vorigen gilt als Neubeginn, die Summe läuft weiter — Tag, Monat und Jahr stimmen dann
auch für einen Zähler, der jeden Tag auf null geht. Nicht verlässlich bleiben „heute“ und „gestern“ im Live-Bereich (sie
vergleichen mit dem Stand um Mitternacht) und Geräte-Tageswerte aus der Zeit davor; einen Vorschlag im Monatsabschluss
gibt es für so ein Feld weiterhin nicht. Die Meldung nennt dann, welche Felder so rechnen. Die Empfehlung bleibt dieselbe:
den fortlaufenden Stand schicken.

> ⚠ **eedc rechnet den fehlenden Teil nicht hoch**, obwohl es die Stundenstände hätte. Was zwischen dem letzten
> mitgeschriebenen Stand und dem Rücksprung verbraucht wird, steht in keinem Stand mehr — eine hochgerechnete Zahl wäre
> systematisch zu niedrig und im Monatsabschluss per Knopfdruck ein gespeicherter Wert. Die Reparatur liegt beim Absender;
> sobald die Reihe wieder fortlaufend ist, verschwindet der Befund von selbst.

---
