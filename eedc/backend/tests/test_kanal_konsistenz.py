"""Proben Konsistenzlauf Spiegel ↔ HA (HA-Bauform E2, Auftrag Punkt 4; Gegenprüfung G6).

Pflichtprobe des Auftrags: HA-``sum`` ab Stunde t um −480 verschoben (HAs „Summe anpassen",
``recorder_statistics.py::_adjust_sum_statistics``: derselbe Versatz auf ALLE Folgezeilen) ⇒ nach dem Lauf
steht die Korrektur an der Ursprungsstunde, die Zeilen davor sind unverändert, Bestand und Mitschrift
unberührt. Dazu: eine Stunde, die HA nachgereicht hat (``compile_missing_statistics``), ein Sensortausch
(die Naht bleibt stetig) und der Schutz „HA hat keine Zeile mehr".

Datenstand und Fixtures wie ``test_kanal_nachfuellen.py`` (dort beschrieben). Keine Probe liest die Uhr.

Schwesterdateien: test_kanal_nachfuellen.py, test_kanal_spiegel.py, test_kanal_symmetrie.py.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import delete, select, text

from backend.models.kanal import (
    FAMILIE_BESTAND,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal.konsistenz import konsistenz_alle, konsistenz_anlage
from backend.services.kanal.lesen import delta, kanalwert
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures
    JETZT,
    LUECKE,
    ZEIT,
    _quellen,
    _reihe,
    _s,
    _ts,
    _zeilen,
    datei,
    ha,
)

_EINSP_MID = 1          # sensor.einsp ist der erste Sensor der Fixture `ha`


def _verschiebe(svc, mid: int, ab_ts: int, um: float) -> None:
    """HAs „Summe anpassen": ``sum`` jeder Zeile ab ``ab_ts`` um ``um`` (Kurzzeit- und Stundentabelle)."""
    with svc._engine.begin() as conn:
        conn.execute(text("UPDATE statistics SET sum = sum + :um WHERE metadata_id = :m AND start_ts >= :t"),
                     {"um": um, "m": mid, "t": ab_ts})


