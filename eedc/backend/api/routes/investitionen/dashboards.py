"""
Investitionen-Dashboards — API Routes.

Pro-Investitionstyp-Dashboards (E-Auto, Wärmepumpe, Speicher, Wallbox,
Balkonkraftwerk, Sonstiges) plus die Investition-Monatsdaten-Abfrage.
2026-05-20 aus investitionen.py ausgelagert; der gemeinsame Router wird
in investitionen/__init__.py aggregiert.

Seit 18.09.2026 (Vorlage 6 des Refactorings grosser Dateien, reiner Umzug) liegt jedes Typ-Dashboard in
``dashboard_<typ>.py`` und die Preis-Mittelung samt Monatsdaten-Antwortmodell in ``dashboard_basis.py``; dieses
Modul behaelt die typunabhaengigen Sichten (Monatsdaten je Monat, CO2-Amortisation, Hub-Leer-Grund), haengt die
Typ-Router an ihrer bisherigen Stelle ein und exportiert die bisherigen Namen weiter.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import date
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_im_monat
from backend.core.hub_leer_grund import bestimme_leer_grund
from backend.core.berechnungen import summe_graue_last
from backend.api.routes.investitionen.dashboard_basis import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    GewichtetePreise,
    InvestitionMonatsdatenResponse,
)
from backend.api.routes.investitionen.dashboard_eauto import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_eauto_router,
    EAutoDashboardResponse,
    get_eauto_dashboard,
)
from backend.api.routes.investitionen.dashboard_waermepumpe import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_waermepumpe_router,
    WaermepumpeDashboardResponse,
    get_waermepumpe_dashboard,
)
from backend.api.routes.investitionen.dashboard_speicher import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_speicher_router,
    SpeicherDashboardResponse,
    get_speicher_dashboard,
)
from backend.api.routes.investitionen.dashboard_wallbox import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_wallbox_router,
    WallboxDashboardResponse,
    get_wallbox_dashboard,
)
from backend.api.routes.investitionen.dashboard_balkonkraftwerk import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_balkonkraftwerk_router,
    BalkonkraftwerkDashboardResponse,
    get_balkonkraftwerk_dashboard,
)
from backend.api.routes.investitionen.dashboard_sonstiges import (  # noqa: F401 — Re-Export (investitionen/__init__.py, Tests)
    router as _dashboard_sonstiges_router,
    SonstigesDashboardResponse,
    get_sonstiges_dashboard,
)

router = APIRouter()


# dashboard_eauto.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_eauto_router)


# dashboard_waermepumpe.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_waermepumpe_router)


# dashboard_speicher.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_speicher_router)


@router.get("/monatsdaten/{anlage_id}/{jahr}/{monat}", response_model=list[InvestitionMonatsdatenResponse])
async def get_investition_monatsdaten_by_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle InvestitionMonatsdaten für eine Anlage und einen bestimmten Monat zurück.

    Dies wird vom MonatsdatenForm benötigt, um beim Bearbeiten eines Monats
    die vorhandenen Investitionsdaten (E-Auto km, Speicher Ladung, etc.) zu laden.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        list[InvestitionMonatsdatenResponse]: Liste der InvestitionMonatsdaten
    """
    # Issue #123: MonatsdatenForm-Editor — zeige Investitionen, die in dem
    # bearbeiteten Monat aktiv waren (auch inzwischen stillgelegte).
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(aktiv_im_monat(jahr, monat))
    )
    investitionen = inv_result.scalars().all()

    # Batch-Query: Alle InvestitionMonatsdaten für diesen Monat auf einmal laden
    inv_ids = [inv.id for inv in investitionen]
    if not inv_ids:
        return []

    md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
        .where(InvestitionMonatsdaten.jahr == jahr)
        .where(InvestitionMonatsdaten.monat == monat)
    )
    return md_result.scalars().all()


# dashboard_wallbox.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_wallbox_router)


# dashboard_balkonkraftwerk.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_balkonkraftwerk_router)


# dashboard_sonstiges.py — Vorlage 6: das Dashboard haengt an seiner bisherigen Stelle (Routen-Reihenfolge unveraendert).
router.include_router(_dashboard_sonstiges_router)


# ============================================================================
# CO2-Amortisation (#284) — graue Herstellungs-Last je Anlage
# ============================================================================

class GraueLastPostenResponse(BaseModel):
    """Graue Herstellungs-Last (CO2) einer einzelnen Investition."""
    investition_id: Optional[int]
    typ: str
    bezeichnung: str
    graue_last_kg: float
    quelle: str  # override | default | fehlt | kein_default


