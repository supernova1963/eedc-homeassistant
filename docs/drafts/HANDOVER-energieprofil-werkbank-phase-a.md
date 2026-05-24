# Übergabe: Energieprofil + Reparatur-Werkbank Refactor — Phase A (v3.34.0)

> **Stand:** 2026-05-24 nach Plan-Sichtungs-Session mit Gernot. Diese Datei ist self-contained — die nächste Session braucht keinen Conversation-Kontext, nur dieses Dokument + den Plan + den aktuellen Code-Stand.
>
> **Verbindliche Basis:** [`docs/drafts/PLAN-energieprofil-werkbank-v3.34.md`](PLAN-energieprofil-werkbank-v3.34.md). Pflicht-Vorlesung **vor** jeder Code-Änderung. Insbesondere §3 Phase A (Scope/Tests/Risiken/Akzeptanz), §5 Anti-Scope, §7 Geklärte Punkte.
>
> **Empfohlener Release:** **v3.34.0** als Phase-A-Tag. Phase B kommt **aus eigener Session nach Tester-Zyklus**, nicht in dieser hier.

---

## TL;DR

Phase A des v3.34-Refactors implementieren: Konformitäts-Tests K1 + K2 + Source-Marker als typsicheres Enum, ohne Verhaltens-Änderung. Release als v3.34.0. Phase B wird **nicht** in dieser Session vorbereitet.

Das v3.34-Bündel adressiert den Pattern-Befund aus [`AUDIT-energieprofil-werkbank.md`](AUDIT-energieprofil-werkbank.md) §0.5 (10+ Aggregator-Drift-Vorfälle in ~10 Monaten, jeder lokal gepatcht). Phase A schärft Drift-Erkennung und entkoppelt den `datenquelle`-Magic-String als Steuerungs-Trigger. Phase B (Backfill-Konsolidierung) und Phase C (Hourly-Helper) folgen in eigenen Sessions.

---

## Pre-Condition: in §7 geklärte Punkte sind verbindliche Vorgaben

Diese drei Punkte wurden in der Plan-Sichtungs-Session entschieden und sind **nicht erneut zu diskutieren**:

1. **Phase C als v3.35.0, eigene Etappe.** Phase A + B sind v3.34. Phase C berührt das Snapshot-Subsystem und ist anwender-sichtbar (E-Auto-Doppelmapping-Halbierung); andere Tester-Kommunikations-Klasse, Subsystem-Wechsel zeitlich isolieren. Im v3.34-CHANGELOG wird v3.35.0 = Phase C als Folge-Etappe **angekündigt** (siehe §6 des Plans), damit der Termin nach außen verbindlich wird.

