"""Energie-Profil — Stunden- und Serienreihen.

GET /api/energie-profil/{anlage_id}/komponenten-serien — `komponenten_kwh`-Keys eines Zeitraums als SerieInfo
GET /api/energie-profil/{anlage_id}/stunden            — 24 Stundenwerte eines Tages
GET /api/energie-profil/{anlage_id}/wochenmuster       — Ø-Tagesprofil je Wochentag
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen import (
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    geraete_spalte_kw,
)
from backend.core.berechnungen.slot_konvention import forward_werte_je_backward_zeile
from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from ._shared import (
    SerieInfo,
    StundenAntwort,
    StundenWertResponse,
    WochenmusterPunkt,
    _key_to_serie_info,
)

router = APIRouter()


@router.get("/{anlage_id}/komponenten-serien", response_model=list[SerieInfo])
async def get_komponenten_serien(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Löst alle im Zeitraum vorkommenden `komponenten_kwh`-Keys zu SerieInfo
    (Label/Kategorie/Seite) auf.

    Dient der Tagestabelle, die pro Komponente eine eigene Diagnose-Spalte
    mit echtem Investitions-Label statt Roh-Key anbietet.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    result = await db.execute(
        select(TagesZusammenfassung.komponenten_kwh)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
    )
    alle_keys: set[str] = set()
    for (komponenten_kwh,) in result.all():
        if komponenten_kwh:
            alle_keys.update(komponenten_kwh.keys())

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    serien: list[SerieInfo] = []
    for key in sorted(alle_keys):
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
    return serien

@router.get("/{anlage_id}/stunden", response_model=StundenAntwort)
async def get_stundenwerte(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt die 24 Stundenwerte eines Tages aus TagesEnergieProfil zurück.

    Enthält zusätzlich `serien` mit aufgelösten Labels für alle in `komponenten`
    vorkommenden Einträge — damit Sonstiges-Investments (Poolpumpe, Sauna …)
    namentlich im Frontend angezeigt werden können.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    # N-553: der Ladestand jeder Zeile kommt aus ihrer **Vorzeile** — dieselbe
    # Regel wie in den Rechnungen (N-387, `slot_konvention`). Dafür wird der
    # Vortag mitgeladen: ohne seine Stunde 23 bekäme Slot 0 dieses Tages keinen
    # Wert, und das wäre eine Lücke, die es in den Daten nicht gibt.
    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= datum - timedelta(days=1),
            TagesEnergieProfil.datum <= datum,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    alle = result.scalars().all()
    soc_je_zeile = forward_werte_je_backward_zeile(alle, "soc_prozent")
    paare = [(z, soc) for z, soc in zip(alle, soc_je_zeile) if z.datum == datum]
    rows = [z for z, _ in paare]

    # ⭐ **Zwei Fragen, zwei Groessen** (N-553): Die Zeile oben beantwortet
    # „welcher Ladestand gehoert zu DIESER Stunde" — dafuer die Paarung. Die
    # Kachel „Ladestand · Stand am Tagesende" fragt etwas anderes: „was ist der
    # JUENGSTE gemessene Stand". Der steht ungepaart in der letzten Zeile des
    # Tages; durch die Paarung wandert er aus dem Tagesraster (er gehoert zu
    # Slot 0 des Folgetags). Deshalb reist er als eigenes Feld mit, statt dass
    # eine Groesse beide Fragen halb beantwortet.
    soc_zuletzt = next(
        (z.soc_prozent for z in reversed(rows) if z.soc_prozent is not None), None,
    )

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    # Alle vorkommenden Komponenten-Keys sammeln (über alle Stunden)
    alle_keys: set[str] = set()
    for r in rows:
        if r.komponenten:
            alle_keys.update(r.komponenten.keys())

    # Keys zu SerieInfo auflösen (nur einmal pro Key, geordnet)
    serien: list[SerieInfo] = []
    seen: set[str] = set()
    for key in sorted(alle_keys):
        if key in seen:
            continue
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
            seen.add(key)

    # #263/T1 — die Geräte-Sammelspalten kennen BEIDE Pfade.
    #
    # `waermepumpe_kw`/`wallbox_kw` kommen aus dem Zähler-Snapshot und bleiben
    # leer, wenn nur ein Leistungssensor zugeordnet ist — während derselbe Wert
    # in `komponenten` steht, die gerätebenannte Spalte daneben ihn zeigt und
    # der Monats-Modus-Split aus ihm rechnet. Die Auflösung („Zähler schlägt
    # Leistung, kein Key heißt None") liegt im Layer, nicht hier.
    #
    # ⚠ **Bewusst nur die Geräte-Spalten.** `pv_kw` und `verbrauch_kw` sind
    # Bilanzgrößen — an ihnen hängen Performance-Ratio sowie Überschuss/Defizit
    # (`aggregator.py`). Ein Fallback dort änderte die Bilanz, nicht eine
    # Anzeige; das wäre ein eigener Vorgang mit eigener Messung.
    stunden = [
        StundenWertResponse(
            stunde=r.stunde,
            pv_kw=r.pv_kw,
            verbrauch_kw=r.verbrauch_kw,
            einspeisung_kw=r.einspeisung_kw,
            netzbezug_kw=r.netzbezug_kw,
            batterie_kw=r.batterie_kw,
            waermepumpe_kw=geraete_spalte_kw(
                r.waermepumpe_kw, r.komponenten, WAERMEPUMPE_KOMPONENTEN_PREFIXE,
            ),
            wallbox_kw=geraete_spalte_kw(
                r.wallbox_kw, r.komponenten, WALLBOX_KOMPONENTEN_PREFIXE,
            ),
            ueberschuss_kw=r.ueberschuss_kw,
            defizit_kw=r.defizit_kw,
            temperatur_c=r.temperatur_c,
            globalstrahlung_wm2=r.globalstrahlung_wm2,
            soc_prozent=soc,
            komponenten=r.komponenten,
            wp_starts_anzahl=r.wp_starts_anzahl,
            wp_betriebsstunden=r.wp_betriebsstunden,
            spannen=r.spannen or None,
        )
        for r, soc in paare
    ]

    return StundenAntwort(
        stunden=stunden, serien=serien, soc_zuletzt_prozent=soc_zuletzt,
    )

@router.get("/{anlage_id}/wochenmuster", response_model=list[WochenmusterPunkt])
async def get_wochenmuster(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt durchschnittliche Stundenprofile je Wochentag zurück.

    Aggregiert TagesEnergieProfil-Werte über den Zeitraum und berechnet
    pro Wochentag (0=Mo … 6=So) × Stunde den Mittelwert.
    Basis für den Wochenvergleich-Chart im Energieprofil-Tab.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = result.scalars().all()

    # Aggregation in Python: {(wochentag, stunde) → {field: [values]}}
    # date.weekday(): 0=Mo, 1=Di, …, 6=So
    acc: dict[tuple[int, int], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    tage_set: dict[tuple[int, int], set] = defaultdict(set)

    for r in rows:
        wt = r.datum.weekday()
        key = (wt, r.stunde)
        tage_set[key].add(r.datum)
        for field in ("pv_kw", "verbrauch_kw", "netzbezug_kw", "einspeisung_kw", "batterie_kw"):
            val = getattr(r, field)
            if val is not None:
                acc[key][field].append(val)

    punkte: list[WochenmusterPunkt] = []
    for (wt, stunde) in sorted(acc.keys()):
        felder = acc[(wt, stunde)]
        punkte.append(WochenmusterPunkt(
            wochentag=wt,
            stunde=stunde,
            pv_kw=round(sum(felder["pv_kw"]) / len(felder["pv_kw"]), 3) if felder.get("pv_kw") else None,
            verbrauch_kw=round(sum(felder["verbrauch_kw"]) / len(felder["verbrauch_kw"]), 3) if felder.get("verbrauch_kw") else None,
            netzbezug_kw=round(sum(felder["netzbezug_kw"]) / len(felder["netzbezug_kw"]), 3) if felder.get("netzbezug_kw") else None,
            einspeisung_kw=round(sum(felder["einspeisung_kw"]) / len(felder["einspeisung_kw"]), 3) if felder.get("einspeisung_kw") else None,
            batterie_kw=round(sum(felder["batterie_kw"]) / len(felder["batterie_kw"]), 3) if felder.get("batterie_kw") else None,
            anzahl_tage=len(tage_set[(wt, stunde)]),
        ))

    return punkte
