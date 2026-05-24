# Fix-Plan Energieprofil + Reparatur-Werkbank — v3.34

> **Stand:** 2026-05-24, im Anschluss an [`AUDIT-energieprofil-werkbank.md`](AUDIT-energieprofil-werkbank.md) (Sichtungs-Session derselbe Tag).
> **Status:** Plan-Entwurf zur Sichtung. Implementierung erst nach expliziter Freigabe in eigener Session.
> **Verwandte Memories:** [[feedback_aggregations_drift]], [[feedback_aggregator_symmetrie]], [[feedback_step_by_step_berechnungs_layer]], [[feedback_vollbackfill_nur_additiv]], [[feedback_release_bundling]].
>
> **Pflicht-Begrenzungen aus dem Auftrag** (gelten für alle Phasen):
> - Werkbank-Plan/Execute-API (Funktions-Signaturen + Response-Shapes der `_plan_*`/`_execute_*`-Funktionen, Frontend-Verträge) bleibt stabil. Additive Felder erlaubt, brechende Änderungen nicht.
> - Keine Daten-Migration, wenn vermeidbar (v3.33.0 lief vier Wochen vorher mit Migration).
> - Per-Feld-Provenance-Layer (`source_provenance` JSON, `data_provenance_log`, `provenance.py`, `source_priority.py`) wird nicht angefasst.
> - Die zwei Konformitäts-Tests aus Audit-§11 Punkt 1 (Backfill-Rettungsliste) + Punkt 3 (Prognose-Liste-Sync) sind Teil der ersten Phase, nicht eigenes Päckchen.

---

## 1. Ziel und Erfolgskriterien

### 1.1 Übergeordnetes Ziel

Den strukturellen Pattern-Befund aus Audit-§0.5 (10+ Aggregator-Drift-Vorfälle innerhalb ~10 Monaten, jeder lokal gepatcht) auf der **Daily-Schreibseite** des Energieprofils so adressieren, dass die nächste Drift-Klasse nicht mehr durch Inspektion sondern durch Test fällt. Die *Hourly*-Schreibseite (analoge Bug-Klasse, Handover-Dokument liegt) bleibt explizit getrennt — sie ist eigene Phase, weil sie eigene Risikolage hat.

### 1.2 Erfolgskriterien (nachweisbar nach v3.34)

