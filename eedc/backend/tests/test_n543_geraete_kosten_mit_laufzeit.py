"""N-543 — der Geraete-Sensor `investition_gesamt_euro` traegt seine Laufzeit als Attribute.

Gernot, 21.09.2026: „Es werden Gesamtkosten exportiert, aber ohne Anschaffungs-/
Stilllegungsdatum. Wird das nicht gebraucht?" — Gemessen: der Geraete-Export laeuft
ueber alle Investitionen (auch stillgelegte), die anlagenweite Summe nur ueber die
heute aktiven. Ohne Attribut waren das zwei Zahlen in HA, die nicht zusammenpassen.

Schwesterdatei: ``test_s3_geraete_fenster.py`` (dieselbe Route, die Fenster je Geraet).
"""
from datetime import date
from types import SimpleNamespace

from backend.api.routes.ha_export.investition_sensoren import laufzeit_attribute


def _inv(**kw):
    basis = dict(anschaffungsdatum=date(2023, 6, 1), stilllegungsdatum=None, aktiv=True)
    basis.update(kw)
    return SimpleNamespace(**basis)


HEUTE = date(2026, 9, 21)


def test_aktives_geraet_traegt_anschaffung_und_betriebsjahre():
    a = laufzeit_attribute(_inv(), heute=HEUTE)
    assert a["anschaffungsdatum"] == "2023-06-01"
    assert a["stilllegungsdatum"] is None
    assert a["aktiv"] is True
    assert a["betriebsjahre"] == 3.3      # 1208 Tage / 365,25


def test_stillgelegtes_geraet_ist_nicht_aktiv_und_zaehlt_bis_zur_stilllegung():
    a = laufzeit_attribute(_inv(stilllegungsdatum=date(2025, 6, 1)), heute=HEUTE)
    assert a["stilllegungsdatum"] == "2025-06-01"
    assert a["aktiv"] is False
    assert a["betriebsjahre"] == 2.0


def test_stilllegung_in_der_zukunft_zaehlt_noch_als_aktiv():
    a = laufzeit_attribute(_inv(stilllegungsdatum=date(2027, 1, 1)), heute=HEUTE)
    assert a["aktiv"] is True
    assert a["betriebsjahre"] == 3.3


def test_ohne_anschaffungsdatum_keine_erfundenen_jahre():
    a = laufzeit_attribute(_inv(anschaffungsdatum=None), heute=HEUTE)
    assert a["anschaffungsdatum"] is None
    assert a["betriebsjahre"] is None


def test_aktiv_false_am_stammdatum_schlaegt_durch():
    a = laufzeit_attribute(_inv(aktiv=False), heute=HEUTE)
    assert a["aktiv"] is False
