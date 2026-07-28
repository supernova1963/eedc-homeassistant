# Konzept: Berechnungs-Layer (`core/berechnungen/`)

**Status:** Aktiv — **Architektur-Detail zu [`ADR-001`](ADR-001-BERECHNUNGS-LAYER.md)** (die Regel steht dort, hier der Submodul-Schnitt und die Erweiterungen). Ursprung 2026-05-19, Faktenstand gegen den Code geprüft **2026-07-28**. | **Auslöser:** BKW-Doppelzählung (Rainer-PN) als sichtbarster Vertreter einer ganzen Drift-Klasse

## 0. Maßnahmen-Register (fortschreibbar)

> Eine Zeile je paketierter Maßnahme. **Beleg = Datei:Zeile**, nicht „laut Konzept".
> Erledigtes bleibt stehen (mit Beleg), damit niemand es ein zweites Mal aufmacht.

| # | Maßnahme | Status | Beleg / Rest |
| --- | --- | --- | --- |
| **BL-1** | Akut-Fix: Aggregator-Mode-Switch + Pflicht-Invariante (§3.1) | ✅ v3.31.5 | `core/berechnungen/invarianten.py` |
| **BL-2** | Konformitäts-Test als CI-Guardrail (§5) | ✅ v3.31.5 | `backend/tests/test_berechnungs_layer_konformitaet.py` |
| **BL-3** | Layer-Grundbestand `energie.py` + `invarianten.py` (§4) | ✅ | beide vorhanden |
| **BL-4** | **Konsumenten-Migration** (§2-Liste) | ✅ **für die sechs namentlich genannten Module** — die „(offen)"-Marker in §2 waren am 2026-07-28 **falsch**: `prognosen.py` · `energie_profil/{repair,views}.py` · `live_wetter.py` · `live_history_service.py` · `live_komponenten_builder.py` importieren alle aus `core.berechnungen` | Liste korrigiert. **Rest bleibt:** die vollständige Inventur (~30 Konsumenten) in `project_berechnungs_layer_offen` — opportunistisch beim Touch |
| **BL-5** | **Geplante Submodule** (§4-Tabelle) | 🟡 **teilweise** — `counter.py` ✅ · `kennzahlen.py` ✅ · Einsparungen ✅ (anders geschnitten: `speicher*.py`, `emob.py`, `alternativkosten.py`) · **`peaks.py` ❌** (steht seit v3.31.5 als geplant in `__init__.py:30`) · **`roi.py` ❌** — `berechne_roi` lebt weiter in `core/calculations.py:620` | → Backlog **DOK-3**, opportunistisch |
| **BL-6** | **Herleitungs-Transparenz §6** (Vertrag zu Style-Guide A6) | ⛔ **verworfen (Gernot, 2026-07-28)** — der Trigger war gefeuert, die Entscheidung fiel gegen den Bau. Formel-SoT bleibt [`BERECHNUNGEN.md`](BERECHNUNGEN.md); die Tooltip-Texte sind **Anzeige**, keine zweite Rechnung. Begründung + Preis stehen in §6 | § 6 umgeschrieben; Backlog-Punkt **DOK-2 geschlossen** |
| **BL-7** | Alt-JSONs mit BKW-Doppel-Bug migrieren (§8) | ⏸ bewusst nicht automatisch — Reparatur-Werkbank (`feedback_kein_grosser_heiler_knopf`) | unverändert gültig |

**Was dieses Dokument NICHT ist:** die Regel (→ [`ADR-001`](ADR-001-BERECHNUNGS-LAYER.md)) und nicht die Invarianten-Liste (→ [`ADR-002`](ADR-002-WURZELMUSTER.md)).

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
  services/daten_checker.py            (✓ migriert 2026-05-19)
  api/routes/prognosen.py              (✓ geprüft 2026-07-28)
  api/routes/energie_profil/repair.py  (✓ geprüft 2026-07-28)
  api/routes/energie_profil/views.py   (✓ geprüft 2026-07-28)
  api/routes/live_wetter.py            (✓ geprüft 2026-07-28)
  services/live_history_service.py     (✓ geprüft 2026-07-28)
  services/live_komponenten_builder.py (✓ geprüft 2026-07-28)
  ... Long-Tail (~30) weiter offen — vollständige Inventur in Memory
      project_berechnungs_layer_offen; Migration beim Touch (§3.3)
