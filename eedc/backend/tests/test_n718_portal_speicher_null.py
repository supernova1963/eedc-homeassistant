"""N-718 — Portal-Import: eine gelieferte Speicher-0 kommt an (0 ist ein Wert), leer bleibt leer.

Beide Speicher-Wege des Portal-Imports schrieben nur bei `(ladung or 0) > 0 or (entladung or 0) > 0`: der Ziel-Weg
(`data_import.py::_verteile_ziel_erzeugung`, eine Quelle je Wechselrichter, #349) und der anlagenweite Weg
(`_verteile_batterie`). Gemessen am HEAD `0c3a89fa` (`factories.zwei_wechselrichter(mit_speicher=True)`, 06/2025):

* Ziel-Weg, A 50/45, B 0/0 ⇒ Akku B ohne Zeile, Daten-Checker WARNING «Akku Sofar 1100: Speicher-Ladung fehlt in
  1 Monat(en)»;
* anlagenweit 0/0 ⇒ kein Speicher mit Zeile, Monatszeile ohne Batteriewerte, 2 × WARNING «… Speicher-Ladung fehlt …»
  und WARNING «Batterie-Ladung/-Entladung nicht erfasst (Speicher vorhanden)».

Die Summe stimmte (keine Zeile zählt 0), das Kennzeichen nicht. Dieselbe Regel wie N-707 (anlagenweiter PV-Weg) und
N-711 (Ziel-Weg PV): eine gelieferte 0 ist exakt — jeder Speicher 0, ohne `abgeleitet`-Marke —, ein fehlender Wert
bleibt leer.

Schwesterdateien: test_n711_ziel_geraet_pv_null.py, test_n707_import_pv_null_ist_messwert.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from backend.api.routes.data_import import ApplyMonthInput, ApplyRequest, apply_import
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.tests import factories

JAHR, MONAT = 2025, 6


async def _apply(db, anlage_id: int, ziel_id=None, **werte):
    antwort = await apply_import(
        anlage_id=anlage_id,
        data=ApplyRequest(monate=[ApplyMonthInput(jahr=JAHR, monat=MONAT, **werte)], ziel_investition_id=ziel_id),
        ueberschreiben=False, datenquelle="portal_import", db=db,
    )
    assert antwort.erfolg, antwort.fehler
    return antwort


async def _speicher(db, inv_id: int):
    row = (await db.execute(select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id == inv_id,
        InvestitionMonatsdaten.jahr == JAHR, InvestitionMonatsdaten.monat == MONAT,
    ))).scalar_one_or_none()
    if row is None:
        return None
    d = row.verbrauch_daten or {}
    return d.get("ladung_kwh"), d.get("entladung_kwh")


async def _speicher_meldungen(db, anlage_id: int) -> list[str]:
    from backend.services.daten_checker import DatenChecker

    return [e.meldung for e in (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse
            if "Speicher-Ladung fehlt" in e.meldung or "Speicher-Entladung fehlt" in e.meldung
            or "nicht erfasst (Speicher vorhanden)" in e.meldung]


@pytest.mark.asyncio
async def test_ziel_weg_speicher_null_kommt_an(db):
    ids = await factories.zwei_wechselrichter(db, mit_speicher=True)
    await _apply(db, ids["anlage"], ids["Sofar 2200"]["wr"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0,
                 einspeisung_kwh=300.0, batterie_ladung_kwh=50.0, batterie_entladung_kwh=45.0)
    await _apply(db, ids["anlage"], ids["Sofar 1100"]["wr"], pv_erzeugung_kwh=500.0,
                 batterie_ladung_kwh=0.0, batterie_entladung_kwh=0.0)

    assert await _speicher(db, ids["Sofar 2200"]["speicher"]) == (50.0, 45.0)
    assert await _speicher(db, ids["Sofar 1100"]["speicher"]) == (0.0, 0.0), "die 0 der Station kommt an"
    assert await _speicher_meldungen(db, ids["anlage"]) == []


@pytest.mark.asyncio
async def test_anlagenweit_speicher_null_kommt_an(db):
    ids = await factories.zwei_wechselrichter(db, mit_speicher=True)
    await _apply(db, ids["anlage"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0, einspeisung_kwh=300.0,
                 batterie_ladung_kwh=0.0, batterie_entladung_kwh=0.0)

    for name in ("Sofar 2200", "Sofar 1100"):
        assert await _speicher(db, ids[name]["speicher"]) == (0.0, 0.0), name
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == ids["anlage"]))).scalar_one()
    assert (md.batterie_ladung_kwh, md.batterie_entladung_kwh) == (0.0, 0.0)
    assert await _speicher_meldungen(db, ids["anlage"]) == []


@pytest.mark.asyncio
async def test_anlagenweit_eine_seite_null(db):
    """Ladung 50, Entladung 0: die Ladung wird nach Kapazität verteilt (5 + 5 kWh ⇒ je 25), die 0 kommt bei jedem
    Speicher als 0 an — vorher fehlte die Entladung an beiden."""
    ids = await factories.zwei_wechselrichter(db, mit_speicher=True)
    await _apply(db, ids["anlage"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0, einspeisung_kwh=300.0,
                 batterie_ladung_kwh=50.0, batterie_entladung_kwh=0.0)
    for name in ("Sofar 2200", "Sofar 1100"):
        assert await _speicher(db, ids[name]["speicher"]) == (25.0, 0.0), name


@pytest.mark.asyncio
async def test_ohne_speicherwerte_bleibt_leer(db):
    """Gegenprobe: liefert die Quelle keine Speicherwerte, entsteht keine Speicherzeile und die Monatszeile bleibt
    leer — auf beiden Wegen."""
    ids = await factories.zwei_wechselrichter(db, mit_speicher=True)
    await _apply(db, ids["anlage"], ids["Sofar 1100"]["wr"], pv_erzeugung_kwh=500.0)
    assert await _speicher(db, ids["Sofar 1100"]["speicher"]) is None
    ids2 = await factories.zwei_wechselrichter(db, mit_speicher=True)
    await _apply(db, ids2["anlage"], pv_erzeugung_kwh=1000.0, netzbezug_kwh=200.0, einspeisung_kwh=300.0)
    for name in ("Sofar 2200", "Sofar 1100"):
        assert await _speicher(db, ids2[name]["speicher"]) is None, name
    md = (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == ids2["anlage"]))).scalar_one()
    assert (md.batterie_ladung_kwh, md.batterie_entladung_kwh) == (None, None)
