"""N-619 — Tag-Status, Leere-Tage-Check, Werkbank- und Reload-Vorschau lesen dieselben Investitionen wie der Lauf.

``aggregate_day`` lädt seine Investitionen mit ``aktiv_am_tag(datum)``. Drei Sichten, die denselben Tag
beschreiben, lasen die HA-Statistik mit **allen** Investitionen der Anlage: Tag-Status
(``energie_profil/tag_status.py``), der Leere-Tage-Check (``daten_checker/datenquelle/tage.py``) und die
Vorschau der Reparatur-Werkbank (``repair_orchestrator._plan_reaggregate_day``), dazu als vierter Leser die
Reload-Vorschau ``GET …/reaggregate-tag/preview`` (``api/routes/energie_profil/diagnose.py``). Gemessen (04.10.2026) an
einem Balkonkraftwerk, dessen zwei Modul-Kinder erst nach dem Tag angeschafft wurden, deren Sensoren aber
schon Historie haben: kein Status und keine Zahl des Laufs wich ab, aber Tag-Status und Leere-Tage-Check
nannten „Kind 1, Kind 2" statt „Balkon", die Vorschau zählte die Zählerzeilen der noch nicht angeschafften
Kinder mit (175 statt 125 geänderte Stände).

Gehalten wird über die echten Einstiege (``baue_tag_status``, ``DatenChecker.check_anlage``,
``repair_orchestrator.plan``, die Route ``reaggregate_tag_preview``): an einem Tag vor der Anschaffung der Kinder nennen alle das
Balkonkraftwerk mit dem Wert, den ``aggregate_day`` schreibt, und keine Zeile eines Kindes; nach der
Anschaffung bleibt alles, wie es war.

Schwesterdateien: test_tag_status_leere_tagessicht.py (Tag-Status), test_n615_tag_abtretung_am_datum.py
(dieselbe Zeitfilter-Regel in der Tagesauflösung).
"""

from __future__ import annotations

import os
import time as _time
from contextlib import ExitStack
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

import backend.services.daten_checker  # noqa: F401 — Modelle vor create_all laden
import backend.services.energie_profil.aggregator  # noqa: F401
import backend.services.snapshot.reaggregator  # noqa: F401
from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil._helpers import StrompreisStunden
from backend.services.energie_profil.source import Source
from backend.tests import ha_lts_helfer

# Feste Tage für Tag-Status und Werkbank-Vorschau (beide bekommen den Tag übergeben). Nur der
# Leere-Tage-Check prüft „die letzten 90 Tage" ab der Uhr des Prozesses — seine Probe legt ihre Tage deshalb
# relativ zu heute (eine Stelle, in `test_konformitaet_echte_uhr_in_tests.py::_BASELINE` geführt; die Tage
# liegen fünf und mehr Tage auseinander, keine Stunde des Laufs entscheidet).
FEST = dict(kinder_ab=date(2026, 9, 1), vor=date(2026, 8, 15), nach=date(2026, 9, 15), seit=date(2024, 1, 1))
RATE = {"sensor.sued": 2.0, "sensor.west": 1.0, "sensor.bkw": 0.5, "sensor.k1": 0.2, "sensor.k2": 0.3,
        "sensor.einsp": 1.0, "sensor.netz": 0.0}


