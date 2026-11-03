# MQTT-Inbound: Universelle Datenbruecke

MQTT-Inbound ermoeglicht es, Live-Leistungsdaten und Zaehlerstaende von **jedem Smarthome-System** an EEDC zu senden. Es wird nur ein MQTT-Broker benoetigt (z.B. Mosquitto).

## Unterstuetzte Systeme

- Home Assistant (Automation oder Node-RED Add-on)
- Node-RED (standalone oder als Add-on)
- ioBroker (JavaScript-Adapter)
- FHEM (MQTT2-Modul)
- openHAB (MQTT Binding)
- Jedes System mit MQTT-Publish-Faehigkeit

## Einrichtung

1. **MQTT-Broker installieren** (z.B. Mosquitto)
2. In EEDC unter *Einstellungen > Einrichtung > MQTT-Inbound*:
   - Broker-Adresse und Port eintragen
   - Optional: Benutzername/Passwort
   - "Speichern & Verbinden" klicken
3. Die generierten Topics im Smarthome-System befuellen

## Topic-Struktur

EEDC generiert die Topics automatisch aus den angelegten Anlagen und Investitionen. Das Format ist:

```
eedc/{anlage_id}_{name}/
├── live/                              # Momentanwerte (W, °C, %) und der Betriebsmodus
│   ├── einspeisung_w                  → 1100
│   ├── netzbezug_w                    → 0
│   └── inv/{inv_id}_{name}/
│       ├── leistung_w                 → 4200
│       ├── soc                        → 72       (nur Speicher/E-Auto)
│       ├── vorlauf_temperatur_c       → 34.5     (nur Waermepumpe; ebenso ruecklauf_/warmwasser_temperatur_c)
│       └── betriebsmodus              → 1        (nur Waermepumpe: Wort oder Code, siehe unten)
│
└── energy/                            # ZAEHLERSTAENDE (kWh, kumuliert)
    ├── einspeisung_kwh                → 6675.3
    ├── netzbezug_kwh                  → 6424.8
    └── inv/{inv_id}_{name}/
        └── {key}                      → Wert     (siehe Felder-Referenz)
```

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

| Investitionstyp | Key | Einheit | Beschreibung |
|---|---|---|---|
| **PV-Module** | `pv_erzeugung_kwh` | kWh | PV-Erzeugung |
| **Speicher** | `ladung_kwh` | kWh | Batterie-Ladung |
| **Speicher** | `entladung_kwh` | kWh | Batterie-Entladung |
| **Waermepumpe** | `stromverbrauch_kwh` | kWh | Stromverbrauch |
| **Waermepumpe** | `heizenergie_kwh` | kWh | Erzeugte Heizenergie |
| **Waermepumpe** | `warmwasser_kwh` | kWh | Warmwasser-Erzeugung |
| **E-Auto** | `km_gefahren` | km | **Tachostand** (Odometer) — eedc bildet die gefahrenen Kilometer daraus |
| **E-Auto** | `v2h_entladung_kwh` | kWh | Vehicle-to-Home Entladung |
| **Wallbox** | `ladung_kwh` | kWh | Ladung gesamt |
| **Wallbox** | `ladung_pv_kwh` | kWh | PV-Anteil der Ladung — **auch als Zaehlerstand**, eedc bildet die Monatsdifferenz daraus (s. Kasten unten) |
| **Wallbox** | `ladevorgaenge` | Anzahl | **Fortlaufender Zaehler** der Ladevorgaenge — eedc bildet die Anzahl im Monat daraus |
| **E-Auto** | `ladung_pv_kwh` / `ladung_netz_kwh` | kWh | Heimladung PV-/Netz-Anteil für dieses Auto. Neben einer Wallbox freiwillig: zählt für dieses Auto, die Wallbox trägt den Rest |
| **E-Auto** | `ladung_kwh` | kWh | Heimladung gesamt für dieses Auto (Zähler am Auto, der PV und Netz nicht trennt) — mit `ladung_pv_kwh`/`ladung_netz_kwh` leer lassen. Neben einer Wallbox freiwillig wie oben |
| **E-Auto** | `ladung_extern_kwh` / `ladung_extern_euro` | kWh / EUR | Externe Ladung (Menge und Kosten) |
| **Speicher** | `ladung_netz_kwh` | kWh | Netz-Anteil der Ladung (Arbitrage) |
| **BKW** | `pv_erzeugung_kwh` | kWh | BKW-Erzeugung |
| **BKW** | `eigenverbrauch_kwh` | kWh | Eigenverbrauch |
| **BKW** | `speicher_ladung_kwh` | kWh | BKW-Speicher Ladung |
| **BKW** | `speicher_entladung_kwh` | kWh | BKW-Speicher Entladung |
| **Sonstiges** | `erzeugung_kwh` | kWh | Erzeugung (Erzeuger/Speicher) |
| **Sonstiges** | `verbrauch_sonstig_kwh` | kWh | Verbrauch (Verbraucher/Speicher) |

