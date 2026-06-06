# Konzept: Counter-Daily-Drift — `wp_starts_anzahl` vs `komponenten_starts`

> **✅ GESCHLOSSEN 2026-06-06 — Variante 2-light umgesetzt (Tier-1-Quick-Win, im Bündel, noch nicht released).** Fix gebaut:
> - Neuer Layer-Helper [`core/berechnungen/counter.py`](../eedc/backend/core/berechnungen/counter.py): `verteile_counter_auf_stunden` leitet die Stunden-Σ aus dem Tages-Boundary-Diff ab (eine Quelle/Tag), `pruefe_counter_konsistent`/`assert_counter_konsistent` als Pflicht-Invariante (analog kWh-Pfad, ADR-001).
> - [`energie_profil/aggregator.py`](../eedc/backend/services/energie_profil/aggregator.py): `komponenten_starts` (Boundary-Diff) wird vor der Stunden-Schleife geholt; `wp_starts_anzahl`/`wp_betriebsstunden` werden daraus abgeleitet; Invariante am Schreib-Ende. Greift nur bei NULL-Slots/Lücken — bei sauberen Daten verhaltensneutral.
> - Tests: `test_counter_daily_drift_2light.py` (Helper + echter NULL-Slot via Snapshots; Invariante feuert bei künstlicher Drift).
>
> Variante 3 verworfen (Symptompatch ohne Drift-Abbau). Memory [[project_counter_daily_drift]]. **Doc bleibt als Referenz; kann nach Release archiviert werden.** Das folgende Konzept ist historischer Stand.

> **Status (2026-05-19, aktualisiert):** Sub-Konzept des Berechnungs-Layers ([`KONZEPT-BERECHNUNGS-LAYER.md`](KONZEPT-BERECHNUNGS-LAYER.md), [`ADR-001`](ADR-001-BERECHNUNGS-LAYER.md)). Beim Touch des betroffenen Counter-Codes wird der Fix in `backend/core/berechnungen/counter.py` umgesetzt und die Pflicht-Invariante `pruefe_counter_konsistent` ergänzt — analog zum kWh-Pfad. Klein-Konzept, Spin-off aus dem 3C-Re-Audit (archivierte Haupt-Doc unter [`docs/archive/KONZEPT-ENERGIEPROFIL-3C.md`](archive/KONZEPT-ENERGIEPROFIL-3C.md)).
>
> **Priorität:** niedrig — Etappe 4 hat die kWh-Drift bereits geschlossen (Berechnungs-Layer-Akut-Fix 2026-05-19 hat die strukturelle Wurzel zusätzlich entfernt), die hier verbleibende Counter-Drift greift nur bei NULL-Slots / Snapshot-Lücken. Anlassbezogen mitnehmen, wenn der WP-Sprint sowieso angefasst wird (#238 detLAN WP-Betriebszeiten ist plausibler Trigger, weil dort das Counter-Pattern erweitert wird).

## Problem

Zwei Pfade tragen denselben Tageswert (z.B. Σ Kompressor-Starts) auf unterschiedlichen Wegen:

| Pfad | Quelle | Code-Stelle |
|---|---|---|
| `TagesEnergieProfil.wp_starts_anzahl[h]` | Hourly-Σ aus `get_hourly_counter_sum_by_feld` (Snapshot-Inkremente Slot h) | [`energie_profil/aggregator.py:219-221`](../eedc/backend/services/energie_profil/aggregator.py) |
| `TagesZusammenfassung.komponenten_starts` | Boundary-Diff über das Tagesfenster via `get_daily_counter_deltas_by_inv` | [`energie_profil/aggregator.py:434-438`](../eedc/backend/services/energie_profil/aggregator.py) + [`522`](../eedc/backend/services/energie_profil/aggregator.py) |

Bei sauber gepflegten Snapshots ist Σ `wp_starts_anzahl[h]` für `h ∈ 0..23` == `komponenten_starts[inv_id]`. Bei NULL-Slots (fehlender Snapshot) oder partiellem Resnap divergieren die zwei Sichten. Das UI zeigt dann zwei unterschiedliche „Tages-Starts"-Werte für denselben Tag.

## Warum Etappe 4 das nicht erledigt hat

Etappe 4 hat den **kWh-Pfad** auf HA-LTS-SoT umgestellt (Rainer-PN 2026-05-16). Die HA-LTS liefert kWh-Aggregate; Counter-Werte (kumulative Starts) sind aber **nicht** als HA-LTS-Statistic verfügbar, weil HA `state_class=total_increasing` zwar zählt, aber im Long-Term-Storage nur Snapshots, keine separaten „Σ-Starts pro Stunde" hinterlegt. Deshalb bleibt der Counter-Pfad bei Snapshot-Aggregation.

## Fix-Pattern

Analog zur Etappe-4-Lösung für `komponenten_kwh` (siehe [`energie_profil/aggregator.py:445-454`](../eedc/backend/services/energie_profil/aggregator.py)):

1. **Single Source of Truth pro Tag wählen.** Wenn beide Pfade auf denselben Snapshots arbeiten, soll der Boundary-Diff-Pfad gewinnen (HA-konform, robust gegen NULL-Slots).
2. **Hourly-Σ aus dem Boundary-Diff ableiten,** wenn die Hourly-Σ-Werte für die Anzeige im Tagesverlauf gebraucht werden — d.h. `wp_starts_anzahl[h]` wird als Inkrement-Annäherung aus dem Boundary-Diff distribuiert, nicht eigenständig aus Snapshots gerechnet.
3. **Alternativ pragmatisch:** Konsistenz-Check beim Schreiben — wenn `Σ wp_starts_anzahl != komponenten_starts`, Warning loggen und den Boundary-Diff-Wert behalten (Σ Hourly == Daily per Schreib-Invariante).

Variante 3 ist kleiner und reicht für den niedrigen Schmerz aus.

## Test

Akzeptanztest, der einen NULL-Slot simuliert und prüft, dass `Σ TagesEnergieProfil.wp_starts_anzahl[h] == TagesZusammenfassung.komponenten_starts[inv_id]` bleibt.

## Trigger

- WP-Sprint zu #238 (WP-Betriebszeiten, total-increasing-Sensor pro WP) — gleicher Counter-Architektur-Bereich.
- Oder Anwender meldet konkrete Tagesgesamt-vs-Stundenverteilung-Drift.

Bis dahin: liegen lassen.
