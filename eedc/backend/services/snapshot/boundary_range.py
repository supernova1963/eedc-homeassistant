"""
Typed Range über Snapshot-Boundaries (Etappe 3c P2, KONZEPT-ENERGIEPROFIL-3C.md).

Kapselt die Backward-Konvention nach Issue #144 für Hourly-Slots
und das HA-konforme Tagesfenster für Boundary-Diff-Tagesgesamt.
Konsumenten dürfen Slot-Indices nicht selbst rechnen — sie iterieren über
`boundary_offsets` und `slot_pairs`, lesen Snapshots an `boundary_at(offset)`
und nehmen für jeden Slot das Tupel `(slot_idx, prev_offset, curr_offset)`.

Backward-Konvention #144 (Slot 0..23):
    Snapshots @ Vortag 23:00, Heute 00:00, ..., Heute 23:00 → 25 Boundaries
    Slot h = snap[curr=h] − snap[prev=h-1]                  → 24 Slots
    Slot 0  = Energie [Vortag 23:00, Heute 00:00)
    Slot 23 = Energie [Heute 22:00, Heute 23:00)

HA-Tagesgesamt (Boundary-Diff über [Heute 00:00, Folgetag 00:00)):
    Snapshots @ Heute 00:00, Folgetag 00:00 → 2 Boundaries
    Tagesgesamt = snap[24] − snap[0]

Beide Fenster sind 24 Stunden lang, aber semantisch verschieden — Konsumenten
dürfen nicht erwarten, dass `Σ slot[0..23] == Tagesgesamt` ist (Slot-Σ deckt
[Vortag-23, Heute-23) ab, nicht [Heute-00, Folgetag-00)).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class BoundaryRange:
    """Typed Range über Snapshot-Zeitstempel für eine bestimmte Aggregat-Variante."""

    datum: date
    boundary_offsets: tuple[int, ...]
    """Stunden-Offsets relativ zu `datum` 00:00, an denen Snapshots gelesen werden."""

    slot_pairs: tuple[tuple[int, int, int], ...]
    """Liste von `(slot_idx, prev_offset, curr_offset)` für die Slot-Aggregation.

    Leer für `for_day_total` — dort `boundary_offsets` direkt nutzen.
    """

    @classmethod
    def for_hourly_slots(cls, datum: date) -> "BoundaryRange":
        """Backward-Hourly nach Issue #144.

        25 Boundaries (offsets `-1..23`), 24 Slots (`0..23`).
        Slot h = `snap[curr=h] − snap[prev=h-1]`.
        Slot 0 = Energie [Vortag 23:00, Heute 00:00).
        """
        return cls(
            datum=datum,
            boundary_offsets=tuple(range(-1, 24)),
            slot_pairs=tuple((h, h - 1, h) for h in range(24)),
        )

    @classmethod
    def for_day_total(cls, datum: date) -> "BoundaryRange":
        """HA-konformer Tagesgesamt-Range.

        2 Boundaries (offsets `0` und `24`).
        Tagesgesamt = `snap[24] − snap[0]` = Energie [Heute 00:00, Folgetag 00:00).
        Wird in Päckchen 3 (E2) primärer Truth-Pfad für TagesZusammenfassung-Felder.
        """
        return cls(
            datum=datum,
            boundary_offsets=(0, 24),
            slot_pairs=(),
        )

    def boundary_at(self, offset: int) -> datetime:
        """Zeitstempel für einen Boundary-Offset (Stunden seit `datum` 00:00)."""
        return datetime.combine(self.datum, datetime.min.time()) + timedelta(hours=offset)
