"""H-2 der Werkbank «Werte vor dem Sensorbeginn verwerfen» (HA-Bauform S3, E-S3-5): kommt das Verworfene zurück?

Gegen die HA-Langzeitstatistik im echten Recorder-Schema und eine Datei-Datenbank (Fixtures aus
``test_kanal_nachfuellen.py``). Ablauf je Probe: der alte Sensor ``sensor.einsp`` wird nachgefüllt (Marke), die Zuordnung
wechselt auf ``sensor.einsp_neu`` (HA kennt ihn schon zwei Tage VOR dem Wechsel — die Versuchung für jedes Nachfüllen),
der Stundenlauf legt die neue Quelle an, die Werkbank verwirft vor ihrem Beginn ``t``. Danach laufen

* (a) der **Startlauf** (``nachfuellen_anlage``: Spiegel und Eigene Summe) — mit Marke und ohne (Marke gelöscht),
* (b) das **Stände-Nachfüllen** (``nachfuellen_eigene_summe``) an einem Feld, das vom HA-Sensor auf MQTT gewechselt ist
  und Stundenstände vor ``t`` in ``sensor_snapshots`` hat — mit Marke und ohne,
* (c) der **Konsistenzlauf** (``konsistenz_anlage``) nach HA-Korrekturen im alten UND im neuen Abschnitt,
* (d) der **Stundenlauf** (``schreibe_kanaele_im_stundenlauf``) —

und jede Probe zählt die Kanalzeilen vor ``t``: **0**.

⛔ **Offen (H-2 im Bericht E-S3-5, gemessen, nicht gesperrt):** wird später wieder der ALTE Sensor zugeordnet (A → B,
verwerfen, → A), füllt der Startlauf die verworfene Zeit aus HA wieder auf — ``_fuelle_kanal`` sieht als erste Quelle
den alten Sensor, der jetzt wieder die Entity der Zuordnung ist. Die Probe ``test_rueckkehr_zum_alten_sensor_…`` hält den
gemessenen Stand fest; sie kippt, wenn der Master eine Sperre beschließt.

Schwesterdateien: test_werkbank_verwerfen_vor_quellbeginn.py, test_kanal_nachfuellen.py, test_kanal_konsistenz.py,
test_kanal_eigene_summe_nachfuellen.py.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.orm.attributes import flag_modified

from backend.models.anlage import Anlage
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.kanal.konsistenz import konsistenz_anlage
from backend.services.kanal.nachfuellen import nachfuellen_anlage, nachfuellen_eigene_summe, nachfuellen_spiegel
from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf, schreibe_spiegel
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    execute,
    plan,
)
from backend.services.snapshot.keys import _sensor_key_to_mqtt_key
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_konsistenz import _verschiebe
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    ZEIT,
    _s,
    _ts,
    datei,
    ha,
)

TAUSCH = ZEIT + timedelta(days=20)
STUNDENLAUF = TAUSCH + timedelta(days=5)
EINSP = "basis:einspeisung"
NETZ = "basis:netzbezug"


@pytest.fixture(autouse=True)
def _leer():
    _reset_state_for_tests()


def _neuer_sensor(svc, sid: str, ab, *, start: float = 0.0) -> int:
    """HA-Statistik eines zweiten Sensors, ab ``ab`` bis zum Ende der Fixture-Historie."""
    mid = ha_lts_helfer.sensor(svc, sid, "kWh")
    wert, t = start, ab
    while t < JETZT.replace(minute=0):
        wert += 2.0
        ha_lts_helfer.zeile(svc, mid, t, state=wert, sum_wert=wert)
        t += timedelta(hours=1)
    return mid


async def _zuordnung(sitzungen, aid: int, **basis) -> None:
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        m = dict(a.sensor_mapping or {})
        b = dict(m.get("basis") or {})
        for feld, sid in basis.items():
            if sid is None:
                b.pop(feld, None)
            else:
                b[feld] = _s(sid)
        m["basis"] = b
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")


async def _stundenlauf(sitzungen, aid: int, svc, zeitpunkt) -> None:
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await schreibe_spiegel(s, a, zeitpunkt, ha_svc=svc)


async def _kanal(sitzungen, aid: int, key: str) -> Kanal:
    async with sitzungen() as s:
        return (await s.execute(select(Kanal).where(and_(Kanal.anlage_id == aid, Kanal.key == key)))).scalar_one()


async def _quellen(sitzungen, kanal_id: int) -> list[KanalQuelle]:
    async with sitzungen() as s:
        return list((await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id)
                                     .order_by(KanalQuelle.gueltig_ab))).scalars().all())


async def _vor_t(sitzungen, kanal_id: int, t: int) -> int:
    async with sitzungen() as s:
        return int((await s.execute(select(func.count()).select_from(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts < t)))).scalar_one())


async def _verwerfen(sitzungen, aid: int, key: str, t: int) -> dict:
    from backend.services.kanal.verwerfen import text_aus_zeitpunkt

    req = RepairOperationRequest(anlage_id=aid, operation=RepairOperationType.VERWERFEN_VOR_QUELLBEGINN,
                                 params={"kanal": key, "zeitpunkt": text_aus_zeitpunkt(t)})
    async with sitzungen() as s:
        p = await plan(req, s)
    async with sitzungen() as s:
        return (await execute(p.plan_id, s)).actual_changes


async def _marke_weg(sitzungen, kanal_id: int) -> None:
    async with sitzungen() as s:
        await s.execute(delete(KanalNachfuellung).where(KanalNachfuellung.kanal_id == kanal_id))


async def _tausch_und_verwerfen(ha, datei) -> tuple:
    """Alter Sensor nachgefüllt (Marke), Wechsel auf ``sensor.einsp_neu`` (HA ab TAUSCH − 2 Tage), Stundenlauf, Anstoß
    des Nachfüllens wie nach jedem Stundenlauf (Marke folgt der neuen Entity), Verwerfen vor dem Beginn der neuen Quelle.
    Returns ``(svc, sitzungen, aid, kanal, t, zeilen_vor_t_vorher, neu_mid)``."""
    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    neu_mid = _neuer_sensor(svc, "sensor.einsp_neu", TAUSCH - timedelta(days=2))
    await nachfuellen_spiegel(sitzungen, aid, jetzt=TAUSCH, ha_svc=svc)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp_neu")
    await _stundenlauf(sitzungen, aid, svc, STUNDENLAUF)
    await nachfuellen_anlage(sitzungen, aid, jetzt=STUNDENLAUF, ha_svc=svc, nur_vorhandene=True)
    k = await _kanal(sitzungen, aid, EINSP)
    qs = await _quellen(sitzungen, k.id)
    assert [(q.statistic_id, q.gueltig_ab) for q in qs] == [("sensor.einsp", _ts(ZEIT)), ("sensor.einsp_neu", _ts(TAUSCH))]
    t = qs[-1].gueltig_ab
    vorher = await _vor_t(sitzungen, k.id, t)
    assert vorher > 0
    erg = await _verwerfen(sitzungen, aid, EINSP, t)
    assert erg["kanalzeilen_geloescht"] == vorher and await _vor_t(sitzungen, k.id, t) == 0
    return svc, sitzungen, aid, k, t, vorher, neu_mid


async def test_a_startlauf_fuellt_nichts_vor_t(ha, datei):
    svc, sitzungen, aid, k, t, vorher, neu_mid = await _tausch_und_verwerfen(ha, datei)
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert await _vor_t(sitzungen, k.id, t) == 0
    await _marke_weg(sitzungen, k.id)                       # schärfste Lage: keine Marke, HA hat den neuen Sensor vor t
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert erg.uebersprungen.get("vorgeschichte_andere_quelle", 0) >= 1
    assert await _vor_t(sitzungen, k.id, t) == 0


async def test_c_konsistenzlauf_laedt_nichts_vor_t_neu(ha, datei):
    svc, sitzungen, aid, k, t, vorher, neu_mid = await _tausch_und_verwerfen(ha, datei)
    _verschiebe(svc, 1, _ts(ZEIT + timedelta(days=5)), -50.0)          # Korrektur im ALTEN Abschnitt (vor t)
    _verschiebe(svc, neu_mid, _ts(TAUSCH + timedelta(days=1)), +7.0)    # Korrektur im neuen Abschnitt (nach t)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert erg.fehler == 0
    assert any(x["key"] == EINSP and x["ab_ts"] >= t for x in erg.korrigiert)      # der Lauf hat gearbeitet …
    assert await _vor_t(sitzungen, k.id, t) == 0                                  # … aber nicht vor t


async def test_d_stundenlauf_schreibt_nichts_vor_t(ha, datei, monkeypatch):
    svc, sitzungen, aid, k, t, vorher, neu_mid = await _tausch_und_verwerfen(ha, datei)
    monkeypatch.setattr("backend.services.ha_statistics_service.get_ha_statistics_service", lambda: svc)
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        n = await schreibe_kanaele_im_stundenlauf(s, a, JETZT.replace(minute=0))
    assert n is not None and n > 0
    assert await _vor_t(sitzungen, k.id, t) == 0


async def test_b_staende_nachfuellen_fuellt_nichts_vor_t(ha, datei):
    """Netzbezug wechselt vom HA-Sensor auf MQTT (keine HA-Entity mehr): Stundenstände in ``sensor_snapshots`` reichen
    über den ganzen Zeitraum — vor ``t`` lagen sie dem alten Sensor gegenüber."""
    svc, _ = ha
    sitzungen, _pfad, aid, _gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=TAUSCH, ha_svc=svc)
    await _zuordnung(sitzungen, aid, netzbezug=None)
    mqtt = _sensor_key_to_mqtt_key(NETZ)
    k = await _kanal(sitzungen, aid, NETZ)
    async with sitzungen() as s:
        s.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(TAUSCH), familie=FAMILIE_MITSCHRIFT, statistic_id=mqtt,
                          offset=0.0))
        await s.execute(insert(KanalStatistik), [
            {"kanal_id": k.id, "start_ts": _ts(TAUSCH) + h * 3600, "sum": 1000.0 + h, "state": 5000.0 + h,
             "familie": FAMILIE_MITSCHRIFT} for h in range(48)])
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": NETZ, "zeitpunkt": ZEIT + timedelta(hours=h), "wert_kwh": 4000.0 + h,
             "quelle": "mqtt_inbound"} for h in range(1, 22 * 24)])
    t = _ts(TAUSCH)
    await _verwerfen(sitzungen, aid, NETZ, t)
    assert await _vor_t(sitzungen, k.id, t) == 0
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert await _vor_t(sitzungen, k.id, t) == 0
    await _marke_weg(sitzungen, k.id)
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert erg.uebersprungen.get("vorgeschichte_andere_quelle") == 1
    assert await _vor_t(sitzungen, k.id, t) == 0


async def test_rueckkehr_zum_alten_sensor_fuellt_die_verworfene_zeit_wieder_halt_h2(ha, datei):
    """⛔ H-2, gemessen: A → B, verwerfen vor B, dann wieder A zugeordnet ⇒ der Startlauf füllt die Zeit vor t aus HAs
    Statistik von A wieder auf (``_fuelle_kanal``: erste Quelle = A = heutige Entity). Hält den Stand fest; keine Sperre
    gebaut (Auftrag Punkt 4)."""
    svc, sitzungen, aid, k, t, vorher, neu_mid = await _tausch_und_verwerfen(ha, datei)
    await _zuordnung(sitzungen, aid, einspeisung="sensor.einsp")
    await _stundenlauf(sitzungen, aid, svc, STUNDENLAUF + timedelta(days=2))
    assert [q.statistic_id for q in await _quellen(sitzungen, k.id)] == ["sensor.einsp", "sensor.einsp_neu", "sensor.einsp"]
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert await _vor_t(sitzungen, k.id, t) == vorher           # die verworfene Zeit ist wieder da