> ⭐ **Ein selbst errechneter PV-Ladezaehler (Discussion #414).** Liefert die Wallbox oder evcc
> keinen eigenen PV-Zaehlerstand, sondern nur einen Solar-Anteil in Prozent, laesst sich
> `ladung_pv_kwh` als Produkt *Gesamtzaehler × kumulierter Solaranteil* bilden — **aber nur,
> wenn Prozent und Zaehler dieselbe Energiebasis haben** (derselbe Zaehler seit demselben Tag).
> eedc bildet aus diesem Stand die Monatsdifferenz wie aus jedem anderen. Die Monatswerte zeigen
> dann den **Anteil des jeweiligen Monats** (Sommer nahe 100 %, Winter nahe 0 %), nicht den
> kumulierten Durchschnitt, den evcc anzeigt — die Summe ueber die Monate trifft ihn wieder.

**Nicht per MQTT lieferbar** (werden im Monatsabschluss manuell eingegeben oder berechnet):
- Wetterdaten (`globalstrahlung`, `sonnenstunden`, `temperatur`)
- `sonderkosten_euro`, `notizen`

### Live-Mittelwerte: was eedc aus den Live-Topics mitschreibt

Jedes Live-Topic mit einer Zahl ist ein Momentanwert — senden bei jeder Aenderung genuegt (ein Wert gilt bis zur
naechsten Nachricht, wie in Home Assistant). Alle 5 Minuten haelt eedc daraus das **zeitgewichtete Mittel** des
Fensters fest (mit Minimum und Maximum) und bildet je abgeschlossener Stunde **Stundenmittel** — dasselbe, was Home
Assistant aus seinen 5-Minuten-Statistiken macht (seit Standalone-Gleichstand S2). Mitgeschrieben werden alle
Live-Felder in W, °C und %:

| Ebene | Topics (`live/…`) |
|---|---|
| Anlage | `einspeisung_w`, `netzbezug_w`, `netz_kombi_w`, `pv_gesamt_w`, `aussentemperatur_c` |
| PV-Module, Wechselrichter, Balkonkraftwerk, Wallbox, Sonstiges | `inv/…/leistung_w` |
| Speicher, E-Auto | `inv/…/leistung_w`, `inv/…/soc` |
| Waermepumpe | `inv/…/leistung_w`, `leistung_heizen_w`, `leistung_warmwasser_w`, `leistung_kuehlen_w`, `vorlauf_temperatur_c`, `ruecklauf_temperatur_c`, `warmwasser_temperatur_c`, `heizstab_leistung_w` |
| Klimaanlage mit Innengeraeten | zusaetzlich `soll_temperatur_c`, `ist_temperatur_c`; je Innengeraet `leistung_w-<n>`, `soll_temperatur_c-<n>`, `ist_temperatur_c-<n>` |
| Betriebsmodus | `inv/…/betriebsmodus` — als Anteil je Modus (siehe naechster Abschnitt) |

Daraus entstehen ohne Home Assistant u. a. das Temperatur-Diagramm, Ø Vorlauf und Ø Spreizung der Waermepumpe. Der
**Tagesverlauf** in *Cockpit → Live* zeigt ueber MQTT damit 5-Minuten-Mittel statt einzelner Momentanwerte, ab der
ersten Aufzeichnung — ohne Home Assistant auch ohne jede Zuordnung unter *Datenquellen* (reine Inbound-Anlage).

**Add-on mit MQTT-Geraeten (Mischform).** Laeuft eedc mit Home Assistant, liefern aber einzelne oder alle Geraete ihre
Leistung nur ueber diese Topics (kein HA-Sensor zugeordnet), zeichnet der Tagesverlauf auch sie aus den 5-Minuten-
Aufzeichnungen: ohne jede `live`-Zuordnung die ganze Kurve aus MQTT, sonst die Geraete ohne HA-Leistungssensor aus MQTT
neben den Geraeten aus HA — Netz, PV gesamt und Preis bleiben dann bei HA. Ein Geraet mit HA-Sensor bleibt bei HA. Die
Tagesaggregation liest dieselbe Kurve (Geraetewerte je Stunde). Voraussetzung: „Daten ueber MQTT empfangen (Import)" an.

- **Nicht rueckwirkend:** Die Stundenmittel beginnen mit der Zuordnung (dem ersten empfangenen Wert).
- **Broker-Ausfall:** Die Zeit ohne Verbindung bleibt eine Luecke; die Stunde ist das Mittel der uebrigen Minuten.
  Ein Absender, der verstummt, waehrend der Broker laeuft, behaelt seinen letzten Wert.
- **HA-Sensor geht vor:** Ist einem Feld ein HA-Sensor zugeordnet, gilt er — auch ohne Langzeitstatistik (der
  Daten-Checker nennt ihn dann); das MQTT-Topic wird fuer die Stundenmittel nicht gelesen.
- **Strompreis:** `strompreis_ct` zeigt eedc nur im Tagesverlauf; Stundenpreise und Kosten entstehen nur aus einem
  HA-Preissensor.

### Betriebsmodus der Waermepumpe (Zustand statt Zahl)

Der Betriebsmodus traegt **keine Zahl im physikalischen Sinn**, sondern einen Zustand (wie die Zustaende der
E-Mobilitaet weiter unten). eedc versteht dieselben Woerter wie bei einem HA-Sensor und zusaetzlich — nur hier, ueber MQTT — einen **Zahlencode**:

| Code | Wort (Beispiele) | eedc versteht es als |
|---|---|---|
| `0` | `aus`, `off` | Aus |
| `1` | `heizen`, `heat` | Heizen |
| `2` | `warmwasser`, `dhw` | Warmwasser |
| `3` | `kuehlen`, `cool` | Kuehlen |
| `4` | `lueften`, `fan_only` | Lueften |
| `5` | `entfeuchten`, `dry` | Entfeuchten |

Die vollstaendige Wortliste steht im Handbuch Waerme & Klima (Werte-Tabelle) und in *Einstellungen → Datenquellen*
am Feld „Betriebsmodus". `1.0` gilt wie `1`. Jeder andere Wert zaehlt als *unbestimmt* (das Geraet lief, die
Betriebsart ist nicht zuordenbar).

