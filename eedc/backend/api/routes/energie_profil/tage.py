"""Energie-Profil — Tagesreihen.

GET /api/energie-profil/{anlage_id}/tage       — Tageszusammenfassungen
GET /api/energie-profil/{anlage_id}/tage-werte — Tages-Werte-Zeilen (Bilanz + Finanzen)
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.einspeise_erloes_service import neg_preis_einspeisung_tageswert
from ._shared import TagesZusammenfassungResponse, TagWerteResponse

router = APIRouter()


@router.get("/{anlage_id}/tage", response_model=list[TagesZusammenfassungResponse])
async def get_tages_zusammenfassungen(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Tageszusammenfassungen für einen Zeitraum zurück.

    Enthält Per-Komponenten-kWh (z.B. pv_3, waermepumpe_5, wallbox_7)
    sowie Gesamtkennzahlen (Überschuss, Defizit, Peaks, Performance Ratio).
    """
    # Anlage prüfen
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    # Maximal 366 Tage (ein Jahr)
    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    # Tageszusammenfassungen laden
    result = await db.execute(
        select(TagesZusammenfassung)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
        .order_by(TagesZusammenfassung.datum)
    )
    tage = result.scalars().all()
    # HA-Bauform E4a-2 (Umschaltstelle 4): an Kanal-Tagen die Bilanz-Schlüssel aus den Kanälen (B-3).
    from backend.services.kanal.bilanz_leser import bilanz_ziele, kanal_tage, mische_komponenten

    kanal_je_tag = await kanal_tage(db, anlage_id, von, bis)
    ziele = await bilanz_ziele(db, anlage_id, kanal_je_tag) if kanal_je_tag else {}

    def _komp(t):
        k = kanal_je_tag.get(t.datum)
        return t.komponenten_kwh if k is None else mische_komponenten(t.komponenten_kwh, k, ziele[t.datum])

    return [
        TagesZusammenfassungResponse(
            datum=t.datum,
            ueberschuss_kwh=t.ueberschuss_kwh,
            defizit_kwh=t.defizit_kwh,
            peak_pv_kw=t.peak_pv_kw,
            peak_netzbezug_kw=t.peak_netzbezug_kw,
            peak_einspeisung_kw=t.peak_einspeisung_kw,
            batterie_vollzyklen=t.batterie_vollzyklen,
            temperatur_min_c=t.temperatur_min_c,
            temperatur_max_c=t.temperatur_max_c,
            strahlung_summe_wh_m2=t.strahlung_summe_wh_m2,
            gti_summe_wh_m2=t.gti_summe_wh_m2,
            performance_ratio=t.performance_ratio,
            stunden_verfuegbar=t.stunden_verfuegbar,
            datenquelle=t.datenquelle,
            komponenten_kwh=_komp(t),
            komponenten_starts=t.komponenten_starts,
            boersenpreis_avg_cent=t.boersenpreis_avg_cent,
            boersenpreis_min_cent=t.boersenpreis_min_cent,
            negative_preis_stunden=t.negative_preis_stunden,
            # §51-Menge nur bei Anlagen mit gesetztem Schalter; die Stundenzahl
            # daneben bleibt ungegatet — sie ist reine Marktinfo, kein Abzug.
            einspeisung_neg_preis_kwh=neg_preis_einspeisung_tageswert(
                anlage, t.einspeisung_neg_preis_kwh
            ),
        )
        for t in tage
    ]

@router.get("/{anlage_id}/tage-werte", response_model=list[TagWerteResponse])
async def get_tage_werte(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """Tages-Werte-Zeilen (Energie-Bilanz + Finanzen + tag-native Metriken)
    für die Werte/Tabelle-Embed-Sicht in Tagesgranularität (IA v4 E3).

    Eine Zeile pro Tag, additiv zur Monatsbilanz (Σ stündl. TEP-Rows über den
    SoT-Helper `bilanz_aus_stundenrows`). Finanzen über den `baue_finanz_zeile`-
    SoT (je-Monat-Tarif).
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    # Lazy-Import: Service importiert das Routes-Schema (`_shared`) → Top-Level-
    # Import hier ergäbe einen Zyklus (routes-Package ↔ Service).
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    return await baue_tage_werte(db, anlage, von, bis)
