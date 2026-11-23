"""Counter-Aggregate (WP-Kompressor-Starts, Betriebsstunden) — die Invariante Stunden-Σ ↔ Menge im Fenster.

Zwei Pfade tragen einen Counter auf unterschiedlichen Wegen:

- `TagesEnergieProfil.wp_starts_anzahl[h]` — die Stunden aus den Ständen (`get_hourly_counter_sum_by_feld`), Fenster
  `[Vortag 23:00, 23:00)`; nach einer Lücke trägt die erste Stunde mit Stand die Menge (Bündel, wie N-817).
- `TagesZusammenfassung.komponenten_starts[inv_id]` — Boundary-Diff über den Kalendertag (`get_daily_counter_deltas_by_inv`).

**Fund-Päckchen F (F6, Entscheid Master 23.11.2026):** bis dahin reskalierte `verteile_counter_auf_stunden` (Variante
2-light, KONZEPT-COUNTER-DAILY-DRIFT.md) die Stunden auf den Tageswert — an Lückentagen verteilt (gemessen: die fehlenden
Starts auf die Stunden 0–4 statt an die Lücke) und an jedem Tag mit Starts zwischen 23 und 24 Uhr verfälscht (die zwei
Fenster unterscheiden sich; gemessen: 5 Starts in der Stunde 0, Tageswert 0 ⇒ alle Stunden 0). Die Funktion ist entfernt:
die Stunden tragen, was die Stände hergeben; der Tageswert bleibt der Kalendertag. Die Pflicht-Invariante
`pruefe_counter_konsistent` vergleicht Σ Stunden mit der Menge im Fenster der Stunden (`CounterStunden.fenster`) und macht
eine Rest-Drift sichtbar (Spike-Kappe, Rücksprung; analog `pruefe_*` im kWh-Pfad, ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.zahlenformat import fmt_zahl


# ─── Invariante ───────────────────────────────────────────────────────────────

@dataclass
class CounterKonsistenzBericht:
    """Ergebnis der Counter-Konsistenz-Prüfung (Stunden-Σ vs. Tages-Boundary-Diff)."""
    konsistent: bool
    name: str
    erwartet: float       # Tages-Boundary-Diff (Σ_inv) — die SoT
    tatsaechlich: float   # Σ_h der Stunden-Σ
    toleranz: float
    details: str = ""

    @property
    def abweichung(self) -> float:
        return abs(self.tatsaechlich - self.erwartet)

    def __str__(self) -> str:
        status = "✓" if self.konsistent else "✗"
        return (
            f"{status} {self.name}: erwartet={fmt_zahl(self.erwartet, 3)}, "
            f"tatsächlich={fmt_zahl(self.tatsaechlich, 3)}, "
            f"Δ={fmt_zahl(self.abweichung, 3)} (Toleranz {fmt_zahl(self.toleranz, 3)})"
            f"{' — ' + self.details if self.details else ''}"
        )


def pruefe_counter_konsistent(
    stunden: dict[int, Optional[float]],
    tages_summe: float,
    *,
    name: str = "counter",
    toleranz: float = 0.5,
) -> CounterKonsistenzBericht:
    """Prüft: `Σ_h stunden[h] == tages_summe` (Boundary-Diff = SoT).

    Args:
        stunden: `{h: wert}` der Stunden-Σ (None = Snapshot-Lücke, zählt nicht).
        tages_summe: Tages-Boundary-Diff über alle Investitionen für dieses Feld.
        name: Label für die Diagnose-Meldung (z. B. `counter:wp_starts_anzahl`).
        toleranz: akzeptierte Abweichung (Default 0.5 — deckt Float-Rundung +
            Ganzzahl-Restverteilung ab).
    """
    s = sum(v for v in stunden.values() if v is not None)
    return CounterKonsistenzBericht(
        konsistent=abs(s - tages_summe) <= toleranz,
        name=name,
        erwartet=tages_summe,
        tatsaechlich=s,
        toleranz=toleranz,
    )


def assert_counter_konsistent(
    stunden: dict[int, Optional[float]],
    tages_summe: float,
    *,
    name: str = "counter",
    toleranz: float = 0.5,
) -> CounterKonsistenzBericht:
    """`pruefe_counter_konsistent`-Variante, die bei Verletzung wirft (Tests/CI)."""
    bericht = pruefe_counter_konsistent(
        stunden, tages_summe, name=name, toleranz=toleranz
    )
    assert bericht.konsistent, str(bericht)
    return bericht
