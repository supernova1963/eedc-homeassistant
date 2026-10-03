"""N-612 — *Auswertungen → Tabelle*, Spalte „Spez. Ertrag": derselbe Wert wie das Cockpit.

Die Tabelle rechnet den spezifischen Ertrag im Client
(``pages/auswertung/types.ts``: ``pv_erzeugung_kwh / anlagen_kwp``). Beide Zahlen
kommen aus ``/monatsdaten/aggregiert``. ``pv_erzeugung_kwh`` ist dort
``f.erzeugung.pv_kwh`` — Module **und** Balkonkraftwerk —, der Nenner
``anlagen_kwp`` stand bis 03.10.2026 auf ``mit_bkw=False``. Gemessen an
10 kWp Modulen + 0,8 kWp Balkonkraftwerk (je Monat 930 + 70 kWh): Tabelle
100,0 kWh/kWp im Mai, Cockpit → Monat 92,6; im Jahr 1200 gegen 1111.

Die Regel ist F-58: Zähler und Nenner dieselbe Grundgesamtheit. Diese Proben
halten die Tabelle gegen die Sichten, die den Wert schon richtig nannten —
Cockpit → Monat (``aktueller_monat/finanzen.py``, ``mit_bkw=True``) und die
Übersicht des Jahres —, statt gegen eine eigene Erwartungszahl.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

J = 2025


async def _anlage(db, *, bkw: bool, kinder: bool = False, bkw_ab: date = date(2024, 1, 1)) -> int:
    a = Anlage(anlagenname="N612", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    sued = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd", leistung_kwp=6.0,
                       anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1.0)
    west = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="West", leistung_kwp=4.0,
                       anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=1.0)
    db.add_all([sued, west])
    await db.flush()
    balkon = None
    if bkw:
        balkon = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                             anschaffungsdatum=bkw_ab, anschaffungskosten_gesamt=1.0)
        db.add(balkon)
        await db.flush()
        if kinder:
            for name in ("Kind 1", "Kind 2"):
                db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung=name, leistung_kwp=0.4,
                                   parent_investition_id=balkon.id, anschaffungsdatum=bkw_ab,
                                   anschaffungskosten_gesamt=1.0))
            await db.flush()
    for monat in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=monat, einspeisung_kwh=400.0, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=sued.id, jahr=J, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": 550.0}))
        db.add(InvestitionMonatsdaten(investition_id=west.id, jahr=J, monat=monat,
                                      verbrauch_daten={"pv_erzeugung_kwh": 380.0}))
        if balkon is not None and date(J, monat, 28) >= bkw_ab:
            db.add(InvestitionMonatsdaten(investition_id=balkon.id, jahr=J, monat=monat,
                                          verbrauch_daten={"pv_erzeugung_kwh": 70.0}))
    await db.commit()
    return a.id


def _still(monkeypatch):
    """Cockpit → Monat ohne Live-Quellen: nur die gespeicherten Werte zählen."""
    import backend.api.routes.aktueller_monat as am

    async def _leer(*a, **k):
        return {}

    async def _leer_set(*a, **k):
        return set()
    for name in ("_collect_connector_data", "_collect_mqtt_inbound_data", "_collect_ha_statistics_data"):
        monkeypatch.setattr(am, name, _leer)
    monkeypatch.setattr(am, "_ha_heimlade_felder_mit_daten", _leer_set)
    return am


async def _tabelle(db, anlage_id: int) -> dict[int, float]:
    """Der Wert der Spalte, wie der Client ihn bildet (``calcSpezifischerErtrag``)."""
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    zeilen = await list_monatsdaten_aggregiert(anlage_id=anlage_id, jahr=J, db=db)
    return {z.monat: z.pv_erzeugung_kwh / z.anlagen_kwp for z in zeilen}


@pytest.mark.parametrize("fall", [
    dict(bkw=True),
    dict(bkw=True, kinder=True),
    dict(bkw=False),
    dict(bkw=True, bkw_ab=date(J, 7, 1)),
], ids=["mit-bkw", "bkw-mit-kindern", "ohne-bkw", "bkw-ab-juli"])
async def test_tabelle_nennt_je_monat_den_wert_des_cockpits(db, monkeypatch, fall):
    anlage_id = await _anlage(db, **fall)
    am = _still(monkeypatch)
    tabelle = await _tabelle(db, anlage_id)
    for monat in (1, 5, 7, 12):
        cockpit = (await am.get_aktueller_monat(anlage_id=anlage_id, jahr=J, monat=monat, db=db)).spez_ertrag
        assert round(tabelle[monat], 1) == cockpit, (monat, tabelle[monat], cockpit)


async def test_mit_bkw_mai_und_jahr_wie_gemessen(db, monkeypatch):
    """Die Zahlen des Fundes: 92,6 statt 100,0 im Mai, 1111 statt 1200 im Jahr — wie die Übersicht."""
    anlage_id = await _anlage(db, bkw=True)
    tabelle = await _tabelle(db, anlage_id)
    assert round(tabelle[5], 1) == 92.6
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    uebersicht = (await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=J, db=db)).spezifischer_ertrag_kwh_kwp
    # `registry.ts`: Jahreswert der Spalte = Σ der Monatswerte (aggregation 'sum').
    assert round(sum(tabelle.values()), 1) == uebersicht == 1111.1