@pytest.fixture(autouse=True)
def _berlin():
    alt = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    _time.tzset()
    try:
        yield
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _time.tzset()


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _ha(vor: date, nach: date):
    """HA-Statistik mit Stundenständen um ``vor`` und ``nach``; die Kinder-Sensoren haben auch vorher schon Historie."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    for sid, rate in RATE.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        w = 1000.0
        with svc._engine.begin() as conn:
            for basis in (vor, nach):
                t = datetime.combine(basis - timedelta(days=2), datetime.min.time())
                ende = datetime.combine(basis + timedelta(days=2), datetime.min.time())
                while t <= ende:
                    conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                                 {"m": mid, "t": t.timestamp(), "w": round(w, 3)})
                    if 10 <= t.hour <= 15:
                        w += rate
                    elif sid == "sensor.netz":
                        w += 0.4
                    t += timedelta(hours=1)
    return svc


def _quellen(svc) -> ExitStack:
    st = ExitStack()
    for ziel in ("backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
                 "backend.services.ha_statistics_service.get_ha_statistics_service",
                 "backend.services.snapshot.reaggregator.get_ha_statistics_service"):
        st.enter_context(patch(ziel, return_value=svc))
    for ziel, wert in (
        ("backend.services.energie_profil._helpers._get_wetter_ist", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden", StrompreisStunden(sensor={}, boerse={})),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld", {}),
    ):
        st.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return st


def _tagesverlauf() -> dict:
    punkte = [{"zeit": f"{h:02d}:00", "werte": {"pv_gesamt": 0.1}} for h in range(24)]
    return {"serien": [{"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle", "bidirektional": False}],
            "punkte": punkte, "vortagsrand": [{"zeit": "23:00", "werte": {"pv_gesamt": 0.1}}]}


async def _anlage(db, kinder_ab: date, seit: date) -> tuple[Anlage, dict[str, int]]:
    basis = {"einspeisung": _sensor("sensor.einsp"), "netzbezug": _sensor("sensor.netz")}
    anlage = Anlage(anlagenname="N619", leistung_kwp=10.8, installationsdatum=seit,
                    sensor_mapping={"basis": basis, "investitionen": {}})
    db.add(anlage)
    await db.flush()
    ids: dict[str, int] = {}
    for name, typ, kwp, ab, parent in (("Süd", "pv-module", 6.0, date(2024, 1, 1), None),
                                       ("West", "pv-module", 4.0, date(2024, 1, 1), None),
                                       ("Balkon", "balkonkraftwerk", 0.8, date(2024, 1, 1), None),
                                       ("Kind 1", "pv-module", 0.6, kinder_ab, "Balkon"),
                                       ("Kind 2", "pv-module", 0.2, kinder_ab, "Balkon")):
        inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=name, leistung_kwp=kwp, anschaffungsdatum=ab,
                          anschaffungskosten_gesamt=1.0, parent_investition_id=ids.get(parent))
        db.add(inv)
        await db.flush()
        ids[name] = inv.id
    sensoren = {"Süd": "sensor.sued", "West": "sensor.west", "Balkon": "sensor.bkw", "Kind 1": "sensor.k1", "Kind 2": "sensor.k2"}
    anlage.sensor_mapping = {"basis": basis, "investitionen": {
        str(ids[n]): {"felder": {"pv_erzeugung_kwh": _sensor(s)}} for n, s in sensoren.items()}}
    await db.commit()
    return anlage, ids


async def _lauf(db, anlage, tag) -> dict:
    from backend.services.energie_profil.aggregator import aggregate_day

    await aggregate_day(anlage, tag, db, source=Source.MANUAL_REPAIR, prefetched_tagesverlauf=_tagesverlauf())
    await db.commit()
    z = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == tag))).scalar_one()
    return z.komponenten_kwh


@pytest.mark.asyncio
async def test_tag_status_nennt_die_geraete_des_laufs(db):
    from backend.services.energie_profil.tag_status import baue_tag_status

    anlage, ids = await _anlage(db, FEST["kinder_ab"], FEST["seit"])
    with _quellen(_ha(FEST["vor"], FEST["nach"])):
        vor = await baue_tag_status(db, anlage, FEST["vor"])
        nach = await baue_tag_status(db, anlage, FEST["nach"])
        geschrieben = await _lauf(db, anlage, FEST["vor"])
    assert geschrieben[f"bkw_{ids['Balkon']}"] == pytest.approx(3.0)
    assert "Balkon 3.0 kWh" in vor.details and "Kind 1" not in vor.details and "Kind 2" not in vor.details
    assert "Kind 1 1.2 kWh" in nach.details and "Kind 2 1.8 kWh" in nach.details


@pytest.mark.asyncio
async def test_werkbank_vorschau_ohne_zaehler_kuenftiger_geraete(db):
    from backend.services.repair_orchestrator import RepairOperationRequest, RepairOperationType, plan

    anlage, ids = await _anlage(db, FEST["kinder_ab"], FEST["seit"])
    with _quellen(_ha(FEST["vor"], FEST["nach"])):
        p_vor = await plan(RepairOperationRequest(anlage_id=anlage.id, operation=RepairOperationType.REAGGREGATE_DAY,
                                                  params={"datum": FEST["vor"].isoformat()}), db)
        p_nach = await plan(RepairOperationRequest(anlage_id=anlage.id, operation=RepairOperationType.REAGGREGATE_DAY,
                                                   params={"datum": FEST["nach"].isoformat()}), db)
    keys_vor = {b["sensor_key"] for b in p_vor.operation_preview["preview"]["boundaries"]}
    keys_nach = {b["sensor_key"] for b in p_nach.operation_preview["preview"]["boundaries"]}
    kinder = {f"inv:{ids['Kind 1']}:pv_erzeugung_kwh", f"inv:{ids['Kind 2']}:pv_erzeugung_kwh"}
    assert not (keys_vor & kinder)
    assert f"inv:{ids['Balkon']}:pv_erzeugung_kwh" in keys_vor
    assert kinder <= keys_nach


@pytest.mark.asyncio
async def test_leere_tage_check_nennt_das_balkonkraftwerk_vor_den_kindern(db):
    from backend.services.daten_checker import DatenChecker

    heute = date.today()   # der Check prüft „die letzten 90 Tage" ab der Prozessuhr — s. Kopf
    anlage, _ = await _anlage(db, heute - timedelta(days=10), heute - timedelta(days=18))
    with _quellen(_ha(heute - timedelta(days=15), heute - timedelta(days=5))):
        res = await DatenChecker(db).check_anlage(anlage.id)
    meldungen = [e for e in res.ergebnisse if e.kategorie == "tageswerte_fehlen" and e.details]
    assert meldungen, [e.kategorie for e in res.ergebnisse]
    details = " ".join(e.details for e in meldungen)
    # Die Tage vor den Kindern tragen das Balkonkraftwerk, die danach die Kinder.
    assert "Balkon" in details and "Kind 1" in details


@pytest.mark.asyncio
async def test_reload_vorschau_der_route_ohne_zaehler_kuenftiger_geraete(db):
    """Vierter Leser: ``GET /energie-profil/{id}/reaggregate-tag/preview`` — vorher 175 Stände, davon 50 der Kinder."""
    from backend.api.routes.energie_profil.diagnose import reaggregate_tag_preview

    anlage, ids = await _anlage(db, FEST["kinder_ab"], FEST["seit"])
    with _quellen(_ha(FEST["vor"], FEST["nach"])):
        vor = await reaggregate_tag_preview(anlage_id=anlage.id, datum=FEST["vor"], db=db)
        nach = await reaggregate_tag_preview(anlage_id=anlage.id, datum=FEST["nach"], db=db)
    kinder = {f"inv:{ids['Kind 1']}:pv_erzeugung_kwh", f"inv:{ids['Kind 2']}:pv_erzeugung_kwh"}
    keys_vor = {b.sensor_key for b in vor.boundaries}
    keys_nach = {b.sensor_key for b in nach.boundaries}
    assert not (keys_vor & kinder) and f"inv:{ids['Balkon']}:pv_erzeugung_kwh" in keys_vor
    assert kinder <= keys_nach