2. **Source-Marker als Enum, nicht Boolean.** Der Magic-String `datenquelle` steuert heute drei Verzweigungen — preserve-Trigger ([aggregator.py:581/589](../../eedc/backend/services/energie_profil/aggregator.py#L581)), Provenance-Writer-Format via `auto_writer` ([aggregator.py:89](../../eedc/backend/services/energie_profil/aggregator.py#L89)) und `datenquelle`-Spaltenwert. Ein Boolean würde nur eine abdecken; Enum mit `to_db_string()` / `to_provenance_source(...)` erschlägt alle drei strukturell.

3. **K1-Konformitäts-Test über die Subsystem-Grenze, keine geteilte Konstante.** Eine geteilte Konstante zwischen Aggregator und `live_wetter._speichere_prognose` würde zwei Subsysteme mit unabhängigen Lebenszyklen verkleben — saubere Auflösung wäre die Prognose-Tabellen-Auslagerung (Audit-§10.4), die im Anti-Scope bleibt. K1 läuft als reiner Konformitäts-Test.

---

## Scope dieser Session — nur Phase A

Drei in §3 Phase A des Plans definierte Bausteine. Reihenfolge frei, aber alle drei müssen ins Release.

### 1. Konformitäts-Test K1 — Prognose-Felder-Sync

**Was:** Unit-Test, der die drei real existierenden Prognose-Felder-Listen einliest und Gleichheit als Menge prüft. Bricht bei jedem Drift.

**Drei Stellen während Phase A** (nach Phase B reduziert sich K1 auf zwei Stellen, weil die Backfill-Liste mit der Backfill-Eigenständigkeit entfällt — Phase B nimmt die Anpassung mit):

1. `_PROGNOSE_FELDER_RETTEN` in [`eedc/backend/services/energie_profil/aggregator.py:42-50`](../../eedc/backend/services/energie_profil/aggregator.py#L42) (7 Einträge)
2. Hardcode-Liste in [`eedc/backend/services/energie_profil/backfill.py:543-547`](../../eedc/backend/services/energie_profil/backfill.py#L543) (5 Einträge — heute Drift-Risiko-Stelle laut Audit-§4.1, neutralisiert durch `existing_dates`-Skip)
3. Schreibfelder von `live_wetter._speichere_prognose` (Wetter-Endpoint, der asynchron in TZ schreibt)

**Akzeptanz:** Test ist im CI-Pflicht-Pfad und grün. Test ist PR-blockierend analog ADR-001-Test. **Wichtig:** Der Test bricht heute vermutlich rot — die Listen sind nicht identisch. Das ist Befund, nicht Bug — Phase A muss entscheiden: entweder Backfill-Liste auf 7 Einträge angleichen (defensiv, kostet ~zwei Zeilen), oder Allowlist im Test definieren, die das Delta dokumentiert. Empfehlung: angleichen, weil günstig.

### 2. Konformitäts-Test K2 — TZ-Felder-Vollständigkeits-Check

**Was:** Unit-Test gegen das SQLAlchemy-Modell + den Aggregator-Code. Jede Spalte auf `TagesZusammenfassung` muss eines der drei Schicksale haben:

(a) wird von `aggregate_day` gesetzt,
(b) steht auf `_PROGNOSE_FELDER_RETTEN` (extern befüllt, wird gerettet),
(c) ist in einer expliziten Allowlist „bleibt NULL".

**Risiko-Befund:** K2 kann beim ersten Lauf rot sein. Plan §3 Phase A.3 sagt: beide Fälle sind Befunde, die entweder als Pflicht-Fix in A oder als bewusste Schiebung in B aufgenommen werden müssen. Konkret: wenn eine Spalte „bleibt NULL" sein soll (z.B. veraltetes Legacy-Feld), wandert sie in die Allowlist mit Begründungs-Kommentar; wenn sie versehentlich nicht gesetzt wird, ist das ein Bug und gehört noch in Phase A.

**Akzeptanz:** K2 im CI grün. Allowlist-Spalten haben pro Eintrag einen Begründungs-Kommentar im Test.

### 3. Source-Marker als typsicheres Enum

**Was:** Enum mit drei Werten (Phase B fügt einen vierten hinzu):

- `Source.Scheduler` — projiziert auf `datenquelle="scheduler"`, Provenance-Source `external:ha_statistics:hourly`/`daily` oder `auto:monatsabschluss` je nach Hourly-Quelle
- `Source.MonatsabschlussBackfill` — projiziert auf `datenquelle="monatsabschluss"`, Provenance wie Scheduler
- `Source.ManualRepair` — projiziert auf `datenquelle="manuell"`, Provenance-Writer `energieprofil:manuell`

Wird als **Pflicht-Parameter** an `aggregate_day` eingeführt — kein Default. Alle Aufrufer (Audit-§1 Tabelle, Trigger #1–#6) setzen ihn explizit.

**Projektions-Methoden auf dem Enum:**

- `to_db_string() -> str` — liefert die heutigen `TagesZusammenfassung.datenquelle`-Spaltenwerte (UI ändert nichts)
- `to_provenance_source(hourly_source: HourlySource) -> str` — setzt den Provenance-Source-String zusammen je nach gewählter Hourly-Quelle (LTS, Snapshot-Fallback, oder `auto:monatsabschluss`)

**Verzweigungen, die heute am Magic-String hängen** (alle drei werden auf Enum umgestellt):

1. Preserve-Trigger im Aggregator (`aggregator.py:581/589`) → fragt jetzt den Enum-Wert ab (`source == Source.ManualRepair`)
2. `auto_writer = f"energieprofil:{datenquelle}"` (`aggregator.py:89`) → nutzt `source.to_provenance_source(...)` oder ableitbare Form
3. `TagesZusammenfassung.datenquelle`-Spaltenwert beim Schreiben → nutzt `source.to_db_string()`

**Vorab-Schritt Pflicht:** Grep auf `datenquelle\s*=\s*"` und `datenquelle:` über die gesamte Codebase (`backend/`, `tests/`, `scripts/`) findet alle Setter-Stellen. Cloud-Import-Pfade sind irrelevant — sie schreiben auf `Monatsdaten`, nicht auf TZ.

**Akzeptanz:**

- Grep auf `datenquelle ==` im Aggregator-Modul liefert keine Verzweigung mehr (Plan-Erfolgskriterium E4)
- Bestehende Tests grün (479 + die in v3.33.0 ergänzten Symmetrie-Tests)
- Zusätzlicher Test: `to_db_string()` + `to_provenance_source(...)` liefern für jeden Enum-Wert die heutigen Magic-String-Werte (Regressions-Schutz)

### Bonus-Aufgabe: Asymmetrie-Klärung Scheduler-Preserve vs Manuell-Preserve

Plan-§3 Phase A.1 letzter Punkt + Plan-§1.2 E5: die heutige Verzweigung „preserve nur bei `datenquelle=="manuell"`, nicht beim Scheduler" muss **positiv begründet** werden. Tradeoff-Vermutungen (*„vermutlich weil sonst stillschweigend alte Werte eingefroren würden"*) reichen nicht aus — sie sind dann **Trigger für eine Eskalation an Gernot vor dem Release**, nicht für eine bequeme Dokumentations-Notiz.

Konkret: Code-Kommentar im Aggregator + CHANGELOG-Eintrag, der die heutige Entscheidung positiv begründet. Falls beim Schreiben klar wird, dass die Asymmetrie kein Tradeoff sondern ein Vorfall war: **Stop**, an Gernot melden, nicht stillschweigend fixen.

---

## Anti-Scope — explizit nicht in dieser Session

Bei jedem dieser Punkte gilt: **wenn der Gedanke auftaucht „während ich eh dabei bin, mache ich noch schnell...", stoppen und an die Plan-Disziplin halten.** Phase B + C haben eigene Sessions.

| Verbot | Begründung |
|---|---|
| **Backfill-Konsolidierung** (`backfill_from_statistics` als dünne Schleife über `aggregate_day` umbauen) | Phase B, eigene Session. Diese Session ändert die Backfill-Logik **nicht**. Lediglich K1 macht die Backfill-Hardcode-Liste sichtbar, aber sie bleibt eigenständig. |
| **Hourly-Helper-Migration** (`_categorize_counter`, E-Auto-Doppelmapping) | Phase C, v3.35.0, eigene Session nach Tester-Zyklus auf v3.34. Snapshot-Subsystem bleibt in dieser Session unangetastet. |
| **`rollup.py` anfassen** | Out-of-Scope laut Plan §5 + Audit-§9. Auch wenn die K2-Test-Logik dort vorbeischrammt — Pflicht-Notiz für späteren Refactor in Audit-§9. |
| **Prognose-Tabellen-Schnitt** (eigene `tages_prognose`-Tabelle) | Anti-Scope laut Plan §5 + Audit-§11 Punkt 3. K1 ist genau das Mittel, das ohne diesen Schnitt funktioniert. |
| **Werkbank Plan-Diff-Refactor** | Anti-Scope (Plan §5). Auftrags-Pflichtbegrenzung: Plan/Execute-API stabil. |
| **Provenance-Layer anfassen** (`source_provenance` JSON, `provenance.py`, `source_priority.py`) | Auftrags-Pflichtbegrenzung. Source-Marker projiziert nur **auf** Provenance, ändert das Modell selbst nicht. |
| **Daten-Migration** | Auftrags-Pflichtbegrenzung (v3.33.0 lief vier Wochen vorher mit Migration). Phase A ist verhaltens­identisch — keine Wert-Änderung in bestehenden Rows, kein neuer Migrations-Eintrag in `eedc/backend/migrations/`. |
| **`datenquelle`-Spaltentyp ändern** (z.B. von VARCHAR auf Enum-DB-Type) | Hieße Migration. Spalte bleibt VARCHAR(30), nur die Werte kommen aus `to_db_string()`. |
| **Performance-Optimierungen, Cleanup-Refactorings, Naming-Anpassungen** | Wenn beim Lesen auffallen — als Audit-Befund festhalten (z.B. neue Sektion in `AUDIT-energieprofil-werkbank.md` oder als Issue-Entwurf), **nicht** in dieser Session umsetzen. |

---

## Output dieser Session

Pflichtmäßige Artefakte vor dem Release:

| Artefakt | Inhalt |
|---|---|
| **Code-Änderungen** | Enum-Datei (neu, z.B. `eedc/backend/services/energie_profil/source.py` — Detail-Entscheidung in Implementierung), `aggregator.py`-Anpassung (Verzweigungen auf Enum), alle Aufrufer-Stellen umgestellt, Backfill-Hardcode-Liste an Aggregator-Liste angeglichen (falls als A-Pflicht-Fix entschieden), K2-Allowlist-Begründungen im Test |
| **Tests** | K1, K2, Source-Marker-Verhalten + Projektions-Regressions-Test. Bestehende Suite (479 + v3.33.0-Symmetrie-Tests) grün. |
| **CHANGELOG** | Eintrag unter v3.34.0 mit Framing aus Plan-§6: „Drift-Erkennung für Aggregat-Felder verschärft (Konformitäts-Tests, Vorarbeit für v3.34.x-Refactor). Keine User-spürbare Funktionsänderung." Plus Asymmetrie-Klärung dokumentieren, falls relevant. **Plus Folge-Etappen-Anker:** Hinweis am Ende des Phase-A-Eintrags, dass v3.34.1 = Phase B (Backfill-Konsolidierung) und v3.35.0 = Phase C (Hourly-Helper-Migration, analog zur in v3.33.0 sanierten Daily-Symmetrie) angekündigt sind — analog dem v3.32.4 → v3.33.0-Ankündigungs-Pattern. |
| **WAS-IST-NEU** | Kein User-spürbarer Inhalt — Phase A ist Vorbereitung. Minimal-Eintrag, der auf den Folge-Refactor hindeutet, ist OK, aber kein Funktions-Versprechen. Falls unsicher: bei Gernot vor Release rückfragen. |
| **Release-Lauf** | `./scripts/release.sh 3.34.0` nach Sichtung des Diff durch Gernot — **nicht** ohne explizite Freigabe. |

---

## Stop-Punkt

Nach erfolgreichem Release v3.34.0:

- **Stop.** Nicht in Phase B übergehen, nicht in „während ich eh dabei bin, schaue ich mal..."-Modus geraten.
- Tester-Zyklus auf v3.34.0 abwarten — mindestens ein normaler Zyklus, in dem die Konformitäts-Tests + der Source-Marker in echter Tester-Last laufen, bevor Phase B gestartet wird.
- Phase B kommt **aus eigener Session** mit eigenem Übergabe-Prompt. Der Phase-B-Prompt wird beim Übergang geschrieben — entweder von Gernot oder durch eine Plan-Session vor B.

Wenn während der Phase-A-Implementierung weitere strukturelle Befunde auftauchen (insbesondere im Source-Marker-Grep-Sweep oder bei K2): notieren in einer neuen Sektion am Ende dieses Dokuments oder in einer eigenen Notiz-Datei in `docs/drafts/`, **nicht** stillschweigend mit erschlagen. Plan-Disziplin gilt durchgehend.

---

## Memory-Referenzen (zur Konsistenz)

- `feedback_aggregations_drift` — die Drift-Klasse, gegen die Phase A schärft
- `feedback_aggregator_symmetrie` — Symmetrie-Tests Pflicht (gilt für Phase B/C; K1 + K2 sind die Phase-A-Variante)
- `feedback_step_by_step_berechnungs_layer` — ADR-001 + Konformitäts-Test, dasselbe Pattern wie K1/K2
- `feedback_release_bundling` — keine Release-Orgie. Phase A allein ist eine begründete Etappe (eigener sichtbarer Wert: Drift-Erkennung scharf), kein Mikro-Release.
- `feedback_release_workflow` — WAS-IST-NEU vor `release.sh`, Tester-Pakte vorsichtig
- `feedback_neue_felder_pflicht` — falls beim K2-Sweep eine Spalte ohne Aggregator-Setter auffällt, die drei Pflicht-Stellen prüfen
