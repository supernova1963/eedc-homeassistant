"""N-770 E4 F4 (Bauplan §2) — Prognose und ROI-Jahresformel mit dem gemessenen PV-Anteil der Wärmepumpe.

Gemessener Anteil P/S der letzten 12 abgeschlossenen Monate (``monats_fakten.gemessener_wp_pv_anteil``), nur Monate, in
denen die Monats-Fakten den Netzbezug zum WP-Tarif ansetzen; ohne Messung rechnen Prognose und ROI wie bisher (bitgleich).
Zahlen aus der E2-Probe (S = 426,7, N = 256 ⇒ P = 170,7; H = 30 ct, W = 22 ct).

Schwesterdateien: test_n770_netzbezug_komponenten_tarif.py, test_n770_e3_tag_stunde.py, test_rf18_finanz_prognose_faelle.py.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.api.routes.aussichten.finanz_prognose import _ev_ersparnis_prognose
from backend.api.routes.investitionen.roi_pv import _ev_ersparnis_jahr
from backend.services.monats_fakten import gemessener_wp_pv_anteil, lade_monats_fakten
from backend.tests.test_n770_netzbezug_komponenten_tarif import JAHR, N, P, S, _anlage

HEUTE = date(JAHR + 1, 1, 15)


async def test_gemessener_anteil_der_letzten_zwoelf_abgeschlossenen_monate(db):
    anlage = await _anlage(db, monate=range(1, 13))
    fakten = await lade_monats_fakten(db, anlage.id)
    a = gemessener_wp_pv_anteil(fakten, HEUTE)
    assert a.monate == 12 and a.quote == pytest.approx(P / S)
    assert a.pv_jahr_kwh == pytest.approx(12 * P) and a.strom_jahr_kwh == pytest.approx(12 * S)
    # der laufende Monat zählt nicht
    assert gemessener_wp_pv_anteil(fakten, date(JAHR, 1, 20)) is None


async def test_ohne_feld_kein_anteil(db):
    anlage = await _anlage(db, wp=((S, None),), monate=range(1, 13))
    assert gemessener_wp_pv_anteil(await lade_monats_fakten(db, anlage.id), HEUTE) is None


async def test_ohne_eigenen_wp_tarif_kein_anteil(db):
    anlage = await _anlage(db, wp_tarif=False, monate=range(1, 13))
    assert gemessener_wp_pv_anteil(await lade_monats_fakten(db, anlage.id), HEUTE) is None


def test_prognose_bewertet_den_pv_anteil_des_wp_stroms_zum_wp_tarif():
    ev, wp_strom = 350.0, 200.0
    assert _ev_ersparnis_prognose(ev, 30.0, wp_strom, None) == ev * 30.0 / 100
    p = P / S * wp_strom
    assert _ev_ersparnis_prognose(ev, 30.0, wp_strom, (P / S, 22.0)) == pytest.approx((ev - p) * 0.30 + p * 0.22)


async def test_roi_jahresformel_mit_gemessenem_anteil(db):
    anlage = await _anlage(db, monate=range(1, 13))
    fakten = await lade_monats_fakten(db, anlage.id)
    ctx = SimpleNamespace(anlage_fakten=fakten, strompreis_cent=30.0, wp_tarif_cent=22.0)
    ev_jahr = 12 * 350.0
    euro, anteil = _ev_ersparnis_jahr(ctx, ev_jahr, heute=HEUTE)
    p_jahr = 12 * (S - N)
    assert anteil is not None and euro == pytest.approx((ev_jahr - p_jahr) * 0.30 + p_jahr * 0.22)
    ohne = SimpleNamespace(anlage_fakten=fakten, strompreis_cent=30.0, wp_tarif_cent=None)
    assert _ev_ersparnis_jahr(ohne, ev_jahr, heute=HEUTE) == (ev_jahr * 30.0 / 100, None)
