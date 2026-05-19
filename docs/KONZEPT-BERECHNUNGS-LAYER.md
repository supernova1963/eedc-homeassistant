# Konzept: Berechnungs-Layer (`core/berechnungen/`)

**Status:** Aktiv (2026-05-19) | **Auslöser:** BKW-Doppelzählung (Rainer-PN) als sichtbarster Vertreter einer ganzen Drift-Klasse | **Regel-Doku:** [`ADR-001`](ADR-001-BERECHNUNGS-LAYER.md)

## 1. Problem-Kontext

Etappe 4 (v3.31.0) sollte HA-LTS zur Source-of-Truth für `TagesEnergieProfil` + `TagesZusammenfassung` machen. Der Konzept-Plan (Z.48 + Z.75 in [archiv-doc](archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md)) sagte explizit: **„keine parallele Riemann-Integration mehr, Riemann-Pfad entfällt"**.

Real wurde der HA-LTS-Pfad **additiv** eingebaut — der Live-Σ-Riemann-Pfad in `aggregate_day` blieb stehen, wurde nur an einzelnen Stellen vom Boundary überschrieben. Bei Schema-Mismatch (z.B. balkonkraftwerk → Live `pv_<id>`, Boundary `bkw_<id>`) blieben beide Keys parallel in `komponenten_kwh`, alle Konsumenten mit Prefix-Whitelist zählten doppelt.

Dieser Bug wurde gefunden, weil Rainer **+22% Bias** im Genauigkeits-Tab meldete. Diagnose-Fehler dabei: zuerst User-Setup verdächtigt (HA-Sensoren prüfen, AC-Total-Sensor-Vergleich vorschlagen), bevor eigener Berechnungs-Code geprüft wurde. Beide Fehler — Code-Architektur + Diagnose-Reflex — bilden das Pattern, das dieses Konzept adressiert.

## 2. Architektur-Ziel

```
WRITE-Pfad (eine Stelle, eine Wahrheit pro Modus):
  energie_profil/aggregator.py::aggregate_day()
    HA-Add-on-Modus: boundary_kwh (HA-LTS) ist alleiniger Schreiber von komponenten_kwh
    Standalone:      Live-Σ-Riemann als Pfad 2 mit Provenance-Marker
    Pflicht-Invariante: pruefe_tep_tz_konsistenz am Ende jedes Laufs

READ-Pfad (eine Heimat für Berechnungen):
  core/berechnungen/
    energie.py        — PV_KOMPONENTEN_PREFIXE, summe_pv_bkw_kwh
    invarianten.py    — pruefe_tep_tz_konsistenz, assert_tep_tz_konsistent
    (geplant beim Touch)
    counter.py        — komponenten_starts-Σ, wp_starts_pro_stunde
    peaks.py          — peak_pv/bezug/einspeisung
    kennzahlen.py     — eigenverbrauch, autarkie, spez_ertrag
    einsparungen.py   — Migration aus calculations.py
    roi.py            — Migration aus calculations.py

KONSUMENTEN (alle importieren aus core/berechnungen):
  services/daten_checker.py (✓ migriert 2026-05-19)
  api/routes/prognosen.py (offen)
  api/routes/energie_profil/repair.py (offen)
  api/routes/energie_profil/views.py (offen, anderes Pattern)
  api/routes/live_wetter.py (offen, anderes Pattern)
  services/live_history_service.py (offen, anderes Pattern)
  services/live_komponenten_builder.py (offen, anderes Pattern)
  ... (vollständige Inventur in Memory project_berechnungs_layer_offen)
```

## 3. Migrations-Pattern (Step-by-Step, opportunistisch)

Disziplin durch **Architektur**, nicht durch Sprint-Plan:

1. **Akut-Fix (v3.31.5):** Aggregator-Mode-Switch (Live-Σ-Akkumulation nur im Standalone-Modus) + Pflicht-Invariante → schließt die akute Drift-Klasse strukturell. Neue BKW-äquivalente Schema-Drifts im HA-Add-on-Modus sind per Konstruktion unmöglich.
2. **Konformitäts-Test als CI-Guardrail:** Jeder PR, der neue Whitelist-Definitionen außerhalb des Layers einführt, schlägt fehl.
3. **Bestehende Konsumenten:** Migration beim nächsten Touch (Bugfix, Feature, Refactor). Kein eigener Sprint, kein Big-Bang. Long-Tail ist akzeptabel, solange die Akut-Falle zu ist.
4. **Bei jeder Anwender-Drift-Meldung:** ZUERST eigenen Berechnungscode prüfen (Memory `feedback_eigenen_code_zuerst`).