```
eedc/1_Meine_PV/live/inv/7_Vitocal/betriebsmodus → 2
```

- **Senden bei jeder Aenderung genuegt** (retained empfohlen): eedc haelt den letzten Wert, bis ein neuer kommt.
- **Was eedc daraus macht:** den Modus-Chip in *Cockpit → Live* und im Hub, den HA-Sensor/das Export-Topic des
  Modus, und je abgeschlossener Stunde die **Betriebsart-Mitschrift** (Anteil der Stunde je Modus, aus 5-Minuten-
  Fenstern) — daraus „Strom nach Betriebsart" und „Betrieb heute".
- **Grenzen:** Die Mitschrift beginnt mit dem ersten empfangenen Wert und ist **nicht rueckwirkend**. Faellt der
  Broker aus, bleibt die Zeit ohne Verbindung eine Luecke; ein Publisher, der verstummt, waehrend der Broker laeuft,
  behaelt seinen letzten Wert. **Leerlauf** (die HA-Aktion `idle`) gibt es ueber MQTT nicht. Das **Gateway**
  (Fremd-Topic umschreiben) steht fuer dieses Feld nicht zur Wahl (es reicht am Modus nur Zahlen weiter; den Text gibt es
  seit der naechsten Version nur an den Zustandsfeldern der E-Mobilitaet). Die Topic-Abdeckung
  im Daten-Checker ueberwacht das Modus-Topic nicht (ein Modus, der sich stundenlang nicht aendert, ist kein Ausfall).
