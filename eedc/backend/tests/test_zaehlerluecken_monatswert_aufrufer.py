"""HA-Bauform S4-R-5: die Aufrufer des HA-Monatswerts reichen KEINEN Deckel mehr mit.

Bis S4 (Vorlage §10, W-R10) reichten Monatsabschluss-Vorschlag, laufender Monat (Cockpit → Monat) und der HA-Import
(Vorschau, Import, Monatswerte je Monat und alle Monate) ``deckel_je_sensor`` für Felder der Achsen PV/Einspeisung
mit. Seit S4-R-5 (Bauplan S4 §3/§4, Entscheid S4-E3 A) nennt ein Monat HAs Zahl wie Tag und Kanal-Monat — ohne Deckel
deckelte ein Lesart-1-Monat, während der Kanal-Monat daneben nicht deckelte (N-586 umgekehrt). Der Rücksprung (R4)
gilt in `get_sensor_monatswert` weiter; einen Phantomsprung benennt der Daten-Checker ``ha_zaehlersprung``. Die
Wirkung je Weg mit einem Sprung mittags: test_s4_r5_deckel_lesepfad.py.

Schwesterdateien: test_zaehlerluecken_n563_monatswert.py (die Regel selbst, mit Deckel-Parameter),
test_n156_ha_wege_ohne_supervisor.py und test_n533_ha_import_anlagen_pv_zaehler.py (dieselben Aufrufer, dieselbe
Attrappen-Form).
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.models.anlage import Anlage
from backend.models.investition import Investition

#: Was die Attrappe als Deckel sieht: nichts (S4-R-5). Bis S4: {"sensor.einsp": 15.0, "sensor.pv1": 15.0} (10 kWp × 1,5).
ERWARTET = None


def _s(sid):
    return {"strategie": "sensor", "sensor_id": sid}


class _Wert:
    def __init__(self, sid, differenz):
        self.sensor_id, self.differenz = sid, differenz
        self.start_wert, self.end_wert, self.einheit = 0.0, differenz, "kWh"


class _Monat:
    def __init__(self, sensoren, jahr=2026, monat=7):
        self.jahr, self.monat, self.monat_name, self.sensoren = jahr, monat, "Juli", sensoren


class _Aufzeichner:
    """LTS-Attrappe, die mitschreibt, welchen Deckel ein Aufrufer mitgibt."""

    is_available = True

    def __init__(self):
        self.deckel: list = []

    def get_monatswerte(self, sensor_ids, jahr, monat, deckel_je_sensor=None):
        self.deckel.append(deckel_je_sensor)
        return _Monat([_Wert(s, 1.0) for s in sensor_ids], jahr, monat)

    def get_alle_monatswerte(self, sensor_ids, ab_datum=None, deckel_je_sensor=None):
        self.deckel.append(deckel_je_sensor)
        return [_Monat([_Wert(s, 1.0) for s in sensor_ids])]


async def _anlage(db):
    a = Anlage(anlagenname="Deckel", leistung_kwp=10.0, standort_plz="10115",
               latitude=48.0, longitude=11.0, installationsdatum=date(2025, 1, 1),
               sensor_mapping={"basis": {"einspeisung": _s("sensor.einsp"),
                                         "netzbezug": _s("sensor.netz")},
                               "investitionen": {}})
    db.add(a)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach",
                     anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0)
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="WB",
                     anschaffungsdatum=date(2025, 1, 1))
    db.add_all([pv, wb])
    await db.flush()
    a.sensor_mapping = {**a.sensor_mapping, "investitionen": {
        str(pv.id): {"felder": {"pv_erzeugung_kwh": _s("sensor.pv1")}},
        str(wb.id): {"felder": {"ladung_kwh": _s("sensor.wb")}},
    }}
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_monatsabschluss_ruft_ohne_deckel(db, monkeypatch):
    from backend.api.routes.monatsabschluss.views import get_monatsabschluss
    a = await _anlage(db)
    rec = _Aufzeichner()
    monkeypatch.setattr("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: rec)
    await get_monatsabschluss(a.id, 2026, 7, db=db)
    assert rec.deckel == [ERWARTET]


@pytest.mark.asyncio
async def test_laufender_monat_ruft_ohne_deckel(db, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.api.routes import aktueller_monat as am
    a = await _anlage(db)
    geladen = (await db.execute(select(Anlage).where(Anlage.id == a.id)
                                .options(selectinload(Anlage.investitionen)))).scalar_one()
    rec = _Aufzeichner()
    monkeypatch.setattr("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: rec)
    await am._collect_ha_statistics_data(geladen, 2026, 7)
    assert rec.deckel == [ERWARTET]


@pytest.mark.asyncio
async def test_ha_import_vorschau_import_und_monatswerte_rufen_ohne_deckel(db, monkeypatch):
    from backend.api.routes import ha_statistics as hs
    a = await _anlage(db)
    rec = _Aufzeichner()
    monkeypatch.setattr(hs, "get_ha_statistics_service", lambda: rec)

    await hs.get_import_vorschau(a.id, db)
    await hs.import_ha_statistics(a.id, hs.ImportRequest(monate=[{"jahr": 2026, "monat": 7}]), db)
    await hs.get_monatswerte(a.id, 2026, 7, db=db)
    await hs.get_alle_monatswerte(a.id, ab_jahr=None, ab_monat=None, db=db)
    assert rec.deckel == [ERWARTET] * 4
