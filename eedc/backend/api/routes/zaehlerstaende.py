"""Zählerstände unter *Sonstiges* — die eine Route für alle vier Anzeigen (#377).

*Live/Auf einen Blick*, *Cockpit Tag/Monat/Jahr*, *Komponenten/Sonstiges* und die
Tabellen fragen **dieselbe** Auskunft: Stand am Anfang, Stand am Ende, Differenz,
Verlauf — je Gerät. Sie bekommen sie hier, aus `services/zaehlerstaende.py`.

**Warum eine eigene Route und kein Anhängsel an Live/Cockpit:** Ein Zählerstand
gehört in keine der bestehenden Antworten hinein. Er ist keine Energiegröße, und
in `cockpit/uebersicht` oder der Live-Antwort mitzufahren hieße, ihn in genau
die Strukturen zu legen, aus denen er herausgehalten werden soll — vier Stellen,
die ihn dann versehentlich mitsummieren könnten.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.services.zaehlerstaende import lade_zaehlerstaende

router = APIRouter()


class ZaehlerVerlaufPunktResponse(BaseModel):
    zeitpunkt: datetime
    stand: float


class ZaehlerStandResponse(BaseModel):
    """Ein Zähler über das angefragte Fenster.

    ``differenz`` ist ``None``, wenn einer der beiden Stände fehlt — **nicht 0**
    (ADR-002/P4: eine fehlende Messung ist keine Nullmenge).
    """

    investition_id: int
    name: str
    art: str
    einheit: str
    stand_anfang: Optional[float] = None
    stand_ende: Optional[float] = None
    differenz: Optional[float] = None
    #: False = die Aufzeichnung beginnt **innerhalb** des Fensters, die
    #: Differenz deckt also nur einen Teil davon ab. Die Anzeige sagt es an.
    anfang_vollstaendig: bool = True
    #: True = der Endstand liegt **unter** dem Anfangsstand. Ein Zählerstand
    #: läuft nicht rückwärts ⇒ die Reihe ist gebrochen (Zählertausch ohne
    #: Stilllegung, Sensorwechsel, oder der einmalige F-58-Übergang).
    #: ``differenz`` ist dann ``None`` — keine Aussage statt einer falschen.
    reihe_gebrochen: bool = False
    verlauf: list[ZaehlerVerlaufPunktResponse] = []


def _fenster(
    zeitraum: str, datum: Optional[date], jahr: Optional[int], monat: Optional[int]
) -> tuple[datetime, datetime]:
    """Den angefragten Zeitraum in ein konkretes Fenster übersetzen.

    Die vier Anzeigen sprechen vier Sprachen — *heute*, *ein Tag*, *ein Monat*,
    *ein Jahr*, *alles*. Sie hier aufzulösen hält die Fensterarithmetik an einer
    Stelle statt in vier Komponenten.
    """
    heute = date.today()
    if zeitraum == "tag":
        tag = datum or heute
        return datetime.combine(tag, datetime.min.time()), datetime.combine(
            tag, datetime.max.time()
        )
    if zeitraum == "monat":
        j = jahr or heute.year
        m = monat or heute.month
        return (
            datetime(j, m, 1),
            datetime(j, m, monthrange(j, m)[1], 23, 59, 59),
        )
    if zeitraum == "jahr":
        j = jahr or heute.year
        return datetime(j, 1, 1), datetime(j, 12, 31, 23, 59, 59)
    # "gesamt" — die ganze Aufzeichnung (Komponenten-Hub).
    return datetime(1970, 1, 1), datetime.combine(heute, datetime.max.time())


@router.get("/{anlage_id}", response_model=list[ZaehlerStandResponse])
async def get_zaehlerstaende(
    anlage_id: int,
    zeitraum: str = Query(
        "tag", pattern="^(tag|monat|jahr|gesamt)$",
        description="tag | monat | jahr | gesamt",
    ),
    datum: Optional[date] = Query(None, description="Nur bei zeitraum=tag"),
    jahr: Optional[int] = Query(None),
    monat: Optional[int] = Query(None, ge=1, le=12),
    mit_verlauf: bool = Query(True, description="Verlaufspunkte mitliefern"),
    db: AsyncSession = Depends(get_db),
):
    """Zählerstände einer Anlage für das gewählte Fenster — je Gerät.

    ⚠ **Es wird nie summiert.** Ein Zählerstand ist eine Bestandsgröße; zwei
    Gaszähler mit 12.345 und 8.900 ergeben nicht 21.245. Wer eine Summe
    braucht, meint die Differenzen — und die stehen einzeln in der Antwort.

    ``gesamt`` liefert auch **stillgelegte** Geräte: Nach einem Zählerwechsel
    gehört der alte Zähler in die Vergangenheit, in die er hineingemessen hat.
    Die laufenden Sichten (Tag/Monat/Jahr) zeigen ihn nur, solange er im
    Fenster aktiv war.
    """
    von, bis = _fenster(zeitraum, datum, jahr, monat)
    fenster = await lade_zaehlerstaende(
        db, anlage_id, von, bis,
        mit_verlauf=mit_verlauf,
        nur_aktive=(zeitraum != "gesamt"),
    )
    return [
        ZaehlerStandResponse(
            investition_id=f.investition_id,
            name=f.name,
            art=f.art,
            einheit=f.einheit,
            stand_anfang=f.stand_anfang,
            stand_ende=f.stand_ende,
            differenz=f.differenz,
            anfang_vollstaendig=f.anfang_vollstaendig,
            reihe_gebrochen=f.reihe_gebrochen,
            verlauf=[
                ZaehlerVerlaufPunktResponse(zeitpunkt=p.zeitpunkt, stand=p.stand)
                for p in f.verlauf
            ],
        )
        for f in fenster
    ]


@router.get("/{anlage_id}/heute", response_model=list[ZaehlerStandResponse])
async def get_zaehlerstaende_heute(
    anlage_id: int, db: AsyncSession = Depends(get_db)
):
    """*Live / Auf einen Blick*: aktueller Stand + Veränderung heute.

    Eigener Weg statt `?zeitraum=tag`, weil die Kachel den **aktuellsten**
    Stand zeigen soll und nicht den um 23:59 — das Fenster endet deshalb jetzt
    und nicht am Tagesende.
    """
    heute = date.today()
    fenster = await lade_zaehlerstaende(
        db, anlage_id,
        datetime.combine(heute, datetime.min.time()),
        datetime.now() + timedelta(minutes=1),
        mit_verlauf=False,
    )
    return [
        ZaehlerStandResponse(
            investition_id=f.investition_id,
            name=f.name,
            art=f.art,
            einheit=f.einheit,
            stand_anfang=f.stand_anfang,
            stand_ende=f.stand_ende,
            differenz=f.differenz,
            anfang_vollstaendig=f.anfang_vollstaendig,
            reihe_gebrochen=f.reihe_gebrochen,
        )
        for f in fenster
    ]
