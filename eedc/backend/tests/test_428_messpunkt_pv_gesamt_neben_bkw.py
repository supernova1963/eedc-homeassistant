"""GitHub #428 (chuck2941, 16.10.2026) — Daten-Checker «Messpunkt» (e): Anlagenzähler „PV gesamt“, ein aktives PV-Modul ohne
eigenen Zähler und ein Balkonkraftwerk mit eigenem Zähler ⇒ INFO. eedc liest den Anlagenzähler als Zähler der ganzen
Erzeugung einschließlich Balkonkraftwerk; sitzt er am Wechselrichter, fehlt das Balkonkraftwerk in „PV gesamt“ (Melder: Tag
11,7 statt 14,5 kWh). Nur Stammdaten und Zuordnung, keine Monatszahlen (In-Memory-DB ohne Kanäle)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.daten_checker import DatenChecker
from backend.tests import factories

MELDUNG = "„PV gesamt“ gilt als Zähler der ganzen Erzeugung einschließlich Balkonkraftwerk"


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


async def _anlage(db, *, pv_gesamt=True, modul_zaehler=False, bkw_zaehler=True, modul_kind_des_bkw=False):
    a = await factories.anlage(db, anlagenname="chuck", standort_land="DE")
    bkw = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", anschaffungsdatum=date(2024, 1, 1),
                      leistung_kwp=0.8)
    db.add(bkw)
    await db.flush()
    modul = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süddach", anschaffungsdatum=date(2024, 1, 1),
                        leistung_kwp=8.0, parent_investition_id=bkw.id if modul_kind_des_bkw else None)
    db.add(modul)
    await db.flush()
    a.sensor_mapping = {
        "basis": {"pv_gesamt": _s("sensor.pv_gesamt")} if pv_gesamt else {},
        "investitionen": {
            str(bkw.id): {"felder": {"pv_erzeugung_kwh": _s("sensor.bkw")} if bkw_zaehler else {}},
            str(modul.id): {"felder": {"pv_erzeugung_kwh": _s("sensor.modul")} if modul_zaehler else {}},
        },
    }
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return (await db.execute(select(Anlage).options(selectinload(Anlage.investitionen))
                             .where(Anlage.id == a.id))).scalar_one()


async def _meldungen(db, a) -> list:
    return [e for e in await DatenChecker(db)._check_messpunkt(a) if e.meldung == MELDUNG]


async def test_konstellation_428_bekommt_den_hinweis(db):
    a = await _anlage(db)
    (e,) = await _meldungen(db, a)
    assert getattr(e.schwere, "value", e.schwere) == "info" and e.link == "/einstellungen/datenquellen"
    assert "Misst er nur den Wechselrichter, ordne ihn dem PV-Modul als Erzeugungszähler zu" in e.details
    assert "Balkon" in e.details and "Süddach" in e.details


@pytest.mark.parametrize("kwargs", [
    {"pv_gesamt": False},            # kein Anlagenzähler
    {"modul_zaehler": True},         # jedes Modul misst selbst — kein Rest
    {"bkw_zaehler": False},          # Balkonkraftwerk ohne eigenen Zähler
    {"modul_kind_des_bkw": True},    # das Modul gehört dem Balkonkraftwerk (N-266)
])
async def test_ohne_die_konstellation_kein_hinweis(db, kwargs):
    a = await _anlage(db, **kwargs)
    assert await _meldungen(db, a) == []
