"""N-700 — der Jahresbericht druckt keinen Speicher-Wirkungsgrad über 100 %, sondern dasselbe wie Cockpit → Übersicht.

Gemessen am HEAD `ee222ed7` (Speicher 2025, Ladung 1 200 / Entladung 1 320 kWh): PDF „Wirkungsgrad 110,0 %",
Cockpit `speicher_effizienz_prozent=None` mit `quelle="nicht-ermittelbar"`. Über 100 % kann kein Speicher (N-252); die
häufigste Ursache ist eine Ladung, die nur die PV-Ladung trägt (#281), und die meldet der Daten-Checker.

Seit N-700 ruft der Bericht den SoT `core/berechnungen/speicher_wirkungsgrad.py` wie das Cockpit; er steht in
`test_n252_speicher_wirkungsgrad_deckung.py::BRAUCHT_DEN_SOT`.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten


async def _anlage(db, entladung_je_monat: float):
    a = Anlage(anlagenname="N700", leistung_kwp=6.0, installationsdatum=date(2025, 1, 1),
               standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2020, 1, 1)))
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="PV", anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=10000.0, leistung_kwp=6.0)
    sp = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Speicher", anschaffungsdatum=date(2025, 1, 1),
                     anschaffungskosten_gesamt=6000.0, parameter={"kapazitaet_kwh": 10.0})
    db.add_all([pv, sp])
    await db.flush()
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=m, einspeisung_kwh=300.0, netzbezug_kwh=150.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=m,
                                      verbrauch_daten={"pv_erzeugung_kwh": 500.0}))
        db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2025, monat=m,
                                      verbrauch_daten={"ladung_kwh": 100.0, "entladung_kwh": entladung_je_monat}))
    await db.commit()
    return a.id


@pytest.mark.asyncio
@pytest.mark.parametrize("jahr", [2025, None])
async def test_ueber_100_prozent_steht_nicht_im_bericht(db, jahr):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _anlage(db, entladung_je_monat=110.0)
    pdf = (await build_jahresbericht_context(db, aid, jahr))["speicher"]["effizienz_prozent"]
    cockpit = await get_cockpit_uebersicht(aid, jahr=jahr, db=db)

    assert cockpit.speicher_effizienz_prozent is None
    assert cockpit.speicher_effizienz_quelle == "nicht-ermittelbar"
    assert pdf is None, f"PDF {pdf} % — am HEAD 110,0 %"


@pytest.mark.asyncio
async def test_moeglicher_wirkungsgrad_bleibt_derselbe(db):
    """Die Gegenrichtung: unter 100 % ändert sich nichts, PDF und Cockpit nennen dieselbe Zahl."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _anlage(db, entladung_je_monat=90.0)
    pdf = (await build_jahresbericht_context(db, aid, 2025))["speicher"]["effizienz_prozent"]
    cockpit = await get_cockpit_uebersicht(aid, jahr=2025, db=db)

    assert pdf == pytest.approx(90.0)
    assert round(pdf, 1) == cockpit.speicher_effizienz_prozent
