"""Welche Tage taugen für einen **Tag-gegen-Tag**-Vergleich? (Zählerlücken wie HA, §2)

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7. Seit eedc je Stunde
ablegt, was HA zeigt, landet die Energie einer Lücke über Mitternacht im
**Folgetag**: D ist um genau die Energie zu niedrig, um die D+1 zu hoch ist.
Für jede Summe ist das richtig (wie im HA-Dashboard) — für einen Vergleich
eines **einzelnen Tages** gegen eine Prognose, einen Sollwert oder eine
Schwelle nicht. Solche Leser (Lernfaktor, Genauigkeit, Prognose-vs-IST je Tag,
PV-Über-Erfassung/PR im Daten-Checker) lassen deshalb **beide** Tage aus (Ü2),
dazu jeden Tag mit einer verworfenen Menge auf der Achse (R4).

Ein 0-Bündel (nachts, mameier) lässt beide Tage drin; ein Bündel innerhalb des
Tages lässt den Tag drin (seine Energie gehört zu ihm).

DB-Zugriff hier, die Regel im Layer (`core/berechnungen/spannen.py`, ADR-001).
Gelesen werden **nur** Stundenzeilen mit Spanne — die Spalte ist dünn, der
Zugriff kostet auch über zwei Jahre Historie wenige Zeilen.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.spannen import tage_um_mitternachtsbuendel
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

#: Achse → Spalte, deren Wert „trägt Energie" beantwortet (wie im Layer).
_SPALTE = {
    "pv": TagesEnergieProfil.pv_kw,
    "einspeisung": TagesEnergieProfil.einspeisung_kw,
    "netzbezug": TagesEnergieProfil.netzbezug_kw,
    "batterie": TagesEnergieProfil.batterie_kw,
    "waermepumpe": TagesEnergieProfil.waermepumpe_kw,
    "wallbox": TagesEnergieProfil.wallbox_kw,
}


async def tage_ohne_tagesvergleich(
    db: AsyncSession,
    anlage_id: int,
    achse: str = "pv",
    *,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> set[date]:
    """Die Tage, die ein Tag-gegen-Tag-Leser auf ``achse`` auslässt.

    ``{D, D+1}`` um jedes Mitternachtsbündel mit Energie (Ü2) und jeder Tag
    mit ``verworfen[achse]`` (R4). ``von``/``bis`` grenzen das Ergebnis ein
    (beide inklusive); für ``bis`` wird der Folgetag mitgelesen, damit D = bis
    erkannt wird.
    """
    spalte = _SPALTE.get(achse)
    q = select(
        TagesEnergieProfil.datum, TagesEnergieProfil.stunde, TagesEnergieProfil.spannen,
        *( [spalte] if spalte is not None else [] ),
    ).where(
        TagesEnergieProfil.anlage_id == anlage_id,
        TagesEnergieProfil.spannen.isnot(None),
    )
    if von is not None:
        q = q.where(TagesEnergieProfil.datum >= von)
    if bis is not None:
        q = q.where(TagesEnergieProfil.datum <= bis + timedelta(days=1))
    rows_je_tag: dict[date, list] = defaultdict(list)
    for row in (await db.execute(q)).all():
        rows_je_tag[row.datum].append(row)
    tage = tage_um_mitternachtsbuendel(rows_je_tag, achse)

    tq = select(TagesZusammenfassung.datum, TagesZusammenfassung.verworfen).where(
        TagesZusammenfassung.anlage_id == anlage_id,
        TagesZusammenfassung.verworfen.isnot(None),
    )
    if von is not None:
        tq = tq.where(TagesZusammenfassung.datum >= von)
    if bis is not None:
        tq = tq.where(TagesZusammenfassung.datum <= bis)
    for datum, verworfen in (await db.execute(tq)).all():
        if verworfen and achse in verworfen:
            tage.add(datum)

    if von is not None:
        tage = {t for t in tage if t >= von}
    if bis is not None:
        tage = {t for t in tage if t <= bis}
    return tage
