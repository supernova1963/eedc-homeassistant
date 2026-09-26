"""Nachträge II (Vorlage §10): Tages-Checker „Einspeisung über Erzeugung".

Die EV-Klemme (EV = max(0, ΣPV − ΣEinsp)) verweist auf den Daten-Checker; der
prüfte das bisher nur je Monat. Neu: Tage **mit Regelmarke**, an denen
Σ Einspeisung > Σ PV + Σ Entladung + 0,5 kWh — Entladung ins Netz ist erlaubt.
Eine Hinweis-Zeile je Anlage mit Tagesliste und Reparaturweg („Zeitraum neu
aggregieren"), wie E7.

Schwesterdateien: test_zaehlerluecken_e7_bestandstage.py (dieselbe Bauform),
test_tagesbilanz_pv_nicht_erfasst.py (die EV-Klemme am Tag).
"""
from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.daten_checker import CheckKategorie, CheckSeverity, DatenChecker

TAG = date(2026, 5, 3)


async def _anlage(db):
    a = Anlage(anlagenname="Einsp", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    return a


def _tag(db, a, d, stunden, marke=None):
    """stunden: {h: (pv, einsp, netz, batterie_kw)} — batterie_kw > 0 = Entladung."""
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, verworfen=marke))
    for h, (pv, ei, nz, bat) in stunden.items():
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=h, pv_kw=pv,
                                  einspeisung_kw=ei, netzbezug_kw=nz, batterie_kw=bat))


@pytest.mark.asyncio
async def test_pv_toter_tag_mit_einspeisung_wird_genannt(db):
    a = await _anlage(db)
    _tag(db, a, TAG, {h: (0.0, 2.0, 0.1, None) for h in range(10, 14)}, marke={})       # PV 0, Einsp 8
    _tag(db, a, TAG + timedelta(days=1), {h: (3.0, 2.0, 0.0, None) for h in range(10, 14)}, marke={})
    await db.commit()
    erg = await DatenChecker(db)._check_einspeisung_ueber_erzeugung(a)
    assert len(erg) == 1
    e = erg[0]
    assert e.kategorie == CheckKategorie.ENERGIEPROFIL_PLAUSIBILITAET
    assert e.schwere == CheckSeverity.INFO
    assert e.meldung.startswith("1 Tag(e) mit mehr Einspeisung als Erzeugung")
    assert "2026-05-03: Einspeisung 8,0 kWh, PV 0,0 kWh" in e.details
    assert e.action_kind == "reaggregate_range"
    assert e.action_params == {"anlage_id": a.id, "von": "2026-05-03", "bis": "2026-05-03"}


@pytest.mark.asyncio
async def test_entladung_ins_netz_ist_erlaubt(db):
    """PV 4, Einspeisung 8, Entladung 6 (Arbitrage) ⇒ still."""
    a = await _anlage(db)
    _tag(db, a, TAG, {h: (1.0, 2.0, 0.0, 1.5) for h in range(10, 14)}, marke={})
    await db.commit()
    assert await DatenChecker(db)._check_einspeisung_ueber_erzeugung(a) == []


@pytest.mark.asyncio
async def test_altbestand_ohne_marke_wird_nicht_geprueft(db):
    a = await _anlage(db)
    _tag(db, a, TAG, {h: (0.0, 2.0, 0.1, None) for h in range(10, 14)}, marke=None)
    await db.commit()
    assert await DatenChecker(db)._check_einspeisung_ueber_erzeugung(a) == []


@pytest.mark.asyncio
async def test_toleranz_halbe_kilowattstunde(db):
    a = await _anlage(db)
    _tag(db, a, TAG, {10: (3.0, 3.4, 0.0, None)}, marke={})                        # +0,4 ⇒ still
    _tag(db, a, TAG + timedelta(days=1), {10: (3.0, 3.6, 0.0, None)}, marke={})   # +0,6 ⇒ genannt
    await db.commit()
    e = (await DatenChecker(db)._check_einspeisung_ueber_erzeugung(a))[0]
    assert e.meldung.startswith("1 Tag(e)")
    assert "2026-05-04" in e.details and "2026-05-03" not in e.details


def test_pruefung_ist_im_lauf_eingehaengt():
    assert "self._check_einspeisung_ueber_erzeugung(anlage)" in inspect.getsource(DatenChecker.check_anlage)
