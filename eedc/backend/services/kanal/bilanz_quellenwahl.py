"""Quellenwahl der Bilanz-Gruppe je Tag und je Monat (HA-Bauform E4a, Teil 1, Auftrag Punkt 3; Bauplan §3b).

Die Bilanz-Formel hat Netz, PV/Balkonkraftwerk, Speicher und Erzeuger hinter dem Zähler als gemeinsame Eingänge
(``bilanz_adapter.BILANZ_ACHSEN``). Je Tag und je Monat gibt es deshalb EINE Wahl für alle diese Eingänge: ``kanal``
nur, wenn JEDER benötigte Kanal den Zeitraum voll deckt; sonst ``bestand`` mit Grund je Kanal — die Regel ist
``quellenwahl.waehle_quelle`` (Tag über ``quellenwahl.quellenwahl``, Monat über ``monatsraster.monatsreihe``).

**Benötigt** sind die Zähler, die der Tagespfad an diesem Tag für die Achsen der Gruppe nähme
(``bilanz_adapter.zaehler_eintraege`` → ``bilanz_eintraege``; Filter aktiv · Anschaffung · Stilllegung je Tag),
nach der Either-Or-Auflösung: von einer Ersatzgruppe zählt der erste Zähler, der einen Kanal HAT — ein unbenutzter
Ersatz ohne Kanal macht den Tag nicht ungedeckt. Ein zugeordnetes Feld ohne Kanal (Sensor ohne HA-Statistik) zählt
als ``kein_kanal`` ⇒ ``bestand``. Monat = Vereinigung der benötigten Zähler seiner Tage.

**Reine Auskunft. Stand E4a-1: von niemandem benutzt** (Umschalten ist E4a-2).

Schwesterdateien: ``bilanz_adapter.py``, ``quellenwahl.py``, ``monatsraster.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal
from backend.services.kanal.bilanz_adapter import bilanz_eintraege, zaehler_eintraege
from backend.services.kanal.fenster import monate, tagesfenster
from backend.services.kanal.monatsraster import monatsreihe
from backend.services.kanal.quellenwahl import Quellenwahl, quellenwahl
from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege


async def _benoetigt(db: AsyncSession, anlage, invs: list, tag: date, mit_kanal: set[str]) -> list[str]:
    invs_by_id = {str(i.id): i for i in invs if i.ist_aktiv_an(tag)}
    eintraege = bilanz_eintraege(await zaehler_eintraege(db, anlage, invs_by_id, tag))
    eintraege = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: e.schluessel in mit_kanal,
    )
    return list(dict.fromkeys(e.schluessel for e in eintraege))


async def _stamm(db: AsyncSession, anlage_id: int):
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
    mit_kanal = set((await db.execute(select(Kanal.key).where(Kanal.anlage_id == anlage_id))).scalars().all())
    return anlage, invs, mit_kanal


async def bilanz_benoetigte_kanaele(db: AsyncSession, anlage_id: int, tag: date) -> list[str]:
    """Die Kanal-Schlüssel, die die Bilanz-Gruppe an ``tag`` braucht."""
    anlage, invs, mit_kanal = await _stamm(db, anlage_id)
    return await _benoetigt(db, anlage, invs, tag, mit_kanal)


async def bilanz_quellenwahl_tag(
    db: AsyncSession, anlage_id: int, tag: date, *, jetzt: Optional[int] = None,
) -> Quellenwahl:
    """``kanal`` oder ``bestand`` für die Bilanz-Gruppe am Tag ``tag`` (Fenster ``fenster.tagesfenster``)."""
    anlage, invs, mit_kanal = await _stamm(db, anlage_id)
    benoetigt = await _benoetigt(db, anlage, invs, tag, mit_kanal)
    von, bis = tagesfenster(tag)
    return await quellenwahl(db, anlage_id, von, bis, benoetigt, jetzt=jetzt)


async def bilanz_quellenwahl_monate(
    db: AsyncSession, anlage_id: int, von: tuple[int, int], bis: tuple[int, int], *, jetzt: Optional[int] = None,
) -> dict[tuple[int, int], Quellenwahl]:
    """Je Monat EINE Wahl über alle Eingänge der Gruppe (Fenster ``fenster.monatsfenster``)."""
    anlage, invs, mit_kanal = await _stamm(db, anlage_id)
    out: dict[tuple[int, int], Quellenwahl] = {}
    for jahr, monat in monate(von, bis):
        tag = date(jahr, monat, 1)
        benoetigt: list[str] = []
        while tag.month == monat:
            benoetigt.extend(await _benoetigt(db, anlage, invs, tag, mit_kanal))
            tag += timedelta(days=1)
        reihe = await monatsreihe(db, anlage_id, list(dict.fromkeys(benoetigt)), (jahr, monat), (jahr, monat),
                                  jetzt=jetzt)
        out[(jahr, monat)] = reihe[0].wahl
    return out


__all__ = ["bilanz_benoetigte_kanaele", "bilanz_quellenwahl_monate", "bilanz_quellenwahl_tag"]
