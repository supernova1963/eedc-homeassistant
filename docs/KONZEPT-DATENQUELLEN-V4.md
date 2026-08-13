# Konzept — Datenquellen V4 (MQTT + HA, feld-zentrisch)

> ## **Status (gemessen 2026-08-08): P1 + P2 ausgeliefert · P3 offen**
>
> **Aus `docs/drafts/` nach `docs/` gewandert (2026-08-08).** **`api/routes/datenquellen.py` und `api/routes/ha_remote.py` nennen dieses Dokument im Modul-Docstring wörtlich als SoT — ein versionierter Verweis darf nicht ins Gitignore zeigen** (dieselbe Begründung, aus der [`KONZEPT-MONATS-FAKTEN.md`](KONZEPT-MONATS-FAKTEN.md) gewandert ist). Auch [`KONZEPT-IA-V4.md`](KONZEPT-IA-V4.md) verweist in Invariante I16 hierher.
> Es trägt bewusst **keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359) — ein Status,
> der eine Version nennt, altert garantiert.
>
> **Nicht auf der Website und nicht in der In-App-Hilfe:** `website/scripts/sync-docs.sh` und
> `scripts/sync-help.sh` arbeiten beide mit einer **Allowlist**, in der Konzepte und ADRs bewusst
> fehlen. Dieses Dokument ist im Repository lesbar — es ist kein Anwender-Handbuch.
>
> ⚑ **Präzisiert 2026-08-13 (gegen den Code gemessen): P3 bleibt offen, aber die Hälfte, die dem Anwender wehtat, ist gebaut.** v4.0.13/v4.0.14 haben die **Verbraucher**-Seite umgehängt — Tagesverlauf, Prognosequellen (SFML/Solcast), kWh heute/gestern, Verbrauchsprofil, Langzeitstatistik und der Statistik-Import fragen nicht mehr nach der Betriebsart, sondern über `is_available` nach der **Verbindung** (die Kommentare in `live_tagesverlauf_service.py:204`, `live_history_service.py:517`, `prognose_discovery.py:127`, `solcast_service.py:135` schreiben den Umbau ausdrücklich fest). **Das zentrale Gate steht weiterhin** — heute **30** Stellen im Backend tragen `HA_INTEGRATION_AVAILABLE` (nicht „rund 20"), und `ha_connection.py:24` sagt selbst „das bleibt P3". ⇒ Der Status stimmt, die Umfangs-Angabe stimmte nicht.
>
> **Offen:** **P3 — Remote-HA (LL-Token)** samt Gate-Umbau `HA_INTEGRATION_AVAILABLE` (der riskanteste Teil, 30 Guard-Stellen — Stand 2026-08-13) und der Rest aus P2 (Wissensbasis über den Initial-Umfang hinaus, Takt-Check für Bestands-Zuordnungen). In der Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) als **Datenquellen-Ausbau** geführt.
>
> **Historie:** alles, was unten mit ✅ steht, ist mit v4.0.0 ausgeliefert und wird nicht mehr fortgeschrieben.


## Maßnahmen-Register (fortschreibbar — Stand 2026-07-28)