## 4. Submodul-Schnitt

### `energie.py` (existiert)

- `PV_KOMPONENTEN_PREFIXE: tuple[str, ...]` — Whitelist für PV-Erzeugung in komponenten_kwh
- `summe_pv_bkw_kwh(komponenten_kwh)` — Tages-PV-Σ aus dem JSON

### `invarianten.py` (existiert)

- `pruefe_tep_tz_konsistenz(tep_rows, tz_komponenten_kwh, toleranz_kwh=0.5)` → `KonsistenzBericht`
- `assert_tep_tz_konsistent(...)` → Test-Variante mit AssertionError

### Geplante Submodule (entstehen beim nächsten Touch des betroffenen Codes)

| Submodul | Inhalt | Trigger für Anlage |
|---|---|---|
| `counter.py` | komponenten_starts-Σ, wp_starts_pro_stunde-Σ | WP-Counter-Drift-Fix (siehe [KONZEPT-COUNTER-DAILY-DRIFT.md](KONZEPT-COUNTER-DAILY-DRIFT.md)) oder #238 WP-Betriebszeiten |
| `peaks.py` | peak_pv/bezug/einspeisung | Tagesverlauf-Refactor oder Peak-bezogener Bug |
| `kennzahlen.py` | eigenverbrauch, autarkie, spez_ertrag | Migration aus `calculations.py` wenn dort eine Funktion angefasst wird |
| `einsparungen.py` | speicher, e-auto, wärmepumpe ROI | Migration aus `calculations.py` |
| `roi.py` | roi_prozent, amortisation_jahre, ust_eigenverbrauch | Migration aus `calculations.py` |

## 5. Schutzmechanismen

| Mechanismus | Greift | Aktiviert |
|---|---|---|
| Pytest-Konformitäts-Test | künftige Whitelist-Duplikate, Inline-Patterns außerhalb Layer | ✓ v3.31.5 |
| Pflicht-Invariante im Aggregator | Schreib-Drift (BKW-Klasse) | ✓ v3.31.5 |
| ADR-001 | Code-Review-Anker, Onboarding | ✓ v3.31.5 |
| `INLINE_PATTERN_GRANDFATHERED`-Liste mit "veraltet"-Check | erzwingt Bereinigung nach Migration | ✓ v3.31.5 |
| Memory `feedback_eigenen_code_zuerst` | Diagnose-Reflex beim nächsten Anwender-Drift | ✓ v3.31.5 |
| Memory `feedback_step_by_step_berechnungs_layer` | Migrations-Disziplin in künftigen Sessions | ✓ v3.31.5 |

## 6. Anwender-Kommunikation

Für v3.31.5-Release in WAS-IST-NEU/CHANGELOG: BKW-Doppelzählungs-Fix mit Dank an Rainer, Aggregator-Verhalten im HA-Add-on-Modus auf „HA-LTS exklusiv" konsolidiert (Etappe-4-Komplettierung). KEINE große Refactoring-Ankündigung — der Step-by-Step-Pfad läuft unter der Haube, Anwender sehen nur die Bugfixes.

## 7. Was NICHT in diesem Konzept ist

- Daten-Checker-Refactor (Achse A/B/C, eigenes [KONZEPT-DATENCHECKER-KONSISTENZ.md](KONZEPT-DATENCHECKER-KONSISTENZ.md)) — orthogonal, kann unabhängig laufen.
- Migration der bestehenden alten `TagesZusammenfassung.komponenten_kwh`-JSONs mit dem BKW-Doppel-Bug — wird über die Reparatur-Werkbank gelöst (Anwender wählen Bereich und „Mehrere Tage neu berechnen"). Auto-Migration ist denkbar, aber bisher nicht implementiert; siehe Memory `project_berechnungs_layer_offen` falls Tester-Befunde dazu zwingen.
- Frontend-Berechnungs-Layer — separate Migration, kein Backend-ADR-Thema.
