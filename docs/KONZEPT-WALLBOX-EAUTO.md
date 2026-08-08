# Konzept: Wallbox / E-Auto — Datenarchitektur

> ## Stand 2026-08-08 — neu erhoben
>
> **Dieses Dokument stand bis heute auf dem Stand vom 29.06.2026** — also vor dem
> Oberflächen-Umbau v4.0.0 (25.07.). Erhoben wurde gegen den Code, nicht gegen die Historie;
> die Abschnitte darunter bleiben inhaltlich gültig, wo nichts anderes vermerkt ist.
> **Es trägt bewusst keine Versionsnummer, nur dieses Mess-Datum** (Muster aus #359).
>
> **Was sich seit dem 29.06. geändert hat und hier eingearbeitet ist:**
>
> - **Die Sichten heißen anders.** Seit v4.0.0 gibt es keine „Dashboards" mehr, sondern den
>   **Komponenten-Hub** je Gerätetyp (`frontend/src/v4/WallboxHubBloecke.tsx`,
>   `v4/EAutoHubBloecke.tsx`) und das **Cockpit** nach Zeitraum. Wo unten noch
>   „Wallbox-Dashboard" steht, ist die Wallbox-Fläche des Hubs gemeint; die Backend-Route
>   heißt weiterhin `api/routes/investitionen/dashboards.py`.
> - **Die Monatszeile wird einmal aufbereitet (ADR-002/P10).** Der kanonische Helfer wird
>   heute auch aus `services/monats_fakten.py:882` gerufen; die Read-Sites lesen die Zeile
>   von dort, statt `InvestitionMonatsdaten` selbst zu falten. Die Zeilenangaben in Etappe 2
>   sind entsprechend nachgezogen.
> - **Der Dienstwagen kostet, statt zu verdienen** (v4.0.5). `core/berechnungen/dienstliche_ladekosten.py`
>   ist eine eigene Layer-Formel und die vierte Stelle, an der E-Auto-Ladung in Geld
>   umgerechnet wird — sie war in diesem Konzept nicht vorgesehen. Aufrufer:
>   `cockpit/uebersicht.py:282` · `aussichten.py:1366` · `ha_export.py`.
> - **Die Achse-2-Lücke hat ein Issue:** **#356**. Ihr Trigger („gebündelt mit der nächsten
>   echten Wallbox/E-Auto-Arbeit") **tritt mit Phase 4 ein** — siehe dort.
> - **Neu aufgenommen: Phase 4 — PHEV-Anteile (#331)**, ausspezifiziert mit getroffenen
>   Entscheidungen. Das ist der erste Punkt dieser Domäne mit einem **wartenden Melder**
>   (Safi105, Discussion #330 vom 09.06.).
> - **Offen und ohne anderen Ort: N-141** — welcher der drei Wege den Wallbox-PV-Anteil
>   bestimmt. Wartet auf Maintainer-Entscheid, blockiert seither.
> - **Erledigt:** die im Kopf als „UNRELEASED" markierten Schwächen-Fixes A+B (`fa89255c`)
>   sind längst ausgeliefert; `aggregiere_emob_ladung` ist tatsächlich gelöscht (baumweit
>   ungekappt geprüft, 0 Treffer).

> **✅ Update 2026-06-06 (Koordinator-Abgleich):** Phase 1 + **Phase 2a komplett RELEASED in v3.36.0** (kanonische Heimladungs-Quelle, Migration, Read-/Write-Kanonisierung). Phase 2b/3 (Vehicle-Sensor-Mapping, Multi-Fahrzeug) Trigger weiter **nicht** erfüllt → geparkt. **Schwächen A+B ✅ behoben** (Tier-1-Bündel, Commit `fa89255c`; damals UNRELEASED, **inzwischen ausgeliefert**): A) `_check_emob_pool_pflege` bildet die E-Auto-Heimladung nur noch aus explizitem `ladung_kwh` (kein `verbrauch_kwh`-Fahrverbrauch-Fallback; `get_eauto_ladung_kwh` selbst unverändert für echte Legacy-Daten); B) E-Auto-kWh-Zähler-Bedarf wird übersprungen, wenn eine aktive Wallbox mit `ladung_kwh`-Sensor deckt. Damit ist dieses Konzept inhaltlich abgeschlossen (nur Phase 2b/3 trigger-gebunden offen). Memory [[project_wallbox_eauto_konzept]].

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

> ⚠ **2026-08-08: Die Sichten heißen seit v4.0.0 anders.** „Wallbox-Dashboard" ist heute die
> **Wallbox-Fläche des Komponenten-Hubs** (`frontend/src/v4/WallboxHubBloecke.tsx`),
> „E-Auto-Dashboard" die **E-Auto-Fläche** (`v4/EAutoHubBloecke.tsx`). Die Backend-Route heißt
> weiterhin `api/routes/investitionen/dashboards.py`. Die Skizzen darunter beschreiben den
> **Inhalt**, nicht das heutige Layout — wer sie umsetzt, tut das im Hub und nach Regel 0a.

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
   - ⚠ **Nachtrag 2026-08-08 — die Read-Site-Liste oben ist historisch, die Zeilennummern sind es
     auch.** Seit ADR-002/**P10** liest eine Read-Site die Monatszeile nicht mehr selbst; die
     Auflösung ist einmal in `services/monats_fakten.py` passiert. Baumweit gemessen (ungekappt,
     ohne `tests/`) rufen den kanonischen Helfer heute **vier** Stellen:
     `services/monats_fakten.py:882` (die Schicht) · `services/pdf/builders/jahresbericht.py:250` ·
     `api/routes/investitionen/dashboards.py:1311` · `api/routes/cockpit/uebersicht.py:244`.
     Die km-Attribution (`compute_emob_pool_attribution`) rufen `api/routes/aktueller_monat.py:740`
     (Vorjahr) und `:1893` sowie `api/routes/investitionen/dashboards.py:316`.
     **`cockpit/komponenten.py` steht nicht mehr darunter** — es liest `EmobFakten` (`:204`, `:206`,
     `:269`) statt selbst zu falten. Die Regel selbst ist unverändert; nur der Ort, an dem sie
     einmal angewandt wird, ist ein anderer.
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

## Offene Lücke 2026-06-29: Tages-Energieprofil-Leistungspfad nicht von Phase 2a erfasst (Achse-2-Magnitude-Drift)

> **Status: ENTDECKT + zu scopen (kein Code).** Aufgetaucht beim Live-Gegencheck der v3.45.9-Achse-2-Diagnose (`GET /api/energie-profil/{id}/achse2-drift`) an Gernots Anlage. SoT für die Weiterarbeit ist dieser Abschnitt + Memory [[project_achse2_magnitude_drift]].
>
> ⚠ **Nachtrag 2026-08-08: Dieser Abschnitt hat ein Issue — [#356](https://github.com/supernova1963/eedc-homeassistant/issues/356)** (seit 30.07., offen). Bis dahin stand die Lücke nur hier und im Memory; wer nur die Issue-Liste las, hat sie nicht gesehen. Die Linie dort ist dieselbe wie hier: **Diagnose zuerst, Korrektur alter Tage nur über den Reparatur-Knopf, nie als Start-Migration.**

### Befund (Daten, Gernots Anlage 1, v3.45.9)

Die Achse-2-Invariante (`pruefe_tep_komponenten_intern_konsistenz`) meldet für die Kategorie **„Wallbox+E-Auto"** eine **gegenläufige ~2×-Drift** zwischen den beiden gespeicherten Stunden-Repräsentationen:

| Tag | Zählerpfad (`wallbox_kw`-Spalte) | Leistungspfad (Σ `komponenten[wallbox_*]+[eauto_*]`) | Faktor |
|-----|----------------------------------|------------------------------------------------------|--------|
| 2026-06-22 | **+7,00** kWh | **−14,00** kWh | −2,00× |
| 2026-06-24 | **+3,00** kWh | **−6,43** kWh | −2,14× |

Setup: Wallbox (SMA eCharger, inv 2, `parent=None`) + E-Auto (Smart #1, inv 1, `parent=None`) — **getrennt, unverlinkt**. Genau die im Kopf dieses Dokuments (Update 2026-06-03) notierte „Verbleibende Lücke": *Wallbox + E-Auto mit getrennten Sensoren, unverlinkt → Live-/Aggregations-Pfad poolen mit divergenten Heuristiken.*

### Warum das eine eigene Lücke ist (Abgrenzung zu Phase 2a)

- **Phase 2a (v3.36.0)** kanonisierte die **Monats-Read-Sites** (Wallbox/E-Auto-Dashboard, Cockpit, jahresbericht, ha_export) + die einmalige Migration auf die strukturelle Regel „Wallbox vorhanden → Wallbox ist Quelle". Der **tägliche Energieprofil-/Tagesverlauf-Pfad** (die `komponenten`-JSON-**Leistungsserien** aus `live_tagesverlauf_service`/`live_komponenten_builder`, gespeichert in `TagesEnergieProfil.komponenten`) war **nicht** Teil davon.
- **Nicht heilbar durch Re-Aggregation:** 2026-06-22 wurde am 2026-06-29 manuell neu aggregiert → Drift **unverändert** (+7 / −14). Also **kein** Stale-Mapping-Artefakt, sondern laufendes Verhalten des Tages-Leistungspfads mit aktuellem Mapping.
- **Kein aktuelles Sensor-Doppelmapping:** `_check_emob_sensor_doppelmapping` ist auf der Anlage **grün** (Gernot hat `evcc_pv_charged` vom E-Auto entfernt; E-Auto trägt nur noch `km_gefahren`). Die Drift besteht **trotzdem** → sie kommt **nicht** aus einem doppelt gemappten Sensor, sondern aus der Pfad-internen Serien-Bildung.
- **Monats-Pool separat:** `_check_emob_pool_pflege` warnt weiterhin (Monats-Altdaten, EA = WB identisch in 01/2026, 12/2025, 08/2025) — das ist der **Monats**-Pflege-Konflikt, nicht die Tages-Drift.

### Diagnose-only — keine falschen Anzeige-Werte

Die **angezeigten** Werte (Kacheln, Bilanz, Charts, Tages-/Monats-Auswertung) stammen aus dem **Zählerpfad** (`*_kw`-Spalten / `komponenten_kwh` Boundary) und sind **korrekt** (+7). Nur das interne `komponenten`-JSON (Leistungspfad, butterfly-signiert) driftet. Symptom ist die dauerhafte Achse-2-Log-Warnung, jetzt auch im Diagnose-Endpoint sichtbar. Kein Anwender-sichtbarer Wert ist falsch.

### Noch zu klären vor einem Fix-Konzept (per-Key-Mechanismus)

Der Diagnose-Endpoint summiert die Kategorie (`summe_wallbox_eauto_kwh` = Σ `wallbox_*` + `eauto_*`), zeigt also **nicht**, welcher Key die −14 trägt. Zwei Hypothesen, verschiedene Fixes:

1. **Wallbox-Selbst-Verdopplung:** der Leistungspfad baut die Wallbox-Kurve aus **mehreren** Zählern (`ladung_kwh` **+** `ladung_pv_kwh`), obwohl `ladung_pv_kwh` eine **Teilmenge** ist (der Zählerpfad addiert in `komponenten_beitraege.py` bewusst nur `ladung_kwh`). Spräche für genau −2× bei Voll-PV-Ladung.
2. **Phantom-`eauto_1`-Serie:** der Leistungspfad erzeugt eine eigene E-Auto-Serie (Quelle noch unklar, da E-Auto keinen Lade-Sensor mehr hat) → echter Querschluss `wallbox_2` + `eauto_1`. Der Faktor **2,14×** am 06-24 (> 2×) passt eher hierzu als zur reinen PV-Teilmengen-Verdopplung.

**Auflösung (Scoping-Schritt, kein Fix):** entweder (a) gezielter Code-Read des Tages-Leistungspfads (`extract_live_config` / `baue_investitions_serien` / `live_komponenten_builder.py`: Serien-Quellen + Entity-Dedup) oder (b) den Diagnose-Endpoint um eine **Per-Key-Aufschlüsselung** erweitern und on-box messen.

### Vorgeschlagene Fix-Richtung (im Konzept-Rahmen, NICHT entschieden)

- **Strukturelle Quellen-Regel auf den Tages-Leistungspfad ausdehnen:** die in Phase 2a beschlossene Regel („Wallbox vorhanden + hat Heimladung → Wallbox ist Quelle; E-Auto trägt nur Nutzung") gilt bisher nur monatlich/read-seitig. Der Tages-Leistungspfad muss dieselbe Regel anwenden, statt heuristisch zu poolen — und `ladung_pv_kwh`/`ladung_netz_kwh` als **Teilmengen** behandeln (nie zusätzlich als Kurve aufaddieren), konsistent zu `komponenten_beitraege`.
- **Achse-2-Invariante für Senken-Vorzeichen normalisieren:** `summe_wallbox_eauto_kwh` (und die anderen Senken-Kategorien) vergleichen die **positive** `*_kw`-Spalte gegen das **negativ** butterfly-signierte JSON → systematischer Vorzeichen-Fehlalarm unabhängig vom Magnituden-Bug. Die Invariante sollte die Senken-Konvention kennen (Betrag/Seite normalisieren), sonst flaggt sie auch nach dem Magnitude-Fix weiter.
- **Leitplanke:** im abgenommenen Wallbox/E-Auto-Rahmen reparieren, Konzept nicht umwerfen ([[feedback_korrektur_nicht_konzept_umwerfen]]); strukturelle Regel statt neuer Heuristik ([[feedback_sonderfaelle_nicht_reflexhaft_codieren]]); falls ein Fix die Aggregation ändert, Alt-Tage **nur** über manuellen Daten-Checker-Knopf nachziehen, nie als Start-Migration ([[feedback_migration_startup_kein_http]]).

### Trigger / Priorität

Diagnose-only, niedrig-prioritär (keine falschen Anzeige-Werte). Sinnvoll **gebündelt** mit der nächsten echten Wallbox/E-Auto-Arbeit (gemeinsamer Test-/Migrations-Zyklus), nicht als isolierter Hotfix. Re-Evaluierung beim nächsten emob-Pool-Signal.

> ⚠ **2026-08-08: Dieser Trigger ist eingetreten.** **Phase 4 (#331)** *ist* die nächste echte
> Wallbox/E-Auto-Arbeit. Das heißt **nicht**, dass #356 mitgebaut werden muss — es heißt, dass der
> Scoping-Schritt (Per-Key-Aufschlüsselung des Diagnose-Endpunkts) im selben Zug **billig** ist,
> weil der Tages-Leistungspfad dann ohnehin aufgeschlagen ist. **Entscheid des Maintainers**, nicht
> automatisch Teil von Phase 4; ein stillschweigend mitgebautes zweites Thema wäre eine
> Auftragsausweitung.

---

## Phase 4 — PHEV: elektrischen und fossilen Anteil trennen (#331)

> **Status: GEBAUT 2026-08-08.** Ausspezifiziert am Vormittag desselben Tages, gebaut im
> Anschluss — alle neun Etappen, beide Achsen, Anzeige und Daten-Checker. Melder **Safi105**,
> [Discussion #330](https://github.com/supernova1963/eedc-homeassistant/discussions/330)
> vom 09.06.2026 — der erste Punkt dieser Domäne mit einem **wartenden Melder**.
> Issue: [#331](https://github.com/supernova1963/eedc-homeassistant/issues/331).
>
> ⚠ **Eine Präzisierung gegenüber der Spezifikation, gemessen statt angenommen:** Entscheidung 5
> sagt „die Strom-Kosten bleiben unberührt" und begründet das damit, dass eedc die geladene
> Energie ohnehin misst. Das gilt für die **IST**-Achse. Auf der **Prognose**-Achse leitet
> `berechne_eauto_einsparung` den Strombedarf aber aus der Fahrleistung ab
> (`km × verbrauch_kwh_100km / 100`) — dort *muss* der elektrische Anteil den Bedarf begrenzen,
> sonst zahlt ein Plug-in-Hybrid in der ROI-Prognose Strom für alle Kilometer **und** Benzin für
> die verbrennergefahrenen, also dieselbe Strecke zweimal. Gebaut ist deshalb:
> `Strom_Bedarf = km_elektrisch × verbrauch / 100`, Vergleichs-Benziner weiterhin über alle km.
>
> ⚠ **Zwei Etappen-Angaben trugen nicht** (am Code geprüft, statt sie abzuarbeiten): Etappe 1
> nennt „Response-Model" und `core/field_definitions.py`. Das Response-Model führt `parameter` als
> freies `dict[str, Any]` (`investitionen/crud.py`), es strippt nichts; und `field_definitions.py`
> ist die Registry der **Monatsdaten-** und Live-Felder, nicht der Investitions-Parameter — ein
> Eintrag dort wäre am falschen Ort. Die tatsächlichen Pflicht-Stellen für einen
> `parameter`-Schlüssel sind `core/investition_parameter.py` **und** sein Frontend-Spiegel
> `lib/investitionParameter.ts`; beide sind gepflegt.

### Das Problem

Die Fahrzeug-Investition unterstellt in Ersparnis **und** CO₂-Rechnung **100 % elektrisch
gefahrene Kilometer**. Für ein BEV ist das richtig; für einen Plug-in-Hybrid werden dadurch
**Ersparnis und CO₂-Bilanz zu gut** dargestellt — der Benzin-Anteil fällt unter den Tisch, und
zwar zweimal: er wird weder als Kosten noch als Emission gezählt, obwohl er real anfällt.

### ⚠ Zwei Rechenachsen, nicht eine

Der Issue-Text nennt `core/calculations.py` — das ist richtig, aber **nur die halbe Fläche**.
Gemessen am Code gibt es zwei voneinander unabhängige Pfade, und ein Anteil, der nur in einem
von beiden wirkt, erzeugt genau die Drift-Klasse, die dieses Projekt wiederholt getroffen hat
([[feedback_aggregations_drift]]):

| Achse | Ort | Rechnet mit | Wer liest sie |
| --- | --- | --- | --- |
| **IST** (Vergangenheit) | `services/eauto_wirtschaftlichkeit.py` | **gemessenen** `km_gefahren` + **tatsächlicher** Ladung + `vergleich_verbrauch_l_100km` | Komponenten-Hub, Cockpit, Monatsbericht, HA-Export, Aussichten-Historie, CO₂ |
| **Prognose/ROI** (Zukunft) | `core/calculations.py:310-364` (`berechne_eauto_einsparung`) | **geplanter** `jahresfahrleistung_km` × `verbrauch_kwh_100km` × `pv_ladeanteil_prozent` | ausschließlich `api/routes/investitionen/crud.py:1508` (ROI-Tabelle) |

Beide müssen den Anteil kennen — **aber sie bestimmen ihn verschieden**, weil die Zukunft keine
Messung hat. Das ist kein Sonderfall, sondern die schon bestehende Trennung des Systems.

### Getroffene Entscheidungen (2026-08-08)

**1. Der Anteil wird gemessen, nicht geschätzt — wo eine Messung existiert.**
Die elektrisch gefahrenen Kilometer folgen aus dem **elektrischen Fahrverbrauch** und dem
Fahrzeug-Kennwert:

```text
km_elektrisch  = min( km_gefahren ,  fahrverbrauch_kwh / verbrauch_kwh_100km × 100 )
km_verbrenner  = km_gefahren − km_elektrisch
```

Beide Eingangsgrößen **existieren heute**: `fahrverbrauch_kwh` ist das E-Auto-Feld `verbrauch_kwh`
(„der reine Fahrverbrauch, NICHT pro Fahrt und NICHT kWh/100 km", `core/field_definitions.py`),
`verbrauch_kwh_100km` ist ein gepflegter Parameter (`PARAM_E_AUTO`, Default 18). **Keine
Schema-Erweiterung für die Messung**, und keine Schätzung — das ist die Zusage aus #330.

> ⚠ **Das `min(…)` ist nicht kosmetisch.** Ist `verbrauch_kwh_100km` zu niedrig gepflegt oder der
> Fahrverbrauchs-Zähler zu großzügig, kommt rechnerisch mehr elektrische Strecke heraus als
> überhaupt gefahren wurde. Ohne Deckelung entstünden **negative Verbrenner-Kilometer** und damit
> eine Ersparnis, die größer ist als die Wahrheit. Gedeckelt bleibt der Fehler sichtbar
> (Verbrenner-Anteil 0) statt sich in einen Gewinn zu verwandeln.

**2. Ein eigenes Feld für den realen Verbrenner-Verbrauch — `vergleich_verbrauch_l_100km` bleibt,
was es ist.**
Neuer Parameter **`eigener_verbrauch_l_100km`**. Das bestehende Feld beschreibt einen **fiktiven
Vergleichs-Benziner** („was hätte ein gleichwertiges Verbrenner-Fahrzeug gebraucht", Default 7,5)
und hat **sieben** Produktions-Leser (`aussichten.py` ×2 · `ha_export.py` ×2 ·
`cockpit/nachhaltigkeit.py` · `investitionen/crud.py` · `eauto_wirtschaftlichkeit.py`). Es beim
PHEV umzudeuten würde Zahlen bei allen Nicht-PHEV-Nutzern bewegen und wäre dieselbe Doppelbelegung,
die bei `verbrauch_kwh` als **Schwäche A** dokumentiert ist und dort einen Daten-Checker-Fehlalarm
erzeugt hat. **Zwei Bedeutungen brauchen zwei Felder.**

**3. Das gesetzte Feld IST die Aussage — kein Fahrzeugtyp, kein Flag.**
eedc kennt keinen „Fahrzeugtyp PHEV" und bekommt auch keinen. Die Regel ist strukturell, nicht
magnitudenabhängig — dieselbe Linie wie Entscheidung 1 von Phase 2a („existiert eine Wallbox?"):

> **Ist `eigener_verbrauch_l_100km` gesetzt (> 0), hat das Fahrzeug einen Verbrenner.**
> Ist es leer, ist es ein BEV und **jede Zahl bleibt exakt wie heute.**

Damit gibt es keine Erkennungsheuristik, die kippen kann, und **keinen Breaking Change**: Bestands-
anlagen haben das Feld nicht, also ändert sich für sie nichts — auch nicht um einen Cent.

**4. Die Prognose-Achse nutzt den Prozentwert als Fallback, nicht als Primärweg.**
Neuer Parameter **`elektrischer_fahranteil_prozent`** (0–100). Er greift **genau zwei Mal**:
in der Prognose/ROI-Achse (dort gibt es keine Messung) und im IST, wenn `verbrauch_kwh` **nicht
gepflegt** ist. **Kein Zahlen-Default für PHEV** — kein „Richtwert 40–60 %", wie der Issue-Body
ihn erwägt: ein erfundener Mittelwert ist eine Behauptung über ein fremdes Fahrzeug. Fehlt der
Wert, gilt **100 % elektrisch** (heutiges Verhalten) und der Daten-Checker sagt, dass die Angabe
fehlt.

**5. Die Vergleichsrechnung wird nicht angefasst — der fossile Anteil ist eine eigene Kostenposition.**
Der entscheidende Kunstgriff, der Entscheidung 2 erst trägt:

```text
benzin_kosten_vergleich = km_gefahren   / 100 × vergleich_verbrauch_l_100km × benzinpreis   ← UNVERÄNDERT
fossile_restkosten      = km_verbrenner / 100 × eigener_verbrauch_l_100km   × benzinpreis   ← NEU
strom_kosten            = (wie heute, aus der tatsächlich gemessenen Ladung)                ← UNVERÄNDERT

ersparnis = benzin_kosten_vergleich − strom_kosten − fossile_restkosten
```

Die Frage „was hätte ein Benziner gekostet" bleibt über **alle** Kilometer gestellt — sonst
verglichen wir ein Auto mit einem halben Auto. Neu ist nur, dass die **real angefallenen**
Benzinkosten des PHEV als Kosten danebenstehen. Analog CO₂: die vermiedene Emission wird um
`km_verbrenner / 100 × eigener_verbrauch_l_100km × CO2_FAKTOR_BENZIN_KG_LITER` **reduziert**.

> ⚠ **Die Strom-Kosten bleiben unberührt, und das ist kein Versehen.** eedc misst die geladene
> Energie ohnehin — sie ist nicht aus der Fahrleistung abgeleitet. Ein PHEV lädt weniger, also
> steht dort schon die kleinere Zahl. Wer die Ladung zusätzlich mit dem Anteil skalierte, zöge sie
> **zweimal** ab.

### Etappen (Reihenfolge wichtig)

1. **Parameter + die drei Pflicht-Stellen.** `eigener_verbrauch_l_100km` und
   `elektrischer_fahranteil_prozent` in `core/investition_parameter.py` (`PARAM_E_AUTO` +
   `PARAM_E_AUTO_DEFAULTS` + Alias-Map), Response-Model, `core/field_definitions.py`.
   ⚠ **Kein DB-Default für `eigener_verbrauch_l_100km`** — „nicht gesetzt" ist die tragende
   Aussage aus Entscheidung 3 und darf nicht durch einen Default zerstört werden.
2. **`EmobFakten.fahrverbrauch_je_fahrzeug`** — additiv, exakt parallel zum vorhandenen
   `km_je_fahrzeug` (`services/monats_fakten.py:274`), dessen Docstring die Begründung schon
   trägt: *„Voraussetzung dafür, dass eine Ersparnis je Fahrzeug mit DESSEN Verbrauchs-Parameter
   gerechnet wird"*. Der anlagenweite `fahrverbrauch_kwh` (vier Leser) **bleibt unverändert**.
   Muster: `BkwFakten.erzeugung_je_investition` aus F-10 — additiv statt eine bestehende Summe
   umzudeuten.
3. **Layer-Formel `core/berechnungen/phev_anteil.py`** (ADR-001: eine Aggregat-Formel wird in
   `core/berechnungen/` definiert, nicht in einer Route). Eine reine Funktion
   `teile_fahrleistung(km, fahrverbrauch_kwh, verbrauch_kwh_100km, anteil_prozent) -> (km_e, km_v)`
   mit der Deckelung aus Entscheidung 1 und der Fallback-Kette aus Entscheidung 4.
   **Beide Achsen rufen dieselbe Funktion** — das ist der Punkt, an dem die Drift verhindert wird.
4. **IST-Achse:** `services/eauto_wirtschaftlichkeit.py` (`berechne_eauto_ersparnis` +
   `berechne_eauto_ersparnis_periode`) um die fossile Kostenposition erweitern; `EAutoErsparnisErgebnis`
   bekommt sie als eigenes Feld, damit die Anzeige sie **benennen** kann statt sie zu verstecken.
5. **CO₂:** ausschließlich über `berechne_co2_bilanz` — ADR-001/**DI-2** sagt, das ist die einzige
   Konstruktions-Stelle einer CO₂-Menge, und `npm run check:co2-roh` hält die Client-Hälfte.
   Fundstelle der km-gewichteten Vergleichsrechnung: `api/routes/cockpit/nachhaltigkeit.py:95 ff.`
6. **Prognose-Achse:** `core/calculations.py::berechne_eauto_einsparung` + der einzige Aufrufer
   `api/routes/investitionen/crud.py:1508`.
7. **Anzeige:** E-Auto-Fläche des Komponenten-Hubs (`frontend/src/v4/EAutoHubBloecke.tsx`) und das
   Investitions-Formular. Regel 0a — Farben/Komponenten aus der SoT, keine zweite Kachel-Klasse.
8. **Daten-Checker:** ist `eigener_verbrauch_l_100km` gesetzt, aber weder `verbrauch_kwh` gepflegt
   noch `elektrischer_fahranteil_prozent` angegeben, dann rechnet eedc still 100 % elektrisch —
   **das muss es sagen.** Linie unverändert: melden und erklären, kein „Akzeptiert"-Knopf, keine
   stille Datenänderung.
9. **Symmetrie-Test über beide Achsen** — Pflicht, nicht optional. Vorbild
   `test_emob_readsite_symmetrie.py` aus Phase 2a und `test_netto_ertrag_vier_wege_symmetrie.py`.
   ⚠ Ein Symmetrie-Test deckt nur die Achsen ab, die **die Fixture variiert**
   ([[feedback_aggregator_symmetrie]]): die Fixture muss BEV **und** PHEV führen, mit und ohne
   gepflegten Fahrverbrauch.

### Wechselwirkungen — vor dem Bau je einzeln entscheiden

| Fläche | Frage | Vorschlag |
| --- | --- | --- |
| `pv_ladeanteil_prozent` | Gilt der PV-Anteil auf die ganze Ladung oder nur auf den E-Teil? | **Auf die ganze Ladung** — die Ladung *ist* schon vollständig elektrisch. Hier ist nichts zu teilen; die Frage aus dem Issue-Body beruht auf der Annahme, die Ladung würde aus der Fahrleistung abgeleitet. Das tut sie im IST nicht. |
| Dienstwagen (`ist_dienstlich`) | Wirkt der fossile Anteil in `dienstliche_ladekosten.py`? | **Nein — am Code gemessen, nicht angenommen.** `berechne_dienstliche_ladekosten` liest ausschließlich `ladung_pv_kwh` und `ladung_netz_kwh` und bewertet **geladene Energie**; die Fahrleistung kommt in der Formel nicht vor. Der fossile Anteil eines Dienstwagens ist Sache des Arbeitgebers und war nie in eedcs Bilanz. **Phase 4 lässt diese Formel unberührt.** |
| CO₂-Amortisation **#284** | Graue Last vs. reduzierte Betriebs-Einsparung | **Nicht Teil von Phase 4.** #284 ist ein eigenes Issue; hier nur sicherstellen, dass die Betriebs-Einsparung, die #284 konsumiert, den fossilen Anteil bereits abzieht. |
| **N-141** | Wallbox-PV-Anteil, drei Wege, wartet auf Maintainer-Entscheid | **Blockiert und getrennt halten.** Berührt die Ladung, nicht die Fahrleistung — keine Abhängigkeit in beide Richtungen. |
| **#356** | Achse-2-Drift, Trigger tritt hiermit ein | Siehe Nachtrag oben — **eigener Entscheid**, nicht automatisch mitgebaut. |

### Bekannte Schwäche, die Phase 4 erbt

`verbrauch_kwh` am E-Auto ist **doppelt belegt** (Fahrverbrauch ∧ Legacy-Heimladung, s. Schwäche A)
— `get_eauto_ladung_kwh(data)` = `ladung_kwh or verbrauch_kwh`. Phase 4 macht dieses Feld erstmals
**rechnerisch tragend** für eine Anzeige-Zahl. Zwei Folgerungen:

- Der Anteil darf **nur** aus dem expliziten `verbrauch_kwh` gebildet werden, nie über
  `get_eauto_ladung_kwh` — sonst wird eine Heimladung als Fahrverbrauch gelesen.
- Gernots eigenes Fahrzeug (Smart #1) führt das Feld **bewusst leer** (s. Schwäche A). Die
  Fallback-Kette aus Entscheidung 4 ist deshalb kein Randfall, sondern der Normalfall der einzigen
  Anlage, an der live gegengeprüft werden kann. **Ein Live-Gegencheck an einem echten PHEV fehlt
  — Safi105 hat einen und hat die Datenlage in #330 selbst beschrieben.**

### Was NICHT dazugehört

- **Kein Feld für getankte Liter.** Wurde erwogen und verworfen: die wenigsten Fahrzeuge liefern
  einen kumulativen Liter-Zähler an HA, und der gemessene Weg aus Entscheidung 1 kommt ohne aus.
  Wird ein solcher Zähler später verbreitet, ist er ein additiver dritter Weg, kein Umbau.
- **Kein Fahrzeugtyp-Feld** (s. Entscheidung 3).
- **Keine Session-/Fahrten-Ebene.** eedc bleibt bei Monatsaggregaten — unverändert seit
  §„Abgrenzung" ganz oben.
