### Energy-Felder Referenz (Investitions-Topics)

> ⚠ **Unter `energy/` gehoert der ZAEHLERSTAND, nicht der Monatsverbrauch.** Also der
> fortlaufende Stand, den dein Zaehler oder Wechselrichter anzeigt — eedc bildet die
> Differenzen daraus selbst (Tag, Monat, Jahr).
>
> ⛔ **Ein taeglich oder monatlich zurueckgesetzter Zaehler ist dafuer NICHT geeignet** — also
> ein Feld, das „heute" oder „diesen Monat" meint und dann wieder bei null anfaengt. eedc
> erkennt den Ruecksprung und liefert fuer diesen Zeitraum **keinen Wert**, statt zwei Staende
> voneinander abzuziehen, die zu verschiedenen Zaehlerlaeufen gehoeren.
>
> **Warum nicht einfach hochrechnen?** Technisch ginge es: Die Staende sind stuendlich
> mitgeschrieben, eine Summe daraus traefe auf rund 3 % genau. eedc tut es trotzdem nicht.
> Was zwischen dem letzten Stand und dem Ruecksprung verbraucht wird, taucht in keinem Stand
> mehr auf — der Fehlbetrag geht **immer** in dieselbe Richtung, und im Monatsabschluss wuerde
> aus so einer Zahl per Knopfdruck ein gespeicherter Wert, der aussieht wie eine Messung.
> Genau davor warnt der Daten-Checker schon beim Anlegen: *Zuruecksetzen „nie" (ohne Zyklus)*.
>
> ⭐ **Was du stattdessen tust:** Publiziere den **fortlaufenden** Stand. Bei einem
> `utility_meter` in Home Assistant heisst das Zuruecksetzen auf *„nie"*; kommt der Wert aus
> einer eigenen App, sende den Lebenszaehler statt des Tageswerts. eedc bildet Tag, Monat und
> Jahr daraus selbst — und exakt.
>
> ⛔ **Bis eedc 4.0.32 stimmte dieser Absatz nicht.** Hier stand *„Ein taeglich oder monatlich
> zurueckgesetzter Zaehler funktioniert ebenfalls; eedc erkennt den Ruecksprung"*. Im
> **Tagesfenster** stimmte das, im **Monatsfenster** nur dann, wenn der Ruecksprung zufaellig an
> den Raendern ablesbar war. Ein „…heute"-Zaehler ergab im laufenden Monat einen Wert, der
> aussah wie eine Messung und den Verbrauch **eines** Tages nannte (gemessen: 5,6 statt
> 140 kWh) — *Cockpit → Monat* zeigte ihn an.
>
> **Bis eedc 4.0.29 stand hier „Monatswerte", und das war missverstaendlich.** Wer korrekt
> seinen Zaehlerstand schickte, bekam ihn im Monatsabschluss als Monatsmenge vorgehalten
> („weicht ab": 6675,3 gegen 552,75 kWh) und in *Cockpit → Monat* sogar angezeigt. Seit
> 4.0.30 rechnet eedc die Differenz ueber den Monat. **Du musst nichts umstellen** — der
> Zaehlerstand war und ist das Richtige.
>
> ⭐ **`km_gefahren` und `ladevorgaenge` folgen derselben Regel — seit sie eine eigene
> Zaehlerreihe haben.** Sie tragen keine kWh, und deshalb schrieb eedc fuer sie lange
> gar keine Reihe mit: Ein HA-Anwender bekam seine Monatswerte trotzdem, weil die
> HA-Statistik die Differenz direkt rechnet, ein Standalone-Anwender bekam **nichts** und
> trug von Hand ein — obwohl derselbe Feld-Hinweis ihm den „kumulativen km-Zaehler
> (Auto-Integration/OBD)" als Quelle anbot (Discussion #396). Jetzt schreibt eedc auch
> diese beiden Staende mit. **Schick den Tachostand, nicht die gefahrenen Kilometer.**
>
> **Seit P-433-2b K4** zeigt das E-Auto den Stand von `km_gefahren` live als **Kilometerstand** (aus dem Energie-Cache des
> Inbound, `inv/<id>/km_gefahren`, bis 60 s alt) und die Karte „Heute" den Zuwachs der abgeschlossenen Stunden als
> **„Gefahren heute"** (dazu `verbrauch_kwh` als **„Fahrverbrauch heute"**). Der Kanal-Katalog fuehrt `km_gefahren` und
> `ladevorgaenge` am Geraet als Spiegel/Mitschrift: mit HA-Entitaet (Datenquellen-Wahl HA) spiegelt eedc den Stand aus der
> Langzeitstatistik, sonst schreibt es den MQTT-Stand mit.

Die Felder unter `energy/inv/{id}_{name}/` entsprechen den Monatsdaten-Feldern der jeweiligen Investition. EEDC erkennt alle Felder automatisch — es muss kein Mapping konfiguriert werden.

Welche Felder das je Gerätetyp sind, steht in den Tabellen unter [Topics je Gerätetyp](#topics-je-gerätetyp) — vollständig, auch die Felder ohne Topic.

> ⭐ **Ein selbst errechneter PV-Ladezaehler (Discussion #414).** Liefert die Wallbox oder evcc
> keinen eigenen PV-Zaehlerstand, sondern nur einen Solar-Anteil in Prozent, laesst sich
> `ladung_pv_kwh` als Produkt *Gesamtzaehler × kumulierter Solaranteil* bilden — **aber nur,
> wenn Prozent und Zaehler dieselbe Energiebasis haben** (derselbe Zaehler seit demselben Tag).
> eedc bildet aus diesem Stand die Monatsdifferenz wie aus jedem anderen. Die Monatswerte zeigen
> dann den **Anteil des jeweiligen Monats** (Sommer nahe 100 %, Winter nahe 0 %), nicht den
> kumulierten Durchschnitt, den evcc anzeigt — die Summe ueber die Monate trifft ihn wieder.

Was nicht per MQTT lieferbar ist (Wetterdaten, Preise, Sonderkosten, Notizen — im Monatsabschluss von Hand eingetragen oder berechnet), nennt die Basis-Tabelle unter [Topics je Gerätetyp](#topics-je-gerätetyp) mit „kein MQTT-Topic".

