"""Sizing-Simulator — „lohnt sich ein größerer Speicher?" (#358 Phase 3).

Eigene Route aus demselben Grund wie `speicher_potential.py`: die Auswertung
liest **Stundendaten** über die ganze Lebensdauer und soll nur laufen, wenn die
Sicht sie anfordert.

Die Antwort liefert **Zahlen und ihre Herkunft**, keinen fertigen Satz — der
Klartext-Befund steht in der Sicht (`SpeicherSizingIST.tsx`), wo auch die
Sprach-Wächter greifen. Was sie mitliefern muss, ist alles, was diesen Satz
ehrlich macht: ob die Basis gemessen oder gepflegt ist, wie lang die Historie
ist, und mit welchem Tarif gerechnet wurde.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.speicher_sizing_service import (
    MIN_TAGE_FUER_AUSSAGE,
    lade_sizing_auswertung,
)

router = APIRouter()


class SizingPunktResponse(BaseModel):
    """Eine simulierte Kapazität und ihr Ergebnis."""

    faktor: float = Field(description="Vielfaches der heutigen Kapazität (0,5 … 2,0)")
    kapazitaet_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    eigenverbrauch_kwh: float
    delta_netzbezug_kwh: float = Field(
        description="Gegen heute; negativ = weniger Netzbezug"
    )
    delta_einspeisung_kwh: float
    nutzen_euro_jahr: Optional[float] = Field(
        description="Netto auf ein Jahr hochgerechnet: gesparter Bezug MINUS "
                    "entgangene Einspeisung (Spread-Kanon)"
    )
    mehrkosten_euro: Optional[float]
    amortisation_jahre: Optional[float] = Field(
        description="None, wenn es nichts zu amortisieren gibt oder der Nutzen ≤ 0 ist"
    )


class SpeicherSizingResponse(BaseModel):
    """Antwort des Sizing-Simulators.

    ``basis_kalibriert`` ist das wichtigste Feld für die Sicht: es entscheidet,
    ob die Kurve auf der **gemessenen** Speicherbewegung steht oder nur auf den
    gepflegten Parametern. Mit gepflegten Parametern verfehlte die Simulation an
    der Vorprüfungs-Anlage den Netzbezug um −17,5 %, kalibriert um −4,3 % — der
    Unterschied gehört ausgewiesen, nicht verschwiegen.
    """

    kurve: list[SizingPunktResponse]

    basis_kapazitaet_kwh: float
    basis_roundtrip_prozent: float
    basis_kalibriert: bool
    #: Nur bei geglückter Kalibrierung gefüllt — die Belege der Messung.
    kalibrierung_paare_laden: Optional[int]
    kalibrierung_paare_entladen: Optional[int]
    kalibrierung_stunden_verworfen: Optional[int]

    gepflegte_kapazitaet_kwh: Optional[float]
    gepflegter_wirkungsgrad_prozent: float

    tage_mit_daten: int
    tage_simuliert: int
    historie_reicht: bool
    min_tage_fuer_aussage: int
    von: Optional[date]
    bis: Optional[date]
    anzahl_speicher: int

    #: Der HEUTE gültige Tarif — die Frage ist nach vorn gerichtet (s. Service).
    bezug_preis_cent: Optional[float]
    einspeise_verg_cent: Optional[float]
    richtpreis_eur_je_kwh: float


@router.get("/speicher-sizing/{anlage_id}", response_model=SpeicherSizingResponse)
async def get_speicher_sizing(
    anlage_id: int,
    von: Optional[date] = Query(None, description="Erster Tag (Vorgabe: gesamte Historie)"),
    bis: Optional[date] = Query(None, description="Letzter Tag"),
    db: AsyncSession = Depends(get_db),
):
    """Simuliert die reale Stundenreihe mit 50 % bis 200 % der heutigen Kapazität.

    Die Kurve kommt vollständig in **einer** Antwort: der Slider in der Sicht
    liest daraus und fragt nicht bei jedem Schritt nach.
    """
    a = await lade_sizing_auswertung(db, anlage_id, von=von, bis=bis)

    return SpeicherSizingResponse(
        kurve=[
            SizingPunktResponse(
                faktor=p.faktor,
                kapazitaet_kwh=round(p.kapazitaet_kwh, 1),
                einspeisung_kwh=round(p.einspeisung_kwh, 1),
                netzbezug_kwh=round(p.netzbezug_kwh, 1),
                eigenverbrauch_kwh=round(p.eigenverbrauch_kwh, 1),
                delta_netzbezug_kwh=round(p.delta_netzbezug_kwh, 1),
                delta_einspeisung_kwh=round(p.delta_einspeisung_kwh, 1),
                nutzen_euro_jahr=(
                    None if p.nutzen_euro_jahr is None else round(p.nutzen_euro_jahr, 2)
                ),
                mehrkosten_euro=(
                    None if p.mehrkosten_euro is None else round(p.mehrkosten_euro, 0)
                ),
                amortisation_jahre=(
                    None if p.amortisation_jahre is None else round(p.amortisation_jahre, 1)
                ),
            )
            for p in a.kurve
        ],
        basis_kapazitaet_kwh=round(a.basis_kapazitaet_kwh, 1),
        basis_roundtrip_prozent=round(a.basis_roundtrip * 100, 1),
        basis_kalibriert=a.basis_kalibriert,
        kalibrierung_paare_laden=a.kalibrierung.paare_laden if a.kalibrierung else None,
        kalibrierung_paare_entladen=(
            a.kalibrierung.paare_entladen if a.kalibrierung else None
        ),
        kalibrierung_stunden_verworfen=(
            a.kalibrierung.stunden_verworfen if a.kalibrierung else None
        ),
        gepflegte_kapazitaet_kwh=(
            None if a.gepflegte_kapazitaet_kwh is None
            else round(a.gepflegte_kapazitaet_kwh, 1)
        ),
        gepflegter_wirkungsgrad_prozent=a.gepflegter_wirkungsgrad_prozent,
        tage_mit_daten=a.tage_mit_daten,
        tage_simuliert=a.tage_simuliert,
        historie_reicht=a.historie_reicht,
        min_tage_fuer_aussage=MIN_TAGE_FUER_AUSSAGE,
        von=a.von,
        bis=a.bis,
        anzahl_speicher=a.anzahl_speicher,
        bezug_preis_cent=a.bezug_preis_cent,
        einspeise_verg_cent=a.einspeise_verg_cent,
        richtpreis_eur_je_kwh=a.richtpreis_eur_je_kwh,
    )