- **Hat das Geraet in eedc einen HA-Sensor fuer den Modus, gilt der HA-Sensor**; das MQTT-Topic wird dann nicht
  gelesen.

### Zustand und Sitzung der E-Mobilitaet (ab der naechsten Version)

Wallbox und E-Auto haben eigene Live-Topics fuer den Ueberblick im Komponenten-Hub — Topic = Registry-Feld unter
`…/live/inv/{id}_{name}/`:

| Geraet | Topic-Suffix | Payload |
|---|---|---|
| Wallbox | `ladezustand` | Zustand: `kein_fahrzeug` · `verbunden` · `wartet` · `laedt` · `fertig` · `gesperrt` · `fehler` (go-e-Code `0`…`5` geht auch) |
| Wallbox | `lademodus` | Zustand: `aus` · `pv` · `smart` · `schnell` · `plan` · `eco` (go-e `lmo` `3`/`4`/`5` geht auch) |
| Wallbox | `fahrzeug_am_ladepunkt` | Text: der Fahrzeugname der Steuerung (evcc `vehicleName`); **leer ist ein Wert** (kein bzw. unbekanntes Fahrzeug) |
| Wallbox | `evcc_verbunden`, `evcc_laedt`, `evcc_freigegeben` | Zustand: `an` · `aus` (`true`/`false`, `on`/`off`, `1`/`0` gehen auch) — nur ohne `ladezustand` noetig, eedc setzt daraus den Ladezustand zusammen |
| Wallbox | `sitzung_kwh`, `sitzung_dauer_s`, `ladestrom_a`, `phasen_aktiv`, `ziel_ladestand_prozent`, `restzeit_min` | Zahl (kWh, s, A, Anzahl, %, min) |
| E-Auto | `ladezustand_fahrzeug` | Zustand: `nicht_verbunden` · `verbunden` · `laedt` · `laedt_dc` · `fertig` · `fehler` |
| E-Auto | `zu_hause` | Zustand: `zu_hause` · `unterwegs` |
| E-Auto | `reichweite_km`, `ziel_ladestand_prozent`, `restzeit_min` | Zahl (km, %, min) |

```
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/ladezustand → laedt
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/sitzung_kwh → 9.8
eedc/1_Meine_PV/live/inv/5_Smart_1/reichweite_km     → 312
```

