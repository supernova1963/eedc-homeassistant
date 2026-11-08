"""N-781 — Die ROI-Prognose bewertet die V2H-Entladung ohne Override zum Spread Bezug − Einspeisevergütung.

Regel (BERECHNUNGEN §3.4, CHANGELOG #397): ein gepflegter ``v2h_entlade_preis_cent`` gilt; ohne ihn bewertet der
Spread aus Bezugspreis und Einspeisevergütung die Entladung — dieselbe Rechnung wie Komponenten-Hub
(``dashboard_eauto.py``) und Aussichten (``finanzen.py``/``finanz_zerlegung.py``), alle über
``core/berechnungen/speicher_wirtschaftlichkeit.py::berechne_v2h_ersparnis`` (Spread ≥ 0).

Geprüft an der Route *Auswertungen → ROI* (``get_roi_dashboard``), Detail ``v2h_einsparung_euro`` der E-Auto-Zeile.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.roi import get_roi_dashboard
from backend.core.berechnungen.speicher_wirtschaftlichkeit import berechne_v2h_ersparnis
from backend.models import Anlage, Investition
from backend.models.strompreis import Strompreis

BEZUG_CENT = 32.0
EINSPEISE_CENT = 8.0
V2H_KWH_JAHR = 500.0

BASIS_E_AUTO = {
    "verbrauch_kwh_100km": 18,
    "jahresfahrleistung_km": 15000,
    "pv_ladeanteil_prozent": 60,
    "vergleich_verbrauch_l_100km": 7.5,
    "benzinpreis_euro": 1.70,
    "v2h_faehig": True,
    "v2h_entladung_kwh_jahr": V2H_KWH_JAHR,
}


async def _anlage_mit_eauto(db, params: dict, *, bezug: float = BEZUG_CENT, einspeise: float = EINSPEISE_CENT):
    anlage = Anlage(anlagenname="N781", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2023, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=bezug, einspeiseverguetung_cent_kwh=einspeise,
        verwendung="allgemein",
    ))
    inv = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="N781-Auto",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, parameter=dict(params),
    )
    db.add(inv)
    await db.flush()
    return anlage, inv


async def _v2h_einsparung(db, anlage, inv) -> float:
    result = await get_roi_dashboard(
        anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    zeile = next(x for x in result.berechnungen if x.investition_id == inv.id)
    return zeile.detail_berechnung["v2h_einsparung_euro"]


async def test_ohne_override_der_spread_wie_der_hub(db):
    """(1) Ohne Override: kWh × (Bezug − Vergütung)/100 — gleich der Layer-Rechnung, die der Hub ruft."""
    anlage, inv = await _anlage_mit_eauto(db, BASIS_E_AUTO)
    wert = await _v2h_einsparung(db, anlage, inv)
    hub = berechne_v2h_ersparnis(
        v2h_entladung_kwh=V2H_KWH_JAHR, bezug_preis_cent=BEZUG_CENT, einspeise_verg_cent=EINSPEISE_CENT,
    ).ersparnis_euro
    assert wert == pytest.approx(V2H_KWH_JAHR * (BEZUG_CENT - EINSPEISE_CENT) / 100)  # 120,00 €
    assert wert == pytest.approx(round(hub, 2))
    # (3) Gegenprobe: der alte Wert (voller Bezugspreis) ist es nicht mehr.
    assert wert != pytest.approx(V2H_KWH_JAHR * BEZUG_CENT / 100)  # 160,00 €


async def test_mit_override_gilt_der_gepflegte_preis(db):
    """(2) Mit Override: kWh × Override/100, unabhängig vom Tarif."""
    anlage, inv = await _anlage_mit_eauto(db, {**BASIS_E_AUTO, "v2h_entlade_preis_cent": 25})
    wert = await _v2h_einsparung(db, anlage, inv)
    assert wert == pytest.approx(V2H_KWH_JAHR * 25 / 100)  # 125,00 €


async def test_override_null_ist_ein_wert(db):
    """Ein gepflegter Override 0 ist eine Aussage (F-15) — kein Rückfall auf den Spread."""
    anlage, inv = await _anlage_mit_eauto(db, {**BASIS_E_AUTO, "v2h_entlade_preis_cent": 0})
    assert await _v2h_einsparung(db, anlage, inv) == 0


@pytest.mark.parametrize("leer", ["", None])
async def test_geleerter_override_rechnet_den_spread(db, leer):
    """Ein geleertes Feld (``""``/``None``, N-571) ist «nicht gepflegt» ⇒ Spread."""
    anlage, inv = await _anlage_mit_eauto(db, {**BASIS_E_AUTO, "v2h_entlade_preis_cent": leer})
    wert = await _v2h_einsparung(db, anlage, inv)
    assert wert == pytest.approx(V2H_KWH_JAHR * (BEZUG_CENT - EINSPEISE_CENT) / 100)


async def test_negativer_spread_wird_null_wie_im_layer(db):
    """Vergütung über dem Bezugspreis: der Layer klemmt den Spread auf 0 — die Prognose ebenso."""
    anlage, inv = await _anlage_mit_eauto(db, BASIS_E_AUTO, bezug=8.0, einspeise=12.0)
    assert await _v2h_einsparung(db, anlage, inv) == 0
