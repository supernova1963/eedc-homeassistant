"""N-568 — Wallbox-Hub: jede Karte zeigt die Messung DIESER Wallbox, nicht die der Anlage.

Nebenfund NF-1 des Restfunde-Baus (26.09.2026), gemessen an einer r28-Kopie mit zweiter Wallbox:
die Anlagen-Route `GET /investitionen/dashboard/wallbox/{anlage_id}` liefert eine Karte je Wallbox,
jede trug aber als Kachel „Heimladung" die Summe ALLER privaten Wallboxen (4508 auf beiden Karten),
der Verlauf darunter nur die eigenen Zeilen (4208 bzw. 300). Konzept Heimladung Regel 0:
„Wallbox-Sichten zeigen die Messung DER Wallbox".

Jetzt: kWh, PV-Anteil, Ladevorgänge je Wallbox; Ersparnis gegenüber externem Laden, Kosten und
Amortisation anteilig nach der Messung (gegen die eigenen Anschaffungskosten). Σ Karten = Anlage.
Bei einer Wallbox ist der Anteil exakt 1 — die Karte bleibt, wie sie war (GM Investitionen).

Schwesterdateien: test_n555_stufe2_messung_je_auto.py (NF-1: Kachel = Messung, Ersparnis = Topf).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.dashboard_wallbox import get_wallbox_dashboard
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten


async def _anlage(db, wallboxen: dict[str, tuple[dict[int, dict], dict]], autos: dict[str, dict[int, dict]]):
    """``wallboxen``: ``{bez: ({monat: zeile}, parameter)}``, ``autos``: ``{bez: {monat: zeile}}``."""
    a = Anlage(anlagenname="N568", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    for bez, (zeilen, parameter) in wallboxen.items():
        wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung=bez, anschaffungsdatum=date(2024, 1, 1),
                         anschaffungskosten_gesamt=1200.0, parameter=parameter)
        db.add(wb)
        await db.flush()
        for m, z in zeilen.items():
            db.add(InvestitionMonatsdaten(investition_id=wb.id, jahr=2026, monat=m, verbrauch_daten=dict(z)))
    for bez, zeilen in autos.items():
        ea = Investition(anlage_id=a.id, typ="e-auto", bezeichnung=bez, anschaffungsdatum=date(2024, 1, 1),
                         parameter={})
        db.add(ea)
        await db.flush()
        for m, z in zeilen.items():
            db.add(InvestitionMonatsdaten(investition_id=ea.id, jahr=2026, monat=m, verbrauch_daten=dict(z)))
    await db.commit()
    return a


def _z(karten):
    return {k.investition.bezeichnung: k.zusammenfassung for k in karten}


GARAGE = {4: {"ladung_kwh": 300.0, "ladung_pv_kwh": 150.0, "ladevorgaenge": 6},
          5: {"ladung_kwh": 300.0, "ladung_pv_kwh": 150.0, "ladevorgaenge": 6}}
CARPORT = {5: {"ladung_kwh": 100.0, "ladung_pv_kwh": 20.0, "ladevorgaenge": 2}}
AUTO = {4: {"km_gefahren": 1500.0}, 5: {"km_gefahren": 1500.0}}


@pytest.mark.asyncio
async def test_zwei_wallboxen_jede_karte_ihre_messung_summe_gleich_anlage(db):
    a = await _anlage(db, {"Garage": (GARAGE, {}), "Carport": (CARPORT, {})}, {"Auto": AUTO})
    z = _z(await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))
    assert z["Garage"]["gesamt_heim_ladung_kwh"] == pytest.approx(600.0)
    assert z["Carport"]["gesamt_heim_ladung_kwh"] == pytest.approx(100.0)
    assert z["Garage"]["pv_anteil_prozent"] == pytest.approx(50.0)
    assert z["Carport"]["pv_anteil_prozent"] == pytest.approx(20.0)
    assert z["Garage"]["gesamt_ladevorgaenge"] == 12
    assert z["Carport"]["gesamt_ladevorgaenge"] == 2
    # Ersparnis/Kosten anteilig nach der Messung (600 : 100); Σ Karten = Anlage (der Topf ist
    # die Ladung des einen privaten Autos = 700 kWh, heim_als_extern = 700 × 0,50).
    gesamt_als_extern = sum(k["heim_als_extern_kosten_euro"] for k in z.values())
    assert gesamt_als_extern == pytest.approx(700 * 0.50)
    assert z["Garage"]["heim_als_extern_kosten_euro"] == pytest.approx(700 * 0.50 * 6 / 7, abs=0.01)
    ers = {b: k["ersparnis_vs_extern_euro"] for b, k in z.items()}
    assert ers["Garage"] == pytest.approx(6 * ers["Carport"], abs=0.06)   # je Karte auf 0,01 gerundet
    # Amortisation gegen die EIGENEN Anschaffungskosten: gleiche Kosten, kleinere Ersparnis ⇒ länger.
    assert z["Carport"]["amortisation_jahre"] > z["Garage"]["amortisation_jahre"]


@pytest.mark.asyncio
async def test_eine_wallbox_karte_gleich_anlage(db):
    a = await _anlage(db, {"Garage": (GARAGE, {})}, {"Auto": AUTO})
    (k,) = await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    z = k.zusammenfassung
    assert z["gesamt_heim_ladung_kwh"] == pytest.approx(600.0)
    assert z["heim_als_extern_kosten_euro"] == pytest.approx(600 * 0.50)
    assert z["gesamt_ladevorgaenge"] == 12


@pytest.mark.asyncio
async def test_dienstliche_wallbox_zeigt_ihre_messung_ohne_private_ersparnis(db):
    a = await _anlage(db, {"Garage": (GARAGE, {}), "Firma": (CARPORT, {"ist_dienstlich": True})},
                      {"Auto": AUTO})
    z = _z(await get_wallbox_dashboard(anlage_id=a.id, strompreis_cent=None, db=db))
    assert z["Firma"]["gesamt_heim_ladung_kwh"] == pytest.approx(100.0)
    assert z["Firma"]["gesamt_ladevorgaenge"] == 2
    assert z["Firma"]["ersparnis_vs_extern_euro"] == 0.0
    assert z["Firma"]["heim_als_extern_kosten_euro"] == 0.0
    # Die private Garage trägt das ganze private Ergebnis (Anteil 1).
    assert z["Garage"]["gesamt_heim_ladung_kwh"] == pytest.approx(600.0)
    assert z["Garage"]["heim_als_extern_kosten_euro"] == pytest.approx(600 * 0.50)
