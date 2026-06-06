# Konzept: Wallbox / E-Auto — Datenarchitektur

> **✅ Update 2026-06-06 (Koordinator-Abgleich):** Phase 1 + **Phase 2a komplett RELEASED in v3.36.0** (kanonische Heimladungs-Quelle, Migration, Read-/Write-Kanonisierung). Phase 2b/3 (Vehicle-Sensor-Mapping, Multi-Fahrzeug) Trigger weiter **nicht** erfüllt → geparkt. **Einzig offen:** die zwei Live-Check-Fehlalarme aus Abschnitt »Bekannte Schwächen« (A: `verbrauch_kwh`-Legacy-Fallback in `get_eauto_ladung_kwh`; B: Zähler-Abdeckungs-Check verlangt E-Auto-Zähler trotz Wallbox-Deckung) — beide im Code v3.37.1 noch präsent. Tier 1 in `docs/drafts/UEBERBLICK-20260606.md`, Memory [[project_wallbox_eauto_konzept]].

> **Status (2026-05-20): Phase 1 (Pool-Konsolidierung) vollständig.** Der ursprüngliche Quick-Fix (v3.25.11: getrennte Akkumulatoren EAuto/WB + **Max-pro-Feld**, siehe Memory `project_pool_fix_emob.md`) hat sich selbst als Drift-Quelle erwiesen: feldweises `max()` über `gesamt`/`pv`/`netz` als drei unabhängige Aufrufe konnte die Felder aus verschiedenen Quellen mischen und einen PV-Anteil > 100 % erzeugen (#262 junky84: Komponenten zeigte 48 % PV + 85 % Netz = 133 %). v3.31.6 ersetzt das Max-pro-Feld durch den SoT-Helper `aggregiere_emob_ladung` (`eedc/backend/services/eauto_wirtschaftlichkeit.py`): die Quelle mit der größeren Heimladung gewinnt die **komplette, in sich konsistente Trias** (`pv + netz == ladung` garantiert). **Alle fünf Read-Sites sprechen jetzt dieselbe Pool-Logik:** Wallbox-Dashboard, Komponenten-Zeitreihe, Cockpit-Übersicht und AktuellerMonat über `aggregiere_emob_ladung`, das E-Auto-Dashboard über `compute_emob_pool_attribution` + `attribute_emob_pool_by_km` (km-anteilige Verteilung, selbe use-wb-pool-Entscheidung). **Phase 2 (Vehicle-Sensor-Mapping) und Phase 3 (Multi-Fahrzeug-Dashboard) noch nicht angefangen** — in Roadmap [#110](https://github.com/supernova1963/eedc-homeassistant/issues/110) als „Ideen / Konzeptphase"-Item; Trigger-Stand siehe Abschnitt »Phase-2-Trigger«.
>
> **Update 2026-06-02:** **Phase 2a (kanonische Quelle) ist jetzt mit getroffenen Entscheidungen ausspezifiziert** — siehe Abschnitt »Phase 2a — Umsetzungsplan«. Das ist der beschlossene strukturelle Ausweg aus dem Read-seitigen Heuristik-Flickwerk (zuletzt #262 als 5. Read-Site). Die zwei Daten-Checker-Warnungen, die das Konzept als Brücke vorsah, sind **bereits live** (`_check_emob_pool_pflege` + `_check_sensor_mapping_lts`, `services/daten_checker.py`). **Single Source of Truth für dieses Thema ist dieses Dokument** — keine verstreuten Folgenotizen mehr.
>
> **Update 2026-06-03 (Trigger-Signal für Phase 2a):** Eine #314-Untersuchung (Energiefluss-Mitte) deckte zwei vorbestehende Asymmetrien derselben Pool-Klasse auf, beide jetzt als Brücke entschärft — **aber sie ersetzen Phase 2a nicht**:
> - **Live-Dedup gehärtet** (`live_komponenten_builder.py`, Commit `38ebcc4e`): geteilte `leistung_w`-Entity (Wallbox+E-Auto) wird jetzt deterministisch nach Wallbox-Priorität dedupliziert (vorher dict-reihenfolge-abhängig, analog Tagesverlauf #318); `summe_verbrauch` schließt E-Autos nur noch aus, wenn eine Wallbox existiert (E-Auto ohne Wallbox/Schuko zählt sonst korrekt mit — 086cf70f-Prinzip wiederhergestellt).
> - **Dritte Daten-Checker-Warnung live** (`_check_emob_sensor_doppelmapping`, Commit `688efef2`): gleiche Sensor-Entity (live ODER kWh-Zähler) an Wallbox **und** E-Auto gemappt → WARNING. Deterministisch aus `sensor_mapping`, deckt alle Aggregations-Konsumenten inkl. Reparatur-Werkbank ab (gemeinsamer `investition_hourly_eintraege`-Pfad seit #298).
>
> **Verbleibende Lücke, die NUR Phase 2a schließt:** Wallbox + E-Auto mit **getrennten** Sensoren, **unverlinkt** (`parent_investition_id` nicht gesetzt) → die Aggregation zählt die Ladung doppelt (der Live-Pfad poolt heuristisch per Round-Robin-`parent_key`, die Aggregation nur per Link — divergente Heuristiken). Das ist genau der strukturelle Fall, den die kanonische-Quelle-Regel (Entscheidung 1) deterministisch auflöst. **→ Diese Untersuchung + der wiederkehrende evcc-Pool-Churn erfüllen den dokumentierten Re-Evaluierungs-Trigger; Phase 2a als eigene Session terminieren (Maintainer-Go).**

## Motivation

Die Feldzuordnung zwischen Wallbox und E-Auto ist **mehrdeutig**: `ladung_kwh`/`ladung_pv_kwh`/`ladung_netz_kwh` können auf beiden Investitionstypen liegen, und das Wallbox-Dashboard aggregiert sie über einen Pool, der raten muss, welche Quelle die Wahrheit ist. Diese Mehrdeutigkeit ist die eigentliche Schuld, die das Konzept abträgt — nicht (nur) ein fehlendes Multi-Fahrzeug-Feature.

**Auch das 1-Wallbox-+-1-E-Auto-Setup bricht** — entgegen einer früheren Annahme dieses Konzepts: #260 (NongJoWo) und #262 (junky84) sind beide 1+1-Setups, in denen der Pool inkonsistente Werte lieferte (PV-Anteil > 100 %). Die Mehrdeutigkeit wird in komplexeren Szenarien nur *sichtbarer*:

- Privatauto + Firmenwagen an derselben Wallbox (steuerlich trennbar)
- Mehrere Wallboxen (Garage + Carport)
- Gast-Ladungen ohne zugeordnetes E-Auto
- RFID-basierte Zuordnung (evcc, SMA eCharger, Wattpilot)

## Kernprinzip: Jeder speichert was er misst

### Wallbox = Infrastruktur (misst den Stromfluss)

```
verbrauch_daten:
  ladung_kwh          ← Zählerstand-Differenz (Gesamt am Ladepunkt)
  ladung_pv_kwh       ← davon PV (evcc/Sensor)
  ladung_netz_kwh     ← davon Netz (evcc/Sensor oder abgeleitet)
  ladevorgaenge       ← Zähler (alle Sessions am Ladepunkt)
```

### E-Auto = Fahrzeug (misst Nutzung + eigene Heimladung)

```
verbrauch_daten:
  km_gefahren          ← Tacho
  verbrauch_kwh        ← Gesamtverbrauch
  ladung_heim_kwh      ← Heimladung dieses Autos (NEU, per Vehicle-Sensor)
  ladung_heim_pv_kwh   ← davon PV (NEU, per Vehicle-Sensor)
  ladung_extern_kwh    ← Fremdladung
  ladung_extern_euro   ← Fremdladung Kosten
  v2h_entladung_kwh    ← Vehicle-to-Home
```

### Zuordnung über Sensor-Mapping, nicht über DB-Modell

Die RFID-Intelligenz bleibt bei evcc/Wallbox. EEDC konsumiert die
bereits aufgeschlüsselten Daten über die passenden Sensor-Topics:

```
Wallbox "Garage" (Loadpoint-Perspektive):
├── ladung_kwh      → evcc/loadpoints/1/chargeTotalImport
├── ladung_pv_kwh   → evcc/loadpoints/1/pvCharged
└── ladevorgaenge   → evcc/loadpoints/1/sessions

E-Auto "BMW i4" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/BMW/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/BMW/pvCharged
└── ladevorgaenge      → evcc/vehicles/BMW/sessions

E-Auto "Firmenwagen" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/Firma/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/Firma/pvCharged
└── ladevorgaenge      → evcc/vehicles/Firma/sessions
```

## Zwei Perspektiven, gleiche Realität

evcc liefert dieselben kWh aus zwei Blickwinkeln:

```
PRO LOADPOINT (= Wallbox)               PRO VEHICLE (= E-Auto)
evcc/loadpoints/1/pvCharged → 732 kWh   evcc/vehicles/BMW/pvCharged   → 520 kWh
                                         evcc/vehicles/Firma/pvCharged → 212 kWh
                                                                        ─────────
                                                                  Σ     732 kWh ✓
```

### Konsistenzregel

| Prüfung | Formel |
|---------|--------|
| Wallbox-Gesamt ≥ Σ E-Autos Heim | `WB.ladung_kwh ≥ Σ EAuto.ladung_heim_kwh` |
| PV-Gesamt ≥ Σ PV pro Auto | `WB.ladung_pv_kwh ≥ Σ EAuto.ladung_heim_pv_kwh` |

`≥` statt `=` weil Gast-Ladungen keinem E-Auto zugeordnet sein können.

## Dashboard-Darstellung (Ziel)

### Wallbox-Dashboard

```
SMA eCharger 22 (11 kW) · 34 Monate Daten
┌────────────────┬───────────────┬───────────────────┬──────────────┐
│ Heimladung     │ PV-Anteil     │ Ersparnis vs. Ext │ Ladevorgänge │
│ 1.200 kWh      │ 61%           │ -583 €            │ 48           │
└────────────────┴───────────────┴───────────────────┴──────────────┘
Aufschlüsselung (wenn Vehicle-Sensoren vorhanden):
  BMW i4:       880 kWh (59% PV) · 35 Vorgänge
  Firmenwagen:  320 kWh (66% PV) · 13 Vorgänge
```

### E-Auto-Dashboard

```
BMW i4
┌────────────┬──────────────┬──────────────┬──────────────┐
│ km         │ Heimladung   │ Extern       │ vs. Benzin   │
│ 12.400     │ 880 kWh      │ 340 kWh/170€ │ +1.240 €     │
└────────────┴──────────────┴──────────────┴──────────────┘
```

## Abgrenzung: Was NICHT Teil dieses Konzepts ist

- **RFID-Karten als eigene Entität** — Zuordnung bleibt bei evcc
- **Externe Ladekarten** (EnBW, ADAC etc.) — separates Thema, aktuell `ladung_extern_*` am E-Auto
- **Session-Level-Tracking** — EEDC bleibt bei Monatsaggregaten
- **Wallbox↔E-Auto Zuordnungs-UI** — nicht nötig, Sensor-Mapping reicht

## Migrationspfad

### Phase 1: Bug-Fix (jetzt)
- Ladevorgänge aus Wallbox-Monatsdaten lesen (nicht nur E-Auto)
- Kein Datenmodell-Umbau nötig

### Phase 2a: Feldzuordnung geradeziehen (Schulden-getrieben)
> **Ausspezifiziert 2026-06-02 mit getroffenen Entscheidungen → siehe Abschnitt »Phase 2a — Umsetzungsplan« weiter unten.**
- Eindeutige Feld-Rollen: die Heimladungs-Trias (`ladung_kwh`/`pv`/`netz`) gehört kanonisch an die **Wallbox** (Infrastruktur misst den Stromfluss), das E-Auto trägt Nutzung + km. Read-Sites lesen die kanonische Quelle statt eines Pools.
- Migration des bestehenden `verbrauch_daten`-JSON nötig — Daten-Reconnaissance vorher (siehe Daten-Checker-Warnung unten).
- **Trigger: bereits gefeuert.** Der wiederkehrende evcc-Pool-Patch-Bedarf (#260, #262, ~8 Fix-Commits seit v3.31.0) ist das Symptom der Mehrdeutigkeit; jeder Read-seitige Heuristik-Fix (zuletzt `aggregiere_emob_ladung`) ist nur ein Aufschub. Profitiert auch das 1+1-Setup.

### Phase 2b: Vehicle-Sensor-Mapping (Feature-getrieben)
- `ladung_heim_kwh` und `ladung_heim_pv_kwh` als neue E-Auto-Felder
- Sensor-Mapping erweitern für evcc Vehicle-Topics
- Wallbox-Dashboard liest eigene Daten, E-Auto die Vehicle-Sicht
- Bestehende `ladung_pv_kwh`/`ladung_netz_kwh` am E-Auto bleiben als Fallback
- **Trigger: „wenn Vehicle-Sensoren nachgefragt werden"** — hier stimmt die ursprünglich notierte Bedingung (Power-User mit Per-Vehicle-Aufschlüsselung). Bislang nicht erfüllt.

**Daten-Checker-Warnung bei Pool-Pflege-Mismatch (✅ implementiert + live, `_check_emob_pool_pflege`):** wenn EAuto + WB beide gepflegt sind und die Werte erkennbar ähnlich (≈ derselbe Stromfluss aus zwei Perspektiven) bzw. beide Felder voll sind aber `WB.ladung_pv_kwh > Σ EAuto.ladung_heim_pv_kwh` ist, INFO/WARNING ausgeben — lenkt den User auf eine bewusste Entscheidung, welche Quelle die Wahrheit liefert. Hintergrund: 2026-05-02 fielen bei Joachim und Gernot inkonsistente Pool-Werte auf (PV-Anteil > 100 %, doppelter `kWh/100km`); der Quick-Fix in v3.25.x machte Max-pro-Feld-Auswahl, was sich selbst als Drift-Quelle erwies und in v3.31.6 durch den Gewinner-Pool `aggregiere_emob_ladung` ersetzt wurde. Die Phase-2-Trennung beseitigt die Doppelzählung strukturell, der Daten-Checker bleibt für Altbestand und Pool-Mode. **Diese Warnung braucht kein neues Datenmodell und ist als eigenständiges Stück vor Phase 2 ziehbar** (siehe »Phase-2-Trigger«: junky84 #262 hatte ~3.300 kWh Streudaten auf der E-Auto-Investition, die der Daten-Checker proaktiv sichtbar gemacht hätte).

### Phase 3: Aufschlüsselung im Wallbox-Dashboard (optional)
- Wenn E-Autos Vehicle-Sensoren haben, kann das Wallbox-Dashboard
  die Gesamt-kWh pro Fahrzeug aufschlüsseln
- Konsistenzprüfung WB-Gesamt vs. Σ E-Autos

### Kein Breaking Change
- Nutzer ohne evcc/RFID merken nichts — manuelle Eingabe funktioniert weiter
- 1:1-Setups (eine WB, ein Auto) bleiben identisch
- Pool-Aggregation bleibt Fallback wenn keine Vehicle-Sensoren gemappt sind

## Phase-2-Trigger — Stand 2026-05-20

Der dokumentierte Phase-2-Trigger lautet »wenn Vehicle-Sensoren nachgefragt werden«. Per-Vehicle-/Multi-Fahrzeug-Bedarf ist bislang **nicht** aufgetreten — junky84 (#262) und NongJoWo (#260) fahren beide 1 Wallbox + 1 E-Auto.

Ein *anderes* Signal wird aber deutlich: der **evcc-Portal-Import erzeugt seit v3.31.0 anhaltenden Patch-Bedarf** — #262 (vier Fix-Runden), #260 (zwei Runden), EVCC-Parser DE/EN, insgesamt ~8 emob-Fix-Commits in zwei Wochen. Ursache ist strukturell: evcc schreibt die Heimladung architektonisch an die **Wallbox** (`data_import.py`), während Read-Seite und Datenmodell historisch E-Auto-zentriert sind (siehe »Motivation«). Jeder Fix legt eine weitere Heuristik auf den Pool. Der `aggregiere_emob_ladung`-Gewinner-Pool aus v3.31.6 ist die bestmögliche Heuristik, bleibt aber eine Heuristik — er wählt die falsche Quelle, wenn verirrte Streudaten die echte Quelle übertreffen (bei junky84 lagen ~3.300 kWh Streudaten auf der E-Auto-Investition; die Wallbox gewann nur, weil ihre Heimladung noch größer war).

**Bewertung:**

- **Phase 2 (neue Felder `ladung_heim_*` + Vehicle-Sensor-Mapping)** — der dokumentierte Trigger ist noch nicht erfüllt (kein Multi-Vehicle-Bedarf), aber das evcc-Import-Churn-Signal nähert sich dem Punkt, an dem die strukturelle Lösung günstiger ist als die nächste Heuristik-Runde. Maintainer-Entscheidung; bei der nächsten evcc-Pool-Meldung neu bewerten.
- **Ohne Phase 2 vorziehbar:** die oben verortete »Daten-Checker-Warnung bei Pool-Pflege-Mismatch« braucht kein geändertes Datenmodell. Sie hätte junky84s Streudaten proaktiv sichtbar gemacht und ist ein kleines, eigenständiges Stück.

## Phase 2a — Umsetzungsplan (Entscheidungen 2026-06-02)

> Beschlossener struktureller Ausweg aus dem Read-seitigen Heuristik-Flickwerk. **Eigene Umsetzungs-Session** — echtes Release mit Daten-Migration, kein Read-Pfad-Hotfix (Tester-Zyklus, Pre-Release-Daten-Checker-Scan, DB-Backup-Hinweis).

### Leitprinzip
Die **datenabhängige** Laufzeit-Heuristik (`use_wb_pool` = „größere Heimladung gewinnt", kippt bei Streudaten) wird durch eine **strukturelle, deterministische** Quellen-Regel ersetzt. Die km-anteilige *Attribution* (`attribute_emob_pool_by_km`, `attribute_month_share`) bleibt unverändert — nur das *Raten der Quelle* fällt weg.

### Getroffene Entscheidungen
1. **Fallback ja.** Nutzer **ohne** Wallbox-Investition (inkl. **Steckerlader**/Schuko — sehr häufig!) behalten die E-Auto-Trias als kanonische Quelle. Kein Breaking Change. Regel: *Wallbox-Investition vorhanden + hat Heimladung → Wallbox ist Quelle; sonst → E-Auto.* Strukturell (existiert eine Wallbox?), nicht magnitudenabhängig → kippt nicht.
2. **Migration löst automatisch auf, „höherer Wert gewinnt".** Wo historisch BEIDE Seiten Heimladung tragen, gewinnt pro aktivem Monat der **höhere** Heimladungs-Wert als überlebender kanonischer Wert (in die Wallbox geschrieben, E-Auto-Trias geräumt). Nur Fälle, die diese Regel **nicht** sauber auflösen kann (z. B. Total auf der einen, PV-Split nur auf der anderen Seite → keine konsistente Trias bildbar), bleiben stehen und tauchen im Daten-Checker (`_check_emob_pool_pflege`) auf. Ziel: möglichst wenig manuelle Fälle, kein „großer Heiler-Knopf" für das Unauflösbare.
3. **Nur aktive Monate.** Migration und Auflösung respektieren Anschaffungs-/Stilllegungsdatum (konsistent mit der Aktiv-Filter-Invariante).
4. **Multi-Wallbox:** Liegen mehrere Wallboxen vor, ist jede ein eigener Ladepunkt (Garage + Carport); die Heimladung gesamt = **Summe aller Wallbox-IMD** (entschieden 2026-06-04, physikalisch korrekt, keine Unterzählung). „Größtes Ladevolumen" greift damit nur als Wallbox-vs-E-Auto-Quellenwahl, nicht als Auswahl *einer* Wallbox; für den 0/1-Wallbox-Fall ist das identisch.

### Etappen (Reihenfolge wichtig)
1. ✅ **Kanonischer Read-Helper** `get_emob_heimladung_canonical(...)` in `services/eauto_wirtschaftlichkeit.py` (additiv, strukturelle Regel aus Entscheidung 1; intern via `_summiere_emob_quelle` → `get_emob_pv_netz_kwh`, Trias-Garantie `pv+netz==ladung`). **Erledigt 2026-06-04** (UNRELEASED) + Unit-Test `tests/test_emob_heimladung_canonical.py` (8 Fälle, inkl. Kern-Divergenz zur Magnitude-Heuristik und Steckerlader-Fallback). Noch nicht an Read-Sites verdrahtet (= Etappe 2).
2. ✅ **7 Read-Sites umgestellt** mit **Pflicht-Symmetrie-Test**. **Erledigt 2026-06-04 (UNRELEASED).** Umsetzung:
   - **Klasse A** (`aggregiere_emob_ladung` → `get_emob_heimladung_canonical`): Wallbox-Dashboard (`dashboards.py:1032`), `cockpit/uebersicht.py`, `cockpit/komponenten.py`, `aktueller_monat.py` (Anlage-KPI).
   - **Klasse B** (`compute_emob_pool_attribution.use_wb_pool` von Magnitude → **strukturell** `wb-Heimladung > 0`, km-Attribution unverändert): E-Auto-Dashboard (`dashboards.py:194`), `aktueller_monat.py` (T-Konto `:1364`).
   - **Klasse C** (rohe Summe → kanonisch): `jahresbericht.py` (Doppelzählung E-Auto+Wallbox behoben); `ha_export.py` (Aggregat-Ersparnis + per-Device-E-Auto-Sensoren ziehen jetzt den km-anteiligen Wallbox-Pool via neuem `_EmobPoolCtx`).
   - **Tests:** `test_emob_readsite_symmetrie.py` (Helfer-Kontrakt-Matrix + Cross-Endpoint Wallbox/E-Auto/aktueller_monat = 500/300/200); evcc-Tests in `test_ha_export_multi_eauto.py`; 4 „Premium-Setup"-Tests an Phase-2a-Semantik angepasst (1× roh-dual→strukturell dokumentiert, 3× Post-Migration-Fixtures). **729 Backend-Tests grün.**
   - ⚠️ **Release-Kopplung:** Die strukturelle Read-Regel unterzählt *un-migrierte* Dual-Daten-Setups (nimmt den kleineren Wallbox-Wert). Korrekt erst nach Etappe-4-Migration (höherer Wert → Wallbox-Slot). **Etappe 2+3+4 müssen zusammen released werden** — Etappe 2 ist NICHT allein auslieferbar.
3. ✅ **Write-Side kanonisiert.** **Erledigt 2026-06-04 (UNRELEASED).**
   - **Manuelle Erfassung (monatsabschluss-Form):** neue `bedingung_anlage: "keine_wallbox"` an den E-Auto-Heim-Lade-Feldern `ladung_pv_kwh`/`ladung_netz_kwh` (`core/field_definitions.py`) — existiert eine Wallbox-Investition, blendet `get_felder_fuer_investition` diese Felder am E-Auto aus (analog `keine_pv_module`). Km/Verbrauch/Extern/V2H bleiben am E-Auto. Test `test_emob_write_canonical_felder.py`.
   - **Import-Pfade (geprüft — schon kanonisch):** `data_import.py` schreibt `wallbox_ladung_*` auf die Wallbox-Investition (`wb.id`), E-Auto bekommt nur `km_gefahren`; evcc-Parser schreibt ebenfalls an die Wallbox. Keine Änderung nötig.
   - **Bewusst unangetastet:** generischer CSV-/„alle Felder"-Import (`get_alle_felder_fuer_investition`) akzeptiert weiter alle E-Auto-Felder (Design: „Import nie stillschweigend ignorieren") — Konsolidierung übernimmt die Migration + Read-Layer.
   - Hinweis: `keine_wallbox` ist präsenz-basiert (nicht aktiv-monat-basiert), konsistent mit `keine_pv_module`. Stillgelegte Wallbox = Edge-Case, durch Migration/Read-Layer abgedeckt.
4. ✅ **Einmalige Daten-Migration** `services/migrations/migrate_emob_canonical_source.py`, registriert in `core/database.py:_run_data_migrations()` via `_apply_once` (Key `phase_2a_emob_canonical_source`, idempotent, Rollback bei Fehler). **Erledigt 2026-06-04 (UNRELEASED).** Pro Anlage mit genau 1 (nicht-dienstl.) Wallbox + ≥1 E-Auto, pro aktivem Monat mit E-Auto-Heimladung **und aktiver Wallbox**: höherer Heimladungs-Wert gewinnt → Trias in den Wallbox-Slot (IMD ggf. angelegt), E-Auto-Heim-Keys geräumt (km/Verbrauch/Extern/V2H bleiben). Unauflösbar (Gewinner ohne PV-Split, Verlierer mit PV → „Total vs. PV-Split") → stehenlassen (Daten-Checker). Multi-Wallbox → Anlage übersprungen. Vor-Wallbox-Monate (Schuko) bleiben beim E-Auto. Natürlich idempotent (nach 1. Lauf keine E-Auto-Heimladung mehr). Test `test_emob_canonical_migration.py` (9 Fälle). **742 Backend-Tests grün.**
   - **Release-Pflicht (Risiken-Sektion):** DB-Backup-Hinweis in den Release-Notes; Live-Gegencheck via ha-mcp an Gernots Anlage (hat den Pflege-Konflikt real).
5. ✅ **Laufzeit-Heuristik entfernt.** **Erledigt 2026-06-04 (UNRELEASED).** `aggregiere_emob_ladung` (Magnituden-Quellenwahl) ganz gelöscht — hatte nach Etappe 2 keine Produktiv-Aufrufer mehr. `compute_emob_pool_attribution.use_wb_pool` war bereits in Etappe 2 auf strukturell umgestellt; Pool-Helper (`build_wb_pool_by_month`, `attribute_*`) bleiben nur noch für die km-Attribution. Redundante Magnitude-Unit-Tests entfernt (Coverage liegt jetzt in `test_emob_heimladung_canonical.py` + `test_emob_readsite_symmetrie.py`), #262-Cross-View-Integrationstests behalten. Stale Kommentare/Docstrings in aktueller_monat/komponenten/uebersicht/daten_checker auf den kanonischen Helfer umgestellt. **736 Backend-Tests grün.**

---

**Phase 2a Etappen 1–5 alle ✅ — RELEASED in v3.36.0 (2026-06-04).** Live-Gegencheck an Gernots Anlage erfolgreich: Migration sauber gelaufen (13 Monate Trias→Wallbox, 2 nur geräumt, 15 unauflösbar→Daten-Checker, keine Fehler im Add-on-Log). Der Daten-Checker zeigt korrekt den neuen Pflege-Konflikt-Text + per `_check_emob_sensor_doppelmapping` die Wurzel: derselbe `evcc_pv_charged`-Sensor war an Wallbox **und** E-Auto gemappt. Nach Sensor-Mapping-Korrektur (Heimladung nur an der Wallbox) sind künftige Monate sauber.

### Risiken
DB-Backup-Hinweis vor der Migration; additiv + idempotent; Teil-Umstellung in Schritt 2 nur mit dem Symmetrie-Test absichern (sonst stille Drift); Steckerlader-/Manuell-Nutzer ohne Wallbox müssen unangetastet bleiben. Live-Gegencheck via ha-mcp an Gernots Anlage (hat den Pflege-Konflikt real).

### Phase 2b/3 bleiben getrennt
Vehicle-Sensor-Mapping (`ladung_heim_*`) + Multi-Fahrzeug-Aufschlüsselung — Trigger „Multi-Vehicle-Bedarf" weiter **nicht** erfüllt. Nicht Teil von 2a.

## Offene Fragen

1. Liefern SMA eCharger und Wattpilot ähnliche Per-Vehicle-Topics wie evcc?
2. Gibt es EEDC-Nutzer mit Multi-WB/Multi-E-Auto-Setup? (Joachim-xo prüfen)
3. Braucht das Monatsabschluss-Formular ein geändertes Layout für die neuen Felder?

## Bekannte Schwächen — Phase-2a-Fehlalarme bei Wallbox+E-Auto (Live-Check 2026-06-04)

> **✅ Behoben (Tier-1-Quick-Win, im Bündel, noch nicht released):** Beide Fehlalarme A+B sind gefixt.
> A — `_check_emob_pool_pflege` liest die E-Auto-Heimladung jetzt nur aus dem
> expliziten `ladung_kwh` (kein `verbrauch_kwh`-Fahrverbrauch-Fallback mehr).
> B — `_check_energieprofil_abdeckung` überspringt den E-Auto-kWh-Zähler-Bedarf,
> wenn eine aktive Wallbox mit gemapptem `ladung_kwh`-Zähler die Ladeenergie
> deckt. Tests: `test_daten_checker_wallbox_schwaeche_ab.py`. Die folgenden
> Abschnitte dokumentieren den Befund (historisch).

### A) `verbrauch_kwh` überladen → False-Positive-Pflege-Konflikt

**Symptom:** Bei einer Anlage mit Wallbox (= kanonische Quelle) **und** einem
E-Auto, das sein Feld „Verbrauch (kWh)" (Fahrverbrauch, für kWh/100 km) pflegt,
feuert der Daten-Checker `_check_emob_pool_pflege` einen **falschen** Pflege-
Konflikt — und der kanonische Helfer zählt das E-Auto als „Heimladung tragend".

**Ursache:** `get_eauto_ladung_kwh(data)` = `ladung_kwh or verbrauch_kwh`. Der
`verbrauch_kwh`-Zweig ist ein **Legacy-Fallback** für Alt-E-Auto-Daten, in denen
die Heimladung historisch in `verbrauch_kwh` lag (vor den `ladung_pv/netz`-
Feldern). Heute ist `verbrauch_kwh` am E-Auto aber der **Fahrverbrauch** — das
Feld ist also doppelt belegt (Fahrverbrauch ∧ Legacy-Heimladung). Hat das E-Auto
kein `ladung_kwh`, wird sein Fahrverbrauch als Heimladung gelesen.

**Wirkung:** Anzeige bleibt korrekt (die Wallbox gewinnt strukturell), aber der
Pflege-Konflikt-Hinweis ist ein False Positive. Anlass: Gernots Smart #1 —
deshalb steht „Verbrauch" dort jetzt bewusst auf Manuell/leer (kWh/100 km
entfällt). Real auch: evcc liefert für viele Fahrzeuge ohnehin keinen echten
kumulativen Fahr-Verbrauchszähler (nur Lade-Energie + Momentan-Durchschnitt in W).

**Kandidat-Fix (Variante offen → eher eigenes Issue, [[feedback_issue_vs_memory]]):**
Den `verbrauch_kwh`→Heimladung-Fallback nur greifen lassen, wenn **keine
Wallbox** als kanonische Quelle existiert (bzw. im Pflege-Check die Heimladung
des E-Autos nur aus den expliziten `ladung_*`-Feldern bilden, nicht aus
`verbrauch_kwh`). Risiko: echte Legacy-Daten ohne `ladung_*` dürfen nicht
verloren gehen → sorgfältig abgrenzen. Post-Phase-2a, kein Release-Blocker.

### B) Zähler-Abdeckungs-Check verlangt E-Auto-Zähler trotz Wallbox-Deckung

**Symptom:** Räumt man (korrekt) alle Heimladungs-/Verbrauchs-Sensoren vom E-Auto
(weil die Wallbox die kanonische Quelle ist), meldet der Daten-Checker
»Energieprofil – Zähler-Abdeckung«: „Komponente ohne vollständige kWh-Zähler-
Abdeckung … Smart #1 (e-auto): verbrauch_kwh oder ladung_kwh".

**Ursache:** Der Abdeckungs-Check prüft jede Investition **einzeln** und weiß
nicht, dass die Lade-Energie des E-Autos bereits über den **Wallbox-Zähler**
(`ladung_kwh` → Energiefluss-Kategorie „ladung_wallbox") erfasst ist. Ein
zusätzlicher E-Auto-Zähler würde dieselbe Energie **doppelt zählen**.

**Wirkung:** Reiner Fehlalarm in der „Wallbox = Zähler, E-Auto = Fahrzeug"-
Topologie. Die E-Auto-Linie im Tages-Energieprofil/Heatmap bleibt leer (Energie
steckt korrekt in der Wallbox-Linie); Autarkie, Gesamtverbrauch und Monats-
Auswertungen sind unberührt. **Nicht** auf »Beheben« klicken — das würde Doppel-
zählung + Pflege-Konflikt zurückbringen.

**Kandidat-Fix:** Der Zähler-Abdeckungs-Check soll den kWh-Zähler-Bedarf eines
E-Autos **überspringen, wenn eine Wallbox mit kWh-Zähler** in derselben Anlage
existiert (analog zur strukturellen Quellen-Regel). Gleiche Issue-Familie wie A.
