# Konzept: Counter-Daily-Drift — `wp_starts_anzahl` vs `komponenten_starts`

> **Status (2026-05-19):** Klein-Konzept, Spin-off aus dem 3C-Re-Audit (archivierte Haupt-Doc unter [`docs/archive/KONZEPT-ENERGIEPROFIL-3C.md`](archive/KONZEPT-ENERGIEPROFIL-3C.md)). Befund-Liste aus 3C komplett abgearbeitet außer Befund 2 (Counter-Anteil); dieses Konzept hält den Rest fest.
>
> **Priorität:** niedrig — Etappe 4 hat die kWh-Drift bereits geschlossen, die hier verbleibende Counter-Drift greift nur bei NULL-Slots / Snapshot-Lücken. Anlassbezogen mitnehmen, wenn der WP-Sprint sowieso angefasst wird (#238 detLAN WP-Betriebszeiten ist plausibler Trigger, weil dort das Counter-Pattern erweitert wird).

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