async def _kanal(sitzungen, aid, key) -> Kanal:
    async with sitzungen() as s:
        return (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()


def _roh(z: dict) -> dict:
    return {t: (r.sum, r.state, r.familie) for t, r in z.items()}


async def test_pflichtprobe_versatz_minus_480_steht_an_der_ursprungsstunde(ha, datei):
    svc, reihen = ha
    sitzungen, _pfad, aid, gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    kanal = await _kanal(sitzungen, aid, "basis:einspeisung")
    t_b, t_m = _ts(ZEIT + timedelta(hours=LUECKE.start + 2)), _ts(ZEIT + timedelta(hours=LUECKE.start + 30))
    async with sitzungen() as s:                       # Bestand und Mitschrift in Stunden ohne HA-Zeile
        s.add(KanalStatistik(kanal_id=kanal.id, start_ts=t_b, sum=7.0, state=7.0, familie=FAMILIE_BESTAND))
        s.add(KanalStatistik(kanal_id=kanal.id, start_ts=t_m, sum=8.0, state=8.0, familie=FAMILIE_MITSCHRIFT))
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    netz_vorher = _roh(await _zeilen(sitzungen, aid, "basis:netzbezug"))
    t = _ts(ZEIT + timedelta(days=27, hours=13))
    _verschiebe(svc, _EINSP_MID, t, -480.0)

    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert erg.fehler == 0
    assert [(k["key"], k["ab_ts"]) for k in erg.korrigiert] == [("basis:einspeisung", t)]
    nachher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    assert {ts: w for ts, w in nachher.items() if ts < t} == {ts: w for ts, w in vorher.items() if ts < t}
    assert nachher[t_b] == (7.0, 7.0, FAMILIE_BESTAND) and nachher[t_m] == (8.0, 8.0, FAMILIE_MITSCHRIFT)
    assert set(nachher) == set(vorher)
    async with sitzungen() as s:
        assert await delta(s, kanal, t - 3600, t) == pytest.approx(1.25 - 480.0)   # die Korrektur, genau dort
        assert await delta(s, kanal, t, t + 3600) == pytest.approx(1.25)
        assert await delta(s, kanal, t - 7200, t - 3600) == pytest.approx(1.25)
    assert _roh(await _zeilen(sitzungen, aid, "basis:netzbezug")) == netz_vorher
    assert [(q.gueltig_ab, q.offset) for q in await _quellen(sitzungen, aid, "basis:einspeisung")] == [(_ts(ZEIT), 0.0)]


async def test_zweiter_lauf_nach_der_korrektur_ist_gleich(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    _verschiebe(svc, _EINSP_MID, _ts(ZEIT + timedelta(days=3)), -480.0)
    assert (await konsistenz_anlage(sitzungen, aid, ha_svc=svc)).korrigiert
    zweit = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert (zweit.korrigiert, zweit.gleich, zweit.abschnitte) == ([], 3, 3)


class _Zaehler:
    def __init__(self, svc):
        self._svc, self.abrufe = svc, 0

    def __getattr__(self, name):
        attr = getattr(self._svc, name)
        if callable(attr) and name.startswith("get_"):
            def _gezaehlt(*a, **k):
                self.abrufe += 1
                return attr(*a, **k)
            return _gezaehlt
        return attr


async def test_gleicher_spiegel_kostet_vier_abfragen_je_abschnitt(ha, datei):
    """Gleich ⇒ keine Halbierung: Einheit (eine Zeile), Kennzahlen des Abschnitts, Prüfstelle am Ende
    (Kennzahlen + letzte Zeile) — vier HA-Abfragen, auch mit der Vorsumme (Nachmessung E2 Punkt 2a)."""
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    gezaehlt = _Zaehler(svc)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=gezaehlt)
    assert (erg.korrigiert, erg.gleich) == ([], 3)        # Einspeisung, Netzbezug, Gaszähler (mean nicht)
    assert gezaehlt.abrufe == 3 * 4


async def test_nachgereichte_stunde_wird_eingefuegt(ha, datei):
    """HA reicht eine Stunde nach, die eedc nie sah (``compile_missing_statistics``/Import): die
    Halbierung findet genau sie, der Lauf fügt sie ein — sonst ändert sich nichts."""
    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    kanal = await _kanal(sitzungen, aid, "basis:einspeisung")
    x = _ts(ZEIT + timedelta(days=33, hours=7))
    async with sitzungen() as s:
        await s.execute(delete(KanalStatistik).where(KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts == x))
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert [(k["key"], k["ab_ts"]) for k in erg.korrigiert] == [("basis:einspeisung", x)]
    nachher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    assert nachher[x] == (reihen["sensor.einsp"][x]["sum"], reihen["sensor.einsp"][x]["state"], FAMILIE_SPIEGEL)
    assert {ts: w for ts, w in nachher.items() if ts != x} == vorher


async def test_versatz_vor_einem_sensortausch_verschiebt_die_spaeteren_quellen(ha, datei):
    """Zwei Spiegel-Abschnitte (Tausch am Tag 30). HA korrigiert den ALTEN Sensor ab Tag 20 um −480: die
    Korrektur steht an ihrer Stunde, der ``offset`` des neuen Abschnitts zieht um −480 nach — jedes Δ
    nach der Naht bleibt, wie HA es nennt (die Naht selbst unverändert)."""
    from backend.models.anlage import Anlage
    from sqlalchemy.orm.attributes import flag_modified

    from backend.services.kanal.schreiber import schreibe_spiegel

    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    tausch = ZEIT + timedelta(days=30)
    neu = _reihe(svc, "sensor.einsp_neu", "kWh", start=10.0, rate=2.0)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=tausch, ha_svc=svc)
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = {**a.sensor_mapping, "basis": {**a.sensor_mapping["basis"], "einspeisung": _s("sensor.einsp_neu")}}
        flag_modified(a, "sensor_mapping")
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await schreibe_spiegel(s, a, JETZT.replace(minute=0), ha_svc=svc)
    kanal = await _kanal(sitzungen, aid, "basis:einspeisung")
    q_vorher = [(q.statistic_id, q.gueltig_ab, q.offset) for q in await _quellen(sitzungen, aid, "basis:einspeisung")]
    assert [x[0] for x in q_vorher] == ["sensor.einsp", "sensor.einsp_neu"]
    t_naht = q_vorher[1][1]
    t = _ts(ZEIT + timedelta(days=20, hours=4))
    async with sitzungen() as s:
        naht_vorher = await delta(s, kanal, t_naht - 3600, t_naht)
        nach_naht_vorher = await delta(s, kanal, t_naht, _ts(JETZT.replace(minute=0)) - 3600)
    _verschiebe(svc, _EINSP_MID, t, -480.0)

    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert [(k["key"], k["ab_ts"]) for k in erg.korrigiert] == [("basis:einspeisung", t)]
    q_nachher = [(q.statistic_id, q.gueltig_ab, q.offset) for q in await _quellen(sitzungen, aid, "basis:einspeisung")]
    assert q_nachher[0] == q_vorher[0]
    assert q_nachher[1][2] == pytest.approx(q_vorher[1][2] - 480.0)
    async with sitzungen() as s:
        # Lese-Hilfe `kanalwert`: die eine Zeile der Stunde, Rohwert + offset der geltenden Quelle, Familie dabei.
        w_naht = await kanalwert(s, kanal, t_naht)
        assert (w_naht.familie, w_naht.wert) == (FAMILIE_SPIEGEL, pytest.approx(neu[t_naht]["sum"] + q_nachher[1][2]))
        w_alt = await kanalwert(s, kanal, t_naht - 3600)
        assert w_alt.wert == pytest.approx(reihen["sensor.einsp"][t_naht - 3600]["sum"] - 480.0 + q_nachher[0][2])
        assert await kanalwert(s, kanal, _ts(ZEIT + timedelta(hours=LUECKE.start))) is None    # HA-Lücke
        assert await delta(s, kanal, t - 3600, t) == pytest.approx(1.25 - 480.0)
        assert await delta(s, kanal, t_naht - 3600, t_naht) == pytest.approx(naht_vorher)
        assert await delta(s, kanal, t_naht, _ts(JETZT.replace(minute=0)) - 3600) == pytest.approx(nach_naht_vorher)
    assert neu  # die neue Reihe ist gesät


