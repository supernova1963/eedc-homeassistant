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

**HA-Bauform S5 (E-S5-1, Bauplan §10a Leser 23):** die Stunden kommen aus `kanal_stunden.stunden_der_tage` — an einem
Kanal-Tag der Bilanz die Mischzeilen: ob eine Stunde Energie über Mitternacht trägt, sagen dort die Kanal-Stunden
(HAs `change`, Spanne der Kanal-Zeile) und nicht die gefaltete Stundenzeile; die Regelmarke `verworfen` gilt dort ohne
die Bilanz-Achsen (`verworfen_der_tage`, wie `tage-werte` — der Kanal verwirft nichts). Ein Kanal-Tag ohne Bündel in
seinen Kanal-Stunden taugt damit für den Tagesvergleich; ein Bestandstag liest wie bisher.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.spannen import tage_um_mitternachtsbuendel

#: Achse → Spalte, deren Wert „trägt Energie" beantwortet (wie im Layer).
_SPALTE = {
    "pv": "pv_kw",
    "einspeisung": "einspeisung_kw",
    "netzbezug": "netzbezug_kw",
    "batterie": "batterie_kw",
    "waermepumpe": "waermepumpe_kw",
    "wallbox": "wallbox_kw",
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
    erkannt wird. HA-Bauform S5: Stunden und Regelmarke wie *Cockpit → Tag*
    (Mischzeilen an Kanal-Tagen, Modul-Docstring).
    """
    from backend.core.berechnungen.slot_konvention import ist_beginn_raster
    from backend.services.energie_profil.kanal_stunden import stunden_der_tage, verworfen_der_tage

    spalte = _SPALTE.get(achse)
    zeilen = await stunden_der_tage(
        db, anlage_id, von, bis + timedelta(days=1) if bis is not None else None,
        felder=(spalte,) if spalte is not None else (),
    )
    rows_je_tag: dict[date, list] = defaultdict(list)
    for row in zeilen:
        if row.spannen is not None:
            rows_je_tag[row.datum].append(row)
    tage = tage_um_mitternachtsbuendel(rows_je_tag, achse)

    kanal = {z.datum for z in zeilen if ist_beginn_raster(z)}
    for datum, verworfen in (await verworfen_der_tage(db, anlage_id, von, bis, kanal=kanal)).items():
        if achse in verworfen:
            tage.add(datum)

    if von is not None:
        tage = {t for t in tage if t >= von}
    if bis is not None:
        tage = {t for t in tage if t <= bis}
    return tage
