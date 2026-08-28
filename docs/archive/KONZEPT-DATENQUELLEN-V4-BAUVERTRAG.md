# Bau-Vertrag — Datenquellen V4 (archiviert)

> ## **Historie, kein gültiges Dokument.** Hier stehen die **Ausgangslage vor dem Umbau**
> (Stand Juli 2026) und die **Bau-Reihenfolge**, in der P1–P3 gefahren wurden. Beides wurde am
> 2026-08-28 aus [`KONZEPT-DATENQUELLEN-V4.md`](../KONZEPT-DATENQUELLEN-V4.md) ausgelagert,
> als der Bau abgeschlossen war.
>
> ⚠ **Der „Ist-Stand" in §1 ist der Zustand VON DAMALS und heute in Teilen widerlegt** — HA war
> dort „rein Supervisor-gebunden" (P3 hat das aufgelöst) und MQTT hatte Vorrang vor HA (§2d hat
> das umgedreht). Wer wissen will, wie eedc Datenquellen **heute** auflöst, liest das
> [Lebend-Dokument](../KONZEPT-DATENQUELLEN-V4.md), nicht diese Seite.
>
> **Warum es überhaupt aufgehoben wird:** Es sagt, aus welchem Bau-Vertrag die Regeln dort
> stammen — Herkunftsbeleg, keine Voraussetzung (die Regel dazu steht in
> [`DEVELOPMENT.md`](../DEVELOPMENT.md), Abschnitt „Ein Dokument, das im Code als SoT zitiert
> wird, gehört nach `docs/`").

---

## Der Vertrag selbst (Kopf des Entwurfs v0.4)

> **Status: ✅ ABGENOMMEN (Gernot 2026-07-13) v0.4 — Vorgabe für die Umsetzung.** Bau slice-/paketweise (§5); P1, P2 und P3 sind ausgeliefert (28.08.).
> Auslöser: In Runde 18 wurden MQTT-Inbound/-Gateway auf einen Wizard umgestellt; die umgesetzte Form entsprach nicht Gernots Vorstellung. Konzept gemeinsam erarbeitet (v0.1→v0.4), inkl. Kritik-Runde.
> **Name:** „Datenquellen" statt „Livequellen" — „Live" ist in eedc ein Feld-*Typ* (Live-Felder W/%/°C vs. Energie-Felder kWh); der Begriff wäre doppeldeutig. Das Konzept regelt, **welche Quelle den Wert eines eedc-Feldes liefert** (Live- wie Energie-Feld).
> **Prinzip:** kein Redesign der Berechnung — Aggregation/Snapshots bleiben; **Konfigurations-Struktur + UX** vereinheitlichen, **Merge-Reihenfolge** anpassen (§2d) ([[feedback_ist_anzeigen_nur_aendern_wo_noetig]], [[feedback_bestehende_mechanik_nutzen_nicht_erfinden]], [[feedback_a5_analytische_sichten_konzept_zuerst]]).
> **Heimat nach Abnahme:** offen — vermutlich eigener Abschnitt bei Forms→V4 ([[KONZEPT-FORMULARE-V4]]) + Style-Guide-Verweis. Gehört in die IA-V4-Linie (Einstellungen → Integration).

**Änderungslog:** v0.1→v0.2 (2026-07-13): Rename; Quellen-Priorität kontextabhängig (§2d, Gernot); Fähigkeits-Matrix Quelle × Achse (§2c); untertägige Recovery vs. historischer Backfill getrennt (§2e); WebSocket/LTS aus dem Scope genommen.
· v0.2→v0.3 (2026-07-13): **genau eine Quelle pro Feld** (F5, §2d) statt Runtime-Merge; **F2b strikt eine Quelle, kein Fallback**; F1/F3 (kein Flip-Gating, Bau jetzt — §5 Bau-Pakete); F4 eigener `#`-Scan + Presets; F6 #343 integrieren; **§2g Integration-Blöcke neu strukturiert** (B7). Alle offenen Punkte geklärt.
· v0.3→v0.4 (2026-07-13): Kritik-Runde 1–8 eingearbeitet: **B8 Migration** HA-first (§2h); **Remote-HA-fähiges Design ab P1** (§2a, Punkt 2); **kein stiller Quellen-Wechsel + Ausfall sichtbar** (§2d, Punkt 3); Riemann/Stunden-Form als *Ableitung* geklärt (§2c, Punkt 4); **„keine Zuordnung" gültige Wahl** → Monatsabschluss manuell/Vorjahr/Durchschnitt (§2d/§2b, Punkt 5); **Wächter benannt** (§7, Punkt 6); Discovery-Symmetrie HA↔MQTT (§2b, Punkt 7); Gateway summiert nicht — verifiziert `mqtt_gateway_service.py:231` (Punkt 8).

---

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

---

## Entscheidungs-Log (Kritik-Runden v0.3/v0.4, Juli 2026)

Die Liste der Streitpunkte und wie sie ausgingen. Die **Ergebnisse** stehen im
[Lebend-Dokument](../KONZEPT-DATENQUELLEN-V4.md) als geltende Regeln — hier steht, dass
darüber verhandelt wurde und mit welchem Ausgang.

Alle hier aufgeführten Punkte sind entschieden **und gebaut**; sie stehen als Begründung, nicht als Vorhaben.

- ~~F2b (Fallback)~~ → **strikt eine Quelle, kein Laufzeit-Fallback** (§2d); Ausfall → Lücke, Recovery schließt sie.
- ~~F1/F3 (Scope + Timing)~~ → **kein Flip-Gating, Bau jetzt**; Paket-Schnitt §5 (Gernot delegiert Schnitt an Claude). Guest-Rebuild erst „wenn alles rund".
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