| # | Kriterium | Wie nachweisbar |
|---|---|---|
| E1 | Es gibt nur noch **einen** Schreibpfad auf `tages_energie_profil` + `tages_zusammenfassung` für Mess-/Aggregat-Felder (Live-Wetter-Schreiber bleibt separat, siehe Anti-Scope). | Grep nach `INSERT INTO tages_energie_profil` / `INSERT INTO tages_zusammenfassung` liefert genau einen Aufrufer im Aggregator-Modul; `backfill_from_statistics` schreibt nicht mehr direkt. |
| E2 | Symmetrie-Test zwischen Scheduler-Pfad und Backfill-Pfad existiert und ist grün. | Parametrisierter Test analog `test_aggregator_symmetrie.py` (Daily), aber für die Achse Scheduler-Tag vs Backfill-Tag — gleiche Anlage, gleicher historischer Tag, gleiche Quelle → gleiches Ergebnis. |
| E3 | Konformitäts-Test (K1) koppelt die Prognose-Felder-Listen über alle real existierenden Stellen. **Nach Phase A:** drei Stellen (`_PROGNOSE_FELDER_RETTEN` im Aggregator, Hardcode-Liste im Backfill, Schreibfelder in `live_wetter._speichere_prognose`). **Nach Phase B:** zwei Subsystem-Grenzen (Aggregator vs Wetter-Endpoint), weil die Backfill-Liste mit der Backfill-Eigenständigkeit entfällt. Drift in einer der jeweils existierenden Stellen bricht den Test. | Konformitäts-Test wird PR-blockierend, analog ADR-001-Test. Nach Phase B wird der Test schlankweg auf zwei Stellen reduziert, gleiche Test-Datei. |
| E4 | Steuerung „preserve-Logik greift" hängt nicht mehr am `datenquelle`-Magic-String. | Grep nach `datenquelle == "manuell"` im Aggregator liefert keine Verzweigung mehr; semantischer Marker ist explizit. |
| E5 | Verhaltens-Asymmetrie Scheduler-Preserve vs Manuell-Preserve (Audit-§4.2) ist **positiv begründet**: entweder strukturell aufgelöst (Preserve gilt für beide oder für keinen), oder mit nachvollziehbarer Begründung dokumentiert, warum genau diese Anwender-Klasse den Schutz braucht und die andere nicht. Tradeoff-Vermutungen („vermutlich weil sonst stillschweigend alte Werte eingefroren würden") sind keine Begründung — sie reichen als E5-Erfüllung nicht aus und triggern stattdessen die Eskalation aus §3 Phase A.1 letzter Punkt. | Code-Kommentar + CHANGELOG-Eintrag; Begründungs-Qualität wird im Sichtungs-Schritt vor Release geprüft, nicht erst im PR-Review. |
| E6 | Keine Daten-Migration erforderlich. Bestehende TZ/TEP-Rows bleiben unverändert. Verbesserte Boundary-Werte greifen nur bei aktiver Neu-Aggregation (User-Trigger oder nächster Scheduler-Lauf für heutigen/gestrigen Tag). | DB-Migrations-Verzeichnis enthält keinen neuen Eintrag für v3.34. |

### 1.3 Verhaltenserhaltend? — Drei Stufen

- **Verhaltens­identisch bei semantisch äquivalenter Projektion:** Phase A. Geschriebene Werte (TEP/TZ + Provenance + `datenquelle`-Spalte) unverändert; Aggregator-Code wird durch Enum-Pflichtparameter + Wegfall der String-Verzweigung minimal-invasiv umgestellt, der Enum projiziert auf dieselben Magic-Strings, die heute direkt verwendet werden.
- **Verhaltens­erhaltend bis auf stille Datenkorrektur:** Phase B (Backfill-Konsolidierung). Wenn ein Anwender heute auf einem Tag re-aggregiert, dessen Snapshot-DB leer ist (typisch für Tage vor dem ersten Snapshot-Lauf) **und** dessen HA-LTS-Boundary belegt ist, würde Backfill bisher snapshot-leere Komponenten-Boundary liefern, nach Phase B LTS-Komponenten-Boundary. Das ist eine *Verbesserung*. Für bereits in der DB stehende Tage greift sie erst beim nächsten User-Trigger, also keine automatische Migration.
- **Verhaltens­erhaltend bis auf latenten Bugfix:** Phase C (Hourly-Helper). Strukturelle Auflösung des E-Auto-Doppelmapping-Bugs; Anwenderbericht bisher nicht vorhanden (Audit-§6.2), Wirkung damit für die meisten Anwender unsichtbar.

---

## 2. Phasen + Reihenfolge

Drei Phasen, jede eigenständig releasebar. Reihenfolge zwingend — Phase B braucht den Source-Marker aus A, Phase C ist von B unabhängig, kann auch ohne B fliegen, profitiert aber strukturell von B.

| # | Inhalt | Release-Hülle (Vorschlag) | Pflicht für v3.34? |
|---|---|---|---|
| **Phase A** | Konformitäts-Tests + Source-Marker (Enum) + Asymmetrie-Klärung | v3.34.0 | Ja |
| **Phase B** | Backfill-Konsolidierung (ein Schreibpfad) | v3.34.1 (Fallback v3.34.2 bei Verzögerung — **nicht v3.35.0**, das ist Phase C reserviert) | Ja, sonst kein E1/E2 |
| **Phase C** | Hourly-Helper-Migration (`_categorize_counter`-Bugfix strukturell) | v3.35.0 (eigene Etappe nach Tester-Zyklus auf v3.34) | Nein — eigene Etappe mit eigenem Sichtungs-/Übergabe-Zyklus (Begründung §7 Punkt 1) |

**Nicht-Anweisung:** zwischen Phase A und Phase B sollte mindestens ein normaler Tester-Zyklus liegen, damit Drift-Erkennungs-Tests in der echten Tester-Last laufen, bevor der größere Schnitt fliegt. **Phase C als v3.35.0** bedeutet nicht „später wenn Zeit", sondern: nach einem normalen Tester-Zyklus auf v3.34, mit eigenem Sichtungs-Schritt analog zur heutigen Audit-Sichtung und eigenem Übergabe-Prompt für die nächste Plan-Session. Ohne aktiven Termin läuft das Vorhaben in die „später wenn Zeit"-Zone — dem soll das CHANGELOG-Framing des v3.34-Release entgegenwirken (siehe §6, Verweis auf v3.35-Folge-Etappe).

---

## 3. Phasen-Details

### Phase A — Vorarbeiten + Tests + Marker

**Ziel:** Drift-Erkennung scharf stellen und den Magic-String-Steuerungs-Trigger entkoppeln, ohne Verhalten zu ändern.

#### A.1 Scope

- Konformitäts-Test K1 — Prognose-Felder-Sync zwischen drei Stellen (`_PROGNOSE_FELDER_RETTEN` im Aggregator, Hardcode-Liste im Backfill, Schreibfelder in `live_wetter._speichere_prognose`). Erfüllt Auftrags-Pflicht §11 Punkt 1+3. **Rolle des Tests:** Übergangs-Sicherung bis Phase B die Aggregator-vs-Backfill-Listen-Achse strukturell auflöst (nach B existiert die Backfill-Liste nicht mehr — Backfill schreibt nicht eigenständig). Nach B bleibt K1 als Schutz an der einzigen verbleibenden Subsystem-Grenze (Aggregator vs Wetter-Endpoint). Eine geteilte Konstante zwischen Aggregator und Wetter-Endpoint wurde verworfen (§7 Punkt 3), weil sie zwei Subsysteme mit unabhängigen Lebenszyklen verkleben würde — die saubere Auflösung dieser Grenze wäre die Prognose-Tabellen-Auslagerung (Audit-§10.4), die im Anti-Scope §5 bewusst draußen bleibt.
- Konformitäts-Test K2 — Symmetrie-Vorbereitung Daily-Pfad: gemeinsame Helper-Liste aller Felder, die `aggregate_day` auf TZ schreibt. Test stellt sicher, dass jede Spalte mindestens eines der drei Schicksale hat: (a) wird von `aggregate_day` gesetzt, (b) steht auf `_PROGNOSE_FELDER_RETTEN` (extern befüllt), (c) ist in einer expliziten Allowlist „bleibt NULL". Verhindert Drift-Klassen wie „neue Spalte hinzugefügt, Aggregator vergisst sie".
- Source-Marker — ein **typsicheres Enum** (`Source.Scheduler | Source.MonatsabschlussBackfill | Source.ManualRepair` — das sind die drei heutigen `aggregate_day`-Aufrufer) wird als Pflichtparameter an `aggregate_day` eingeführt. Begründung siehe §7 Punkt 2: ein Boolean `is_manual_repair` würde nur eine der drei heute Magic-String-gesteuerten Verzweigungen abdecken (preserve-Trigger), die anderen zwei (`auto_writer = f"energieprofil:{datenquelle}"` für die Provenance, `TagesZusammenfassung.datenquelle`-Spaltenwert für die UI) blieben Magic-String-basiert — exakt die Pattern-Klasse aus Audit-§0.5. Das Enum projiziert via `to_db_string()` auf die bisherigen `datenquelle`-Spaltenwerte (UI ändert nichts) und via `to_provenance_source(hourly_source: ...)` auf den Provenance-Source-String. Phase B fügt `Source.VollbackfillFromLts` hinzu, weil dort `backfill_from_statistics` erstmals durch `aggregate_day` läuft — typsicher statt eines weiteren Magic-Strings (heute `"ha_statistiken"`).
- Asymmetrie-Klärung Scheduler-Preserve vs Manuell-Preserve (Audit-§4.2 Frage): Inline-Kommentar im Aggregator + CHANGELOG-Eintrag, der die heutige Entscheidung dokumentiert. Falls beim Schreiben des Kommentars klar wird, dass die Asymmetrie kein Tradeoff sondern ein Vorfall war, eskaliert das Thema in eine eigene Diskussion **vor** Phase B.

#### A.2 Tests

- K1 läuft als Unit-Test, der die drei Listen einliest und Gleichheit als Menge prüft. Bricht bei jedem Drift.
- K2 läuft als Unit-Test gegen das SQLAlchemy-Modell + Aggregator-Code (Inspektion der gesetzten Spalten in `aggregate_day`).
- Source-Marker: Test-Setup mit Mock-DB, Aufruf mit `source=Source.ManualRepair` führt zur preserve-Pfad-Aktivierung; andere Enum-Werte (`Scheduler`, `MonatsabschlussBackfill`) nicht. Zusätzlicher Test: `to_db_string()` + `to_provenance_source(...)` liefern für jeden Enum-Wert die bisherigen Magic-String-Werte (Regressions-Schutz für UI-/Provenance-Konstanz).
- Bestehende Test-Suite muss vollständig grün bleiben (479 Tests laut Stand v3.32.4 + die in v3.33.0 ergänzten Symmetrie-Tests).

#### A.3 Risiken

- Konformitäts-Test K2 könnte heute bereits rot sein — entweder weil eine Spalte unerwartet nicht gesetzt wird, oder weil die „bleibt NULL"-Allowlist Spalten enthält, die bei genauerem Hinsehen doch gesetzt werden sollten. Beide Fälle sind *Befunde*, die in Phase A erscheinen und entweder als Pflicht-Fix in A oder als bewusste Schiebung in B aufgenommen werden müssen.
- Source-Marker als Pflicht-Enum-Parameter ändert die Aufrufsignatur. Kein Default — alle Aufrufstellen müssen explizit gesetzt werden. Vorab Grep nach Aufrufstellen + Umstellen auf Keyword-Args ist Pflicht-Schritt vor dem Einbau.
- Enum-Projektions-Methoden (`to_db_string`, `to_provenance_source`) zentralisieren die heute drei verstreuten Magic-String-Quellen. Falls in der Codebase weitere Magic-String-Werte für `TagesZusammenfassung.datenquelle` existieren, die im Audit nicht auftauchten (Test-Fixtures, die direkt setzen; ältere Migrations-Skripte; Inline-Repair-Tools), müssen sie beim Enum-Mapping aufgenommen werden. Vorab Grep auf `datenquelle\s*=\s*"` + `datenquelle:` über die gesamte Codebase (`backend/`, `tests/`, `scripts/`) findet alle Setter-Stellen. Cloud-Import-Pfade sind irrelevant — sie schreiben auf `Monatsdaten`, nicht auf TZ (Audit-§9).

#### A.4 Akzeptanzkriterien

- K1 und K2 sind im CI-Pflicht-Pfad und grün.
- Source-Marker (Enum) ist eingeführt, alle bestehenden `aggregate_day`-Aufrufer setzen ihn explizit. Die drei bisherigen Magic-String-Verzweigungen (preserve-Trigger, Provenance-Writer-Format, `datenquelle`-Spaltenwert) laufen über das Enum bzw. seine Projektions-Methoden. Der Magic-String existiert in der DB-Spalte und UI weiter — aber als Output des Enums, nicht mehr als Eingangs-Trigger im Aggregator. Grep auf `datenquelle ==` im Aggregator-Modul liefert keine Verzweigung mehr (E4).
- CHANGELOG-Eintrag dokumentiert Phase A als Vorbereitung; keine User-spürbare Funktionsänderung.

### Phase B — Backfill-Konsolidierung

**Ziel:** Audit-§6.1 (parallele Top-Level-Schreibpfade) strukturell auflösen — Erfolgskriterium E1 + E2.

#### B.1 Scope

- `backfill_from_statistics` wird zur dünnen Schleife über `aggregate_day`. Die Stunden-Datenbeschaffung (heute HA-Statistics-Range-Bulk-Read `get_hourly_sensor_data` einmal pro Range) bleibt im Backfill-Modul; sie wird über eine pre-fetched-Datenstruktur an `aggregate_day` durchgereicht. Die konkrete Form (zusätzlicher optionaler Parameter `prefetched_hourly_data: dict[date, dict] | None`) ist Implementierungs-Detail.
- Backfill-eigene Komponenten-Aggregation entfällt — die Beiträge-Berechnung läuft über `komponenten_beitraege.py` (in v3.33.0 als geteilter Helper eingeführt).
- Backfill-eigene Boundary-Logik (Audit-§3.4, §8.2): entfällt; Boundary-Pfad läuft über die in `aggregate_day` etablierte LTS-bevorzugt-Logik.
- Backfill-eigene 5-Felder-Rettungsliste: entfällt — Backfill schreibt nicht mehr direkt, einzige verbleibende Liste ist `_PROGNOSE_FELDER_RETTEN` im Aggregator. Damit löst Phase B die Aggregator-vs-Backfill-Achse der §11-Punkt-1-Pflicht **strukturell**. K1 aus Phase A bleibt im CI als Schutz an der verbleibenden Subsystem-Grenze (Aggregator vs `live_wetter._speichere_prognose`), siehe Phase A K1-Rolle.
- Die Felder, die heute der Backfill *nicht* setzt (Audit-§6.1: Peaks aus LTS, Strompreis-Stunden, `boersenpreis_avg_cent`, `negative_preis_stunden`, `einspeisung_neg_preis_kwh`), werden in der konsolidierten Form automatisch gesetzt, weil `aggregate_day` sie setzt. **Das ist eine stille Datenverbesserung** — siehe §6 Tester-Kommunikation.
- `aktiv_im_zeitraum`-vs-`aktiv_jetzt`-Asymmetrie (Audit-§6.4) — **eigener kleiner Schnitt in B.1**, nicht Nebensatz: heute existieren zwei Aktiv-Filter (`aktiv_jetzt` Scheduler-Pfad, `aktiv_im_zeitraum` Backfill-Pfad), die für historische Tage abweichende Resultate liefern können (stillgelegte Investitionen). In der konsolidierten Form braucht `aggregate_day` einen Per-Tag-Filter `aktiv_am_tag(datum)` als dritte Variante — entweder neuer Helper im `utils/investition_filter`-Modul oder Methoden-Wrapper, der je nach Datum auf die passende existierende Variante zeigt. Konkrete Form ist Implementierungs-Detail; **dass es eine eigene Filter-Variante ist, gehört in den Phase-B-Scope explizit hinein**, nicht als Folgerung versteckt. Symmetrie-Test S1 muss historische Tage mit zwischenzeitlicher Stilllegung als Konstellation enthalten.

#### B.2 Tests

- Symmetrie-Test S1 (E2): historischer Tag, gleiche Anlage, identische HA-LTS-/Snapshot-Datenlage → Scheduler-Pfad-Ergebnis == Backfill-Pfad-Ergebnis. Parametrisiert über die Konstellationen aus Audit-§3.6 (HA-Add-on normal, LTS-Lücke, Standalone-MQTT, …) — soweit fixtur-bar.
- Symmetrie-Test S2: ein Tag, der heute durch Backfill geschrieben wurde, vs. derselbe Tag nach erneutem Lauf durch konsolidierten Pfad → erwartete Felder gleich; die heute leer gelassenen Felder (Peaks etc.) sind neu gefüllt. Test dokumentiert das erwartete Delta explizit.
- Bestehende Test-Suite (inkl. Phase-A-Tests) grün.
- Konformitäts-Test aus Phase A (K1/K2) bleibt im CI, fängt jede Liste-Drift zwischen den konsolidierten Stellen.

#### B.3 Risiken

- **Backfill-Verhalten ändert sich für nicht-Schreib-relevante Aspekte** (Per-Tag-Performance, DB-Lock-Verhalten, Memory-Footprint des HA-Statistics-Range-Bulk-Reads). Wenn `aggregate_day` pro Tag einen eigenen HA-Statistics-Read auslöst statt den Bulk-Read zu nutzen, kann ein Vollbackfill über 12 Monate signifikant langsamer werden. **Mitigation:** pre-fetched-Daten-Durchreichung ist Pflicht-Bestandteil von B.1; ohne sie nicht releasen. Performance-Test in S1/S2 mit Fixtur über 30 Tage als Sanity-Check.
- **Per-Tag-Commit (#291)** muss in der konsolidierten Form erhalten bleiben — sowohl beim Scheduler-Range als auch beim Backfill-Range. Test-Fall: verschachtelte async-Tasks im selben Worker-Event-Loop (Scheduler-Job läuft, parallel triggert Werkbank-Operation `_execute_reaggregate_range`), beide halten DB-Sessions, ohne Per-Tag-Commit greift SQLite-`busy_timeout`-Pfad. Single-Worker — keine echten OS-parallelen Schreiber, aber die async-Verschachtelung erzeugt dasselbe Lock-Verhalten, das #291 motiviert hat.
- **`_sonderschluessel`-Asymmetrie** (Audit-§8.3, `{"strompreis", "haushalt"}` nur im Aggregator): Im konsolidierten Pfad fällt diese Asymmetrie automatisch weg. Falls es im konsolidierten Pfad einen impliziten Verlass auf das Backfill-Verhalten gab, wird der hier sichtbar. Symmetrie-Test S1 sollte das fangen.
- **Werkbank-VOLLBACKFILL-Operation** ruft heute `resolve_and_backfill_from_statistics` → `backfill_from_statistics`. Der äußere Werkbank-Endpunkt + die Response-Form (`status`-Map mit `geschrieben`/`uebersprungen_*`-Countern) bleibt unverändert. Innen wird umgeschaltet auf die konsolidierte Schleife. Pflicht-Test: VOLLBACKFILL-Endpoint-Response-Schema-Test (vor- und nach-Phase-B identisch).

#### B.4 Akzeptanzkriterien

- E1 erfüllt (Grep auf `INSERT INTO tages_*`).
- E2 erfüllt (S1 grün).
- Werkbank-Endpoint-Schema-Tests grün, keine Frontend-Anpassung nötig.
- Konformitäts-Tests K1/K2 grün.
- Performance-Sanity (30-Tage-Backfill in Test-Umgebung) im selben Größenbereich wie vorher (±30 %).
- CHANGELOG-Eintrag dokumentiert die stille Datenverbesserung (siehe §6).

### Phase C — Hourly-Helper-Migration

**Ziel:** Audit-§6.2 + [`HANDOVER-hourly-categorize-eauto-doppelmapping.md`](HANDOVER-hourly-categorize-eauto-doppelmapping.md) strukturell schließen. Erfolgskriterium: latenter E-Auto-Doppelmapping-Bug fällt durch Test, nicht durch Inspektion.

#### C.1 Scope

- `_categorize_counter` (`snapshot/keys.py`) wird auf Mapping-Pre-Normalisierung umgestellt — die `sensor_mapping`-Auflösung passiert einmalig zentral (Analogie: `komponenten_beitraege.py` für Daily-Boundary).
- Beide Hourly-Aggregatoren (`get_hourly_kwh_by_category`, `get_hourly_kwh_by_category_lts`) konsumieren das normalisierte Mapping; doppelmappende Sensoren werden in der Normalisierungs-Schicht aufgelöst, nicht in den Aggregatoren.
- Symmetrie-Test analog Daily-Pfad — parametrisiert über Either-Or-Konstellationen für Hourly, inkl. E-Auto-Parent-Skip, BKW-Pool-Schema und Wallbox/E-Auto-Shared-Sensor.

#### C.2 Tests

- Symmetrie-Test S3: 24-Stunden-Lauf eines Tages mit konstruiertem Doppelmapping (E-Auto mit `verbrauch_kwh` UND `ladung_kwh`) → Σ über Hourly == Tages-Boundary. Bricht heute ohne Migration; muss nach C grün sein.
- Konformitäts-Test K3: die Normalisierungs-Helper-Auflösung darf keinen Sensor zweimal in zwei Kategorien zählen. Strukturell prüfbar.

#### C.3 Risiken

- Anwender-Wirkung ist nicht-trivial **wenn** Doppelmapping in echten Setups auftritt. Pre-Release-Check: Daten-Checker-Report über alle Tester-Anlagen, ob das Doppelmapping-Muster vorkommt. Wenn ja: explizite Forum-Notification, weil sich Hourly-Werte für diese Anlagen ändern werden (vermutlich Halbierung verdoppelter Verbrauchs-Werte).
- Phase C berührt das Snapshot-Subsystem (`snapshot/keys.py` + beide Hourly-Aggregatoren), das im Audit-§10.7 als „nicht anfassen" markiert wurde. Phase C verletzt das bewusst — die Migration ist genau die Erlaubnis, dort einzugreifen, weil der Bug strukturell nur dort lösbar ist.

#### C.4 Akzeptanzkriterien

- S3 + K3 grün.
- Daten-Checker-Pre-Release-Lauf identifiziert betroffene Anlagen, Kommunikation entsprechend §6.
- Konformitäts-Tests aus A/B bleiben grün.

---

## 4. Rollback/Mitigation pro Phase

| Phase | Rollback-Strategie | Mitigation während des Refactors |
|---|---|---|
| A | Tests sind reine Additionen; Source-Marker-Einführung berührt Aggregator + alle Aufrufstellen, ist aber semantisch verhaltens­identisch (Projektion auf bisherige Magic-Strings). Rollback = `git revert` des Enum-Commits — reicht, weil Single-Worker-Codebase ohne persistierte Marker-Zustände. Konformitäts-Tests können bei Bedarf temporär als `xfail` markiert werden — Auftrags-Memory [[feedback_aggregator_symmetrie]] sagt jedoch „Pflicht-Test schreiben" → `xfail` nur mit dokumentierter Begründung. | Enum-Einführung und Aufruf-Stellen-Umstellung in einem **eigenen Commit** vor dem Magic-String-Verzweigungs-Entfernungs-Commit — so kann der zweite Commit isoliert revertiert werden, falls die Verzweigungs-Auflösung Regressionen zeigt, ohne den Enum-Boilerplate-Aufbau zu verlieren. |
| B | Größere Code-Bewegung; Rollback = Revert des konsolidierenden Commits. Die alte `backfill_from_statistics`-Implementierung wird im Commit gelöscht, aber bleibt im Git-Verlauf greifbar. Single-Worker-Codebase, ein-Commit-Revert ist sauber. | Vor dem Release ein **Schatten-Vergleichs-Lauf** in einer lokalen Test-DB: alter Backfill schreibt in eine Schatten-Tabelle, neuer Backfill in die echte; Diff wird inspiziert. Schatten-Code danach entfernt (nicht ins Release). Damit ist die stille Datenverbesserung vor dem Release einmal real verifiziert. |
| C | Wie B (klassischer Revert). Phase C ist von B logisch unabhängig — falls B regrediert, kann C trotzdem fliegen, falls C regrediert, kann B davorbleiben. | Daten-Checker-Pre-Release-Scan vorausschicken; falls echte Anwender-Setups Doppelmapping zeigen, Phase C als **angekündigtes** Release fliegen lassen (Forum-Notification 1 Tag vorher) statt als stille Korrektur. |

**Allgemein:** Jede Phase fliegt erst, wenn die Phase davor mindestens einen normalen Tester-Zyklus überlebt hat. Keine Bundle-Releases („Big Bang") über mehrere Phasen — verstößt gegen [[feedback_release_bundling]] und gegen die Audit-§0.5-Lehre, dass Pattern-Reduktion nur durch enge Iterations-Schleifen verifizierbar wird.

---

## 5. Anti-Scope — was bewusst NICHT in v3.34 gehört

| Punkt | Audit-§ | Begründung |
|---|---|---|
| Prognose-Felder aus TZ in eigene Tabelle auslagern | §10.4 | Entschieden in §11 Punkt 3: zu kurz nach v3.33.0-Migration; Konformitäts-Test (Phase A K1) deckt die Drift-Klasse ab. |
| `rollup.py` (Monatsdaten-Schreiber) anfassen | §9, §11 Punkt 2 | Out-of-Scope; Pflicht-Notiz für späteren Refactor in Audit-§9 dokumentiert. |
| Werkbank Plan-Diff-Refactor (gemeinsame Diff-API über alle Operationen) | §10.5 | Verstößt gegen Auftrags-Pflichtbegrenzung „Plan/Execute-API stabil"; eigene Etappe. |
| In-Memory-Plan-Cache → Redis (Multi-Worker-Tauglichkeit) | §8.7 | Single-Worker-Codebase bleibt; kein akuter Druck. |
| Vollbackfill-Flag von Boolean → Status-Enum | §8.11 | Datenmodell-Aufweichung; kein akuter Anwender-Schmerz. |
| Pool-Dedup → Setup-Wizard-Validierung | §4.10 | Setup-Wizard-Subsystem, nicht Energieprofil. |
| Spike-Cap-Diagnose-Sichtbarkeit (Snapshot-Subsystem) | §4.6, §4.7 | Memory-Konflikt mit [[feedback_grenze_externe_daten_diagnose]] — diskussionswürdig, aber außerhalb des Daily-Schreibpfad-Fokus. |
| Reaggregate-Today-Filter auf Per-Anlage-Filter | §8.10 | UI-Cleanup, kein struktureller Drift-Vektor. |
| Provenance-Skip-Liste für Stundenprofil-Felder | §8.8 | Kosmetisch; Provenance-Layer wird nicht angefasst (Pflichtbegrenzung). |
| DELETE_MONATSDATEN, KRAFTSTOFFPREIS_BACKFILL, RESET_CLOUD_IMPORT, SOLCAST_REWRITE | Audit-§7 | Funktionieren stabil oder sind als Stub markiert; kein Refactor-Bedarf. |
| Snapshot-Subsystem (`services/snapshot/*`) berühren | §10.7 | **Ausnahme: Phase C** berührt `snapshot/keys.py` + Hourly-Aggregatoren — bewusste Verletzung, weil die Hourly-Bug-Klasse nur dort lösbar ist. Restliche Snapshot-Module (reader, fallback, plausibility, aggregator-Tagesreset-Logik) bleiben unangetastet. |
| Live-Σ-Bypass-Bedingung (Audit-§3.2, §4.9) auflösen durch BKW-Key-Harmonisierung | §4.9 | Standalone-Pfad-Risiko, aber kein aktueller Anwenderbericht; eigene Etappe für die Live-Service-Key-Konvention. |

---

## 6. Tester-Kommunikation

| Phase | CHANGELOG-Framing | Forum-Notification? |
|---|---|---|
| A | „Drift-Erkennung für Aggregat-Felder verschärft (Konformitäts-Tests, Vorarbeit für v3.34.x-Refactor). Keine User-spürbare Funktionsänderung." | Nein. |
| B | „Vollbackfill ist jetzt strukturell identisch mit dem täglichen Aggregat-Lauf. **Stille Verbesserung:** für Tage, die per Vollbackfill geschrieben wurden, fehlen heute Peaks, Strompreis-Stunden und Börsenpreis-Felder; diese werden bei erneuter Aggregation (Werkbank → „Tag(e) neu aggregieren" oder „Vollbackfill") nun automatisch befüllt. Bestehende Werte bleiben unverändert, bis du selber re-aggregierst." | Optional — abhängig davon, wie viele Tester betroffene Backfill-Tage haben. Wenn ja: kurzer Hinweis im aktuellen Forums-Thread (kein eigener Post), Pattern [[feedback_pn_kein_vor_argumentieren]]. |
| C | „E-Auto-Doppelmapping in der Stunden-Aggregation strukturell behoben. Falls dein E-Auto-Sensor mehrere Mess-Felder hat (`verbrauch_kwh` + `ladung_kwh`), waren Hourly-Werte bisher latent doppelt gezählt." | **Ja, wenn Daten-Checker-Pre-Release-Lauf echte Treffer findet** — 1-Tag-Vorlauf-Notification mit Hinweis auf konkrete Anlagen-Werte-Korrektur. Sonst nur CHANGELOG. |

**Phase C als v3.35.0-Ankündigung im v3.34-CHANGELOG:** Der CHANGELOG-Eintrag zu Phase B nimmt am Ende einen Satz auf, dass die Hourly-Aggregat-Symmetrie (analog zur in v3.33.0 sanierten Daily-Symmetrie) als v3.35.0 angekündigt ist — analog dem v3.32.4 → v3.33.0-Ankündigungs-Pattern. Damit ist Phase C auch nach außen terminiert, nicht „später wenn Zeit". Wenn der CHANGELOG des v3.34-Release diesen Anker nicht trägt, ist der Plan-§2-Termin „v3.35.0 nach Tester-Zyklus" nicht durchgesetzt — Folge: in 4 Wochen muss aktiv geprüft werden, ob Phase C konkret terminiert wurde.

**Memory-Konsistenz-Checks für Kommunikation:**
- [[feedback_release_bundling]]: drei Phasen sind ok, weil jede einen eigenen sichtbaren Wert hat (Phase A: Test-Schärfung; B: Vollständigkeits-Verbesserung Backfill; C: latenter Bugfix).
- [[feedback_user_fehlermeldungen]]: keine Phase verschiebt Diagnose-Last auf den User; im Gegenteil, Drift-Erkennung wird strenger.
- [[feedback_keine_vor_screenshot_pakte]]: Phase C kein Pre-Screenshot-Druck auf Tester; nur Daten-Checker-Auswertung intern.
- [[feedback_externer_druck_reflex]]: keine Phase ist als Reaktion auf externen Druck konstruiert.

---

## 7. Geklärt in Sichtungs-Session (2026-05-24, Anschluss)

Drei beim Planen aufgetauchte Punkte, in dieser Sichtungs-Session geklärt und in §2 / §3 / §5 / §6 eingearbeitet. Hier festgehalten, damit die Entscheidungs-Spur sichtbar bleibt.

1. **Phase C als v3.35.0, eigene Etappe.** Begründung: Phase C ist Anwender-sichtbar (Halbierung verdoppelter Verbrauchs-Werte bei betroffenen Setups, §6), während A+B latent sind — andere Tester-Kommunikations-Klasse. Phase C berührt das Snapshot-Subsystem (§5 Anti-Scope-Ausnahme), das in v3.34 sonst unangetastet bleibt; Subsystem-Wechsel in eigene Etappe isolieren. [[feedback_release_bundling]] + [[feedback_aggregator_symmetrie]]: zwei strukturelle Schnitte hintereinander im selben Subsystem erzeugen das Bug-Pattern, das v3.34 aufräumen will — Tester-Zyklus zwischen den Schnitten ist die Disziplin. Pre-Release-Daten-Checker-Scan für C läuft sauberer ohne parallele B-Tester-Last. **Eingearbeitet in §2** (Tabelle + Nicht-Anweisung) **und §6** (Phase-C-als-v3.35-Ankündigung im v3.34-CHANGELOG, damit der Termin auch nach außen verbindlich wird).

2. **Source-Marker als Enum, nicht Boolean.** Begründung: der Magic-String `datenquelle` steuert heute drei Verzweigungen — preserve-Trigger ([aggregator.py:581/589](../../eedc/backend/services/energie_profil/aggregator.py#L581)), Provenance-Writer-Format via `auto_writer` ([aggregator.py:89](../../eedc/backend/services/energie_profil/aggregator.py#L89)), `datenquelle`-Spaltenwert. Ein Boolean `is_manual_repair` deckt nur die erste ab; die anderen zwei bleiben Magic-String-basiert und wachsen in Phase B um einen weiteren Wert — exakt die Pattern-Klasse aus Audit-§0.5. Enum mit `to_db_string()`/`to_provenance_source()`-Projektion erschlägt die Klasse strukturell, UI sieht die existing Spaltenwerte weiter. **Eingearbeitet in §3 Phase A.1 (Source-Marker-Punkt) + §3 Phase A.3 (Risiken) + §3 Phase A.4 (Akzeptanzkriterien).**

3. **K1-Test ja, geteilte Konstante über Subsystem-Grenze nein.** Begründung: Phase B löst die Aggregator-vs-Backfill-Listen-Achse strukturell auf — nach B existiert die Backfill-Liste nicht mehr, weil Backfill nicht eigenständig schreibt. Was bleibt, ist die Achse Aggregator vs `live_wetter._speichere_prognose` (zwei verschiedene Subsysteme mit unabhängigen Lebenszyklen). Eine geteilte Konstante hier würde die Subsysteme verkleben — die saubere Auflösung dieser Grenze wäre die Prognose-Tabellen-Auslagerung (Audit-§10.4), die im Anti-Scope §5 bewusst draußen bleibt. K1 bleibt als Subsystem-Grenzen-Schutz, ohne die Grenze zu verwischen. **Eingearbeitet in §3 Phase A K1-Beschreibung (Rolle des Tests) + §3 Phase B.1 Rettungslisten-Punkt (was nach B übrig bleibt).**

Implementierung erst nach expliziter Freigabe in eigener Session, mit aufgefrischtem Übergabe-Prompt aus dem konsolidierten Plan-Stand.
