# ADR-001 — Berechnungs-Layer als Single Source of Truth

**Status:** Akzeptiert (2026-05-19)
**Auslöser:** BKW-Doppelzählung in `komponenten_kwh` (Rainer-PN), gefunden bei Code-Audit nach Anwender-Drift-Meldung. Strukturelle Ursache: paralleler Schreibpfad (Live-Σ-Riemann + HA-LTS-Boundary) mit Schema-Mismatch.

## Regel

Alle Aggregat-Berechnungen über die zentralen Daten-Tabellen (`TagesEnergieProfil`, `TagesZusammenfassung`, `InvestitionMonatsdaten`) — Whitelist-Filter, Σ-Helper, Invarianten, Sub-Key-Resolver, Kennzahlen — werden in `backend/core/berechnungen/` definiert. Domain-Module (`services/`, `api/routes/`) sind ausschließlich Konsumenten.

**Pflicht ab heute:**
1. Neuer Code mit Aggregat-Berechnung wird im Berechnungs-Layer definiert. Domain-Module importieren.
2. Wenn bestehender Code mit duplizierter Aggregat-Logik aus anderem Grund angefasst wird, MUSS dieser Touch die Migration auf den Layer beinhalten.
3. Der Pytest-Konformitäts-Test `tests/test_berechnungs_layer_konformitaet.py` blockiert PRs mit neuen Whitelist-/Inline-Pattern-Definitionen außerhalb des Layers.
4. Der Aggregator (`energie_profil/aggregator.py::aggregate_day`) ruft die Pflicht-Invariante `pruefe_tep_tz_konsistenz` am Ende jedes Schreib-Laufs auf. Verletzung wird als Warning geloggt — Tag wird nicht zurückgehalten, aber Drift ist sofort sichtbar.

## Was bleibt erlaubt

- Bestehende SoT-Module (`core/calculations.py`, `core/field_definitions.py`, `snapshot/plausibility.py`, `snapshot/lts_aggregator.py`, `snapshot/aggregator.py`) bleiben funktional und werden formal als Teil des Berechnungs-Layers betrachtet — sie werden nicht zwingend umgezogen, aber Aufrufer dürfen nicht inline re-implementieren.
- Inline-Σ-Logik innerhalb eines einzelnen Moduls (z.B. lokale Hilfsvariable für eine einzige Funktion) ist OK, solange sie nicht woanders dupliziert wird.

## Was NICHT erlaubt ist

- Eigene Whitelist-Konstanten wie `_PV_PREFIXES = ("pv_", "bkw_")` außerhalb des Layers — direkt aus `backend.core.berechnungen` importieren.
- Inline-Pattern wie `k.startswith("pv_") or k.startswith("bkw_")` außerhalb des Layers — `summe_pv_bkw_kwh()` aus dem Layer benutzen.
- Parallel-Implementierungen von Σ-Berechnungen über dieselben Tabellen-Felder.

## Migration bestehender Konsumenten

Step-by-step, opportunistisch beim nächsten Touch des betroffenen Codes. Übersicht der bekannten offenen Stellen: siehe Memory `project_berechnungs_layer_offen.md` und `INLINE_PATTERN_GRANDFATHERED` in `tests/test_berechnungs_layer_konformitaet.py`.

Beim Migrieren:
1. Konsument importiert aus `backend.core.berechnungen`.
2. Lokale Whitelist-Definitionen und Inline-Patterns löschen.
3. Eintrag aus `INLINE_PATTERN_GRANDFATHERED` entfernen (Test `test_grandfathered_dateien_existieren_und_enthalten_pattern` meckert sonst).
4. Test-Suite grün halten.

## Verbundene Konzepte

- `docs/KONZEPT-BERECHNUNGS-LAYER.md` — Architektur-Detail, Submodul-Schnitt, geplante Erweiterungen
- `docs/KONZEPT-DATENPIPELINE.md` Abschnitt 3.4 — „Zentraler Helper Pflicht"
- `docs/archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` — Etappe-4-Auslöser, dessen unvollständiger Riemann-Pfad-Rückbau das Berechnungs-Layer-Konzept erst nötig gemacht hat
- `docs/KONZEPT-COUNTER-DAILY-DRIFT.md` — analoge Drift-Klasse für Counter-Felder, wird Teil des Berechnungs-Layers (`counter`-Submodul) wenn die Stelle angefasst wird

## Verbundene Memory-Einträge

- `feedback_aggregations_drift` — Drift-Pattern (Read-Side, jetzt erweitert um Write-Side via Berechnungs-Layer)
- `feedback_eigenen_code_zuerst` — Verhaltens-Lehre nach BKW-Vorfall: bei jeder Anwender-Drift-Meldung ZUERST eigenen Berechnungscode prüfen
- `feedback_step_by_step_berechnungs_layer` — Migrations-Disziplin für diesen Layer