async def test_ha_ohne_zeilen_loescht_nichts(ha, datei):
    """Schutz: hat HA die Statistik eines Sensors nicht mehr, bleibt der Spiegel stehen."""
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    with svc._engine.begin() as conn:
        conn.execute(text("DELETE FROM statistics WHERE metadata_id = :m"), {"m": _EINSP_MID})
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert erg.uebersprungen.get("ha_ohne_zeilen") == 1 and erg.korrigiert == []
    assert _roh(await _zeilen(sitzungen, aid, "basis:einspeisung")) == vorher


async def test_korrektur_steht_im_aktivitaetsprotokoll(ha, datei):
    from backend.models.activity_log import ActivityLog

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    await konsistenz_alle(sitzungen, ha_svc=svc)              # gleich ⇒ kein Eintrag
    _verschiebe(svc, _EINSP_MID, _ts(ZEIT + timedelta(days=9)), -480.0)
    await konsistenz_alle(sitzungen, ha_svc=svc)
    async with sitzungen() as s:
        log = [(x.aktion, x.erfolg, x.anlage_id) for x in (await s.execute(select(ActivityLog))).scalars().all()]
    assert log == [("Kanalstatistik: Spiegel an HA angeglichen", True, aid)]



# ── Nachmessung E2 (06.10.): sich aufhebende Anpassungen · gekürzte HA-Historie · HA fällt still aus ──────


def _ha_sum(svc, mid: int = _EINSP_MID) -> dict:
    with svc._engine.connect() as c:
        return {int(r[0]): (r[1], r[2]) for r in c.execute(
            text("SELECT start_ts, sum, state FROM statistics WHERE metadata_id = :m"), {"m": mid})}


async def test_zwei_sich_aufhebende_anpassungen_werden_gefunden(ha, datei):
    """−480 ab t1, +480 ab t2 vor demselben Lauf: letzte Zeile und Zeilenzahl stimmen wieder, die Vorsumme
    nicht ⇒ die Halbierung findet t1, das Neu-Laden ab dort übernimmt beide — danach ist jede Zeile == HA."""
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    t1, t2 = _ts(ZEIT + timedelta(days=17, hours=3)), _ts(ZEIT + timedelta(days=19, hours=3))
    _verschiebe(svc, _EINSP_MID, t1, -480.0)
    _verschiebe(svc, _EINSP_MID, t2, +480.0)
    gezaehlt = _Zaehler(svc)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=gezaehlt)
    assert [(k["key"], k["ab_ts"]) for k in erg.korrigiert] == [("basis:einspeisung", t1)]
    ist = await _zeilen(sitzungen, aid, "basis:einspeisung")
    ha_jetzt = _ha_sum(svc)
    assert all((r.sum, r.state) == ha_jetzt[t] for t, r in ist.items())
    assert {t: w for t, w in _roh(ist).items() if t < t1} == {t: w for t, w in vorher.items() if t < t1}
    zweit = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert zweit.korrigiert == [] and zweit.gleich == 3


