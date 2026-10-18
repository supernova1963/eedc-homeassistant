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

**HA-Bauform S5 (E-S5-1b, Bauplan §10b H-3/H-4): «trägt der Tag Energie» ist eine Tagesfrage.** Ein Bestandstag liest
die dünne Stundenzeile (``datum``, ``stunde``, ``spannen`` und die Spalte der Achse, Zeilen mit Spanne) wie vor S5. An
einem Kanal-Tag der Bilanz (``bilanz_leser.kanal_tage``, dieselbe Wahl wie ``tage-werte``) gilt dieselbe Regel wie seit
E-S5-1 — die Stunden sind dort die Mischzeilen, ob eine Stunde Energie über Mitternacht trägt, sagen ihre Kanal-Stunden
(HAs ``change`` und Spanne; der Tageswert des Kanal-Tags trägt die Energie einer Spiegel-Lücke über Mitternacht wie in
HA mit), ``verworfen`` gilt ohne die Bilanz-Achsen (``verworfen_der_tage``, der Kanal verwirft nichts). **Gerechnet
werden die Mischzeilen nur an den Tagen, an denen sie etwas entscheiden können:** ein Kanal-Tag mit einer Spiegel-Lücke
über Mitternacht in einem Kanal der Achse (``kanal_stunden.tage_mit_kanal_luecke_ueber_mitternacht``, eine Anweisung an
die Stände), mit einer Stundenzeile mit Spanne an D oder D+1 oder mit einer Regelmarke; an jedem anderen Kanal-Tag kann
keine Mischzeile ein Bündel tragen. Ergebnis gleich der Fassung über alle Mischzeilen (E-S5-1), ohne deren Laufzeit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.spannen import tage_um_mitternachtsbuendel
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Achse → Spalte, deren Wert „trägt Energie" beantwortet (wie im Layer).
_SPALTE = {
    "pv": TagesEnergieProfil.pv_kw,
    "einspeisung": TagesEnergieProfil.einspeisung_kw,
    "netzbezug": TagesEnergieProfil.netzbezug_kw,
    "batterie": TagesEnergieProfil.batterie_kw,
    "waermepumpe": TagesEnergieProfil.waermepumpe_kw,
    "wallbox": TagesEnergieProfil.wallbox_kw,
}


async def _bereich(
    db: AsyncSession, anlage_id: int, von: Optional[date], bis: Optional[date],
) -> Optional[tuple[date, date]]:
    """Der Bereich der Kanal-Tage wie ``stunden_der_tage`` ihn bildet: ein offenes Ende ist die erste bzw. letzte
    Stundenzeile der Anlage; ``None`` ohne Stundenzeile bzw. bei leerem Bereich."""
    if von is None or bis is None:
        erste, letzte = (await db.execute(
            select(func.min(TagesEnergieProfil.datum), func.max(TagesEnergieProfil.datum))
            .where(TagesEnergieProfil.anlage_id == anlage_id))).one()
        if erste is None:
            return None
        von = erste if von is None else von
        bis = letzte if bis is None else bis
    return (von, bis) if von <= bis else None


async def _kanal_tage_unter(db: AsyncSession, anlage_id: int, von: date, bis: date, fraglich: set[date]) -> set[date]:
    """Welche der Tage ``fraglich`` (im Bereich ``von`` … ``bis``) sind Kanal-Tage der Bilanz (``bilanz_leser.kanal_tage``)?
    Gefragt wird nur für diese Tage, je Lauf aufeinanderfolgender Tage ein Aufruf."""
    from backend.services.energie_profil.kanal_stunden import _kanal_tage_ab_erstem_stand

    tage = sorted(t for t in fraglich if von <= t <= bis)
    out: set[date] = set()
    i = 0
    while i < len(tage):
        j = i
        while j + 1 < len(tage) and tage[j + 1] == tage[j] + timedelta(days=1):
            j += 1
        out |= set(await _kanal_tage_ab_erstem_stand(db, anlage_id, tage[i], tage[j]))
        i = j + 1
    return out


async def _stunden_der_kanal_tage(
    db: AsyncSession, anlage_id: int, kanal: set[date], spalte, rows_je_tag: dict[date, list],
) -> set[date]:
    """Die Stunden je Kanal-Tag aus ``kanal_stunden.stunden_der_tage`` des einen Tags (Mischzeilen, Lade-Hinweis wie
    E-S5-1) in ``rows_je_tag`` — nur Zeilen mit Spanne. Rückgabe: die Tage mit Mischzeilen (dort mischt ``verworfen``)."""
    from backend.core.berechnungen.slot_konvention import ist_beginn_raster
    from backend.services.energie_profil.kanal_stunden import stunden_der_tage

    gemischt: set[date] = set()
    felder = (spalte.key,) if spalte is not None else ()
    for d in sorted(kanal):
        for z in await stunden_der_tage(db, anlage_id, d, d, felder=felder):
            if z.datum != d:
                continue
            if ist_beginn_raster(z):
                gemischt.add(d)
            if z.spannen is not None:
                rows_je_tag[d].append(z)
    return gemischt


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
    erkannt wird. HA-Bauform S5: an einem Kanal-Tag der Bilanz die
    Mischzeilen und ``verworfen`` ohne die Bilanz-Achsen, gerechnet nur an
    Kandidaten-Tagen (Modul-Docstring).
    """
    from backend.services.energie_profil.kanal_stunden import (
        tage_mit_kanal_luecke_ueber_mitternacht,
        verworfen_der_tage,
    )
    from backend.services.kanal.bilanz_leser import mische_verworfen

    folgetag = bis + timedelta(days=1) if bis is not None else None
    spalte = _SPALTE.get(achse)
    q = select(
        TagesEnergieProfil.datum, TagesEnergieProfil.stunde, TagesEnergieProfil.spannen,
        *([spalte] if spalte is not None else []),
    ).where(
        TagesEnergieProfil.anlage_id == anlage_id,
        TagesEnergieProfil.spannen.isnot(None),
    )
    if von is not None:
        q = q.where(TagesEnergieProfil.datum >= von)
    if folgetag is not None:
        q = q.where(TagesEnergieProfil.datum <= folgetag)
    zeilen = (await db.execute(q)).all()
    marken = await verworfen_der_tage(db, anlage_id, von, bis, kanal=())     # ungemischt; gemischt wird unten
    kanal: set[date] = set()
    bereich = await _bereich(db, anlage_id, von, folgetag)
    if bereich is not None:
        luecken = (await tage_mit_kanal_luecke_ueber_mitternacht(db, anlage_id, *bereich, achse)
                   if spalte is not None else set())
        fraglich = {t for z in zeilen for t in (z.datum, z.datum - timedelta(days=1))} | set(marken) | luecken
        kanal = await _kanal_tage_unter(db, anlage_id, *bereich, fraglich)
    rows_je_tag: dict[date, list] = defaultdict(list)
    for row in zeilen:
        if row.datum not in kanal:
            rows_je_tag[row.datum].append(row)
    gemischt = await _stunden_der_kanal_tage(db, anlage_id, kanal, spalte, rows_je_tag)
    tage = tage_um_mitternachtsbuendel(rows_je_tag, achse)

    for datum, verworfen in marken.items():
        if achse in (mische_verworfen(verworfen) if datum in gemischt else verworfen):
            tage.add(datum)

    if von is not None:
        tage = {t for t in tage if t >= von}
    if bis is not None:
        tage = {t for t in tage if t <= bis}
    return tage
