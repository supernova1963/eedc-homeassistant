# Konzept — Datenquellen V4 (MQTT + HA, feld-zentrisch)

> ## **Status (gemessen 2026-08-28): P1 + P2 + P3 ausgeliefert — der Bauplan ist abgearbeitet**
>
> ⚑ **Abgeschlossen 2026-08-28 (Entscheid Gernot, gegen den Code gemessen): P2 und P3 sind fertig — auch Remote-HA (LL-Token).** Der Weg ging über zwei Stufen: v4.0.13/v4.0.14 haben die **Verbraucher**-Seite umgehängt — Tagesverlauf, Prognosequellen (SFML/Solcast), kWh heute/gestern, Verbrauchsprofil, Langzeitstatistik und der Statistik-Import fragen nicht mehr nach der Betriebsart, sondern über `is_available` nach der **Verbindung**. Die Verbindung selbst löst seither `services/ha_connection.py::resolve_ha_connection` auf (**Supervisor oder Remote-LL-Token**) und reicht sie an `HAStatisticsService` **und** `HAStateService` weiter — beim Start *und* beim Speichern. Die Live-Engine liest zugeordnete HA-Entities auch ohne Supervisor (`live_power_service.py:277`, C2a), der `ha_statistics`-Router ist seit 11.08. immer gemountet, und die untertägige Recovery holt nach einem Neustart die letzten sechs Stunden nach (`scheduler.py::sensor_snapshot_startup_recovery`, dazu das 02:15-Self-Healing für den Vortag).
>
> ⛔ **Hier stand bis 2026-08-28: „P3 bleibt offen … heute 30 Stellen im Backend tragen `HA_INTEGRATION_AVAILABLE` (nicht rund 20)".** Die Zahl war **richtig gezählt und trotzdem irreführend** — sie hat fünfzehn Tage lang eine Restschuld behauptet, die es so nicht gab. Heute sind es **28** Vorkommen außerhalb der Tests, davon **neun echte Verzweigungen**, und die sind alle legitim supervisor-spezifisch: die Add-on-API-Router (`main.py:118`/`:635`), die Supervisor-Logs (`system_logs.py:154`), die Quellenart `ha_app` vs. `ha_connector` (`datenquellen.py:908`, `migrate_datenquellen_materialisieren.py:62`), zwei Diagnose-Felder und die beiden Zweige in `live_power_service.py`, die **gemeinsam** Supervisor *und* Remote bedienen. Der Rest sind Importe, die Definition und **Kommentare, die den Rückbau dokumentieren**. *Eine Vorkommens-Zählung misst keine Restschuld — wer eine Zahl als Umfang notiert, notiert dazu, was gezählt wurde.*
>
> **Offen: nichts.** Der Punkt *Datenquellen-Ausbau* steht in der Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) seit dem 28.08. unter **Abgeschlossen**. ⚑ **Der „Takt-Check für Bestands-Zuordnungen" ist kein offener Rest, sondern anders gelöst** (Gernot 28.08.: „es läuft und wird genutzt"): Er sitzt als eine von **fünf** Prüfungen in `services/datenquellen_validierung.py` (`takt_problem`), **nicht** als Daten-Checker-Kategorie. Wer im `daten_checker/` nach einem Takt-Thema greppt, findet nichts und hält es für eine Lücke — es ist keine.

---

> **Was dieses Dokument ist:** die Beschreibung, **wie eedc Datenquellen heute auflöst** — welche
> Quelle den Wert eines eedc-Feldes liefert, in welcher Reihenfolge, und was bei Ausfall passiert.
> **Acht Produktivdateien** zitieren es mit Abschnittsnummer im Datei-Kopf als SoT; deshalb liegt es
> in `docs/` und nicht in `drafts/` (die Regel dazu steht in [`DEVELOPMENT.md`](DEVELOPMENT.md)).
>
> **Was es nicht mehr ist: ein Bauplan.** Die Ausgangslage vor dem Umbau (§1) und die
> Bau-Reihenfolge (§5) sind am 2026-08-28 nach
> [`archive/KONZEPT-DATENQUELLEN-V4-BAUVERTRAG.md`](archive/KONZEPT-DATENQUELLEN-V4-BAUVERTRAG.md)
> gewandert, als P1–P3 abgeschlossen waren — ein Dokument, das öffentlich stehen bleibt, soll den
> **heutigen** Stand sagen und keine Checkliste sein (Entscheid Gernot, 28.08.). **Die
> Abschnittsnummern bleiben trotzdem stehen** — `§2a`, `§2b`, `§2b1`, `§2d` und `§3a` werden aus dem
> Code heraus zitiert; eine Umnummerierung bräche acht Datei-Köpfe.
>
> **Name:** „Datenquellen" statt „Livequellen" — „Live" ist in eedc ein Feld-*Typ* (Live-Felder
> W/%/°C vs. Energie-Felder kWh); der Begriff wäre doppeldeutig.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> **Beobachtung aus dem Feld:** Datenquellen-Felder ohne Zuordnung brauchen nach dem Update einmal
> manuell „keine"; bei Häufung eine Mini-Normalisierung erwägen.

---

## Was wann geliefert wurde

