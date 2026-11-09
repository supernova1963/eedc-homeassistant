"""Päckchen X2 (9.11.2026) — ``GET /monatsdaten/{id}`` nimmt den Speicher der Kennzahlen aus den Monats-Fakten (P10).

Bis dahin reichte die Route ``berechne_monatskennzahlen`` die Legacy-Spalten ``Monatsdaten.batterie_ladung_kwh`` /
``batterie_entladung_kwh``, die kein Service mehr schreibt: ein Monat mit Speicher-Zeile in ``InvestitionMonatsdaten``
und leeren Legacy-Spalten rechnete Direktverbrauch, Eigenverbrauch, EV-Quote und Autarkie mit Ladung/Entladung 0.

Schwesterdateien: test_kennzahlen.py, test_n769_grundpreis_komponenten_tarif.py (dieselbe Route, Grundpreis).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

PV_KWH = 400.0
EINSPEISUNG = 100.0
NETZBEZUG = 150.0
LADUNG = 80.0
ENTLADUNG = 70.0


async def _anlage_mit_speicher(db) -> int:
    from backend.services.provenance import seed_provenance

    anlage = Anlage(anlagenname="X2", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    pv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=12000.0)
    sp = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
                     anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0,
                     parameter={"kapazitaet_kwh": 10.0})
    db.add_all([pv, sp])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=2025, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": PV_KWH}))
    db.add(InvestitionMonatsdaten(investition_id=sp.id, jahr=2025, monat=6,
                                  verbrauch_daten={"ladung_kwh": LADUNG, "entladung_kwh": ENTLADUNG}))
    md = Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6, einspeisung_kwh=EINSPEISUNG, netzbezug_kwh=NETZBEZUG,
                     batterie_ladung_kwh=None, batterie_entladung_kwh=None)
    db.add(md)
    await db.flush()
    seed_provenance(md, source="manual:form", writer="test", fields=["einspeisung_kwh", "netzbezug_kwh"])
    await db.commit()
    return (await db.execute(select(Monatsdaten.id).where(Monatsdaten.anlage_id == anlage.id))).scalar_one()


@pytest.mark.asyncio
async def test_kennzahlen_rechnen_mit_der_fakt_ladung(db):
    from backend.api.routes.monatsdaten import get_monatsdaten

    md_id = await _anlage_mit_speicher(db)
    k = (await get_monatsdaten(md_id, db=db)).kennzahlen

    direkt = PV_KWH - EINSPEISUNG - LADUNG            # 220 (mit Legacy-0: 300)
    eigen = direkt + ENTLADUNG                         # 290 (mit Legacy-0: 300)
    assert k.direktverbrauch_kwh == pytest.approx(direkt)
    assert k.eigenverbrauch_kwh == pytest.approx(eigen)
    assert k.gesamtverbrauch_kwh == pytest.approx(eigen + NETZBEZUG)
