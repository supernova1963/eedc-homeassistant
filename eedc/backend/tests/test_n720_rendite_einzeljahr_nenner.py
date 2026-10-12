"""N-720 — die Rendite eines Einzeljahres teilt durch die Mehrkosten der bis zum 31.12. angeschafften Investitionen.

Gemessen am HEAD `0c3a89fa`: `cockpit/uebersicht.py` lud alle Investitionen ohne Jahresfilter (#123) und teilte auch
mit `jahr=` durch ihre Mehrkosten — T2 (PV 10 000 € ab 01/2024, E-Auto 5 000 € Mehrkosten ab 01/2025) Rendite 2024
**6,7 %** = 1 008 ÷ 15 000, während der Amortisations-Fortschritt desselben Berichts (Stand 31.12.2024, N-699) auf
10 000 € rechnet. Das Jahresbericht-PDF übernimmt beide Zahlen (`rendite_nenner_euro`).

Entscheid Master 12.10.2026: dieselbe Grenze wie beim Fortschritt — im Einzeljahr nur Investitionen mit
Anschaffungsdatum ≤ 31.12. des Jahres im Nenner (ohne Datum bleiben sie, wie `finanz_eingaenge.py`). Soll T2 2024:
1 008 ÷ 10 000 = **10,1 %**. Gesamtzeitraum unverändert (alle Investitionen).

Schwesterdateien: test_n699_pdf_betriebskosten_amortisation.py (Fortschritt mit Stichtag, PDF = Übersicht).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.tests.test_n699_pdf_betriebskosten_amortisation import _m, _seed

_EAUTO_2025 = ("e-auto", dict(anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=35000.0,
                              anschaffungskosten_alternativ=30000.0, parameter={}),
               {jm: {"km_gefahren": 1000, "verbrauch_kwh": 180.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 90.0}
                for jm in _m((2025,))})


@pytest.mark.asyncio
@pytest.mark.parametrize("jahr, nenner, rendite", [(2024, 10000.0, 10.1), (2025, 15000.0, 13.9), (None, 15000.0, 20.6)])
async def test_rendite_nenner_kennt_nur_die_bis_zum_jahresende_angeschafften(db, jahr, nenner, rendite):
    """2024: ohne das Auto (Soll 1 008 ÷ 10 000 = 10,1 %; HEAD 6,7 % auf 15 000 €); 2025 (2 088 ÷ 15 000 = 13,9 %) und
    Gesamtzeitraum (3 096 ÷ 15 000 = 20,6 %): mit dem Auto, am HEAD gemessen und unverändert."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.services.pdf.builders.jahresbericht import build_jahresbericht_context

    aid = await _seed(db, monate=_m((2024, 2025)), extra=[_EAUTO_2025])
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=jahr, db=db)
    k = (await build_jahresbericht_context(db, aid, jahr))["kpis"]

    assert u.investition_mehrkosten_euro == pytest.approx(nenner), (jahr, u.investition_mehrkosten_euro)
    assert u.investition_gesamt_euro == pytest.approx(nenner), jahr
    assert u.jahres_rendite_prozent == pytest.approx(rendite), (jahr, u.jahres_rendite_prozent)
    # PDF folgt der Übersicht und nennt denselben Nenner.
    assert (k["rendite_prozent"], k["rendite_nenner_euro"]) == (u.jahres_rendite_prozent, u.investition_mehrkosten_euro)


@pytest.mark.asyncio
async def test_rendite_nenner_wie_der_kapitaleinsatz_des_fortschritts(db):
    """Dieselbe Grenze wie beim Fortschritt zum 31.12. (N-699): ohne sonstige Positionen ist der Kapitaleinsatz die
    Mehrkosten — beide Nenner des Berichts sind für 2024 dieselbe Zahl."""
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    aid = await _seed(db, monate=_m((2024, 2025)), extra=[_EAUTO_2025])
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=2024, db=db)
    p = await get_finanz_prognose(aid, monate=12, db=db, stichtag=date(2024, 12, 31))
    assert u.investition_mehrkosten_euro == pytest.approx(p.kapitaleinsatz_euro) == pytest.approx(10000.0)


@pytest.mark.asyncio
async def test_investition_ohne_anschaffungsdatum_bleibt_im_nenner(db):
    """Ohne Anschaffungsdatum gibt es keine Grenze — die Investition bleibt (wie `finanz_eingaenge.py`, N-699)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    ohne_datum = ("e-auto", dict(anschaffungsdatum=None, anschaffungskosten_gesamt=35000.0,
                                 anschaffungskosten_alternativ=30000.0, parameter={}), {})
    aid = await _seed(db, monate=_m((2024, 2025)), extra=[ohne_datum])
    u = await get_cockpit_uebersicht(anlage_id=aid, jahr=2024, db=db)
    assert u.investition_mehrkosten_euro == pytest.approx(15000.0)
