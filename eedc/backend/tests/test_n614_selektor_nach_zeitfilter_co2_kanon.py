"""Klasse „Selektor vor Zeitfilter" (N-613/N-614/N-615) — die beiden Stellen ohne sichtbare Wirkung.

ADR-002/P11, Abgrenzung (a): erst der Zeitfilter, dann ``erzeuger_traeger``. Zwei
Stellen wandten den Selektor bis 03.10.2026 auf die ungefilterte Menge an und
filterten erst danach:

* ``core/berechnungen/co2_amortisation.py::summe_graue_last`` — mit Stichtag vor
  der Anschaffung der Modul-Kinder fehlte die graue Last des Balkonkraftwerks.
  Der einzige Aufrufer (``investitionen/dashboards.py``) übergibt keinen Stichtag.
* ``services/prognose_kanon.py::_kappungs_mitglieder`` — an einem Prognosetag vor
  der Anschaffung der Kinder fehlte das BKW in der Mitgliederliste; teilte es
  eine Orientierungsgruppe mit gekappten Mitgliedern, fehlte sein Ertrag dort
  (der Kappungs-Zweig ersetzt das kWp-Tagesgewicht). Nur im Prognose-Horizont
  vor einer Anschaffung in der Zukunft.

Kinder bewusst mit anderer kWp als das BKW (0,6 + 0,2 gegen 0,8 ist gleich —
deshalb hier 0,5 + 0,5 = 1,0 ≠ 0,8), damit eine Verwechslung der Mengen eine
andere Zahl ergibt.

Schwesterdateien: test_n614_jahresbericht_string_vergleich_je_monat.py,
test_n613_pv_strings_abtretung_je_monat.py, test_n615_tag_abtretung_am_datum.py
(dieselbe Klasse), test_bkw_parent_pv_module_n266.py (der Selektor selbst),
test_bkw_kanon_und_wr_kappung_347.py (Kappung der Prognose).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.core.berechnungen.co2_amortisation import summe_graue_last
from backend.core.calculations import GRAUE_LAST_PV_KG_PRO_KWP
from backend.models.investition import Investition

D0 = date(2024, 1, 1)
SEP_25 = date(2025, 9, 1)


def _inv(i, typ, kwp, ab, parent=None, aktiv=True, parameter=None, neigung=None):
    return Investition(id=i, anlage_id=1, typ=typ, bezeichnung=f"inv{i}", leistung_kwp=kwp,
                       anschaffungsdatum=ab, parent_investition_id=parent, aktiv=aktiv,
                       parameter=parameter or {}, neigung_grad=neigung)


def _k3(kind_ab=SEP_25, kind_aktiv=True):
    return [
        _inv(1, "pv-module", 6.0, D0), _inv(3, "balkonkraftwerk", 0.8, D0),
        _inv(21, "pv-module", 0.5, kind_ab, parent=3, aktiv=kind_aktiv),
        _inv(22, "pv-module", 0.5, kind_ab, parent=3, aktiv=kind_aktiv),
    ]


def _posten(bericht) -> dict:
    return {p.investition_id: p.graue_last_kg for p in bericht.posten}


# ── graue Last ───────────────────────────────────────────────────────────────

def test_graue_last_stichtag_vor_den_kindern_traegt_das_bkw():
    b = summe_graue_last(_k3(), date(2025, 5, 31))
    assert _posten(b) == {1: 6.0 * GRAUE_LAST_PV_KG_PRO_KWP, 3: 0.8 * GRAUE_LAST_PV_KG_PRO_KWP}


def test_graue_last_stichtag_nach_den_kindern_tragen_die_kinder():
    b = summe_graue_last(_k3(), date(2025, 12, 31))
    assert _posten(b) == {1: 6000.0, 21: 500.0, 22: 500.0}


def test_graue_last_ohne_stichtag_unveraendert():
    """Der einzige heutige Aufruf (Komponenten-Dashboard) — wie vor dem Umbau."""
    assert _posten(summe_graue_last(_k3())) == {1: 6000.0, 21: 500.0, 22: 500.0}


def test_graue_last_inaktives_kind_nimmt_dem_bkw_nichts_ab():
    """`aktiv=False` heißt „wie gelöscht" — das Kind kann nichts abtreten."""
    assert _posten(summe_graue_last(_k3(kind_aktiv=False))) == {1: 6000.0, 3: 800.0}


# ── Kappungs-Mitglieder der Prognose ─────────────────────────────────────────

def _kanon_anlage(heute: date):
    """Süd 6 kWp an einem 5-kW-Wechselrichter (gekappt), BKW 0,8 kWp in DERSELBEN
    Ausrichtung (Süd, 35°) mit 600 W, Kinder Ost/West ab übermorgen."""
    wr = _inv(9, "wechselrichter", None, D0, parameter={"max_leistung_kw": 5.0})
    sued = _inv(1, "pv-module", 6.0, D0, parent=9, parameter={"ausrichtung_grad": 0}, neigung=35)
    bkw = _inv(3, "balkonkraftwerk", 0.8, D0,
               parameter={"ausrichtung_grad": 0, "wechselrichter_leistung_w": 600}, neigung=35)
    ost = _inv(21, "pv-module", 0.5, heute + timedelta(days=2), parent=3,
               parameter={"ausrichtung_grad": -90}, neigung=35)
    west = _inv(22, "pv-module", 0.5, heute + timedelta(days=2), parent=3,
                parameter={"ausrichtung_grad": 90}, neigung=35)
    return [sued, bkw, ost, west], wr


def test_kappungs_mitglieder_vor_den_kindern_enthalten_das_bkw():
    from backend.core.berechnungen.wr_kappung import zuordne_grenzen
    from backend.services.prognose_kanon import _kappungs_mitglieder
    from backend.services.pv_orientation import orientierungs_gruppen

    heute = date(2026, 10, 3)
    invs, wr = _kanon_anlage(heute)
    gruppen = orientierungs_gruppen(invs)
    grenzen = zuordne_grenzen(invs, [wr], [])
    sued_idx = next(i for i, g in enumerate(gruppen) if g.ausrichtung == 0)

    heute_m = _kappungs_mitglieder(invs, gruppen, heute, grenzen)
    assert sorted(m.kwp for m in heute_m[sued_idx]) == [0.8, 6.0], "BKW trägt heute noch selbst"
    assert sum(len(g) for i, g in enumerate(heute_m) if i != sued_idx) == 0

    spaeter = _kappungs_mitglieder(invs, gruppen, heute + timedelta(days=2), grenzen)
    assert [m.kwp for m in spaeter[sued_idx]] == [6.0], "ab den Kindern ist das BKW Träger, kein Mitglied"
    assert sorted(m.kwp for i, g in enumerate(spaeter) if i != sued_idx for m in g) == [0.5, 0.5]