- Zustaende wie der Betriebsmodus: bei jeder Aenderung senden (retained empfohlen); die volle Werte-Tabelle steht im
  Handbuch Einstellungen §7.10 und am Feld in *Einstellungen → Datenquellen*. Ein fremder Wert ergibt keinen Chip; der
  Daten-Checker nennt ihn („E-Mobilitaet – unbekannter Zustand").
- **Reine Anzeige:** eedc speichert diese Werte nicht (kein Stundenmittel, kein Kanal) und rechnet keine Einheit um — die
  Sitzung in **kWh** senden (nicht Wh), die Restzeit in **Minuten**. **Ausnahme — die Zustands-Mitschrift (seit der
  naechsten Version):** fuer `ladezustand`, `ladezustand_fahrzeug` und `zu_hause` fuehrt der Inbound wie beim Betriebsmodus
  ein **Haltezeit-Fenster je Geraet und Feld** (ein Zustand gilt bis zur naechsten Nachricht); der 5-Minuten-Snapshot
  schreibt daraus `inv:<id>:<feld>:<wert>` = Anteil des Fensters und an der Wallbox `inv:<id>:ladezustand:wechsel_laedt` =
  Zahl der Uebergaenge nach `laedt` im Fenster (nur > 0). Der Stundenlauf (:05) verdichtet sie je abgeschlossener Stunde in
  die Kanaele `zustand:inv:<id>:<feld>:<wert>` und `wechsel:inv:<id>:ladezustand:laedt` — daraus „Betrieb heute" und
  „Ladevorgaenge heute". Eine Nachricht auf `evcc_verbunden`/`evcc_laedt`/`evcc_freigegeben` schreibt das Fenster des
  Ladezustands fort (Option A, dieselbe Regel wie unten; ein gesendeter `ladezustand` geht vor). Grenzen wie beim Modus: ab
  dem ersten Wert, nicht rueckwirkend; Broker weg ⇒ Luecke; nach einem Neustart zaehlt die Stunde erst ab der naechsten
  Meldung, und der erste Wert ist **kein** Ladevorgang. `lademodus`, `fahrzeug_am_ladepunkt` und die drei `evcc_…`-Werte
  selbst werden nicht mitgeschrieben. Hat das Feld einen HA-Sensor, schreibt der HA-Weg mit, nicht MQTT.
- Der Zustand ist bis zu 60 s alt (derselbe Takt wie der Betriebsmodus).
- **Ladezustand aus drei Binaer-Werten (Option A):** liefert `ladezustand` keinen Wert (nicht gesendet, `unknown`, fremder
  Wert), setzt eedc ihn aus `evcc_verbunden`/`evcc_laedt`/`evcc_freigegeben` zusammen: verbunden `aus` ⇒ `kein_fahrzeug`;
  verbunden `an` und laedt `an` ⇒ `laedt`; verbunden `an` und freigegeben `aus` ⇒ `wartet`; sonst `verbunden`. Ein
  gesendeter Ladezustand geht immer vor. ⚠ Der Cache hat keine Ablaufzeit: wer von `ladezustand` auf die drei Werte
  wechselt, sendet einmal `unknown` auf `ladezustand` (ein geloeschter retained-Wert erreicht eedc nicht).
- **Gateway an Zustandsfeldern (seit der naechsten Version):** an `ladezustand`, `lademodus`, `fahrzeug_am_ladepunkt`,
  `ladezustand_fahrzeug`, `zu_hause` und den drei `evcc_…`-Feldern reicht das Gateway den Text **unveraendert** weiter
  (`plain`: der getrimmte Payload, auch leer; `json`/`json_array`: der Wert am Pfad als Text). Faktor und Offset gelten dort
  nicht. Ein Wort auf einem Zahlenfeld bleibt ein Transform-Fehler (Zaehler `transform_fehler`, kein Republish). Am
  Betriebsmodus bleibt das Gateway aus — der Modus kommt ueber das Inbound-Topic.
- **Hat das Geraet in eedc einen HA-Sensor fuer das Feld, gilt der HA-Sensor**; das Topic wird dann nicht gelesen.
- **`fahrzeug_am_ladepunkt` — leer ist ein Wert.** Anders als bei einem Zustand legt eedc hier einen **leeren Payload** als
  Wert ab („die Steuerung kennt kein Fahrzeug") — evcc schreibt `nil` als leeren String. Haengt dann ein Fahrzeug dran
  (`ladezustand` verbunden · wartet · laedt · fertig), zeigt die Wallbox-Karte „Gastfahrzeug"; ein Name, der mit der
  „Kennung in der Steuerung" eines E-Autos uebereinstimmt (Gross/Klein egal), nennt genau dieses Auto. `null`, `none` und
  `-` gelten ebenfalls als leer, `unknown`/`unavailable` als keine Antwort; laenger als 80 Zeichen wird abgeschnitten. Nur
  dieses Textfeld hat die Weiche — ein leerer Betriebsmodus oder Ladezustand wird weiter verworfen.
  ⚠ Ein leerer **retained** Payload loescht die retained Nachricht am Broker: nach einem Neustart von eedc kommt bis zur
  naechsten Meldung der Steuerung keine Antwort an (dann gibt es keinen Gast, die Karte zeigt die Regel ohne Steuerung).
  Kein Startwert „0" fuer dieses Topic (es ist kein Zahlenfeld).

```
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/fahrzeug_am_ladepunkt → Smart
eedc/1_Meine_PV/live/inv/4_SMA_eCharger_22/fahrzeug_am_ladepunkt → (leer)   # Gast, wenn ein Fahrzeug dranhaengt
```

#### Preset „evcc Ladepunkt" (seit der naechsten Version)

Ein Gateway-Preset legt fuer **einen** evcc-Ladepunkt alle Zeilen auf einmal an (Wallbox-Investition waehlen). Variablen:
`prefix` (Wurzel-Topic aus `evcc.yaml` → `mqtt: topic`, Vorgabe `evcc`) und `loadpoint` (Nummer in evcc, der erste ist `1`,
Vorgabe `1`). Die Einheiten stammen aus der evcc-Quelle (`server/mqtt.go`: Kommazahlen mit hoechstens drei Nachkommastellen,
Dauern als ganze Sekunden, `true`/`false`, kein Wert als leerer Payload; retained):

| evcc-Topic `<prefix>/loadpoints/<n>/…` | eedc-Feld | Einheit bei evcc | Faktor |
|---|---|---|---|
| `chargePower` | `leistung_w` | W | 1 |
| `sessionEnergy` | `sitzung_kwh` | Wh | 0,001 |
| `chargeDuration` | `sitzung_dauer_s` | s | 1 |
| `chargeRemainingDuration` | `restzeit_min` | s | 1/60 |
| `phasesActive` | `phasen_aktiv` | Anzahl | 1 |
| `chargeTotalImport` | `ladung_kwh` unter **`energy/`** (`eedc/<anlage>/energy/inv/<id>/ladung_kwh`) | kWh, Zaehlerstand (nur mit Lademeter) | 1 |
| `mode` | `lademodus` | Text (`off` · `smart` · `now`; ältere evcc: `pv` · `minpv`) | — |
| `connected` | `evcc_verbunden` | `true`/`false` | — |
| `charging` | `evcc_laedt` | `true`/`false` | — |
| `enabled` | `evcc_freigegeben` | `true`/`false` | — |
| `vehicleName` | `fahrzeug_am_ladepunkt` | Text, leer = kein bzw. unbekanntes Fahrzeug | — |

- **Nicht im Preset:** Ladestand und Reichweite (`vehicleSoc`, `vehicleRange` — Werte des Autos, das Preset legt die Zeilen
  einer Wallbox; am E-Auto einzeln ueber das Gateway zuordnen) und `chargeCurrent`/`effectiveLimitSoc` (in der evcc-Doku
  nicht beschrieben).
- **`chargeTotalImport` ist ein fortlaufender Zaehlerstand** (kWh, nur mit Lademeter in evcc): das Preset legt ihn unter
  `energy/` ab, eedc bildet daraus Tag und Monat selbst (siehe oben, „Publiziere den fortlaufenden Stand"). Ohne Lademeter
  publiziert evcc das Topic nicht — die Zeile bleibt dann stumm.
- **Anlegen (seit der naechsten Version in der Oberflaeche):** *Einstellungen → Datenquellen* → Wallbox → **„Preset
  anwenden …"** → „evcc Ladepunkt" (Vorgaben pruefen) → „Anwenden". Welche Presets an welchem Geraet stehen, sagt das Preset
  selbst (`typen`, z. B. `wallbox`); Presets ohne Geraet stehen an „Anlage / Zaehler". Weiterhin moeglich ueber die
  Programmierschnittstelle (`POST /api/live/mqtt/gateway/presets/apply` mit
  `{"preset_id": "evcc_ladepunkt", "anlage_id": 1, "investition_id": 4, "variablen": {"prefix": "evcc", "loadpoint": "1"}}`
  — leere Variablen bekommen die Vorgabe).
- **Ersetzen statt Doppeln:** vor dem Anlegen loescht eedc die **aktiven** Gateway-Zeilen derselben Felder (auch eine im
  Gateway-Picker angelegte Zeile mit Namensteil `live/inv/<id>_<name>/<feld>` — ueber die Investitions-ID ist es dasselbe
  Feld); die Antwort nennt sie (`ersetzt`). Andere Felder bleiben unberuehrt.
- **Quelle „Gateway":** danach stellt eedc jedes gemappte Feld in den Datenquellen auf **„Gateway"** mit dem Topic (bis dahin
  zeigten Preset-Felder „Inbound", weil die Preset-Zeilen das Topic ohne Namensteil tragen). Eine Zeile, deren Ziel kein
  Feld der Flaeche ist, bleibt angelegt, ihre Quelle unveraendert (Antwort `ohne_feld`). Das Gateway schreibt weiter auf
  `eedc/<anlage>/live/inv/<id>/<feld>`.
- evcc rundet Kommazahlen auf drei Nachkommastellen; das Gateway gibt Zahlen auf zwei Nachkommastellen weiter.

### Themen je Geraet (ab der naechsten Version)

An Waermepumpe, Wallbox und E-Auto kannst du unter *Einstellungen → Datenquellen* **Themen** mit frei gewaehlten
Eintraegen anlegen ([Handbuch Einstellungen §7.11](HANDBUCH_EINSTELLUNGEN.md#711-themen-frei-gewählte-entitäten)). Jeder
Eintrag hat ein eigenes Live-Topic:

```
eedc/{anlage_id}_{anlage_name}/live/inv/{id}_{name}/thema_e{n}
```

- `e{n}` ist die Kennung des Eintrags (`e2`, `e5` …) — sie steht in der Zeile der Zuordnung und bleibt, auch wenn du den
  Eintrag umbenennst oder verschiebst. Eine geloeschte Kennung wird nie wieder vergeben.
- Der Payload ist **Text** und wird **wie geliefert** angezeigt (`locked`, `2.4`, `2026-11-02T07:00:00+00:00`) — keine
  Umrechnung, keine Einheit. Leer, `unknown` und `unavailable` gelten als „kein Wert".
- Publiziere **retained**: eedc liest den letzten Wert aus dem Cache; ohne retained steht nach einem Neustart nichts da.
- Der Wert wird nicht mitgeschrieben (kein Verlauf), und der Daten-Checker erwartet das Topic nicht.
- Ueber das **Gateway** reicht eedc ein Fremd-Topic als Text an `…/thema_e{n}` weiter (Faktor und Offset gelten nicht).

### Beispiel

Fuer eine Anlage "Meine PV" (ID 1) mit Speicher "BYD HVS" (ID 3):

```
eedc/1_Meine_PV/live/einspeisung_w          → 1100
eedc/1_Meine_PV/live/inv/3_BYD_HVS/leistung_w → -500
eedc/1_Meine_PV/live/inv/3_BYD_HVS/soc      → 72
eedc/1_Meine_PV/energy/pv_gesamt_kwh         → 627.0
eedc/1_Meine_PV/energy/inv/3_BYD_HVS/ladung_kwh → 128.6
```

**Hinweis:** Die numerische ID am Anfang (`1_`, `3_`) ist die DB-ID. Der Name danach ist optional und dient nur der Lesbarkeit. EEDC extrahiert nur die ID.

## Datenquellen-Prioritaet

MQTT-Inbound hat Konfidenz 91% und liegt zwischen Connector (90%) und HA Statistics (92%):

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%)
```

**Diese Reihenfolge gilt nur fuer den laufenden Monat.** Dort ist sie eine
Live-Vorschau: die frischere Quelle gewinnt, wer HA Statistics hat, sieht deren
Werte statt der MQTT-Werte.

Im **abgeschlossenen** Monat gilt das Gegenteil: gespeicherte Werte sind
authoritativ. Connector und HA-Statistics fuellen dort nur Felder, die noch
leer sind, und ueberschreiben nichts rueckwirkend; MQTT-Inbound wird fuer
vergangene Monate gar nicht erst abgefragt. Ein importierter Monatswert
(Cloud-, Portal- oder CSV-Import) bleibt damit stehen, auch wenn fuer dasselbe
Feld ein HA-Sensor zugeordnet ist — die Zuordnung muss dafuer niemand
entfernen.

**Das ist die Anzeige-Seite.** Beim *Schreiben* gilt eine eigene Hierarchie
(`backend/core/source_priority.py`): Cloud-/Portal-Import und HA-Statistik-
Import liegen dort auf **derselben** Stufe, bei gleicher Stufe gewinnt der
spaetere Schreiber. Ein HA-Statistik-Import mit angehaktem „ueberschreiben"
ersetzt also einen importierten Wert dauerhaft. Nur ein im Formular gepflegter
Wert (Stufe `manual:form`) ist gegen beide geschuetzt.

SoT der Regeln: Anzeige
`backend/core/berechnungen/datenquellen.py::merge_datenquellen`, Schreiben
`backend/services/provenance.py::write_with_provenance`.

## Home Assistant als Sender

Einen eingebauten Automations-Generator gibt es seit der Oberfläche 4.0 nicht mehr. Wer Werte aus Home Assistant
per MQTT an eedc schickt, legt die Automation selbst an — Vorlage im nächsten Abschnitt. Im HA-Add-on ist das
in der Regel unnötig: dort ordnest du HA-Sensoren direkt unter *Einstellungen → Datenquellen* zu, ohne MQTT.
Die erwarteten Topics deiner Anlage zeigt der Block **MQTT-Topics** am Ende der Datenquellen-Fläche zum Kopieren.

## Beispiel-Flows (andere Systeme)

Die folgenden Beispiele zeigen die manuelle Konfiguration fuer andere Smarthome-Systeme.

### Home Assistant Automation

```yaml
automation:
  - alias: "EEDC PV-Leistung senden"
    trigger:
      - platform: state
        entity_id: sensor.pv_power
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA_Tripower/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
```

Mehrere Sensoren:

```yaml
automation:
  - alias: "EEDC Live-Daten senden"
    trigger:
      - platform: time_pattern
        seconds: "/5"
    action:
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/einspeisung_w"
          payload: "{{ states('sensor.grid_export_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/netzbezug_w"
          payload: "{{ states('sensor.grid_import_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w"
          payload: "{{ states('sensor.pv_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/leistung_w"
          payload: "{{ states('sensor.battery_power') }}"
      - service: mqtt.publish
        data:
          topic: "eedc/1_Meine_PV/live/inv/3_BYD/soc"
          payload: "{{ states('sensor.battery_soc') }}"
```

### Node-RED

Einfacher Flow: Sensor-Node → MQTT-Out-Node

```json
[
  {
    "id": "eedc_pv",
    "type": "mqtt out",
    "topic": "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w",
    "broker": "localhost",
    "name": "EEDC PV-Leistung"
  }
]
```

Fuer mehrere Werte einen Function-Node verwenden, der die Sensor-Werte auf die passenden Topics mappt.

### ioBroker (JavaScript-Adapter)

```javascript
// Live-Leistung senden
on('sourceDP.pv_power', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/2_SMA/leistung_w',
        message: String(obj.state.val)
    });
});

// Batterie SoC senden
on('sourceDP.battery_soc', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/inv/3_BYD/soc',
        message: String(obj.state.val)
    });
});