class CO2AmortisationResponse(BaseModel):
    """Σ der grauen Herstellungs-Last (CO2) einer Anlage für die CO2-Amortisation.

    Das Frontend zeichnet `graue_last_gesamt_kg` als horizontale Linie in die
    kumulierte CO2-Einsparungskurve (CO2Tab) und markiert den Schnittpunkt
    „ab wann klimapositiv".
    """
    graue_last_gesamt_kg: float
    posten: list[GraueLastPostenResponse]


@router.get("/co2-amortisation/{anlage_id}", response_model=CO2AmortisationResponse)
async def get_co2_amortisation(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Σ der grauen Herstellungs-Last (CO2) über die Investitionen einer Anlage.

    Verwendet den SoT-Helper `core/berechnungen.summe_graue_last` (ADR-001):
    Override (`graue_last_kg`) ∨ Default-Richtwert nach Typ/Größe, Dienstwagen
    ausgeschlossen, inaktive Investitionen raus.
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    bericht = summe_graue_last(investitionen)

    return CO2AmortisationResponse(
        graue_last_gesamt_kg=bericht.gesamt_kg,
        posten=[
            GraueLastPostenResponse(
                investition_id=p.investition_id,
                typ=p.typ,
                bezeichnung=p.bezeichnung,
                graue_last_kg=p.graue_last_kg,
                quelle=p.quelle,
            )
            for p in bericht.posten
        ],
    )


class HubLeerGrundResponse(BaseModel):
    """Warum der Komponenten-Reiter eines Geräts ohne Zahlen dasteht (N-247)."""

    leer: bool
    art: Optional[str] = None
    meldung: Optional[str] = None
    details: Optional[str] = None
    link: Optional[str] = None
    link_label: Optional[str] = None


@router.get("/hub-leer-grund/{anlage_id}/{investition_id}", response_model=HubLeerGrundResponse)
async def get_hub_leer_grund(
    anlage_id: int,
    investition_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Der Grund, warum ein Gerät im Komponenten-Hub keine Monatswerte zeigt (N-247).

    **Der Grund kommt aus dem Backend, nicht aus einer Client-Ableitung**
    (Gernot 2026-08-06: „zweite Wahrheit ist nicht gut") — genau wie bei
    ``TagLeerGrund``/``getTagStatus``. Der Server prüft die Leere auch selbst
    nach, statt der Behauptung des Clients zu folgen: gezählt wird mit
    **demselben Filter wie die Dashboards** (``ist_aktiv_im_monat``), sonst
    könnte der Hinweis neben gefüllten Blöcken stehen.

    ⚠ **Grenze dieser Invariante — ein E-Auto mit nur Restzeilen (N-564).** Gezählt werden
    gespeicherte ``InvestitionMonatsdaten``. Seit N-555 Stufe 2 bekommt ein privates Auto ohne
    eigene Monatszeile den Rest der Wallbox, und der E-Auto-Hub zeigt dafür Anzeigezeilen ohne
    ID (``ladung_aus_rest``, ``dashboard_eauto.py``); seit Stufe 3 kann seine Heimladung auch
    allein aus Ladeblöcken stammen (``emob_ladebloecke``). Hier kommt dann ``leer=True``
    heraus, und weil der Adapter (``v4/komponentenAdapter.tsx``, N-564) nur erfasste Zeilen
    als Monatswerte zählt, **steht der Hinweis „noch keine Monatswerte" in genau diesem Fall
    neben gefüllten Blöcken** — Kachel und Tabelle tragen den Wallbox-Rest. Das ist benannt,
    nicht behoben: der Satz sagt dort weiter die Wahrheit über die *erfassten* Monate.

    ``leer=False`` ⇒ das Gerät hat Monatswerte, die Sicht zeigt nichts an.
    """
    result = await db.execute(
        select(Investition)
        .where(Investition.id == investition_id)
        .where(Investition.anlage_id == anlage_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    md_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )
    hat_werte = any(
        inv.ist_aktiv_im_monat(md.jahr, md.monat) for md in md_result.scalars().all()
    )
    if hat_werte:
        return HubLeerGrundResponse(leer=False)

    grund = bestimme_leer_grund(
        aktiv=bool(inv.aktiv),
        anschaffungsdatum=inv.anschaffungsdatum,
        stilllegungsdatum=inv.stilllegungsdatum,
        heute=date.today(),
    )
    return HubLeerGrundResponse(
        leer=True,
        art=grund.art.value,
        meldung=grund.meldung,
        details=grund.details,
        link=grund.link,
        link_label=grund.link_label,
    )
