"""Handgriff Nr. 35/46 (Triage 12.10.2026) — „PV-Erzeugung aus" nennt das Balkonkraftwerk, auch im Monatsbericht-PDF.

Die PV-Erzeugung des Monats enthält das Balkonkraftwerk, und `get_aktueller_monat` liefert es in
``komponenten_geraete['balkonkraftwerk']``; die Liste las nur Strings und Wechselrichter („Süd, West"). Dieselbe Regel
im Frontend: `frontend/src/v4/bilanzParkIds.ts::pvErzeugerNamen` (Vitest `bilanzParkIds.test.ts`, `MonatBilanz.test.tsx`).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

J, M = 2025, 6


@pytest.mark.asyncio
async def test_monatsbericht_nennt_das_balkonkraftwerk(db):
    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.services.pdf.builders.monatsbericht import _abschnitte_energie

    a = Anlage(anlagenname="PV aus", leistung_kwp=10.8)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    invs = [Investition(anlage_id=a.id, typ=t, bezeichnung=n, leistung_kwp=k, anschaffungsdatum=date(2024, 1, 1))
            for t, n, k in (("pv-module", "Süd", 6.0), ("pv-module", "West", 4.0), ("balkonkraftwerk", "Balkon", 0.8))]
    db.add_all(invs)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=M, einspeisung_kwh=300.0, netzbezug_kwh=100.0))
    for inv, kwh in zip(invs, (400.0, 200.0, 30.0)):
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=J, monat=M, verbrauch_daten={"pv_erzeugung_kwh": kwh}))
    await db.commit()

    d = await get_aktueller_monat(a.id, jahr=J, monat=M, db=db)
    assert d.komponenten_geraete.get("balkonkraftwerk") == ["Balkon"]
    zeilen = {z.label: z.wert for ab in _abschnitte_energie(d) for z in (vars(ab).get("zeilen") or [])}
    assert zeilen["Beteiligte Geräte"] == "Süd, West, Balkon"
