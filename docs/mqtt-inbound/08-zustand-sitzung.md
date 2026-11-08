### Zustand und Sitzung der E-Mobilitaet (ab der naechsten Version)

Wallbox und E-Auto haben eigene Live-Topics fuer den Ueberblick im Komponenten-Hub — Topic = Registry-Feld unter
`…/live/inv/{id}_{name}/`. Welche das sind und welche Werte eedc je Zustand versteht, steht in den Live-Tabellen von
[Wallbox](#wallbox) und [E-Auto](#e-auto) unter Topics je Gerätetyp (Spalte „Payload").

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

<!-- erzeugt: mqtt-preset id=evcc_ladepunkt -->

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

