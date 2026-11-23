"""Stundenform kumulativer Zähler — je Zähler 24 Slot-Mengen eines Tages.

**Warum es diesen Leser gibt** (11.09.2026, Konzept Wärme/Klima §8,
Bauschnitt 5 / E3): Der Tag-Verlauf braucht für die gemessenen
Betriebsart-Zähler, den Gesamtstrom und die Wärme **je Zähler** die Menge jeder
Stunde. Die bestehende Stunden-Funktion (`get_hourly_kwh_by_category`) liefert
dieselben Slots, faltet sie aber sofort zu **Kategorien** — die Zuordnung zum
einzelnen Zähler (und damit zum Innengerät, zur Betriebsart) ist danach weg.

⭐ **Die Regeln werden geteilt, nicht kopiert** — das war der Einwand der
Gegenprüfung („zwei Wahrheiten zwischen Kachel-Stunden und Verlaufs-Stunden"):

* Slot-Raster: `BoundaryRange.for_hourly_slots` (Rückwärts, #144),
* Lücken zwischen Ständen: die Menge steht in der ersten Stunde danach (N-817, wie HA und
  `snapshot_tagestabelle`; bis 23.11.2026 linear gefüllt, #145),
* Menge je Slot samt Tagesreset-Regel der **Stunde**: `stunden_slot_delta`.

⭐ **Warum Snapshots und nicht die HA-Langzeitstatistik direkt.** Die
Tageswerte, die der Verlauf auf die Stunden verteilt, entstehen seit N-434 und
N-435 als Snapshot-Randdifferenz im Fenster der Tageszeile — im HA-Add-on
[Vortag 23:00, 23:00), also genau die 24 Slots. Aus **derselben** Standreihe
gelesen ist Σ Slots = Tageswert ohne jede Skalierung (das Bündel nach einer Lücke
trägt die Randstände). Eine zweite Quelle würde diese Gleichheit aufgeben.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.zaehler_naht import gehobene_staende, trennende, ueber_naht
from backend.services.snapshot.aggregator import stunden_slot_delta
from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte
from backend.services.snapshot.boundary_range import BoundaryRange
from backend.services.snapshot.keys import extract_quellen_energy
from backend.services.snapshot.reader import get_snapshot

#: Ein Zähler: ``(sensor_key, sensor_id)`` — ``sensor_id`` ist ``None`` bei
#: reinen MQTT-Quellen; `get_snapshot` liest dann nur die lokale Ablage.
Zaehler = tuple[str, Optional[str]]


async def lade_stundenformen(
    db: AsyncSession,
    anlage,
    datum: date,
    zaehler: list[Zaehler],
) -> dict[str, list[Optional[float]]]:
    """Je Zähler die 24 Slot-Mengen des Tages (Slot h = Energie [h−1, h)).

    Returns:
        ``{sensor_key: [24 Werte]}`` — ``None`` in einem Slot heißt „kein Stand
        am Slot-Ende" (Lücke; ihre Menge steht im ersten Slot danach, N-817),
        „noch kein Stand im Fenster davor" (Rand, nicht extrapoliert) oder ein
        Rücksprung, der kein Tagesreset ist. Ein Zähler ohne jeden Stand fehlt
        im Ergebnis (keine Aussage statt 24 Nullen, ADR-002/P4).
    """
    if not zaehler:
        return {}
    quellen_energy = extract_quellen_energy(anlage)
    rng = BoundaryRange.for_hourly_slots(datum)

    ergebnis: dict[str, list[Optional[float]]] = {}
    for sensor_key, sensor_id in zaehler:
        staende: dict[int, Optional[float]] = {}
        for offset in rng.boundary_offsets:
            staende[offset] = await get_snapshot(
                db, anlage.id, sensor_key, sensor_id, rng.boundary_at(offset),
                quellen_energy=quellen_energy,
            )
        if all(v is None for v in staende.values()):
            continue
        alle_naehte = await fortsetzungs_naehte(db, anlage.id, sensor_key)     # Sensorwechsel B-3
        staende = gehobene_staende(staende, rng.boundary_at, alle_naehte)      # U2 a1 (F5): Rand-Stände heben beim Laden
        naehte = trennende(alle_naehte)
        slots: list[Optional[float]] = [None] * 24
        anker: Optional[int] = None         # Offset des letzten Stands davor (N-817: Bündel nach einer Lücke, wie HA)
        for slot_idx, prev_off, curr_off in rng.slot_pairs:
            if staende.get(prev_off) is not None:
                anker = prev_off
            s1 = staende.get(curr_off)
            if anker is None or s1 is None:
                continue
            if ueber_naht(rng.boundary_at(anker), rng.boundary_at(curr_off), naehte):
                slots[slot_idx] = 0.0       # B-3: der Naht-Slot zählt nur den neuen Abschnitt — mit Ständen zur vollen Stunde nichts
                continue
            slots[slot_idx] = stunden_slot_delta(
                staende[anker], s1, sensor_key=sensor_key, datum=datum, slot_idx=slot_idx,
            )
        ergebnis[sensor_key] = slots
    return ergebnis
