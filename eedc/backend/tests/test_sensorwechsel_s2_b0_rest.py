"""Sensorwechsel mit Grund, Sitzung 2 — B-0-Rest (Bauplan §8 Nr. 22 b/c): die Zuordnung zum Zeitpunkt auch für die
Heimlade-Zähler je Auto (Ladeblöcke beim Neuaufbau eines alten Tags) und für die zwei LTS-Tages-Leser
(``get_komponenten_tageskwh_lts`` — Tag-Status und drei Daten-Checker — und ``get_hourly_kwh_by_category_lts``).

**(b)** «Tag neu aggregieren» eines Tags vor einem Wechsel des Heimlade-Zählers liest die Fahrzeug-Slots je Slot aus der
Entität, die zum Stand galt (``lts_aggregator._zusatz_plan``) — vorher las er die heutige Entität für den ganzen Tag
(Nachmessung S1 §6: Ladeblock 4.–5.11. mit 58,112 kWh entfiel). **(c)** Die Aufrufer reichen ``wechsel_kwargs`` durch.
Je Probe der Sprengsatz im selben Test: ohne Wechsel liest der Tag die heutige Entität. Korrekturrunde (K-3): die vier
Durchreich-Stellen über ihre öffentlichen Wege (Tag-Status, drei Daten-Checker) und ``_plan_anwenden(streng=False)``.
**(a)** «→ Keine» (die Tageszeile verliert den Schlüssel beim Neuaufbau) ist in Sitzung 2 nicht gebaut — übergeben.

Schwesterdateien: test_sensorwechsel_s1_zeitpunkt.py (B-0 am LTS-Tag der eigenen Zähler), test_zaehlerluecken_lts_tabelle.py.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus
from backend.tests.test_zaehlerluecken_lts_tabelle import _reihe as lts_reihe
from backend.tests.test_zaehlerluecken_lts_tabelle import _svc_sql

D = date(2026, 9, 20)
ERKLAERT = datetime(2026, 10, 18, 10, 47, 42)
A, B = {"art": "ha", "entity_id": "sensor.a"}, {"art": "ha", "entity_id": "sensor.b"}


def _svc():
    von, bis = datetime(2026, 9, 18, 12), datetime(2026, 9, 22, 22)
    return _svc_sql({"sensor.a": lts_reihe(von, bis, 800.0, 0.5), "sensor.b": lts_reihe(von, bis, 5000.0, 1.0),
                     "sensor.wb": lts_reihe(von, bis, 100.0, 2.0)})


async def _wechsel(db, aid: int, key: str):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=ERKLAERT, ab_ts=ab_ts_aus(ERKLAERT),
                            vorher=A, nachher=B, herkunft="wechsel"))
    await db.flush()
    zw.vergiss(db)


def _ha():
    return patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=_svc())


# ═══ (c) die LTS-Tages-Leser ═══════════════════════════════════════════════════════════════════════════════════════

async def _basis_anlage(db):
    a = Anlage(anlagenname="LTS", leistung_kwp=10.0, sensor_mapping={
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}}, "investitionen": {}})
    db.add(a)
    await db.flush()
    await _wechsel(db, a.id, "basis:netzbezug")
    return a


async def test_c_komponenten_tageskwh_lts_mit_den_wechseln(db):
    from backend.services.energie_profil.tag_status import _ha_tageswerte
    from backend.services.snapshot import lts_aggregator as lts

    a = await _basis_anlage(db)
    with _ha():
        kw = await lts.wechsel_kwargs(db, a.id)
        assert (await lts.get_komponenten_tageskwh_lts(a, {}, D, **kw))["netzbezug"] == 12.0      # 24 × 0,5 (A)
        assert (await lts.get_hourly_kwh_by_category_lts(db, a, {}, D))[5]["netzbezug"] == 0.5
        with patch("backend.services.ha_statistics_service.get_ha_statistics_service",
                   return_value=SimpleNamespace(is_available=True)):
            assert (await _ha_tageswerte(a, {}, D, {"netzbezug"}, kw)) is not None
        # Sprengsatz: ohne die Wechsel liest der Tag die heutige Entität B
        assert (await lts.get_komponenten_tageskwh_lts(a, {}, D))["netzbezug"] == 24.0


async def test_c_tag_status_reicht_die_wechsel_durch(db, monkeypatch):
    """``_ha_tageswerte`` ruft den LTS-Leser mit den Wechseln der Anlage (die Daten-Checker ebenso, über ``wechsel_kwargs``)."""
    from backend.services.energie_profil import tag_status
    from backend.services.snapshot import lts_aggregator as lts

    a = await _basis_anlage(db)
    gesehen = {}

    async def _lts(anlage, invs, datum, **kw):
        gesehen.update(kw)
        return {}
    monkeypatch.setattr(lts, "get_komponenten_tageskwh_lts", _lts)
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=SimpleNamespace(is_available=True)):
        await tag_status._ha_tageswerte(a, {}, D, set(), await lts.wechsel_kwargs(db, a.id))
    assert set(gesehen["wechsel"]) == {"basis:netzbezug"}


# ═══ (b) Heimlade-Zähler je Auto ════════════════════════════════════════════════════════════════════════════════════

async def _emob_anlage(db):
    a = Anlage(anlagenname="Heimladung", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {
        "2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}},
        "3": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.b"}}},
    }})
    db.add(a)
    await db.flush()
    wb = Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1))
    auto = Investition(id=3, anlage_id=a.id, typ="e-auto", bezeichnung="Auto", anschaffungsdatum=date(2024, 1, 1))
    db.add_all([wb, auto])
    await db.flush()
    return a, {"2": wb, "3": auto}


async def test_b_heimlade_zaehler_liest_je_slot_die_entitaet_zum_stand(db):
    from backend.services.snapshot import lts_aggregator as lts

    a, invs = await _emob_anlage(db)
    await _wechsel(db, a.id, "inv:3:ladung_kwh")
    with _ha():
        tab = await lts.lts_tagestabelle(a, invs, D, zusatz_schluessel=["sensor.b"], **await lts.wechsel_kwargs(db, a.id))
        assert {s[0] for s in tab.zusatz_slots["sensor.b"].values()} == {0.5}                   # A: 0,5 je Stunde
        # Sprengsatz: ohne die Wechsel trägt der Heimlade-Zähler B (1,0 je Stunde) für den ganzen alten Tag
        tab = await lts.lts_tagestabelle(a, invs, D, zusatz_schluessel=["sensor.b"])
        assert {s[0] for s in tab.zusatz_slots["sensor.b"].values()} == {1.0}


async def test_b_heimlade_zaehler_fruehere_quelle_ausserhalb_ha_liest_nicht(db):
    """Galt am Tag eine Quelle außerhalb von HA (MQTT), liest der Tag den Heimlade-Zähler nicht — nie die heutige Entität."""
    from backend.services.snapshot import lts_aggregator as lts

    a, invs = await _emob_anlage(db)
    db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key="inv:3:ladung_kwh", erklaert_ts=ERKLAERT, ab_ts=ab_ts_aus(ERKLAERT),
                            vorher={"art": "mqtt", "mqtt_key": "inv/3/ladung_kwh"}, nachher=B, herkunft="wechsel"))
    await db.flush()
    zw.vergiss(db)
    with _ha():
        tab = await lts.lts_tagestabelle(a, invs, D, zusatz_schluessel=["sensor.b"], **await lts.wechsel_kwargs(db, a.id))
    assert "sensor.b" not in tab.zusatz_slots


# ═══ K-3: die vier Durchreich-Stellen und `_plan_anwenden(streng=False)` ═══════════════════════════════════════════

#: Platzhalter der verzeichneten Wechsel, den die Spione erkennen (``wechsel_kwargs`` gestellt).
_W = {"basis:netzbezug": ["platzhalter"]}


def _spione(gesehen: list, werte, mit_wechsel: bool):
    """``wechsel_kwargs`` liefert die Wechsel (oder, Gegenprobe, keine — dann bleibt der Aufruf wörtlich der alte); der
    LTS-Tages-Leser merkt sich die Schlüsselwort-Argumente je Aufruf."""
    async def _kw(_db, _aid):
        return {"wechsel": _W} if mit_wechsel else {}

    async def _lts(_anlage, _invs, datum, **kw):
        gesehen.append(kw)
        return werte(datum)
    return [patch("backend.services.snapshot.lts_aggregator.wechsel_kwargs", new=_kw),
            patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts", new=_lts)]


async def _mit_spionen(patches_davor, aufruf, werte, mit_wechsel: bool) -> list:
    gesehen: list = []
    alle = [*patches_davor, *_spione(gesehen, werte, mit_wechsel)]
    for p in alle:
        p.start()
    try:
        await aufruf()
    finally:
        for p in reversed(alle):
            p.stop()
    return gesehen


async def test_durchreichen_tag_status(db, monkeypatch):
    """``baue_tag_status`` (Tag-Status der Tagesansicht) reicht die Wechsel der Anlage an den LTS-Tages-Leser — über den
    öffentlichen Weg, nicht über ``_ha_tageswerte``. Gegenprobe: ohne Wechsel bleibt der Aufruf wörtlich der alte."""

    from backend.services.energie_profil.tag_status import baue_tag_status
    from backend.tests.test_tag_status_leere_tagessicht import _anlage

    tag = D                                         # festes Datum (keine Prozessuhr in der Probe)
    ha = patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=SimpleNamespace(is_available=True))
    for mit, soll in ((True, {"wechsel": _W}), (False, {})):
        a = await _anlage(db)
        gesehen = await _mit_spionen([ha], lambda: baue_tag_status(db, a, tag), lambda d: {"netzbezug": 12.5}, mit)
        assert gesehen == [soll]


async def test_durchreichen_daten_checker_vorzeichen(db):
    """Daten-Checker «Batterie-Vorzeichen» (``datenquelle/speicher.py``)."""

    from backend.tests import test_batterie_vorzeichen_historie_check as t

    tag = D                                         # der Check liest die Tageszeilen der Attrappe ohne Fenster-Filter
    for mit, soll in ((True, {"wechsel": _W}), (False, {})):
        checker, patches = t._build_checker([t._make_tz(tag, -4.0)], [t._make_inv()], lambda d: {"batterie_5": 4.0})
        gesehen = await _mit_spionen(patches, lambda: checker._check_batterie_vorzeichen_historie(t._make_anlage()),
                                     lambda d: {"batterie_5": 4.0}, mit)
        assert gesehen == [soll]


async def test_durchreichen_daten_checker_drift(db):
    """Daten-Checker «Datenquelle weicht ab» (``datenquelle/quellen.py``, über ``_DriftKontext.wechsel_kw``)."""
    from datetime import timedelta

    from backend.tests import test_etappe_6_drift_check as t

    tz = [t._make_tz(D - timedelta(days=i), 30.0) for i in (1, 2)]   # feste Daten; die Attrappe filtert nicht nach dem Fenster
    for mit, soll in ((True, {"wechsel": _W}), (False, {})):
        checker, patches = t._build_checker(tz, [t._make_inv()], lambda d: {"pv_3": 30.0})
        gesehen = await _mit_spionen(patches, lambda: checker._check_datenquelle_drift(t._make_anlage()),
                                     lambda d: {"pv_3": 30.0}, mit)
        assert gesehen and all(kw == soll for kw in gesehen)


async def test_durchreichen_daten_checker_leere_tage(db):
    """Daten-Checker «Leere Tage trotz Zähler» (``datenquelle/tage.py``) — dieselbe Attrappe wie dessen Proben."""
    from unittest.mock import MagicMock

    from backend.services.daten_checker import DatenChecker
    from backend.tests import test_daten_checker_leere_tage_trotz_zaehler as t

    # Der Check geht die Tage seines Fensters (bis gestern, aus der Prozessuhr des Prüflings) durch — der Kandidat muss darin
    # liegen; das Datum kommt aus dem Helfer der Schwesterdatei (dort steht die Begründung für die Uhr), nicht aus dieser Probe.
    tag = t._gestern()
    tz_list = [t._make_tz(tag, {"pv_7": 29.0, "einspeisung": 0.0, "netzbezug": 0.0}), *t._volle_zeilen(2)]
    for mit, soll in ((True, {"wechsel": _W}), (False, {})):
        db_ = MagicMock()
        n = {"n": 0}

        async def _execute(_stmt, _n=n):
            _n["n"] += 1
            r, sc = MagicMock(), MagicMock()
            sc.all = MagicMock(return_value=[t._make_inv()] if _n["n"] == 1 else tz_list)
            r.scalars = MagicMock(return_value=sc)
            r.scalar_one_or_none = MagicMock(return_value=None)
            return r
        db_.execute = _execute
        checker = DatenChecker(db_)
        davor = [patch("backend.services.ha_statistics_service.get_ha_statistics_service",
                       return_value=SimpleNamespace(is_available=True)),
                 patch("backend.services.energie_profil.kanal_stunden.komponenten_der_tage", new=t._bestand_komponenten(tz_list))]
        gesehen = await _mit_spionen(davor, lambda: checker._check_leere_tage_trotz_zaehler(t._make_anlage()),
                                     lambda d: {"einspeisung": 22.0, "netzbezug": 3.4, "pv_7": 29.0}, mit)
        assert gesehen == [soll]


async def test_b_heimlade_fruehere_entitaet_fehlt_in_ha_nie_die_heutige(db):
    """Führt HA die frühere Entität des Heimlade-Zählers nicht (mehr), fallen ihre Slots weg — nie das Delta der heutigen
    Entität für den alten Tag (``_plan_anwenden(streng=False)``). Gegenprobe im selben Test: mit der strengen Form (wie für
    die eigenen Zähler) bräche die Anwendung ab und der Tag trüge B (1,0 je Stunde)."""
    from backend.services.snapshot import lts_aggregator as lts

    a, invs = await _emob_anlage(db)
    await _wechsel(db, a.id, "inv:3:ladung_kwh")
    von, bis = datetime(2026, 9, 18, 12), datetime(2026, 9, 22, 22)
    ohne_a = _svc_sql({"sensor.b": lts_reihe(von, bis, 5000.0, 1.0), "sensor.wb": lts_reihe(von, bis, 100.0, 2.0)})

    async def tabelle():
        with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=ohne_a):
            return await lts.lts_tagestabelle(a, invs, D, zusatz_schluessel=["sensor.b"], **await lts.wechsel_kwargs(db, a.id))

    tab = await tabelle()
    assert 1.0 not in {s[0] for s in (tab.zusatz_slots.get("sensor.b") or {}).values()}
    echt = lts._plan_anwenden
    with patch.object(lts, "_plan_anwenden", lambda r, p, **_k: echt(r, p)):          # Sprengsatz: streng
        tab = await tabelle()
    assert {s[0] for s in tab.zusatz_slots["sensor.b"].values()} == {1.0}
