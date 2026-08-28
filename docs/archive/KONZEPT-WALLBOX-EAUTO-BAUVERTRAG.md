# Bau-Vertrag — Wallbox / E-Auto (archiviert)

> ## **Historie und verworfene Wege. Kein gültiges Dokument.**
>
> Am 2026-08-28 aus [`KONZEPT-WALLBOX-EAUTO.md`](../KONZEPT-WALLBOX-EAUTO.md) herausgelöst, als
> der Bau durch war. Dort steht die **Regel** — hier stehen der Migrationspfad, die Etappen-Pläne
> und die Fragen, die sich mit dem Bau erledigt haben.
>
> ⛔ **Phase 2b und Phase 3 sind VERWORFEN** (Entscheid Gernot, 2026-08-28) — nicht „offen" und
> nicht „später". **Vehicle-Sensor-Mapping** (eigene `ladung_heim_*`-Felder je Fahrzeug, evcc
> Vehicle-Topics) und die **Aufschlüsselung der Wallbox-Ladung je Fahrzeug** werden nicht gebaut.
> Ihr Trigger — „wenn Vehicle-Sensoren nachgefragt werden" — ist seit Mai 2026 nicht eingetreten;
> die Pool-Aggregation deckt jedes gemeldete Setup. Mit ihnen fallen die drei „Offenen Fragen"
> unten: Sie dienten ausschließlich dieser Bauform.
>
> **Stand der übrigen Phasen, am 28.08. gegen den Code gemessen:**
>
> | Phase | Stand |
> | --- | --- |
> | 1 — Bug-Fix | ✅ gebaut |
> | 2a — Feldzuordnung geradeziehen | ✅ gebaut (`services/eauto_wirtschaftlichkeit.py::get_emob_heimladung_canonical`, Migration `migrate_emob_canonical_source.py`) |
> | 2b — Vehicle-Sensor-Mapping | ⛔ **verworfen** (28.08.) |
> | 3 — Aufschlüsselung je Fahrzeug | ⛔ **verworfen** (28.08.) |
> | 4 — PHEV (#331) | ✅ gebaut, v4.0.11 (`core/berechnungen/phev_anteil.py`) |
> | 5 — PV-Anteil abgeleitet (N-141) | ✅ gebaut, v4.0.11 (`services/emob_ladeanteil.py`, `core/berechnungen/pv_anteil_ladung.py`) |
> | Achse-2-Drift | ✅ gebaut, **#356** geschlossen 08.08. |

---

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

---

## Phase-2-Trigger — Stand 2026-05-20

Der dokumentierte Phase-2-Trigger lautet »wenn Vehicle-Sensoren nachgefragt werden«. Per-Vehicle-/Multi-Fahrzeug-Bedarf ist bislang **nicht** aufgetreten — junky84 (#262) und NongJoWo (#260) fahren beide 1 Wallbox + 1 E-Auto.

Ein *anderes* Signal wird aber deutlich: der **evcc-Portal-Import erzeugt seit v3.31.0 anhaltenden Patch-Bedarf** — #262 (vier Fix-Runden), #260 (zwei Runden), EVCC-Parser DE/EN, insgesamt ~8 emob-Fix-Commits in zwei Wochen. Ursache ist strukturell: evcc schreibt die Heimladung architektonisch an die **Wallbox** (`data_import.py`), während Read-Seite und Datenmodell historisch E-Auto-zentriert sind (siehe »Motivation«). Jeder Fix legt eine weitere Heuristik auf den Pool. Der `aggregiere_emob_ladung`-Gewinner-Pool aus v3.31.6 ist die bestmögliche Heuristik, bleibt aber eine Heuristik — er wählt die falsche Quelle, wenn verirrte Streudaten die echte Quelle übertreffen (bei junky84 lagen ~3.300 kWh Streudaten auf der E-Auto-Investition; die Wallbox gewann nur, weil ihre Heimladung noch größer war).

**Bewertung:**

- **Phase 2 (neue Felder `ladung_heim_*` + Vehicle-Sensor-Mapping)** — der dokumentierte Trigger ist noch nicht erfüllt (kein Multi-Vehicle-Bedarf), aber das evcc-Import-Churn-Signal nähert sich dem Punkt, an dem die strukturelle Lösung günstiger ist als die nächste Heuristik-Runde. Maintainer-Entscheidung; bei der nächsten evcc-Pool-Meldung neu bewerten.
- **Ohne Phase 2 vorziehbar:** die oben verortete »Daten-Checker-Warnung bei Pool-Pflege-Mismatch« braucht kein geändertes Datenmodell. Sie hätte junky84s Streudaten proaktiv sichtbar gemacht und ist ein kleines, eigenständiges Stück.

---

## Phase 2a — Etappen und Risiken (abgearbeitet)

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

---

## Offene Fragen

1. Liefern SMA eCharger und Wattpilot ähnliche Per-Vehicle-Topics wie evcc?
2. Gibt es EEDC-Nutzer mit Multi-WB/Multi-E-Auto-Setup? (Joachim-xo prüfen)
3. Braucht das Monatsabschluss-Formular ein geändertes Layout für die neuen Felder?

> ⛔ **Alle drei sind mit dem Verwerfen von Phase 2b/3 gegenstandslos** (28.08.): Sie fragten nach
> Fremdhardware-Topics, nach Multi-Wallbox-Nutzern und nach einem Formular-Layout — alles nur für
> die Bauform, die nicht kommt.

---

## Achse-2-Drift — der Weg vor der Entscheidung (abgearbeitet)

### Noch zu klären vor einem Fix-Konzept (per-Key-Mechanismus)

Der Diagnose-Endpoint summiert die Kategorie (`summe_wallbox_eauto_kwh` = Σ `wallbox_*` + `eauto_*`), zeigt also **nicht**, welcher Key die −14 trägt. Zwei Hypothesen, verschiedene Fixes:

1. **Wallbox-Selbst-Verdopplung:** der Leistungspfad baut die Wallbox-Kurve aus **mehreren** Zählern (`ladung_kwh` **+** `ladung_pv_kwh`), obwohl `ladung_pv_kwh` eine **Teilmenge** ist (der Zählerpfad addiert in `komponenten_beitraege.py` bewusst nur `ladung_kwh`). Spräche für genau −2× bei Voll-PV-Ladung.
2. **Phantom-`eauto_1`-Serie:** der Leistungspfad erzeugt eine eigene E-Auto-Serie (Quelle noch unklar, da E-Auto keinen Lade-Sensor mehr hat) → echter Querschluss `wallbox_2` + `eauto_1`. Der Faktor **2,14×** am 06-24 (> 2×) passt eher hierzu als zur reinen PV-Teilmengen-Verdopplung.

**Auflösung (Scoping-Schritt, kein Fix):** entweder (a) gezielter Code-Read des Tages-Leistungspfads (`extract_live_config` / `baue_investitions_serien` / `live_komponenten_builder.py`: Serien-Quellen + Entity-Dedup) oder (b) den Diagnose-Endpoint um eine **Per-Key-Aufschlüsselung** erweitern und on-box messen.

### Vorgeschlagene Fix-Richtung (im Konzept-Rahmen, NICHT entschieden)

- **Strukturelle Quellen-Regel auf den Tages-Leistungspfad ausdehnen:** die in Phase 2a beschlossene Regel („Wallbox vorhanden + hat Heimladung → Wallbox ist Quelle; E-Auto trägt nur Nutzung") gilt bisher nur monatlich/read-seitig. Der Tages-Leistungspfad muss dieselbe Regel anwenden, statt heuristisch zu poolen — und `ladung_pv_kwh`/`ladung_netz_kwh` als **Teilmengen** behandeln (nie zusätzlich als Kurve aufaddieren), konsistent zu `komponenten_beitraege`.
- **Achse-2-Invariante für Senken-Vorzeichen normalisieren:** `summe_wallbox_eauto_kwh` (und die anderen Senken-Kategorien) vergleichen die **positive** `*_kw`-Spalte gegen das **negativ** butterfly-signierte JSON → systematischer Vorzeichen-Fehlalarm unabhängig vom Magnituden-Bug. Die Invariante sollte die Senken-Konvention kennen (Betrag/Seite normalisieren), sonst flaggt sie auch nach dem Magnitude-Fix weiter.
- **Leitplanke:** im abgenommenen Wallbox/E-Auto-Rahmen reparieren, Konzept nicht umwerfen; strukturelle Regel statt neuer Heuristik; falls ein Fix die Aggregation ändert, Alt-Tage **nur** über manuellen Daten-Checker-Knopf nachziehen, nie als Start-Migration (eine Start-Migration ohne HTTP).

### Trigger / Priorität

Diagnose-only, niedrig-prioritär (keine falschen Anzeige-Werte). Sinnvoll **gebündelt** mit der nächsten echten Wallbox/E-Auto-Arbeit (gemeinsamer Test-/Migrations-Zyklus), nicht als isolierter Hotfix. Re-Evaluierung beim nächsten emob-Pool-Signal.

> ⚠ **2026-08-08: Dieser Trigger ist eingetreten.** **Phase 4 (#331)** *ist* die nächste echte
> Wallbox/E-Auto-Arbeit. Das heißt **nicht**, dass #356 mitgebaut werden muss — es heißt, dass der
> Scoping-Schritt (Per-Key-Aufschlüsselung des Diagnose-Endpunkts) im selben Zug **billig** ist,
> weil der Tages-Leistungspfad dann ohnehin aufgeschlagen ist. **Entscheid des Maintainers**, nicht
> automatisch Teil von Phase 4; ein stillschweigend mitgebautes zweites Thema wäre eine
> Auftragsausweitung.

---

## Phase 4 — Etappen und Wechselwirkungen (abgearbeitet)

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
   ⚠ Ein Symmetrie-Test deckt nur die Achsen ab, die **die Fixture variiert**: die Fixture muss BEV **und** PHEV führen, mit und ohne
   gepflegten Fahrverbrauch.

### Wechselwirkungen — vor dem Bau je einzeln entscheiden

| Fläche | Frage | Vorschlag |
| --- | --- | --- |
| `pv_ladeanteil_prozent` | Gilt der PV-Anteil auf die ganze Ladung oder nur auf den E-Teil? | **Auf die ganze Ladung** — die Ladung *ist* schon vollständig elektrisch. Hier ist nichts zu teilen; die Frage aus dem Issue-Body beruht auf der Annahme, die Ladung würde aus der Fahrleistung abgeleitet. Das tut sie im IST nicht. |
| Dienstwagen (`ist_dienstlich`) | Wirkt der fossile Anteil in `dienstliche_ladekosten.py`? | **Nein — am Code gemessen, nicht angenommen.** `berechne_dienstliche_ladekosten` liest ausschließlich `ladung_pv_kwh` und `ladung_netz_kwh` und bewertet **geladene Energie**; die Fahrleistung kommt in der Formel nicht vor. Der fossile Anteil eines Dienstwagens ist Sache des Arbeitgebers und war nie in eedcs Bilanz. **Phase 4 lässt diese Formel unberührt.** |
| CO₂-Amortisation **#284** | Graue Last vs. reduzierte Betriebs-Einsparung | **Nicht Teil von Phase 4.** #284 ist ein eigenes Issue; hier nur sicherstellen, dass die Betriebs-Einsparung, die #284 konsumiert, den fossilen Anteil bereits abzieht. |
| **N-141** | Wallbox-PV-Anteil, drei Wege, wartet auf Maintainer-Entscheid | **Blockiert und getrennt halten.** Berührt die Ladung, nicht die Fahrleistung — keine Abhängigkeit in beide Richtungen. |
| **#356** | Achse-2-Drift, Trigger tritt hiermit ein | Siehe Nachtrag oben — **eigener Entscheid**, nicht automatisch mitgebaut. |