| Paket | Inhalt | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **P1 — MQTT-Fundament** | B1 Broker-Block · B2 Feld-Fläche · B3 `#`-Discovery+Suche · B5 Feld→eine-Quelle · B7 Block-Layout · B8 Migration (MQTT-Seite) | ✅ **ausgeliefert mit v4.0.0** (`51c81f29`) | `components/live/{MqttBrokerForm,DatenquellenZuordnung,DatenquellenGatewayPicker}.tsx` — alle mit SoT-Kommentar auf dieses Doc |
| **P2 — HA in die Fläche** | HA-Sensor als Quelle · B6 (#343-Assistenz) · Präferenz §2d · B8 HA-first | ✅ **ausgeliefert mit v4.0.0** (`d5c4d768`, Assistenz-Detail im archivierten [`KONZEPT-DATENQUELLEN-P2`](drafts/archive/flip-v4/KONZEPT-DATENQUELLEN-P2.md)) | `components/live/{DatenquellenHaPicker,HaVerbindungForm}.tsx` |
| **P3 — Remote-HA (LL-Token)** | B4 HA-Verbindungs-Block · **Gate-Umbau `HA_INTEGRATION_AVAILABLE`** (Supervisor **oder** Remote) · Remote-Verfügbarkeit + FS-Degradation · untertägige Recovery | ⬜ **offen — der riskanteste Teil** | Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) („Datenquellen-Ausbau"). Betrifft das Gate + ~20 Guard-Stellen (`config.py:24`, `main.py:100-107,456-468`) |
| **Rest aus P2** | Wissensbasis über den Initial-Umfang hinaus (evcc + 4 Wallbox-Integrationen) · Takt-Check für **Bestands**-Zuordnungen als Daten-Checker-Kategorie | ⬜ offen | kuratiert/laufend bzw. P3-Kandidat |

> **Warum dieses Dokument liegen bleibt:** vier Produktiv-Komponenten führen es als SoT im
> Datei-Kopf. Es beschreibt für P1/P2 den **gebauten** Zustand und für P3 den **beschlossenen,
> noch nicht gebauten** — beides muss lesbar bleiben.
>
> **Beobachtung aus dem Feld (Backlog):** Datenquellen-Felder ohne Zuordnung brauchen nach dem
> Update einmal manuell „keine"; bei Häufung eine Mini-Normalisierung erwägen.

---

> **Status: ✅ ABGENOMMEN (Gernot 2026-07-13) v0.4 — Vorgabe für die Umsetzung.** Bau slice-/paketweise (§5), P1+P2 ausgeliefert, P3 offen.
> Auslöser: In Runde 18 wurden MQTT-Inbound/-Gateway auf einen Wizard umgestellt; die umgesetzte Form entsprach nicht Gernots Vorstellung. Konzept gemeinsam erarbeitet (v0.1→v0.4), inkl. Kritik-Runde.
> **Name:** „Datenquellen" statt „Livequellen" — „Live" ist in eedc ein Feld-*Typ* (Live-Felder W/%/°C vs. Energie-Felder kWh); der Begriff wäre doppeldeutig. Das Konzept regelt, **welche Quelle den Wert eines eedc-Feldes liefert** (Live- wie Energie-Feld).
> **Prinzip:** kein Redesign der Berechnung — Aggregation/Snapshots bleiben; **Konfigurations-Struktur + UX** vereinheitlichen, **Merge-Reihenfolge** anpassen (§2d) ([[feedback_ist_anzeigen_nur_aendern_wo_noetig]], [[feedback_bestehende_mechanik_nutzen_nicht_erfinden]], [[feedback_a5_analytische_sichten_konzept_zuerst]]).
> **Heimat nach Abnahme:** offen — vermutlich eigener Abschnitt bei Forms→V4 ([[KONZEPT-FORMULARE-V4]]) + Style-Guide-Verweis. Gehört in die IA-V4-Linie (Einstellungen → Integration).

**Änderungslog:** v0.1→v0.2 (2026-07-13): Rename; Quellen-Priorität kontextabhängig (§2d, Gernot); Fähigkeits-Matrix Quelle × Achse (§2c); untertägige Recovery vs. historischer Backfill getrennt (§2e); WebSocket/LTS aus dem Scope genommen.
· v0.2→v0.3 (2026-07-13): **genau eine Quelle pro Feld** (F5, §2d) statt Runtime-Merge; **F2b strikt eine Quelle, kein Fallback**; F1/F3 (kein Flip-Gating, Bau jetzt — §5 Bau-Pakete); F4 eigener `#`-Scan + Presets; F6 #343 integrieren; **§2g Integration-Blöcke neu strukturiert** (B7). Alle offenen Punkte geklärt.
· v0.3→v0.4 (2026-07-13): Kritik-Runde 1–8 eingearbeitet: **B8 Migration** HA-first (§2h); **Remote-HA-fähiges Design ab P1** (§2a, Punkt 2); **kein stiller Quellen-Wechsel + Ausfall sichtbar** (§2d, Punkt 3); Riemann/Stunden-Form als *Ableitung* geklärt (§2c, Punkt 4); **„keine Zuordnung" gültige Wahl** → Monatsabschluss manuell/Vorjahr/Durchschnitt (§2d/§2b, Punkt 5); **Wächter benannt** (§7, Punkt 6); Discovery-Symmetrie HA↔MQTT (§2b, Punkt 7); Gateway summiert nicht — verifiziert `mqtt_gateway_service.py:231` (Punkt 8).

---

## 0. Getroffene Weichenstellungen (Gernot, 2026-07-13)

Fundament dieses Entwurfs:

1. **Voll vereinheitlichen:** heutige Trennung Inbound-Wizard ↔ Gateway-Wizard auflösen → **eine feld-zentrische Zuordnungs-Fläche**, Quelle pro eedc-Feld wählbar.
2. **Quellen-Priorität ist kontextabhängig** (nicht „immer beide erzwingen", nicht „hart sperren"):
   - **HA-App (Supervisor-Token):** besteht eine HA-Sensor-Zuordnung (aus beliebiger HA-Integration), hat **HA Vorrang** bei der Zuordnung; MQTT deckt Felder **ohne** HA-Sensor. **Kein** Laufzeit-Fallback pro Feld (F2b, §2d).
   - **Standalone + Remote-HA (LL-Token):** HA-Sensor **gleichberechtigt** zur MQTT-Topic-Zuordnung (pro Feld wählbar).
   - **Standalone ohne HA:** nur MQTT.
   Präzisiert [[feedback_ha_mqtt_parallel]] („parallel" = Funktionsgleichheit, verfügbarkeits-/kontextgesteuert).
3. **Neuer Baustein — Remote-HA per Long-Lived-Token:** eedc-Standalone soll sich an eine entfernte HA-Installation anbinden können. Analog MQTT-Broker braucht es einen **HA-Verbindungs-Block**. Damit wird HA im Standalone überhaupt erst wählbar.
4. **Topic-Discovery (Broker-`#`-Scan mit Suche)** wird eigener Baustein (existiert heute nicht).

---

## 1. Inventur (Ist-Stand)

### 1a. MQTT — heute zwei getrennte Mechanismen

| | Inbound | Gateway |
|---|---|---|
| **Modell** | *Du* publishst auf eedc-vorgegebene Topics (Push) | eedc abonniert *deine* Fremd-Topics + rechnet um (Translate) |
| **Feld-Zuordnung** | **implizit** über Topic-Namensschema `eedc/{anlage}_{slug}/energy\|live/inv/{id}_{slug}/{feld}` — **keine** Topic→Feld-Tabelle | **explizit** persistente Mapping-Datensätze |
| **Datenmodell** | Settings-Key `mqtt_inbound` (nur Broker-Config) | Tabelle `mqtt_gateway_mappings` (quell_topic, ziel_key, payload_typ, json_pfad, faktor/offset/invert, preset_id …) |
| **Discovery** | — | **nur Einzel-Topic-Test** (`POST /mqtt/gateway/test-topic`) + statische Geräte-Presets. **Kein** Wildcard-`#`-Scan |

- Wizard: `eedc/frontend/src/pages/MqttInboundSetup.tsx` · Gateway-UI: `eedc/frontend/src/components/live/MqttGateway.tsx`.
- Broker-Config: `eedc/backend/api/routes/live_mqtt_inbound.py` (Key `mqtt_inbound`; Quelle `env`|`db`, DB-Vorrang, Passwort maskiert).
- Presets: `eedc/backend/services/mqtt_presets.py` (Geräte-Templates, **nicht** aus dem Broker gelesen).
- Topic-Registry (SoT erwarteter Inbound-Topics): `eedc/backend/services/mqtt_topic_registry.py::build_expected_topics()`.
- Einbindung: Katalog `integration`, `id: 'mqtt-inbound'` (`einstellungenKatalog.tsx:545`).

### 1b. HA — heute rein Supervisor-/Add-on-gebunden

- **State/Live-Werte:** REST via `httpx` gegen `http://supervisor/core/api` (`config.py:74`, **hartkodiert**) mit `SUPERVISOR_TOKEN` (`config.py:60`). Service: `ha_state_service.py` (`is_available = bool(token)`), REST-generisch (`/states`, `/history/period`).
- **Kurzzeit-History:** REST `/api/history/period` — Recorder-Fenster (Default `purge_keep_days: 10`).
- **LTS/Statistik:** direkter SQLite-Zugriff `/config/home-assistant_v2.db` ODER remote via `ha_recorder_db_url` (`config.py:71`). REST kennt **keine** Statistik.
- **HA-Energy-Vorschläge:** Dateisystem `/config/.storage/core.energy` — add-on-only.
- **Untertägige Recovery:** Self-Healing der Snapshot-Jobs (Restart-Recovery verpasster :05/:55-Slots, v3.23.0) — holt heutige Stunden aus HA-History nach.
- **Gate:** `HA_INTEGRATION_AVAILABLE = bool(SUPERVISOR_TOKEN)` (`config.py:24`). Im Standalone werden **alle 5 HA-Routen nicht registriert** (`main.py:100-107, 456-468`) + ~20 Guard-Stellen.
- **sensor_mapping** (JSON-Spalte `anlage.sensor_mapping:95`): `{ basis:{…,live,live_invert}, investitionen:{<id>:{felder,live,live_invert}}, solcast_config }`, Strategie `sensor`|`keine`. **Verbindungs-unabhängig** — bleibt unverändert.
- **Entity-Discovery:** `GET /api/sensor-mapping/{id}/available-sensors`. Wizard: `SensorMappingWizard.tsx`. Setup-Panel `HAConnectionStep.tsx` = reine Anzeige, **keine** URL/Token-Eingabe.
  > ⚠ **IST-Aufnahme von vor dem Umbau.** Beides gibt es nicht mehr: der Wizard ist mit dem
  > IA-V4-Flip gefallen, der Endpunkt am 2026-08-13 stillgelegt (N-241). Heutige
  > Entity-Discovery: `GET /api/datenquellen/{id}/ha/sensoren`.

### 1c. HA ↔ MQTT heute: Merge mit **MQTT**-Vorrang

`live_power_service.py`: pro Feld gewinnt **MQTT**, wenn Wert da (`basis_values.update(mqtt_basis)`), sonst HA; beides auch je allein. Manche Felder haben bewusst **kein** MQTT-Topic (nur HA/manuell, z. B. `ladung_netz_kwh`). ⚠️ Diese Reihenfolge widerspricht Weichenstellung 0.2 (HA-App → HA-Vorrang) → Umbau nötig (§2d).

### 1d. Feld-Registry (gemeinsamer SoT)

`eedc/backend/core/field_definitions.py`: `BASIS_FELDER`, `INVESTITION_FELDER` (Energy je Typ), `LIVE_FELDER_INV` + `BASIS_LIVE_FELDER` (Live), je `label`/`einheit`/`hinweis`. Frontend: `lib/fieldDefinitions.ts`.

### 1e. Vorbild-Muster: MonatsdatenForm (V4, seit 2026-07-12)

- **Datengetriebene Feldliste** aus Registry + Backend-Status; Sichtbarkeit über Anschaffungs-/Stilllegungsfenster.
- **Ein `FeldStatus` pro Feld** treibt Badge + Placeholder + Abweichungs-Zeile — ein Kanal.
- **Gelesener Wert NICHT im Feldtitel**, sondern in der **Assistenz-Zone** (`AssistenzFeld.tsx`): Badge „gemessen/geschätzt (Quelle)" + Placeholder „Vorschlag: …" + „Sensor meldet X · gespeichert Y" mit InlineAktion. Vokabular-SoT: `ErfassungZustandBadge.tsx`.
- **Verschachtelte einklappbare Sektionen** (`FormSection`, `ebene="typ"|"geraet"`) mit Rollup-Badge; Kopf-Ampel + Abschluss-Review als Rahmen.
- SoT: `ui/{Input,Select,Textarea,Button,Alert,FormSection}`, `InlineAktion`, `ErfassungZustandBadge`; Logik `lib/erfassungZustand.ts`.

### 1f. Einstellungen-V4-Struktur (Ziel-Umgebung)

`v4/EinstellungenV4.tsx` + Registry `config/einstellungenKatalog.tsx`; Kategorien `stammdaten · komponenten · infothek · daten · integration · system`.
- **Integration** enthält: `sensor-mapping`, `ha-statistik-import`, `ha-export`, `import-buendel`, `mqtt-inbound`.
- Block-Anatomie: `BlockShell` (Kopf + Controls, lazy render) über `Block`-Objekt. Leichte Config = `FormBlock`; schwere Assistenz = Wizard-Overlay.

---

## 2. Zielbild

### 2a. Zwei Verbindungs-Blöcke (Integration) — „Verbindung" getrennt von „was darüber fließt"

| Block | Inhalt | Baustein |
|---|---|---|
| **MQTT-Broker-Verbindung** | Host/Port/User/Passwort/enabled + „Verbindung testen" + Status. **Ein** Broker für Inbound, Gateway UND Export. | `FormBlock`; Config existiert (`mqtt_inbound`) — nur UI herauslösen |
| **HA-Verbindung** | HA-App: lokaler Supervisor (automatisch). **Standalone: Basis-URL + Long-Lived-Token** + „Testen" (`GET {url}/api/`) + Status. | **NEU** — B4 |

**Design-Prinzip (Punkt 2 — „Remote-HA kommt!"):** Fläche + Quell-Picker werden **von Anfang an Remote-HA-fähig** entworfen. HA-Sensor ist eine Quell-Option, deren *Verfügbarkeit* der HA-Verbindungs-Block liefert (Supervisor **oder** Remote-Token) — **kein** „HA nur wenn Supervisor"-Kurzschluss in P1/P2. P3 schaltet später nur die Remote-*Verbindung* frei, ohne die Fläche umzubauen.

### 2b. Eine feld-zentrische Zuordnungs-Fläche (analog MonatsdatenForm)

Pro eedc-Feld (Energie + ggf. Live) eine Zeile: neutrales Label, gelesener Wert + **aktive Quelle** im **Badge/Assistenz-Zone** (nicht im Titel). Je Feld ist **genau eine Quelle aktiv** (§2d); „Quelle wechseln" öffnet den Picker:
1. **HA-Sensor** (wenn HA verfügbar) — Auswahl aus Entity-Discovery (Relevanz-Filter + Suche, wie heute) + #343-Assistenz (§2f).
2. **MQTT-Gateway** (Broker-Topic) — Auswahl aus `#`-Discovery mit **Suche** (B3) + Transform, ggf. Preset.
3. **MQTT-Inbound** — kanonisches Standard-Topic aus `build_expected_topics()`.
4. **keine Quelle / manuell** — kein Sensor/Topic zugeordnet (`strategie: 'keine'`); Folge im Monatsabschluss s. §2d.

Gruppierung in einklappbaren `FormSection` (Anlage-Basis, dann je Investitionstyp/Gerät) mit Rollup-Badge.

**Bändigung „unendlich vieler" Quellen (Punkt 7):** HA-Sensoren **und** MQTT-Topics werden gleich behandelt — **Relevanz-Filter** (HA: device_class/unit/state_class; MQTT: retained/energie-nahe Topics) + **Suche** + **#343-Vorschläge** pro Investitionstyp zum Eingrenzen. Der `#`-Scan zusätzlich zeit-/größenbegrenzt (B3). Symmetrie zu HA, kein Sonderweg.

**Kein Mehr-Quellen-auf-ein-Feld (Punkt 8, verifiziert):** Das Gateway re-published pro Mapping nach `eedc/{anlage}/{ziel_key}` und **überschreibt** (last-write-wins, `mqtt_gateway_service.py:231`) — es summiert nicht. Mehrere Geräte auf ein eedc-Feld gibt es also nicht; das ist über mehrere Investitionen zu modellieren. „Eine Quelle pro Feld" kollidiert mit nichts Bestehendem.

### 2b1. Seitengestaltung der Zuordnungs-Fläche (Detail — ✅ Gernot-Weichen 2026-07-14)

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

**Feld-Tabelle je Gerät, 3 Abschnitte nach `einheit`** (SoT `field_definitions.py`, nicht `kategorie`):
| Abschnitt | Regel | Beispiele |
|---|---|---|
| Energie-Sensoren (kWh) | `einheit == 'kWh'` | Einspeisung, Ladung, Heizwärme |
| Leistung-Sensoren (W) | `einheit == 'W'` | leistung_w, pv_gesamt_w |
| Sonstige Sensoren | Rest | soc (%), Temp (°C), km, €, Ladevorgänge |

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

Kernaussage (Gernot): HA (beide) kann heutige Stunden **rückwirkend** liefern, MQTT nicht. Für den *Live-Wert* ist Remote-HA ≈ MQTT; auf der *Recovery-Achse* ist HA (beide) reicher als MQTT. Grenze: rückwirkend nur so weit, wie der Sensor Werte führt ([[feedback_ha_lts_keine_zeitmaschine]]).

**Klarstellung (Punkt 4):** Die letzte Zeile ist **Granularität/Ableitung innerhalb der *einen* zugeordneten Quelle** — die Stunden-*Form* aus dem Live-Leistungssensor holen, während *Menge/Summe* beim Energie-Zähler bleibt (LTS-treu, v3.45.5). Das ist **kein** Wechsel der Werte-Quelle und **kein** Widerspruch zur „eine Quelle pro Feld"-Regel (§2d). Riemann ist derselbe Fall (W→kWh innerhalb der Quelle), nicht ein Cross-Source-Fallback.

### 2d. Genau **eine** aktive Quelle pro Feld (F5) — mit Präferenz-Reihenfolge

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

**F2b entschieden (Gernot):** **strikt eine Quelle, kein Laufzeit-Fallback.** Fällt die zugeordnete Quelle aus → Feld-Lücke, die die untertägige Recovery (§2c) später schließt (bei HA-Quelle); keine Prioritätskette, kein „Notstopfen". Die Präferenz-Reihenfolge oben gilt nur für **Default/Vorschlag** bei der Zuordnung, nicht als Laufzeit-Kette.

**Kein stiller Quellen-Wechsel + Ausfall sichtbar (Punkt 3):** Wählt der Nutzer HA (oder MQTT-Gateway), **bleibt** es dabei — bei Ausfall wird **nicht** stillschweigend auf MQTT umgeschaltet. Der **Ausfall der zugeordneten Quelle wird sichtbar dokumentiert** (Badge „Quelle liefert nicht" + Daten-Checker-Eintrag), nicht verschluckt ([[feedback_silent_except_logs]], [[feedback_daten_checker_kein_akzeptiert]]).

**„Keine Zuordnung" ist eine gültige Wahl (Punkt 5):** Ein Feld darf bewusst *ohne* Sensor-/Topic-Quelle bleiben (`strategie: 'keine'`). Folge im **Monatsabschluss**: **keine Sensorwerte angeboten** → Feld wird **manuell** erfasst bzw. über die bestehenden Vorschläge **Durchschnitt / Vorjahresmonat** (`FeldStatus.vorschlaege`, MonatsdatenForm-Mechanik §1e) gefüllt. Das ist der heutige `strategie: 'keine'`-Pfad, in der Fläche jetzt explizit wählbar.

### 2e. Abgrenzung: laufende Werte vs. historischer Backfill

Dieses Konzept regelt **laufende/aktuelle Werte** (Live + aktueller Monat) **und untertägige Recovery** (heutiger Tag). **Echter historischer Backfill** (vergangene Tage/Monate) bleibt die **bestehende** Reparatur-Werkbank / HA-Statistik-Import — nicht Teil der Feld-Quellen-Zuordnung. Damit fällt die HA-LTS-/WebSocket-Frage aus dem Scope (relevant nur dort, remote via `ha_recorder_db_url`).

### 2f. Zuordnungs-Assistenz #343 in die Fläche integrieren (F6)

Die Sensor-Zuordnungs-Assistenz aus [[project_sensor_zuordnungs_assistenz]] (#343) wird **Teil dieser Fläche**, nicht getrennt:
- **Integration-Dropdown pro Investitionstyp** (kuratierte Wissensbasis Integration × Typ × Feld → Entity-Muster + Hinweis) als **Vorschlag** beim HA-Sensor-Picker — installierte Integrationen nur „gefunden" markieren, Auswahl trifft immer der Nutzer, Eintrag „Manuell" bleibt.
- **Takt-Check bei kWh-Zähler-Auswahl** (`statistics_short_term`, Treppenstufen-Muster) als Warnung im Assistenz-Zonen-Stil (analog Einheiten-Warnung).

Beides greift genau beim Quell-Picker (§2b, Punkt 1) — deshalb hier integriert statt separat. Timing #343 („nach IA-V4-Rollout") wird damit an dieses Konzept gekoppelt.

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

### 2h. Migration bestehender Zuordnungen (B8, Punkt 1)

Bestehende Boxen haben `sensor_mapping` (HA), `mqtt_gateway_mappings`, `mqtt_inbound`. Überführung in „eine Quelle pro Feld" nach **HA-first** (Gernots gelebte Empfehlung; Doppelzuordnungen sind absolute Ausnahme):
- Besteht für ein Feld eine **HA-Sensor-Zuordnung** → **HA** wird die Quelle; ein etwaiges paralleles MQTT-Mapping wird **deaktiviert (nicht gelöscht)** — verlustfrei rückholbar.
- Feld ohne HA-Sensor: bestehendes **Gateway-Mapping** → Quelle „MQTT-Gateway"; sonst „MQTT-Inbound", falls Standard-Topic bespielt wird; sonst „keine".
- Migration **additiv + einmalig** ([[feedback_vollbackfill_nur_additiv]]), **kein** blockierender Start-Job / HTTP ([[feedback_migration_startup_kein_http]]); Korrektheit per Transform-Test, nicht per Dauer-Wächter (§7).

### 2i. Zuordnungs-Validierung (Slice C+D — ✅ Gernot-Weichen 2026-07-16)

> **REFRAME (Gernot-Frage „weitere Daten-Checker-Probleme aus falscher Zuordnung?"):** Der Daten-Checker prüft **config-basierte Zuordnungsfehler bereits** — u. a. `SENSOR_MAPPING_EINHEIT` (= D!), `SENSOR_MAPPING_LTS`, `EmobChecks`-Doppelmapping (#314). Daher **wiederverwenden statt neu bauen** ([[feedback_bestehende_mechanik_nutzen_nicht_erfinden]], kein Drift): die **config-basierten** (zur Zuordnungszeit erkennbaren) Checks proaktiv **feld-bezogen** in der Fläche zeigen; **daten-basierte** (retrospektiv: `PV_UEBER_ERFASSUNG`-Plausibilität, `DATENQUELLE_DRIFT/STATUS`, `PROVENANCE_CONFLICT`, `BATTERIE_VORZEICHEN_HISTORIE`) bleiben im Daten-Checker.

**Umfang (Gernot 2026-07-16, alle 4):** je Feld in `/felder` eine Liste `probleme: [{art, schwere, text, aktion?}]`, im Frontend amber/rot + ggf. Inline-Aktion.
1. **Einheiten-Mismatch (D)** — **Reuse** `SENSOR_MAPPING_EINHEIT`: Dimensions-Klassifikator `_klasse` (W/kW/MW=power, kWh…=energy) + `get_sensor_units`. Mismatch (kWh-Sensor in W-Feld, #200) = ERROR. Nur HA-Felder. **Klassifikator in gemeinsamen Helfer heben** (Checker + Fläche eine Quelle).
2. **Aggregat-Redundanz (C)** — **NEU** (config, proaktiv; ergänzt das daten-basierte `PV_UEBER_ERFASSUNG`). Paare: `basis_*_pv_gesamt` ⊥ per-WR `inv_*_pv_erzeugung_kwh`/`inv_*_leistung_w`; `basis_live_netz_kombi_w` ⊥ `einspeisung_w`+`netzbezug_w`. Aggregat + ≥1 Komponente belegt → Aggregat wirkungslos (Engine-Vorrang, s. u.). Inline **„auf keine"**.
3. **Kein `state_class` / LTS** — **Reuse** `SENSOR_MAPPING_LTS`: zugeordneter HA-Sensor ohne `state_class` → keine History/Zeitmaschine ([[feedback_ha_lts_keine_zeitmaschine]]). Braucht `state_class` je Entity (get_sensor_units liefert nur Unit → um `state_class` erweitern oder zweiter Batch).
4. **Sensor-Doppelmapping** — dieselbe HA-`entity_id` in ≥2 Feldern der `quellen`-Map → Doppelzählung (#314). Config-Scan der Fläche-Zuordnungen; zeigt beide betroffenen Felder.

Alle rein **diagnostisch** (nie blockierend, §2d), backend-berechnet (SoT/testbar), amber im Frontend; C zusätzlich Inline-„auf keine". HA-Picker warnt bei Einheit/`state_class` schon beim Wählen. **Engine-Vorrang-Befund für C** (kein Doppelzählungs-Bug, nur Sichtbarkeit):

**C-Detail — Redundanz/Konflikt (Aggregat vs. Komponenten).** Befund aus der Engine-Inventur: „PV gesamt UND einzeln" ist **kein Doppelzählungs-Bug** — die Engine nutzt durchgängig **Vorrang/Fallback**: der Aggregat-Sensor wird bei vorhandenen Komponenten **still ignoriert** (`live_komponenten_builder:261` `not has_individual_pv`; `live_history:341`; `verbrauchsprofil:227`; Energie-Bilanz: `pv_gesamt_kwh` ohne Snapshot-Counterpart; `netz_kombi_w` nur wenn Split fehlt in `_collect_values`). Problem ist also **Sichtbarkeit**, nicht Rechnung: der Nutzer sieht nicht, dass seine gesamt-Zuordnung wirkungslos ist.
- **Aggregat-Paare** (Backend-Konstante, erweiterbar): (1) `basis_*_pv_gesamt` (W+kWh) ⊥ per-WR `inv_*_pv_erzeugung_kwh`/`inv_*_leistung_w` (pv-module/balkonkraftwerk); (2) `basis_live_netz_kombi_w` ⊥ `basis_live_einspeisung_w`+`basis_live_netzbezug_w`.
- **Regel:** Aggregat belegt **und** ≥1 Komponente belegt (Quelle ≠ keine) → Aggregat `redundant`. `/felder` liefert pro Feld `redundant: {grund, wirksame_felder}`.
- **Frontend (Gernot-Weiche „Warnung + Inline-auf-keine"):** dezenter amber Redundanz-Hinweis an der Aggregat-Zeile + Inline-Aktion **„auf keine setzen"**. **KEIN** Auto-keine (stille Fremd-Änderung vermieden, [[feedback_reparatur_statt_loesch_features]]).
- **„optional erkennbar" ↔ frühere Weiche „keine optional/Pflicht-Kennzeichnung" (Schritt A/Q2):** bewusst als **kontextueller Redundanz-Marker** gelöst (nur im Konflikt-Zustand Aggregat+Komponente), NICHT als statisches optional/Pflicht-Flag je Feld → alte Entscheidung bleibt intakt.

**D — Einheiten-Prüfung pro Zuordnung (HA-only).** [[feedback_sensor_einheit_check]] (kW≠kWh, #200). **Dimensions-basiert**, nicht String-genau (eedc normalisiert kW→W): W-Feld↔power (W/kW/MW), kWh-Feld↔energy (Wh/kWh/MWh), dazu %/°C/km … Mismatch = **andere Dimension** (kWh-Sensor in W-Feld).
- **Nur HA:** HA-Sensor trägt `unit_of_measurement` (im `/ha/sensoren` schon vorhanden). Inbound/Gateway = eedc-Topic/nackte Zahl ohne Einheit-Metadatum → nicht prüfbar.
- **Zwei Stellen (Gernot-Weiche):** (1) **HA-Picker** — Warnung beim Wählen (Picker hat die Units); (2) **persistent `/felder`** `einheit_warnung: {sensor_einheit, feld_einheit}` an HA-Feldern → dafür muss der HA-Batch in `/felder` neben dem Wert auch die Unit holen.
- **Warnung, keine Sperre:** ungewöhnliche-aber-gültige/fehlende Units nicht blockieren.

Beide per pytest-Regel-Tabellen abgesichert (Dimension-Klassifikator; Aggregat-Redundanz-Resolver).

---

## 3. Bausteine (Was existiert / Was neu ist)

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

### 3a. B4 — was Remote-HA konkret braucht (aus Inventur)

1. **Konfig-Quelle:** URL + Token als User-Eingabe → Settings-Key (à la `mqtt_inbound`).
2. **`config.py` entkoppeln:** `ha_api_url` + Token dynamisch statt hartkodiert/Supervisor-Env; `HAStateService.__init__` nicht mehr fix.
3. **Gate umbauen:** `HA_INTEGRATION_AVAILABLE` + Router-Registrierung (`main.py:100-107, 456-468`) + ~20 Guard-Stellen von „`SUPERVISOR_TOKEN` existiert" auf „HA konfiguriert (Supervisor **oder** Remote)". ⚠️ Größter/riskantester Teil.
4. **Filesystem-Features degradieren:** HA-Energy-Vorschläge (`/config/.storage/core.energy`) remote nicht da → „nicht verfügbar". LTS-Backfill remote nur via `ha_recorder_db_url` (außerhalb Scope, §2e).
5. **Sicherheit:** benutzerdefinierte URL → SSRF-Guards (vgl. `test_connector_ssrf_block.py`), SSL/CORS.
6. **Wiederverwendbar:** `HAStateService` (REST `/states` + `/history/period`) trägt Live-Wert **und** untertägige Recovery gegen jede Base-URL+Bearer — kein WebSocket. `sensor_mapping`-Modell bleibt.

---

## 4. Entscheidungen (alle offenen Punkte geklärt)

Keine offene Rückfrage mehr — Konzept bereit für Vorgabe-Abnahme ([[feedback_fundament_pakete_vollstaendig]]).

- ~~F2b (Fallback)~~ → **strikt eine Quelle, kein Laufzeit-Fallback** (§2d); Ausfall → Lücke, Recovery schließt sie.
- ~~F1/F3 (Scope + Timing)~~ → **kein Flip-Gating, Bau jetzt**; Paket-Schnitt §5 (Gernot delegiert Schnitt an Claude). Guest-Rebuild erst „wenn alles rund" ([[feedback_ia_v4_deploy_kein_release]]).
- ~~F4 (Discovery)~~ → **eigener `#`-Scan**, Presets ergänzend.
- ~~F5 (Exklusivität)~~ → **genau eine Quelle pro Feld** (§2d), Präferenz HA-Sensor > MQTT-Gateway > MQTT-Inbound > manuell.
- ~~F6 (#343)~~ → **integrieren** (§2f), B6.
- ~~Blöcke Einstellungen→Integration~~ → **neu strukturiert** (§2g), B7.
- ~~F2 (Priorität)~~ → §2d. ~~Name~~ → „Datenquellen". ~~WS/LTS remote~~ → aus Scope (§2e).

**Kritik-Runde (v0.4):**
- ~~Migration fehlt~~ → **B8 HA-first** (§2h).
- ~~Remote-HA berücksichtigen~~ → **Fläche ab P1 Remote-HA-fähig** (§2a), P3 nur Verbindung.
- ~~Stiller Wechsel~~ → **kein stiller Wechsel; Ausfall sichtbar** (§2d).
- ~~Riemann-Widerspruch~~ → **Ableitung ≠ Fallback** geklärt (§2c).
- ~~„keine Zuordnung"~~ → **gültige Wahl** → Monatsabschluss manuell/Vorjahr/Durchschnitt (§2d/§2b).
- ~~Wächter unklar~~ → **benannt** (§7): Auflösungs-Grep + Resolver-Unit-Test.
- ~~Discovery-Firehose~~ → **Filter+Suche+#343 wie HA-Sensoren** (§2b).
- ~~Gateway summiert?~~ → **nein, last-write-wins** verifiziert (§2b).

---

## 5. Bau-Pakete (Dev-Box-Reihenfolge; kein Flip-Gating)

Alles wird **jetzt** gebaut (nicht nach dem IA-V4-Flip). Reihenfolge nach Risiko/Eigenständigkeit; Deploy-Disziplin: Dev-Box iterativ → Freigabe/PN → Guest-Rebuild erst wenn rund.

| Paket | Inhalt | Warum in dieser Reihe |
|---|---|---|
| **P1 — MQTT-Fundament** | B1 (Broker-Block) · B2 (Feld-Fläche, MQTT-Quellen) · B3 (`#`-Discovery+Suche) · B5 (Feld→eine-Quelle, MQTT-Seite) · B7 (Block-Layout §2g) · B8 (Migration MQTT-Seite) | eigenständig, kein HA-Gate-Risiko, liefert die neue Fläche früh; Fläche **Remote-HA-fähig** entworfen (§2a) |
| **P2 — HA in die Fläche (HA-App)** | HA-Sensor als Quelle in P1-Fläche · B6 (#343-Assistenz) · Präferenz §2d (HA-App) · B8 (HA-first-Auflösung) | baut auf P1-Fläche auf; nutzt bestehendes Supervisor-Gate (kein Umbau) |
| **P3 — Remote-HA (LL-Token)** | B4 (HA-Verbindungs-Block, URL+Token) · Gate-Umbau `HA_INTEGRATION_AVAILABLE` (Supervisor **oder** Remote) · Remote-Verfügbarkeit + FS-Degradation | riskantester Teil (Gate + ~20 Guards) zuletzt, wenn Fläche + HA-Quelle stehen |

> B5 (F2b: strikt eine Quelle, kein Fallback) wird in P1 (MQTT-Seite) grundgelegt und in P2 um die HA-Quelle erweitert. B7 (Block-Layout §2g) läuft über P1+P2 mit (Verbindungs-Blöcke in P1/P3, Datenquellen-Fläche P1/P2).

---

## 6. Bezug zu Regeln / Memory

- [[feedback_ha_mqtt_parallel]] — hier **präzisiert**: parallel = Funktionsgleichheit, kontext-/verfügbarkeitsgesteuert (§2d).
- [[feedback_ha_only_features_gate]] — B4 verändert genau dieses Gate; breit + sorgfältig.
- [[feedback_ha_lts_keine_zeitmaschine]] — rückwirkend nur so weit wie Sensor-Historie.
- [[feedback_ha_statistics_aggregation]] — LTS-Backfill (separater Pfad, §2e) = MAX(sum)-MIN(sum)/Tag.
- [[feedback_neue_felder_pflicht]] — bei neuen Feldern: Migration + Response + field_definitions.
- [[feedback_ia_v4_deploy_kein_release]] — Umsetzung: Dev-Box → Freigabe/PN → Guest-Deploy.
- [[feedback_fundament_pakete_vollstaendig]] — dieser Entwurf = Inventur-Teil; Bau erst nach Vorgabe-Abnahme.
- [[feedback_migration_startup_kein_http]] / [[feedback_vollbackfill_nur_additiv]] — B8-Migration additiv, nicht-blockierend.
- SoT-Trennung: UI = Style-Guide + SoT-Komponenten · Merge/Aggregation = bestehende Engine (ADR-001).

---

## 7. Wächter (nach Umbau) — was prüfbar ist (Punkt 6)

Ehrlich abgegrenzt ([[feedback_verifiziert_nur_was_check_abdeckt]], [[feedback_keine_regel_behaupten_ohne_code_beleg]]): nicht alles ist statisch greppbar. Realistisch tragen:

- **`check:datenquellen-aufloesung` (statischer Grep-Wächter):** Die alten Wizards (`MqttInboundSetup`, `MqttGateway`, `SensorMappingWizard`) dürfen nach dem Umbau nur noch aus der neuen Fläche referenziert werden → Import-Sites außerhalb = **0** (Muster wie `check:parkbar` / `check:form-controls`). Greift gegen Wiederauftauchen der alten Flächen.
- **Resolver-Unit-Test (Gate an der Summenzeile, [[feedback_gate_summenzeile_verifizieren]], [[feedback_aggregator_symmetrie]]):** Der Feld→Quelle-Resolver liefert **genau eine** aktive Quelle pro Feld; Symmetrie-Test über die drei Kontexte (HA-App / Remote / Standalone). Die Invariante „ein Feld liest nie aus zwei Quellen" ist **nur so** prüfbar, **nicht** per Grep — ehrlich benannt.
- **`npm run check:design`** bleibt Pflicht für die neue Fläche (Regel 0a, keine Inline-Hex).

**Nicht als Dauer-Wächter verkleidet:** Die Migrations-Korrektheit (§2h) ist ein einmaliger Datentransform → per **Transform-Test** abgesichert, nicht per laufendem Check.
