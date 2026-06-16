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

## Geteilter Helper ≠ gelöste Drift — auch die EINGABE muss zentral (Lehre #326)

Ein gemeinsamer Aggregat-Helper (z. B. `berechne_finanz_aggregat`) liefert nur dann denselben Wert über alle Read-Sites, wenn er auch **dieselben Eingaben** bekommt. In #326 nutzten zwar alle vier Finanz-Read-Sites denselben Helper, **bauten ihre Eingaben (`FinanzMonatsZeile`) aber jede selbst** — eine löste den Strompreis pro Monat (historische Tarife), zwei nahmen den neuesten Tarif für alle Jahre → ~174 € Drift, die viermal nacheinander auftauchte (jede Reparatur deckte den nächsten Parallelpfad auf). Der WeasyPrint-Jahresbericht (neu 04/2026) riss dabei einen längst gelösten Tarif-Bug wieder auf, weil neuer Code die alte Lösung nicht kannte.

**Regel — bei einer Kennzahl, die an ≥2 Read-Sites gebaut wird:**

1. **Gemeinsamer Eingabe-Builder**, nicht nur ein Formel-Helper. Die Konstruktion des Eingabe-Objekts (inkl. drift-anfälliger Auflösungen wie Tarif-pro-Monat) gehört in **eine** Funktion (DB-I/O → Service-Schicht, nicht core). Beispiel: `services/finanz_zeilen.py` `baue_finanz_zeile`.
2. **Statischer Wächter**, der die Konstruktion außerhalb des Builders verbietet (analog `test_finanz_monatszeile_nur_im_builder`) — so kann auch **künftiger** Code die zentrale Auflösung nicht umgehen.
3. **Symmetrie-Test**, der „Site A == Site B == …" für eine realistische Fixture beweist (inkl. der Edge-Cases, die der Default-Pfad umgeht — z. B. mehrere Jahres-Tarife OHNE Monats-Flex-Ø).

Symmetrie-Test allein reicht nicht (er kennt nur die eingetragenen Sites); statischer Wächter allein reicht nicht (er fängt Formel-, nicht Wert-Drift). Erst der Builder macht Drift strukturell unmöglich; Wächter + Symmetrie-Test sichern es ab.

## Migration bestehender Konsumenten

Step-by-step, opportunistisch beim nächsten Touch des betroffenen Codes. Übersicht der bekannten offenen Stellen: siehe Memory `project_berechnungs_layer_offen.md` und `INLINE_PATTERN_GRANDFATHERED` in `tests/test_berechnungs_layer_konformitaet.py`.

Beim Migrieren:
1. Konsument importiert aus `backend.core.berechnungen`.
2. Lokale Whitelist-Definitionen und Inline-Patterns löschen.
3. Eintrag aus `INLINE_PATTERN_GRANDFATHERED` entfernen (Test `test_grandfathered_dateien_existieren_und_enthalten_pattern` meckert sonst).
4. Test-Suite grün halten.

## Verbundene Konzepte

- `docs/KONZEPT-BERECHNUNGS-LAYER.md` — Architektur-Detail, Submodul-Schnitt, geplante Erweiterungen
- `docs/archive/KONZEPT-DATENPIPELINE.md` Abschnitt 3.4 — „Zentraler Helper Pflicht"
- `docs/archive/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` — Etappe-4-Auslöser, dessen unvollständiger Riemann-Pfad-Rückbau das Berechnungs-Layer-Konzept erst nötig gemacht hat
- `docs/KONZEPT-COUNTER-DAILY-DRIFT.md` — analoge Drift-Klasse für Counter-Felder, wird Teil des Berechnungs-Layers (`counter`-Submodul) wenn die Stelle angefasst wird
- `docs/KONZEPT-BERECHNUNGS-LAYER.md` §6 — Herleitungs-Transparenz: Kennzahl-Helfer liefern eine strukturierte Herleitung (Vertrag zur Style-Guide-Norm A6); Durchsetzung als separater Zukunfts-Punkt nach Projektabschluss

## Verbundene Memory-Einträge

- `feedback_aggregations_drift` — Drift-Pattern (Read-Side, jetzt erweitert um Write-Side via Berechnungs-Layer)
- `feedback_eigenen_code_zuerst` — Verhaltens-Lehre nach BKW-Vorfall: bei jeder Anwender-Drift-Meldung ZUERST eigenen Berechnungscode prüfen
- `feedback_step_by_step_berechnungs_layer` — Migrations-Disziplin für diesen Layer
