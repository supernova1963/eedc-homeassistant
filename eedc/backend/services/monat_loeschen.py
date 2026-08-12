"""Einen Monat löschen — Zählerzeile, auf Wunsch **mit** den Gerätewerten (#349).

**Warum es diesen Helfer gibt.** Bis 2026-08-12 löschte „Monat löschen" nur die
``Monatsdaten``-Zeile der Anlage. Die Gerätewerte desselben Monats
(``InvestitionMonatsdaten`` — PV je Modul, Speicher-Zyklen, Wallbox-Ladung …)
blieben stehen, und **kein einziger Pfad im Baum** hat sie je entfernt. Für den
Anwender war der Monat damit verschwunden (die Monatslisten hängen an der
gelöschten Zählerzeile), für den Import war er es nicht:

* ohne „Überschreiben" übersprang der Import jeden bereits belegten Sub-Key —
  gemessen: 0 geschrieben, der alte Wert blieb stehen;
* mit „Überschreiben" gewann er gegen einen früheren Import, **nicht** gegen
  einen von Hand gepflegten Wert (``manual:*`` steht per Hierarchie über jedem
  Maschinen-Schreiber, FrodoVDR #251).

Gemeldet von OliS2811 (#349): Er löschte alle Monate eines Jahres, importierte
erneut — und bekam „6 Felder wurden durch manuell gepflegte Werte geschützt"
statt seiner Daten.

**Zwei Aufrufer, ein Verhalten.** Die Route (`api/routes/monatsdaten.py`) und
die Reparatur-Werkbank (`services/repair_orchestrator.py`) löschen denselben
Gegenstand; hätte nur einer die Gerätewerte mitgenommen, wäre der Unterschied
genau die Art von Drift, die diesen Befund erzeugt hat.

⚠ **Der Rest wird benannt, nicht stillschweigend mitgelöscht** (Entscheid
Gernot, 12.08.): Der Lösch-Dialog sagt, wie viele Gerätewerte an diesem Monat
hängen, und das Mitlöschen ist eine **bewusste Zusage** des Anwenders —
Vorgabe bleibt „nur die Zählerzeile". Gemessene Gerätewerte sind oft die
teureren Daten; ein Klick auf „Monat löschen" soll sie nicht mitreißen.
Jede gelöschte Zeile bekommt ihren Audit-Log-Eintrag, damit die Spur bleibt.
Wer den Rest übersieht, wird vom Daten-Checker daran erinnert.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.provenance import log_delete

logger = logging.getLogger(__name__)


async def beschreibe_geraetewerte_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> list[dict]:
    """Welche Gerätewerte hängen an diesem Monat — je Komponente benannt?

    Grundlage für den Lösch-Dialog und die Vorschau der Reparatur-Werkbank:
    Eine Lösch-Vorschau, die „1 Zeile" sagt und dann fünf löscht, ist keine
    Vorschau — und „3 weitere Datensätze" ohne Namen ist keine Entscheidung.

    Returns:
        Je Gerätezeile ``{investition_id, bezeichnung, typ, felder}`` mit
        ``felder`` = den belegten Sub-Keys (leere Zeilen tragen keine).
    """
    zeilen = await _geraetewerte_des_monats(db, anlage_id, jahr, monat)
    if not zeilen:
        return []

    inv_res = await db.execute(
        select(Investition).where(
            Investition.id.in_([z.investition_id for z in zeilen])
        )
    )
    inv_map = {i.id: i for i in inv_res.scalars().all()}

    beschreibung = []
    for z in zeilen:
        inv = inv_map.get(z.investition_id)
        beschreibung.append({
            "investition_id": z.investition_id,
            "bezeichnung": (inv.bezeichnung if inv else None) or f"#{z.investition_id}",
            "typ": inv.typ if inv else None,
            "felder": sorted(
                k for k, v in (z.verbrauch_daten or {}).items() if v is not None
            ),
        })
    return beschreibung


async def zaehle_geraetewerte_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> int:
    """Wie viele Gerätezeilen hängen an diesem Monat?"""
    return len(await _geraetewerte_des_monats(db, anlage_id, jahr, monat))


async def _geraetewerte_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int
) -> list[InvestitionMonatsdaten]:
    """Gerätewerte des Monats — über die Investitionen **dieser** Anlage.

    Der Join ist der Punkt: ``InvestitionMonatsdaten`` trägt keine
    ``anlage_id``, sondern hängt an der Investition. Ohne ihn würde ein Monat
    der einen Anlage die Gerätewerte einer anderen mitreißen.
    """
    res = await db.execute(
        select(InvestitionMonatsdaten)
        .join(Investition, Investition.id == InvestitionMonatsdaten.investition_id)
        .where(
            Investition.anlage_id == anlage_id,
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat,
        )
    )
    return list(res.scalars().all())


async def loesche_monat_vollstaendig(
    db: AsyncSession,
    md: Monatsdaten,
    *,
    source: str,
    writer: str,
) -> int:
    """Löscht die Zählerzeile und alle Gerätewerte desselben Monats.

    Kein ``commit`` — das entscheidet der Aufrufer (die Route committet über
    ihre Session, die Werkbank in ihrer Operation).

    Returns:
        Anzahl der zusätzlich gelöschten Gerätezeilen.
    """
    geraetewerte = await _geraetewerte_des_monats(db, md.anlage_id, md.jahr, md.monat)

    for imd in geraetewerte:
        # Audit-Log VOR dem Delete — danach sind die Natural-Keys nicht mehr
        # lesbar (dieselbe Reihenfolge wie beim Löschen der Zählerzeile).
        log_delete(
            db, imd,
            source=source,
            writer=writer,
            decision_reason=(
                f"Monat {md.jahr}-{md.monat:02d} vollständig gelöscht "
                f"(#349) — Gerätewerte der Investition {imd.investition_id}"
            ),
        )
        await db.delete(imd)

    log_delete(db, md, source=source, writer=writer)
    await db.delete(md)

    if geraetewerte:
        logger.info(
            "Monat %s-%02d der Anlage %s gelöscht: 1 Zählerzeile + %d Gerätezeilen",
            md.jahr, md.monat, md.anlage_id, len(geraetewerte),
        )
    return len(geraetewerte)