| Paket | Inhalt | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **P1 — MQTT-Fundament** | B1 Broker-Block · B2 Feld-Fläche · B3 `#`-Discovery+Suche · B5 Feld→eine-Quelle · B7 Block-Layout · B8 Migration (MQTT-Seite) | ✅ **ausgeliefert mit v4.0.0** (`51c81f29`) | `components/live/{MqttBrokerForm,DatenquellenZuordnung,DatenquellenGatewayPicker}.tsx` — alle mit SoT-Kommentar auf dieses Doc |
| **P2 — HA in die Fläche** | HA-Sensor als Quelle · B6 (#343-Assistenz) · Präferenz §2d · B8 HA-first | ✅ **ausgeliefert mit v4.0.0** (`d5c4d768`; das Assistenz-Detail steht im Bau-Archiv des Maintainers — **bewusst ohne Link**, `docs/drafts/` ist gitignored) | `components/live/{DatenquellenHaPicker,HaVerbindungForm}.tsx` |
| **P3 — Remote-HA (LL-Token)** | B4 HA-Verbindungs-Block · **Gate-Umbau `HA_INTEGRATION_AVAILABLE`** (Supervisor **oder** Remote) · Remote-Verfügbarkeit + FS-Degradation · untertägige Recovery | ✅ **abgeschlossen 2026-08-28** (Anwender-Hälfte mit v4.0.13/v4.0.14) | `services/ha_connection.py::resolve_ha_connection` · `api/routes/ha_remote.py` · `live_power_service.py:277` (C2a) · `scheduler.py::sensor_snapshot_startup_recovery`. Vom Gate bleiben **neun** echte Verzweigungen, alle legitim supervisor-spezifisch (s. Kopf) |
| **Rest aus P2** | Wissensbasis über den Initial-Umfang hinaus (evcc + 4 Wallbox-Integrationen) · Takt-Check für **Bestands**-Zuordnungen | ✅ **erledigt** — Wissensbasis wird kuratiert fortgeschrieben (`core/ha_integrations_wissen.py`); der Takt-Check ist **anders gelöst als geplant** | `services/datenquellen_validierung.py::takt_problem` (eine von fünf Prüfungen) statt einer Daten-Checker-Kategorie — Gernot 28.08.: „es läuft und wird genutzt" |

---

## 0. Die vier Grundentscheidungen

Worauf die Fläche steht (Gernot, 2026-07-13) — alle vier sind gebaut. Zwei Formulierungen
tragen ausdrücklich den Zusatz „damals", weil sie sich auf den Zustand vor dem Umbau beziehen.

Fundament dieses Entwurfs:

1. **Voll vereinheitlichen:** heutige Trennung Inbound-Wizard ↔ Gateway-Wizard auflösen → **eine feld-zentrische Zuordnungs-Fläche**, Quelle pro eedc-Feld wählbar.
2. **Quellen-Priorität ist kontextabhängig** (nicht „immer beide erzwingen", nicht „hart sperren"):
   - **HA-App (Supervisor-Token):** besteht eine HA-Sensor-Zuordnung (aus beliebiger HA-Integration), hat **HA Vorrang** bei der Zuordnung; MQTT deckt Felder **ohne** HA-Sensor. **Kein** Laufzeit-Fallback pro Feld (§2d).
   - **Standalone + Remote-HA (LL-Token):** HA-Sensor **gleichberechtigt** zur MQTT-Topic-Zuordnung (pro Feld wählbar).
   - **Standalone ohne HA:** nur MQTT.
   „Parallel" heißt dabei **Funktionsgleichheit**, gesteuert über Kontext und Verfügbarkeit — nicht „beide gleichzeitig".
3. **Remote-HA per Long-Lived-Token** (damals neu, seit P3 gebaut): eedc-Standalone bindet sich an eine entfernte HA-Installation an. Analog MQTT-Broker braucht es einen **HA-Verbindungs-Block**. Damit wird HA im Standalone überhaupt erst wählbar.
4. **Topic-Discovery (Broker-`#`-Scan mit Suche)** als eigener Baustein — bei der Entscheidung gab es ihn nicht, mit P1 ist er gebaut.

---

## 1. Was die Fläche leistet

Zwei Verbindungen und eine Zuordnung: Unter *Einstellungen → Integration* stehen der
**MQTT-Broker** und die **Home-Assistant-Verbindung** als eigene Blöcke — „Verbindung" getrennt
von „was darüber fließt" (§2a). Darunter liegt **eine feld-zentrische Fläche** (§2b): Für jedes
eedc-Feld wählt der Anwender **genau eine** Quelle — HA-Sensor, MQTT-Topic oder bewusst keine —
und sieht den gelesenen Wert daneben. Fällt sie aus, entsteht eine sichtbare Lücke statt eines
stillen Quellenwechsels (§2d).

---

## 2. So ist es gebaut

### 2a. Zwei Verbindungs-Blöcke (Integration) — „Verbindung" getrennt von „was darüber fließt"

| Block | Inhalt | Baustein |
|---|---|---|
| **MQTT-Broker-Verbindung** | Host/Port/User/Passwort/enabled + „Verbindung testen" + Status. **Ein** Broker für Inbound, Gateway UND Export. | `FormBlock`; Config existiert (`mqtt_inbound`) — nur UI herauslösen |
| **HA-Verbindung** | HA-App: lokaler Supervisor (automatisch). **Standalone: Basis-URL + Long-Lived-Token** + „Testen" (`GET {url}/api/`) + Status. | **NEU** — B4 |

**Design-Prinzip „Remote-HA kommt!":** Fläche + Quell-Picker sind **von Anfang an Remote-HA-fähig** entworfen worden. HA-Sensor ist eine Quell-Option, deren *Verfügbarkeit* der HA-Verbindungs-Block liefert (Supervisor **oder** Remote-Token) — **kein** „HA nur wenn Supervisor"-Kurzschluss in P1/P2. P3 schaltet später nur die Remote-*Verbindung* frei, ohne die Fläche umzubauen.

### 2b. Eine feld-zentrische Zuordnungs-Fläche (analog MonatsdatenForm)

Pro eedc-Feld (Energie + ggf. Live) eine Zeile: neutrales Label, gelesener Wert + **aktive Quelle** im **Badge/Assistenz-Zone** (nicht im Titel). Je Feld ist **genau eine Quelle aktiv** (§2d); „Quelle wechseln" öffnet den Picker:
1. **HA-Sensor** (wenn HA verfügbar) — Auswahl aus Entity-Discovery (Relevanz-Filter + Suche, wie heute) + #343-Assistenz (§2f).
2. **MQTT-Gateway** (Broker-Topic) — Auswahl aus `#`-Discovery mit **Suche** (B3) + Transform, ggf. Preset.
3. **MQTT-Inbound** — kanonisches Standard-Topic aus `build_expected_topics()`.
4. **keine Quelle / manuell** — kein Sensor/Topic zugeordnet (`strategie: 'keine'`); Folge im Monatsabschluss s. §2d.

Gruppierung in einklappbaren `FormSection` (Anlage-Basis, dann je Investitionstyp/Gerät) mit Rollup-Badge.

**Bändigung „unendlich vieler" Quellen:** HA-Sensoren **und** MQTT-Topics werden gleich behandelt — **Relevanz-Filter** (HA: device_class/unit/state_class; MQTT: retained/energie-nahe Topics) + **Suche** + **#343-Vorschläge** pro Investitionstyp zum Eingrenzen. Der `#`-Scan zusätzlich zeit-/größenbegrenzt (B3). Symmetrie zu HA, kein Sonderweg.

**Kein Mehr-Quellen-auf-ein-Feld:** Das Gateway re-published pro Mapping nach `eedc/{anlage}/{ziel_key}` und **überschreibt** (last-write-wins, `mqtt_gateway_service.py:231`) — es summiert nicht. Mehrere Geräte auf ein eedc-Feld gibt es also nicht; das ist über mehrere Investitionen zu modellieren. „Eine Quelle pro Feld" kollidiert mit nichts Bestehendem.

### 2b1. Seitengestaltung der Zuordnungs-Fläche

> Verfeinert §2b nach Gernot-Kritik „kein Neubau, sondern die Komponenten-Struktur spiegeln". Die heutige `DatenquellenZuordnung` (FormSection Typ▸Gerät▸Feld + Select-Dropdown) wird durch die **gespiegelte Komponenten-Struktur + Quellen-Button-Tabelle** ersetzt. Bau erst nach dieser Detail-Abnahme.

**Die 4 Transporte (Gernot-Definition) — im Feld-Picker zu 3 Spalten kollabiert (Gernot-Weiche 2026-07-14):**

| Transport | `quelle`-Kennung | Verbindung | LTS | Feld-Spalte |
|---|---|---|---|---|
| **HA App** | `ha_app` | Supervisor-Token (Add-on, automatisch) | ✅ DB-Zugriff | → **HA-Sensor** |
| **HA Connector** | `ha_connector` | Remote-HA per LL-Token (Standalone, `ha_remote`/B4a bereits angelegt) | ❌ nur REST `/states`+`/history` | → **HA-Sensor** |
| **MQTT Gateway** | `mqtt_gateway` | Broker-Fremd-Topic (Discovery) | — | **MQTT Gateway** |
| **MQTT Inbound** | `mqtt_inbound_standard` | eedc-Standard-Topic `eedc/…` | — | **MQTT Inbound** |

- **Nur DREI Quellen-Spalten im Feld-Picker: HA-Sensor · MQTT Gateway · MQTT Inbound** (Gernot 2026-07-14). HA App + HA Connector sind zwei **Verbindungs-Wege zu HA**, keine zwei fachlichen Quellen — und schließen sich pro Installation praktisch aus (Add-on=Supervisor, Standalone=Remote-Token), sonst wäre eine Spalte dauerhaft tot. Pro Feld wählt der Nutzer nur die **HA-Entity**; *ob* Supervisor oder Remote-Token, ergibt sich transparent aus der konfigurierten HA-Verbindung (§2a). Deckt §2d („HA-Sensor > Gateway > Inbound" = *eine* HA-Quelle) korrekt. Der Resolver (B5) löst „HA-Sensor" je nach aktiver Verbindung auf `ha_app`/`ha_connector` auf; die LTS-Differenz lebt im HA-Verbindungs-Block + Fähigkeits-Matrix (§2c), nicht als Feld-Spalte.
- **Der Geräte-Connector (`connector.py`, `connector_mqtt_bridge.py`) ist KEINE dieser Quellen** — er pollt Geräte-REST-APIs und *publisht auf Inbound-Topics*, ist also ein Produzent hinter „MQTT Inbound", keine eigene Achse. (Frühere Prompt-Vermutung „HA Connector = Geräte-Connector" ist damit widerlegt.)

**Struktur = Einstellungen → Komponenten gespiegelt (bis zur Geräte-Ebene):**
- **`BlockShell`** (`persistKey="v4-einst-datenquellen"`), **ein Block pro Investitionstyp** (`INVESTITION_TYP_ORDER`, default zu), `summary` z. B. „3 Geräte · 2 Felder ohne Quelle" — identisch zu `KomponentenEinstellungen`. **Kein „+"** (Zuordnung, keine Geräteverwaltung); Badge trägt ggf. Rollup-Ampel.
- **Zusatz-Block „Anlage / Zähler" ganz oben** für die Basis-Felder (Einspeisung/Netzbezug/Wetter) — nötig, weil Komponenten diese Ebene nicht kennt, die Felder aber zuordenbar sind.
- **Geräte-Ebene = einklappbare Sub-Sektion** (`FormSection ebene="geraet"`, Gernot-Wahl) mit Geräte-Kopf im `InvestitionCard`-Stil (Bezeichnung + Detail-Badges) + Rollup-Badge (Felder mit/ohne Quelle). Weicht bewusst minimal von Komponenten ab (dort Geräte-Zeile), weil die Feld-Tabellen groß sind.

**Feld-Tabelle je Gerät, 3 Abschnitte nach `einheit` + eine vierte Stufe** (SoT `field_definitions.py`, nicht `kategorie`):
| Abschnitt | Regel | Beispiele |
|---|---|---|
| Energie-Sensoren (kWh) | `einheit == 'kWh'` | Einspeisung, Ladung, Heizwärme |
| Leistung-Sensoren (W) | `einheit == 'W'` | leistung_w, pv_gesamt_w |
| Sonstige Sensoren | Rest | soc (%), Temp (°C), km, €, Ladevorgänge |
| **Weitere Größen erfassen** | `erweitert === true` **und** keine Quelle — zugeklappt, am Ende des Geräts | Kühl-Achse an einer Luft-Wasser-WP, Heiz-Achse an einer Brauchwasser-WP, Gesamtzähler neben getrennter Messung |

> ⭐ **Die vierte Stufe (2026-08-26, SOLL Wärme/Klima §3.2a/R1) löst die P-6-Falle anders ein.**
> Sie lautet *„biete nichts an, was niemand einlösen kann"* — die bisherige Antwort war, Felder
> **nach Bauart wegzunehmen**. Daran scheiterte MartyBr, der seit dem Sommer 2026 einen getrennten
> Kühlzähler an einer Nicht-Klimaanlage hat und ihn nirgends hinterlegen konnte (Forum T89667
> #200; pipp086 #199 fragt nach derselben Größe). Die richtige Antwort ist **Sichtbarkeit nach
> Beleglage**: Die Fläche bleibt kurz, und **kein Fall ist ausgeschlossen**.
>
> **Drei Marken, drei Folgen** — die Registry markiert, die Fläche entscheidet:
>
> | Marke | Bedeutung | Fläche |
> | --- | --- | --- |
> | *(keine)* | gilt an diesem Gerät | erste Reihe |
> | `erweitert` | untypisch, aber möglich (weiche Bedingung) | „Weitere Größen erfassen"; **mit** Quelle rückt es vor |
> | `nicht_an_dieser_bauart` | die Größe existiert hier nicht (harte Geräteklasse) | ausgeblendet — **außer** es hat eine Quelle |
>
> ⛔ **Die Ausnahme „außer es hat eine Quelle" ist keine Kür.** Verschwände ein zugeordnetes Feld,
> bliebe die Zuordnung stehen und wäre **nicht mehr löschbar**. Der Fall ist real: azywietz-web
> führt zwei Klimaanlagen als `luft_wasser` (#383, weil das Feld „Wärmepumpenart" wie eine
> Community-Einstellung beschriftet war). Stellt er die Bauart um, braucht ein zugeordneter
> Warmwasser-Sensor einen Weg heraus. Gewächtert von
> `test_klima_ohne_warmwasser_n304.py::test_zuordnungsflaeche_zeigt_das_feld_weiter` — der einen
> ersten, zu groben Fix dieser Stelle am 26.08. gefangen hat.

**Zeilen-Spalten:** `Feld (Einheit) │ IST-Zuordnung │ Wert* │ [HA-Sensor][MQTT Gateway][MQTT Inbound]`
- **3 Quellen-Buttons ersetzen das Select.** Aktive Quelle = gefüllter Button; Klick öffnet das jeweilige Modal (Gateway = vorhandener Picker; Inbound = direkt setzen; HA-Sensor = neu, Entity-Auswahl). „Keine Quelle" = kein Button aktiv.
- **Button-Gating (Gernot):** **nur „HA-Sensor" ausgegraut**, wenn **gar keine** HA-Verbindung besteht (weder Supervisor noch Remote-Token) + Tooltip. Gateway/Inbound bleiben immer aktiv (Zuordnungs-Wechsel jederzeit).
- **`Wert*`-Regel:** kein empfangener Wert → „-" **und** IST-Zuordnung + Wert **amber** (Farbrolle aus `lib/colors.ts`, keine Inline-Hex). ⚠️ **An B5 gekoppelt:** heute liefert der Cache nur **Inbound**-Werte — ein an HA/Gateway zugeordnetes Feld hätte dort keinen Wert und würde fälschlich amber. Bis der Resolver (B5) je Quelle liest, gilt Amber **nur für Inbound-Felder** (HA/Gateway-Wert-Anzeige zieht mit B5 nach), sonst lügt die Fläche.
- **IST-Zuordnung** = aktive Quelle **+ Ziel** (Topic bei Inbound/Gateway, Entity bei HA-Sensor).
- **Mobile (Gernot):** keine Tabelle — pro Feld eine Karte: Zeile 1 Feldname + Wert, Zeile 2 IST-Zuordnung, Zeile 3 die 3 Quellen als **Chip-Reihe** (aktiver Chip gefüllt).
- **Icons:** Typ-Blöcke tragen die farbigen `TYP_ICON_STYLE`-Icons wie Komponenten; der Zusatz-Block „Anlage / Zähler" bekommt ein neutrales Zähler-Icon (z. B. `Gauge`).
- **Leer-Regeln:** leere Abschnitte (kein kWh/W/Sonstige-Feld) ausblenden; Typ-Blöcke mit 0 Geräten ausblenden (anders als Komponenten — hier kein „+").

**Backend-Erweiterung (für den Bau danach):** `QUELLEN_ERLAUBT += {ha_app, ha_connector}` (Feld-Spalte „HA-Sensor" → Resolver B5 wählt anhand der aktiven HA-Verbindung); Migration (B8) kennt beide; HA-Sensor-Picker (aus `available-sensors`) neu, Verbindungs-transparent; Gateway-/Inbound-Pfad unverändert.

### 2c. Fähigkeits-Matrix (Quelle × Achse)

Der Kern-Unterschied zwischen den Quellen — **drei Achsen**, nicht nur „liefert Live-Wert":

| Achse | HA-App (Supervisor) | Remote-HA (LL-Token) | MQTT |
|---|---|---|---|
| **Live-Wert jetzt** | ✓ REST `/states` | ✓ REST `/states` | ✓ Push |
| **Untertägige Stunden-Recovery** (heute verpasste Slots nachholen) | ✓ Self-Healing via HA-History | ✓ REST `/history` — **kein WebSocket nötig** (heutige Stunden liegen im Recorder-Fenster) | ✗ verpasste Werte weg |
| **Historischer Backfill** (vergangene Tage/Monate) | ✓ LTS (DB) via HA-Statistik-Import | ⚙️ nur via `ha_recorder_db_url` bzw. WS — **außerhalb dieses Konzepts** (§2e) | ✗ |
| **Ableitung Leistung→Energie / Stunden-Form** (*innerhalb* der Quelle) | ✓ Zähler = Summe + Live-Sensor = Kurvenform (v3.45.5) | dito | Riemann aus Power nur ohne kWh-Zähler — verlustbehaftet (pre-v3.19, ±5–15 % #135), **nur schlimmsten Falls** |

Kernaussage (Gernot): HA (beide) kann heutige Stunden **rückwirkend** liefern, MQTT nicht. Für den *Live-Wert* ist Remote-HA ≈ MQTT; auf der *Recovery-Achse* ist HA (beide) reicher als MQTT. Grenze: rückwirkend nur so weit, wie der Sensor Werte führt.

**Klarstellung:** Die letzte Zeile ist **Granularität/Ableitung innerhalb der *einen* zugeordneten Quelle** — die Stunden-*Form* aus dem Live-Leistungssensor holen, während *Menge/Summe* beim Energie-Zähler bleibt (LTS-treu, v3.45.5). Das ist **kein** Wechsel der Werte-Quelle und **kein** Widerspruch zur „eine Quelle pro Feld"-Regel (§2d). Riemann ist derselbe Fall (W→kWh innerhalb der Quelle), nicht ein Cross-Source-Fallback.

### 2d. Genau **eine** aktive Quelle pro Feld — mit Präferenz-Reihenfolge

Grundregel (Gernot): **pro eedc-Feld genau eine Quelle**, kein Laufzeit-Merge mehrerer Quellen. Präferenz-/Default-Reihenfolge:

1. **HA-Sensor-Zuordnung** (wenn HA verfügbar)
2. **MQTT-Gateway** (Broker-Topic, übersetzt)
3. **MQTT-Inbound** (Standard-Topic)
4. **manuell** (Monatsdaten-Eingabe)

Kontext-Einfluss auf Verfügbarkeit/Default:
| Kontext | HA-Sensor |
|---|---|
| **HA-App** (Supervisor-Token) | verfügbar + oberste Präferenz → Felder mit HA-Sensor werden HA zugeordnet; MQTT deckt die übrigen |
| **Standalone + Remote-HA** (LL-Token) | verfügbar, aber gleichrangig zu MQTT — Nutzer wählt bewusst (HA hat Recovery-Bonus §2c) |
| **Standalone ohne HA** | — (nur MQTT/manuell) |

⚠️ **Engine-Umbau:** heute Merge mit MQTT-Vorrang (`basis_values.update(mqtt_basis)`, `live_power_service.py`) → ersetzen durch **direkte Auflösung auf die eine zugeordnete Quelle** je Feld.

**Strikt eine Quelle, kein Laufzeit-Fallback** (Entscheid Gernot). Fällt die zugeordnete Quelle aus → Feld-Lücke, die die untertägige Recovery (§2c) später schließt (bei HA-Quelle); keine Prioritätskette, kein „Notstopfen". Die Präferenz-Reihenfolge oben gilt nur für **Default/Vorschlag** bei der Zuordnung, nicht als Laufzeit-Kette.

**Kein stiller Quellen-Wechsel + Ausfall sichtbar:** Wählt der Nutzer HA (oder MQTT-Gateway), **bleibt** es dabei — bei Ausfall wird **nicht** stillschweigend auf MQTT umgeschaltet. Der **Ausfall der zugeordneten Quelle wird sichtbar dokumentiert** (Badge „Quelle liefert nicht" + Daten-Checker-Eintrag), nicht verschluckt.

**„Keine Zuordnung" ist eine gültige Wahl:** Ein Feld darf bewusst *ohne* Sensor-/Topic-Quelle bleiben (`strategie: 'keine'`). Folge im **Monatsabschluss**: **keine Sensorwerte angeboten** → Feld wird **manuell** erfasst bzw. über die bestehenden Vorschläge **Durchschnitt / Vorjahresmonat** (`FeldStatus.vorschlaege`, MonatsdatenForm-Mechanik §1e) gefüllt. Das ist der heutige `strategie: 'keine'`-Pfad, in der Fläche jetzt explizit wählbar.

### 2e. Abgrenzung: laufende Werte vs. historischer Backfill

Dieses Konzept regelt **laufende/aktuelle Werte** (Live + aktueller Monat) **und untertägige Recovery** (heutiger Tag). **Echter historischer Backfill** (vergangene Tage/Monate) bleibt die **bestehende** Reparatur-Werkbank / HA-Statistik-Import — nicht Teil der Feld-Quellen-Zuordnung. Damit fällt die HA-LTS-/WebSocket-Frage aus dem Scope (relevant nur dort, remote via `ha_recorder_db_url`).

### 2f. Zuordnungs-Assistenz (#343) in der Fläche

Die Sensor-Zuordnungs-Assistenz aus der Zuordnungs-Assistenz (#343) wird **Teil dieser Fläche**, nicht getrennt:
- **Integration-Dropdown pro Investitionstyp** (kuratierte Wissensbasis Integration × Typ × Feld → Entity-Muster + Hinweis) als **Vorschlag** beim HA-Sensor-Picker — installierte Integrationen nur „gefunden" markieren, Auswahl trifft immer der Nutzer, Eintrag „Manuell" bleibt.
- **Takt-Check bei kWh-Zähler-Auswahl** (`statistics_short_term`, Treppenstufen-Muster) als Warnung im Assistenz-Zonen-Stil (analog Einheiten-Warnung).

Beides greift genau beim Quell-Picker (§2b) — deshalb hier integriert statt separat. Timing #343 („nach IA-V4-Rollout") wird damit an dieses Konzept gekoppelt.

### 2g. Neustrukturierung der Blöcke unter Einstellungen → Integration

Die Vereinheitlichung ändert das Block-Layout der Kategorie **Integration** (`einstellungenKatalog.tsx:500-549`):

| heute | neu |
|---|---|
| `sensor-mapping` (HA-Sensor-Wizard) + `mqtt-inbound` (Inbound+Gateway-Wizard) | **→ Datenquellen-Zuordnung** (die neue feld-zentrische Fläche §2b — vereint beide) |
| — | **+ MQTT-Broker-Verbindung** (Verbindungs-Block, §2a) |
| — | **+ HA-Verbindung** (Verbindungs-Block, §2a; HA-App = Status, Standalone = URL+Token) |
| `ha-export` (MQTT-Export) | bleibt — nutzt jetzt den gemeinsamen Broker-Block |
| `ha-statistik-import` | bleibt — historischer Backfill (§2e) |
| `import-buendel` | bleibt |

Vorgeschlagene Blockreihenfolge: **Verbindungen zuerst** (MQTT-Broker · HA-Verbindung) → **Datenquellen-Zuordnung** → **Export** → **Import / Statistik-Import**. Pro neuem Block Deep-Link-Öffner (`oeffneBeimMount`) + `useEinstellungenStatus`-Ampel nachziehen; V3→V4-Routen (`v3ZuV4Route.ts`) für die entfallenden `sensor-mapping`/`mqtt-inbound`-Einstiege auf die neue Fläche umbiegen.

### 2h. Migration bestehender Zuordnungen

Bestehende Boxen haben `sensor_mapping` (HA), `mqtt_gateway_mappings`, `mqtt_inbound`. Überführung in „eine Quelle pro Feld" nach **HA-first** (Gernots gelebte Empfehlung; Doppelzuordnungen sind absolute Ausnahme):
- Besteht für ein Feld eine **HA-Sensor-Zuordnung** → **HA** wird die Quelle; ein etwaiges paralleles MQTT-Mapping wird **deaktiviert (nicht gelöscht)** — verlustfrei rückholbar.
- Feld ohne HA-Sensor: bestehendes **Gateway-Mapping** → Quelle „MQTT-Gateway"; sonst „MQTT-Inbound", falls Standard-Topic bespielt wird; sonst „keine".
- Migration **additiv + einmalig**, **kein** blockierender Start-Job / HTTP; Korrektheit per Transform-Test, nicht per Dauer-Wächter (§7).

### 2i. Zuordnungs-Validierung

> **REFRAME (Gernot-Frage „weitere Daten-Checker-Probleme aus falscher Zuordnung?"):** Der Daten-Checker prüft **config-basierte Zuordnungsfehler bereits** — u. a. `SENSOR_MAPPING_EINHEIT` (= D!), `SENSOR_MAPPING_LTS`, `EmobChecks`-Doppelmapping (#314). Daher **wiederverwenden statt neu bauen** (`feedback_bestehende_mechanik_nutzen_nicht_erfinden`, kein Drift): die **config-basierten** (zur Zuordnungszeit erkennbaren) Checks proaktiv **feld-bezogen** in der Fläche zeigen; **daten-basierte** (retrospektiv: `PV_UEBER_ERFASSUNG`-Plausibilität, `DATENQUELLE_DRIFT/STATUS`, `PROVENANCE_CONFLICT`, `BATTERIE_VORZEICHEN_HISTORIE`) bleiben im Daten-Checker.

**Umfang (Gernot 2026-07-16, alle 4):** je Feld in `/felder` eine Liste `probleme: [{art, schwere, text, aktion?}]`, im Frontend amber/rot + ggf. Inline-Aktion.
1. **Einheiten-Mismatch (D)** — **Reuse** `SENSOR_MAPPING_EINHEIT`: Dimensions-Klassifikator `_klasse` (W/kW/MW=power, kWh…=energy) + `get_sensor_units`. Mismatch (kWh-Sensor in W-Feld, #200) = ERROR. Nur HA-Felder. **Klassifikator in gemeinsamen Helfer heben** (Checker + Fläche eine Quelle).
2. **Aggregat-Redundanz (C)** — **NEU** (config, proaktiv; ergänzt das daten-basierte `PV_UEBER_ERFASSUNG`). Paare: `basis_*_pv_gesamt` ⊥ per-WR `inv_*_pv_erzeugung_kwh`/`inv_*_leistung_w`; `basis_live_netz_kombi_w` ⊥ `einspeisung_w`+`netzbezug_w`. Aggregat + ≥1 Komponente belegt → Aggregat wirkungslos (Engine-Vorrang, s. u.). Inline **„auf keine"**.
3. **Kein `state_class` / LTS** — **Reuse** `SENSOR_MAPPING_LTS`: zugeordneter HA-Sensor ohne `state_class` → keine History/Zeitmaschine. Braucht `state_class` je Entity (get_sensor_units liefert nur Unit → um `state_class` erweitern oder zweiter Batch).
4. **Sensor-Doppelmapping** — dieselbe HA-`entity_id` in ≥2 Feldern der `quellen`-Map → Doppelzählung (#314). Config-Scan der Fläche-Zuordnungen; zeigt beide betroffenen Felder.

Alle rein **diagnostisch** (nie blockierend, §2d), backend-berechnet (SoT/testbar), amber im Frontend; C zusätzlich Inline-„auf keine". HA-Picker warnt bei Einheit/`state_class` schon beim Wählen. **Engine-Vorrang-Befund für C** (kein Doppelzählungs-Bug, nur Sichtbarkeit):

**C-Detail — Redundanz/Konflikt (Aggregat vs. Komponenten).** Befund aus der Engine-Inventur: „PV gesamt UND einzeln" ist **kein Doppelzählungs-Bug** — die Engine nutzt durchgängig **Vorrang/Fallback**: der Aggregat-Sensor wird bei vorhandenen Komponenten **still ignoriert** (`live_komponenten_builder:261` `not has_individual_pv`; `live_history:341`; `verbrauchsprofil:227`; Energie-Bilanz: `pv_gesamt_kwh` ohne Snapshot-Counterpart; `netz_kombi_w` nur wenn Split fehlt in `_collect_values`). Problem ist also **Sichtbarkeit**, nicht Rechnung: der Nutzer sieht nicht, dass seine gesamt-Zuordnung wirkungslos ist.
- **Aggregat-Paare** (Backend-Konstante, erweiterbar): (1) `basis_*_pv_gesamt` (W+kWh) ⊥ per-WR `inv_*_pv_erzeugung_kwh`/`inv_*_leistung_w` (pv-module/balkonkraftwerk); (2) `basis_live_netz_kombi_w` ⊥ `basis_live_einspeisung_w`+`basis_live_netzbezug_w`.
- **Regel:** Aggregat belegt **und** ≥1 Komponente belegt (Quelle ≠ keine) → Aggregat `redundant`. `/felder` liefert pro Feld `redundant: {grund, wirksame_felder}`.
- **Frontend (Gernot-Weiche „Warnung + Inline-auf-keine"):** dezenter amber Redundanz-Hinweis an der Aggregat-Zeile + Inline-Aktion **„auf keine setzen"**. **KEIN** Auto-keine (stille Fremd-Änderung vermieden, `feedback_reparatur_statt_loesch_features`).
- **„optional erkennbar" ↔ frühere Weiche „keine optional/Pflicht-Kennzeichnung" (Schritt A/Q2):** bewusst als **kontextueller Redundanz-Marker** gelöst (nur im Konflikt-Zustand Aggregat+Komponente), NICHT als statisches optional/Pflicht-Flag je Feld → alte Entscheidung bleibt intakt.

**D — Einheiten-Prüfung pro Zuordnung (HA-only)** (kW≠kWh, #200). **Dimensions-basiert**, nicht String-genau (eedc normalisiert kW→W): W-Feld↔power (W/kW/MW), kWh-Feld↔energy (Wh/kWh/MWh), dazu %/°C/km … Mismatch = **andere Dimension** (kWh-Sensor in W-Feld).
- **Nur HA:** HA-Sensor trägt `unit_of_measurement` (im `/ha/sensoren` schon vorhanden). Inbound/Gateway = eedc-Topic/nackte Zahl ohne Einheit-Metadatum → nicht prüfbar.
- **Zwei Stellen (Gernot-Weiche):** (1) **HA-Picker** — Warnung beim Wählen (Picker hat die Units); (2) **persistent `/felder`** `einheit_warnung: {sensor_einheit, feld_einheit}` an HA-Feldern → dafür muss der HA-Batch in `/felder` neben dem Wert auch die Unit holen.
- **Warnung, keine Sperre:** ungewöhnliche-aber-gültige/fehlende Units nicht blockieren.

Beide per pytest-Regel-Tabellen abgesichert (Dimension-Klassifikator; Aggregat-Redundanz-Resolver).

---

## 3. Bausteine — was wo sitzt

Alle acht Bausteine (B1–B8) sind gebaut; die Spalte „neu" sagt, was es bei der Konzeption
noch nicht gab.

| # | Baustein | Status | Umfang |
|---|---|---|---|
| **B1** | Broker-Verbindungs-Block aus Wizard herauslösen | Config existiert, UI neu gruppieren | klein |
| **B2** | Feld-zentrische Zuordnungs-Fläche (MonatsdatenForm-Muster) | Muster + Registry + Topic-Registry existieren; Fläche neu | **groß** |
| **B3** | **MQTT-Topic-Discovery** (`#`-Scan, Topic-Baum, Suche) | **komplett neu** (heute nur Einzel-Topic-Test) | mittel-groß |
| **B4** | **HA-Remote-Verbindung** (URL + LL-Token) | **neu** — §3a; WS/LTS **draußen** | **groß** |
| **B5** | Feld-Auflösung auf **genau eine** zugeordnete Quelle (§2d) statt Runtime-Merge | Engine-Änderung `live_power_service.py` | mittel |
| **B6** | #343-Assistenz (Integration-Dropdown + Takt-Check) im HA-Sensor-Picker (§2f) | Wissensbasis (JSON) + `statistics_short_term`-Check | mittel |
| **B7** | Integration-Block-Layout neu (§2g): 2 Verbindungs-Blöcke + Datenquellen-Fläche, alte Wizards auflösen, Routen umbiegen | `einstellungenKatalog.tsx` + `v3ZuV4Route.ts` | mittel |
| **B8** | Migration bestehender `sensor_mapping`/Gateway/Inbound → eine-Quelle-Modell (§2h), HA-first, additiv/einmalig, nicht-blockierend | einmalige Migration + Transform-Test | mittel |

### 3a. Remote-HA — so ist es gebaut

Sechs Punkte standen im Bau-Vertrag, alle sind eingelöst (gemessen 2026-08-28):

1. **Konfig-Quelle:** URL + Long-Lived-Token als Anwender-Eingabe im Settings-Key `ha_remote`
   (`api/routes/ha_remote.py`, Fläche `components/live/HaVerbindungForm.tsx`) — Speichern und
   Testen der Verbindung, analog zum MQTT-Broker-Block.
2. **Verbindung entkoppelt:** `services/ha_connection.py::resolve_ha_connection` liefert
   `(api_url, token, kind)` — **Supervisor bevorzugt, sonst Remote** — und
   `aktualisiere_ha_verbindung` reicht sie an `HAStatisticsService` und `HAStateService` weiter,
   beim Start *und* beim Speichern. Beide sind Singletons ohne DB-Session; sie können den Helper
   nicht selbst rufen.
3. **Gate:** Die Verbraucher fragen über `is_available` nach der **Verbindung** statt nach der
   Betriebsart. `HA_INTEGRATION_AVAILABLE` trägt heute nur noch die echten Add-on-Pfade —
   Supervisor-API-Router, Supervisor-Logs, Quellenart `ha_app` vs. `ha_connector`. ⚠ Das war der
   riskanteste Teil und ist über v4.0.13/v4.0.14 bis zum P3-Abschluss gefahren worden; die
   Zählung dazu steht im Kopf dieses Dokuments.
4. **Dateisystem-Features degradieren:** Die HA-Energy-Vorschläge lesen
   `/config/.storage/core.energy` und gibt es remote nicht — sie melden „nicht verfügbar" statt
   zu raten. Der LTS-Backfill bleibt remote an `ha_recorder_db_url` gebunden (§2e).
5. **Sicherheit:** Eine anwenderdefinierte URL heißt SSRF-Fläche — dieselben Guards wie beim
   Connector (`backend/tests/test_connector_ssrf_block.py`).
6. **Wiederverwendet statt neu gebaut:** `HAStateService` (REST `/states` + `/history/period`)
   trägt Live-Wert **und** untertägige Recovery gegen jede Base-URL + Bearer — kein WebSocket.
   Das `sensor_mapping`-Modell ist unverändert geblieben.

---

## 4. Bezug zu den übrigen Regeln

- **HA und MQTT sind funktionsgleich, nicht gleichzeitig** — welche Quelle ein Feld liefert,
  entscheidet §2d nach Kontext und Verfügbarkeit; einen stillen Laufzeit-Fallback gibt es
  bewusst nicht. Fällt die Quelle aus, entsteht eine sichtbare Feld-Lücke.
- **Rückwirkend nur so weit wie die Sensor-Historie reicht** — Home Assistant ist keine
  Zeitmaschine: Was vor der Zuordnung nicht aufgezeichnet wurde, lässt sich nicht nachträglich
  erzeugen. Der Langzeitstatistik-Backfill ist ein eigener Pfad (§2e) und rechnet je Tag
  `MAX(sum) − MIN(sum)`.
- **Neue Felder ziehen drei Stellen nach:** Migration, Response und `core/field_definitions.py`.
- **Migrationen laufen additiv und beim Start ohne HTTP** (§2h) — ein Datentransform darf den
  Start nicht blockieren und nichts überschreiben, was der Anwender gepflegt hat.
- **SoT-Trennung:** Darstellung = Style-Guide + SoT-Komponenten · Merge/Aggregation = die
  bestehende Engine ([ADR-001](ADR-001-BERECHNUNGS-LAYER.md)) · Invarianten = 
  [ADR-002](ADR-002-WURZELMUSTER.md). Dieses Dokument regelt allein die **Herkunft** eines Wertes.

⛔ **Hier standen bis 2026-08-28 neunzehn `[[…]]`-Verweise in Maintainer-Notizen**, die außerhalb
des Entwicklerrechners niemand öffnen kann — in einem öffentlichen Repository sind das tote
Zeiger. Die tragenden Sätze stehen jetzt im Klartext da; wo eine Regel eine versionierte Heimat
hat (ADR, Style-Guide), verweist die Zeile dorthin.

---

## 5. Wächter — was heute wirklich prüft

Gemessen am 2026-08-28, nicht aus dem Bauplan übernommen:

- **Präzedenz „genau eine Quelle je Feld":** Die Auflösung sitzt in
  `core/berechnungen/datenquellen.merge_datenquellen` (aus `get_aktueller_monat` herausgelöst,
  ADR-001). Sie ist doppelt abgedeckt — `backend/tests/test_datenquellen_merge.py` prüft den
  Helper isoliert, `backend/tests/test_aktueller_monat_datenquellen_prioritaet.py` die
  End-to-End-Symmetrie.
- **Zuordnungs-Validierung (§2i):** `services/datenquellen_validierung.py` mit **fünf** Prüfungen
  (Einheit · `state_class` · Aggregat-Redundanz · Sensor-Doppelmapping · **Takt**), abgedeckt von
  `backend/tests/test_datenquellen_validierung.py`. ⚑ Der Takt-Check ist **anders gelöst als
  geplant** — er sitzt hier statt als Daten-Checker-Kategorie (Gernot 2026-08-28: „es läuft und
  wird genutzt"). Wer im `daten_checker/` nach einem Takt-Thema sucht, findet nichts und hält es
  für eine Lücke; es ist keine.
- **Darstellung:** `npm run check:design` (keine Inline-Hex außerhalb `lib/colors.ts`) gilt für
  die Fläche wie für jede andere.

⛔ **Hier stand bis 2026-08-28 ein Wächter, den es nie gab:** *„`check:datenquellen-aufloesung`
(statischer Grep-Wächter)"* — er sollte verhindern, dass die alten Wizards wieder auftauchen. In
`package.json` stehen **25** `check:*`-Skripte, dieses ist keines davon. **Der Zweck hat sich
erledigt**: `MqttInboundSetup`, `MqttGateway` und `SensorMappingWizard` existieren nicht mehr als
Komponenten — was noch auf sie zeigt, sind drei Kommentare, die ihre Ablösung dokumentieren. Eine
behauptete Absicherung ist schlimmer als eine fehlende, weil niemand mehr nachsieht.

**Nicht als Dauer-Wächter verkleidet:** Die Migrations-Korrektheit (§2h) ist ein einmaliger
Datentransform — abgesichert per Transform-Test, nicht per laufendem Check.
