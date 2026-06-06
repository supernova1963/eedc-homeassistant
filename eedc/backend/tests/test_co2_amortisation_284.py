"""Akzeptanztests #284: CO2-Amortisation — graue Herstellungs-Last.

Die graue Last wird gegen die kumulierte CO2-Betriebs-Einsparung gerechnet
(Schnittpunkt „ab wann klimapositiv"). Spec (Discussion #284, mit Safi105
abgestimmt, in der Übergabe eingefroren):

  - PV/Speicher: voller Herstellungs-Aufwand (× kWp bzw. × kWh).
  - Wärmepumpe/E-Auto: flat-Differenz zur Alternative (Gas/Öl bzw. Verbrenner).
  - Override (`graue_last_kg`, Herstellerdatenblatt) schlägt den Typ-Default.
  - Dienstwagen-E-Autos sind ausgeschlossen ([[feedback_dienstwagen_alle_checks]]).
  - aktiv=False = wie gelöscht → nirgends ([[feedback_aktiv_inaktiv_semantik]]).

Der Helper ist rein → in-memory Investition-Objekte, keine DB nötig.
"""

from __future__ import annotations

from datetime import date

from backend.core.berechnungen.co2_amortisation import (
    QUELLE_DEFAULT,
    QUELLE_FEHLT,
    QUELLE_OVERRIDE,
    graue_last_einzeln,
    summe_graue_last,
)
from backend.core.calculations import (
    GRAUE_LAST_EAUTO_KG,
    GRAUE_LAST_PV_KG_PRO_KWP,
    GRAUE_LAST_SPEICHER_KG_PRO_KWH,
    GRAUE_LAST_WAERMEPUMPE_KG,
)
from backend.models.investition import Investition


def _inv(**kw) -> Investition:
    """In-memory Investition (nicht persistiert) — Helper liest nur Attribute."""
    return Investition(**kw)


# --- Default-Richtwerte je Typ ------------------------------------------------

def test_pv_default_skaliert_mit_kwp():
    last, quelle = graue_last_einzeln(_inv(typ="pv-module", leistung_kwp=10.0))
    assert last == 10.0 * GRAUE_LAST_PV_KG_PRO_KWP  # 10 kWp × 1000 = 10000
    assert quelle == QUELLE_DEFAULT


def test_balkonkraftwerk_wie_pv():
    last, quelle = graue_last_einzeln(_inv(typ="balkonkraftwerk", leistung_kwp=0.8))
    assert last == 0.8 * GRAUE_LAST_PV_KG_PRO_KWP
    assert quelle == QUELLE_DEFAULT


def test_speicher_default_skaliert_mit_kwh():
    inv = _inv(typ="speicher", parameter={"kapazitaet_kwh": 8.0})
    last, quelle = graue_last_einzeln(inv)
    assert last == 8.0 * GRAUE_LAST_SPEICHER_KG_PRO_KWH  # 8 × 85 = 680
    assert quelle == QUELLE_DEFAULT


def test_waermepumpe_flat_differenz():
    last, quelle = graue_last_einzeln(_inv(typ="waermepumpe"))
    assert last == GRAUE_LAST_WAERMEPUMPE_KG  # 1100 flat
    assert quelle == QUELLE_DEFAULT


def test_eauto_flat_differenz():
    last, quelle = graue_last_einzeln(_inv(typ="e-auto"))
    assert last == GRAUE_LAST_EAUTO_KG  # 5000 flat
    assert quelle == QUELLE_DEFAULT


def test_typ_ohne_richtwert_ist_null():
    # Wechselrichter ist in der PV-kWp-Last enthalten, Wallbox/Sonstiges haben
    # keinen Richtwert → 0, aber nicht als ERROR.
    last, quelle = graue_last_einzeln(_inv(typ="wechselrichter"))
    assert last == 0.0
    assert quelle != QUELLE_FEHLT


# --- Override schlägt Default -------------------------------------------------

def test_override_schlaegt_default():
    inv = _inv(typ="pv-module", leistung_kwp=10.0, graue_last_kg=500.0)
    last, quelle = graue_last_einzeln(inv)
    assert last == 500.0  # NICHT 10000
    assert quelle == QUELLE_OVERRIDE


def test_override_auch_fuer_typ_ohne_default():
    inv = _inv(typ="wallbox", graue_last_kg=120.0)
    last, quelle = graue_last_einzeln(inv)
    assert last == 120.0
    assert quelle == QUELLE_OVERRIDE


# --- Fehlende Größe = sichtbar (ERROR), nicht still 0 -------------------------

def test_pv_ohne_kwp_meldet_fehlt():
    last, quelle = graue_last_einzeln(_inv(typ="pv-module", leistung_kwp=None))
    assert last == 0.0
    assert quelle == QUELLE_FEHLT


# --- Σ über die Anlage --------------------------------------------------------

def test_summe_und_dienstwagen_ausschluss():
    investitionen = [
        _inv(id=1, typ="pv-module", leistung_kwp=10.0),                     # 10000
        _inv(id=2, typ="speicher", parameter={"kapazitaet_kwh": 8.0}),      # 680
        _inv(id=3, typ="waermepumpe"),                                      # 1100
        _inv(id=4, typ="e-auto"),                                           # 5000
        _inv(id=5, typ="e-auto", parameter={"ist_dienstlich": True}),      # AUS
    ]
    bericht = summe_graue_last(investitionen)
    assert bericht.gesamt_kg == 10000 + 680 + 1100 + 5000
    # Dienstwagen taucht auch nicht in der Aufschlüsselung auf.
    assert all(p.investition_id != 5 for p in bericht.posten)
    assert len(bericht.posten) == 4


def test_summe_excludes_inaktiv():
    investitionen = [
        _inv(id=1, typ="pv-module", leistung_kwp=10.0),
        _inv(id=2, typ="waermepumpe", aktiv=False),  # wie gelöscht
    ]
    bericht = summe_graue_last(investitionen)
    assert bericht.gesamt_kg == 10000
    assert len(bericht.posten) == 1


def test_stichtag_grenzt_nach_anschaffung_ab():
    investitionen = [
        _inv(id=1, typ="pv-module", leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)),
        _inv(id=2, typ="e-auto", anschaffungsdatum=date(2026, 6, 1)),  # nach Stichtag
    ]
    bericht = summe_graue_last(investitionen, stichtag=date(2025, 12, 31))
    assert bericht.gesamt_kg == 10000  # E-Auto noch nicht angeschafft
    assert len(bericht.posten) == 1


# --- Schnittpunkt-Semantik (Akzeptanz: Σ Einsparung ≥ graue Last) -------------

def test_schnittpunkt_semantik():
    """Klimapositiv ab dem Monat, in dem die kumulierte Einsparung die Σ graue
    Last erreicht. Spiegelt die Frontend-Logik gegen den Backend-Σ-Wert."""
    graue_last = summe_graue_last(
        [_inv(typ="pv-module", leistung_kwp=10.0)]
    ).gesamt_kg  # 10000

    # 3000 kg/Jahr Betriebs-Einsparung → erst nach >3 Jahren gedeckt.
    kumuliert = [3000, 6000, 9000, 12000]
    erster_klimapositiver = next(
        (i for i, k in enumerate(kumuliert) if k >= graue_last), None
    )
    assert erster_klimapositiver == 3  # 12000 ≥ 10000