```

> **Korrektur 2026-07-28:** Die sechs Zeilen oben standen bis dahin auf „(offen)" — sie sind es nicht
> mehr; alle sechs Module ziehen den Layer. Die Liste war ein Beispiel für „Regel ohne Code-Beleg"
> ([[feedback_keine_regel_behaupten_ohne_code_beleg]]): sie wurde beim Migrieren nie nachgezogen und
> hätte den nächsten Leser zu bereits erledigter Arbeit geschickt. Der **Long-Tail** ist echt offen.

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

| Submodul | Inhalt | Stand 2026-07-28 |
|---|---|---|
| `counter.py` | komponenten_starts-Σ, wp_starts_pro_stunde-Σ | ✅ angelegt |
| `kennzahlen.py` | eigenverbrauch, autarkie, spez_ertrag | ✅ angelegt (+ `spez_ertrag.py`, `verbrauch.py`) |
| `einsparungen.py` | speicher, e-auto, wärmepumpe ROI | ✅ **anders geschnitten** — statt eines Sammel-Moduls je Domäne eins: `speicher.py`, `speicher_wirtschaftlichkeit.py`, `emob.py`, `alternativkosten.py` |
| `peaks.py` | peak_pv/bezug/einspeisung | ❌ nie angelegt — steht seit v3.31.5 als geplant in `core/berechnungen/__init__.py:30` |
| `roi.py` | roi_prozent, amortisation_jahre, ust_eigenverbrauch | ❌ nie angelegt — `berechne_roi` liegt weiter in `core/calculations.py:620` |

> Die beiden ❌ sind kein eigener Auftrag, sondern Backlog **DOK-3**: mitnehmen, wer die Dateien
> ohnehin anfasst (ADR-001-Regel „beim Touch"). Der Trigger für `peaks.py` wäre ein Tagesverlauf-
> Refactor, für `roi.py` der nächste Griff in `calculations.py`.

## 5. Schutzmechanismen

| Mechanismus | Greift | Aktiviert |
|---|---|---|
| Pytest-Konformitäts-Test | künftige Whitelist-Duplikate, Inline-Patterns außerhalb Layer | ✓ v3.31.5 |
| Pflicht-Invariante im Aggregator | Schreib-Drift (BKW-Klasse) | ✓ v3.31.5 |
| ADR-001 | Code-Review-Anker, Onboarding | ✓ v3.31.5 |
| `INLINE_PATTERN_GRANDFATHERED`-Liste mit "veraltet"-Check | erzwingt Bereinigung nach Migration | ✓ v3.31.5 |
| Memory `feedback_eigenen_code_zuerst` | Diagnose-Reflex beim nächsten Anwender-Drift | ✓ v3.31.5 |
| Memory `feedback_step_by_step_berechnungs_layer` | Migrations-Disziplin in künftigen Sessions | ✓ v3.31.5 |

## 6. Herleitungs-Transparenz (Vertrag zu Style-Guide A6)

Ein Layer-Helfer, der eine anwender-sichtbare Kennzahl liefert (KPI, ROI, Autarkie, Ersparnis, Wirkungsgrad, Prognose), gibt **neben dem Wert eine strukturierte Herleitung** zurück — nicht nur die Zahl. So hat die Erklärung dieselbe *eine* Quelle wie der Wert und kann nicht von ihm driften (gleiches SoT-Prinzip wie für die Berechnung selbst).

**Form (Vorschlag, beim ersten Touch zu konkretisieren):**

```
Herleitung = { wert, einheit, formel, eingesetzte_werte[], quelle, zeitraum }
```

- **UI-Konsument:** Style-Guide-Norm A6 (Formel-Tooltip) rendert diese Struktur — dezenter Indikator → Hover/Tap zeigt Formel + eingesetzte Werte + Quelle/Zeitraum.
- **Weitere Konsumenten:** dieselbe Herleitung speist perspektivisch PDF-Export + Daten-Checker (eine Quelle, mehrere Sichten).
- **A3-Kopplung:** ist der Wert `—`/`N/A`/`?`, trägt die Herleitung den Grund (Datenlücke vs. strukturell vs. Schätzung).
- **Scope:** nur abgeleitete/aggregierte Kennzahlen — rohe Zählerwerte/triviale Summen brauchen keine Herleitung.

**Durchsetzung — separater Zukunfts-Punkt (nach Projektabschluss):** analog zu den Schutzmechanismen (Abschnitt 5) ist ein Konformitäts-Check denkbar (neuer Kennzahl-Helfer ohne Herleitungs-Feld → Test schlägt an). Bewusst NICHT jetzt umgesetzt — erst nach Abschluss des laufenden Umbaus als eigener Punkt bewerten. Bis dahin gilt die Erwartung dokumentarisch (dieser Abschnitt + Style-Guide A6).

---

> ## ⛔ Dieser Abschnitt ist verworfen (Gernot, 2026-07-28) — er bleibt als Begründung stehen
>
> **Der Trigger ist gefeuert und die Antwort lautet Nein.** „Nach Projektabschluss" war der
> IA-V4-Flip; der ist seit v4.0.0 (2026-07-25) durch. Der Vertrag oben wird **nicht gebaut.**
>
> **Stand, der die Entscheidung getragen hat (gemessen 2026-07-28):** im Backend existiert keine
> `Herleitung`-Struktur — `eingesetzte_werte` hat **0 Treffer** in `core/`. Stattdessen tragen
> **10 Dateien mit zusammen 23 Verwendungsstellen** die Formel als Frontend-String
> (`<FormelTooltip formel=… berechnung=…>`): `pages/auswertung/InvestitionenTab.tsx` (8) ·
> `components/finanzen/TKonto.tsx` (5) · `components/roi/RoiAnalyse.tsx` (2) ·
> `components/ui/KPICard.tsx` (2) · `RingGaugeCard` · `HeroLeiste` · `GrundlastSollIstKachel` ·
> `v4/KomponentenSektionen.tsx` · `v4/TagBilanz.tsx` · `components/dashboard/AmortisationsBar.tsx`.
>
> **Warum verworfen:** der Vertrag würde jeden Kennzahl-Helfer in seiner Rückgabe ändern **und**
> alle 23 Aufrufstellen anfassen — für eine Drift, die in über einem Jahr nie als Fehler aufgetreten
> ist. Die Tooltip-Texte sind **Anzeige**, keine zweite Rechnung: sie beschreiben die Formel, sie
> führen sie nicht aus. Der Formel-SoT ist und bleibt [`BERECHNUNGEN.md`](BERECHNUNGEN.md).
>
> **Der Preis, ehrlich benannt:** Wert und Erklärung haben weiterhin zwei Quellen. Ändert jemand
> eine Formel im Layer und vergisst den Tooltip-Text, erklärt die UI eine Rechnung, die so nicht
> mehr stattfindet — und **kein Wächter merkt es.** Wer eine Formel in `core/berechnungen/` ändert,
> prüft die Tooltip-Texte und `BERECHNUNGEN.md` **von Hand** mit.
>
> **Wiederaufnahme nur mit neuem Anlass:** ein gemeldeter Fall, in dem ein Tooltip nachweislich
> etwas anderes erklärt als der Code rechnet. Ohne den ist diese Zeile abgeschlossen — nicht
> vertagt (`feedback_keine_regel_behaupten_ohne_code_beleg`).

## 7. Anwender-Kommunikation

Für v3.31.5-Release in WAS-IST-NEU/CHANGELOG: BKW-Doppelzählungs-Fix mit Dank an Rainer, Aggregator-Verhalten im HA-Add-on-Modus auf „HA-LTS exklusiv" konsolidiert (Etappe-4-Komplettierung). KEINE große Refactoring-Ankündigung — der Step-by-Step-Pfad läuft unter der Haube, Anwender sehen nur die Bugfixes.

## 8. Was NICHT in diesem Konzept ist

- Daten-Checker-Refactor (Achse A/B/C, eigenes [KONZEPT-DATENCHECKER-KONSISTENZ.md](archive/KONZEPT-DATENCHECKER-KONSISTENZ.md)) — orthogonal, kann unabhängig laufen.
- Migration der bestehenden alten `TagesZusammenfassung.komponenten_kwh`-JSONs mit dem BKW-Doppel-Bug — wird über die Reparatur-Werkbank gelöst (Anwender wählen Bereich und „Mehrere Tage neu berechnen"). Auto-Migration ist denkbar, aber bisher nicht implementiert; siehe Memory `project_berechnungs_layer_offen` falls Tester-Befunde dazu zwingen.
- Frontend-Berechnungs-Layer — separate Migration, kein Backend-ADR-Thema.