async def test_ha_haelt_den_anfang_nicht_mehr_nichts_wird_geloescht(ha, datei):
    """HA hat die Zeilen vor Tag 12 nicht mehr (HAs „alte Statistik löschen"): eigene Klasse
    ``ha_historie_gekuerzt``, verglichen wird ab HAs erster Zeile, KEINE Spiegelzeile verschwindet; eine
    Korrektur danach (−480 ab Tag 20) kommt trotzdem an — die Zeilen vor Tag 12 bleiben bitgleich."""
    from backend.models.activity_log import ActivityLog

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    x = _ts(ZEIT + timedelta(days=12))
    with svc._engine.begin() as conn:
        conn.execute(text("DELETE FROM statistics WHERE metadata_id = :m AND start_ts < :t"), {"m": _EINSP_MID, "t": x})
    erg = await konsistenz_alle(sitzungen, ha_svc=svc)
    assert erg[0].korrigiert == [] and erg[0].uebersprungen.get("ha_historie_gekuerzt") == 1
    alt = sum(1 for t in vorher if t < x)
    assert erg[0].gekuerzt == [{"key": "basis:einspeisung", "ha_erste_ts": x, "behalten": alt}]
    assert _roh(await _zeilen(sitzungen, aid, "basis:einspeisung")) == vorher
    t = _ts(ZEIT + timedelta(days=20, hours=5))
    _verschiebe(svc, _EINSP_MID, t, -480.0)
    zweit = await konsistenz_anlage(sitzungen, aid, ha_svc=svc)
    assert [(k["key"], k["ab_ts"]) for k in zweit.korrigiert] == [("basis:einspeisung", t)]
    nachher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    assert set(nachher) == set(vorher)
    assert {a: b for a, b in nachher.items() if a < t} == {a: b for a, b in vorher.items() if a < t}
    async with sitzungen() as s:
        log = [(x_.aktion, x_.details_json.get("gekuerzt")) for x_ in (await s.execute(select(ActivityLog))).scalars().all()]
    assert log == [("Kanalstatistik: HA hält nicht mehr die ganze Spiegel-Historie",
                    [{"key": "basis:einspeisung", "ha_erste_ts": x, "behalten": alt}])]


class _Kippend:
    """HA-Dienst, der nach ``n`` Abfragen still wegfällt — wie der WebSocket-Transport: ``is_available`` wird
    falsch, die Leser liefern ``None``/``{}`` statt zu werfen."""

    def __init__(self, svc, n: int):
        self._svc, self._n, self.abrufe, self.da = svc, n, 0, True

    @property
    def is_available(self):
        return self.da

    def __getattr__(self, name):
        attr = getattr(self._svc, name)
        if not (callable(attr) and name.startswith("get_")):
            return attr

        def _abruf(*a, **k):
            self.abrufe += 1
            if self.abrufe >= self._n:
                self.da = False
            if not self.da:
                return {} if name == "get_stundenzeilen_mehrere" else None
            return attr(*a, **k)
        return _abruf


async def test_ha_faellt_waehrend_der_halbierung_still_aus_nichts_aendert_sich(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    vorher = _roh(await _zeilen(sitzungen, aid, "basis:einspeisung"))
    _verschiebe(svc, _EINSP_MID, _ts(ZEIT + timedelta(days=21)), -480.0)
    erg = await konsistenz_anlage(sitzungen, aid, ha_svc=_Kippend(svc, 7))     # mitten in der Halbierung
    assert erg.fehler == 3 and erg.korrigiert == []          # alle drei Abschnitte brechen ab, keiner ändert
    assert _roh(await _zeilen(sitzungen, aid, "basis:einspeisung")) == vorher
    assert (await konsistenz_anlage(sitzungen, aid, ha_svc=svc)).korrigiert      # der nächste Lauf holt es nach


def test_kennzahlen_sql_und_websocket_gleich():
    """``get_stundenzeilen_kennzahlen`` rechnet über beide Transporte dieselbe Zahl (Fenster ``(nach, bis]``,
    ``NULL`` zählt nicht in die Summen)."""
    from backend.services.ha_statistics_ws import WsSensorMeta
    from backend.tests.test_ha_statistics_websocket_transport import _service_mit_ws, _zeile

    zeilen = [_zeile(1000.0 + 3600 * i, sum=10.0 + i, state=None if i == 3 else 5.0 + i) for i in range(8)]
    sql = ha_lts_helfer.mach_service()
    mid = ha_lts_helfer.sensor(sql, "sensor.z", "kWh")
    with sql._engine.begin() as conn:
        for z in zeilen:
            conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :st, :su)"),
                         {"m": mid, "t": z["start_ts"], "st": z["state"], "su": z["sum"]})
    ws, _fake = _service_mit_ws({"sensor.z": WsSensorMeta("kWh", True, False)}, {"sensor.z": zeilen})
    for nach, bis in ((999.0, 1000.0 + 3600 * 7), (1000.0, 1000.0 + 3600 * 4), (1000.0 + 3600 * 9, 1000.0 + 3600 * 12)):
        a, b = sql.get_stundenzeilen_kennzahlen("sensor.z", nach, bis), ws.get_stundenzeilen_kennzahlen("sensor.z", nach, bis)
        assert a == b, (nach, bis, a, b)
    assert sql.get_stundenzeilen_kennzahlen("sensor.z", 999.0, 1000.0 + 3600 * 7) == {
        "anzahl": 8, "summe_sum": sum(10.0 + i for i in range(8)),
        "summe_state": sum(5.0 + i for i in range(8) if i != 3), "erste_ts": 1000.0}
    assert sql.get_stundenzeilen_kennzahlen("sensor.unbekannt", 0, 1e10) is None