// Netz-Werte senden
on('sourceDP.grid_export', (obj) => {
    sendTo('mqtt.0', 'publish', {
        topic: 'eedc/1_Meine_PV/live/einspeisung_w',
        message: String(obj.state.val)
    });
});
```

### FHEM

```perl
# MQTT2-Geraet fuer EEDC anlegen
define eedc_mqtt MQTT2_DEVICE

# PV-Leistung bei Aenderung senden
define eedc_pv notify pv_power:.* {\
  fhem("set mqtt2 publish eedc/1_Meine_PV/live/inv/2_SMA/leistung_w " . ReadingsVal("pv_power","state","0"))\
}
```

### openHAB

```java
rule "EEDC PV-Leistung senden"
when
    Item PV_Power changed
then
    val mqttActions = getActions("mqtt", "mqtt:broker:myBroker")
    mqttActions.publishMQTT("eedc/1_Meine_PV/live/inv/2_SMA/leistung_w", PV_Power.state.toString)
end
```

## Testen

### Kommandozeile (mosquitto_pub)

```bash
# Einzelnen Wert senden
mosquitto_pub -h localhost -t "eedc/1_Meine_PV/live/inv/2_SMA/leistung_w" -m "4200"

# Alle Topics subscriben (Monitoring)
mosquitto_sub -h localhost -t "eedc/#" -v
```

### In EEDC pruefen

1. In der MQTT-Einrichtung unter "Empfangene Werte" auf "Aktualisieren" klicken
2. Im Live-Dashboard pruefen ob die Werte angezeigt werden

## Hinweise

- **Payload-Format:** Nur numerische Werte (z.B. `4200`, `72.5`). Kein JSON. Ausnahme: `betriebsmodus` (Wort oder Code, siehe oben).
- **Einheiten:** Live-Topics in **Watt** (nicht kW). Energy-Topics in **kWh**.
- **Batterie:** Positive Werte = Ladung, negative = Entladung
- **Retained Messages:** EEDC publisht beim Speichern Initialwerte (0) als Retained, damit Topics am Broker sichtbar sind — nicht auf `betriebsmodus`: dort hiesse `0` „Aus".
- **Reconnect:** Bei Verbindungsverlust verbindet sich der Subscriber automatisch nach 10 Sekunden neu.
- **Monatsabschluss:** Energy-Topics erscheinen automatisch als Vorschlaege im Monatsabschluss-Wizard (Konfidenz 91%). Kein zusaetzliches Mapping noetig.
