"""RF-77 … RF-80 — benannte Proben für die Zweige, die die direkten Testdateien nicht betreten.

Komplexitäts-Paket 3, Session P3-F (Bauform RF-1). Die vier Funktionen wurden in Phasen geschnitten; diese Proben halten
die Zweige fest, die vorher nur der jeweilige Fixture-GM sah (gemessen per Bogen-Spur über die direkten Testdateien am
Stand vor dem Schnitt). Sie prüfen Verhalten, keine Form — am Stand vor dem Schnitt sind sie ebenso grün.

Schwesterdateien (die direkten Tests der vier Funktionen):
  * ``bilde_ladebloecke`` (RF-80): ``test_n555_stufe3_ladebloecke.py``, ``test_s5_stunden_der_tage.py``,
    ``test_kanal_geraete_leser.py``
  * ``_fetch_solcast_ha_auto`` (RF-77): ``test_solcast_tagesprofile_357.py``, ``test_n156_ha_wege_ohne_supervisor.py``,
    ``test_n547_lern_soll_nicht_zirkulaer.py``
  * ``loese_integration_auf`` (RF-78): ``test_prognose_discovery_integration.py``, ``test_prognose_discovery_sfml.py``
  * ``baue_investitions_serien`` (RF-79): ``test_serien_aufbau_symmetrie_m1.py``, ``test_n555_stufe2_messung_je_auto.py``,
    ``test_377_zaehlerstaende.py``, ``test_n439_leistung_kuehlen_anzeige.py``, ``test_bs7_gesamtleistung_hinweis.py``,
    ``test_f70_sonstiger_speicher_live_bilanz.py``, ``test_n565_tagesverlauf_investitionen_je_tag.py``,
    ``test_zaehlerluecken_s2_8b_wallbox_je_tag.py``

Fixture-GMs (außerhalb des Repos, ``~/.claude/plans/skript-golden-master-<name>.py``): ``ladebloecke``,
``solcast-ha-auto``, ``integration-aufloeser``, ``investitions-serien``.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.services.emob_ladebloecke import (
    FahrzeugSprung,
    WallboxStunde,
    bilde_ladebloecke,
)
from backend.services.live_sensor_config import baue_investitions_serien

TZ = ZoneInfo("Europe/Berlin")
B0 = datetime(2026, 7, 8, 0)
#: fester «heute» für die Solcast-Proben (N-167: keine Probe liest die echte Uhr) — gesetzt über den Modul-Namen
#: ``solcast_service.date``, den der Rumpf für ``date.today()`` liest.
HEUTE = date(2026, 7, 30)


class _FesterTag(date):
    @classmethod
    def today(cls):
        return HEUTE


def _h(n: int) -> datetime:
    return B0 + timedelta(hours=n)


# ── RF-80 bilde_ladebloecke ───────────────────────────────────────────────────────────────────────────────────────────


def test_rf80_leere_und_negative_wallbox_stunden_fallen_weg():
    """Stunden mit ``kwh`` None, 0 oder < 0 tragen nichts zur Restmenge bei."""
    stunden = [WallboxStunde(_h(1), 2.0), WallboxStunde(_h(2), None), WallboxStunde(_h(3), -1.0),
               WallboxStunde(_h(4), 0.0), WallboxStunde(_h(5), 1.0)]
    (block,) = bilde_ladebloecke(stunden, [FahrzeugSprung(1, _h(5), 3.0)])
    assert [s.beginn for s in block.stunden] == [_h(1), _h(5)]
    assert block.stunden_gedeckt == 1.0


def test_rf80_sprung_null_bildet_keinen_block_und_setzt_keine_schranke():
    """Ein Sprung ≤ 0 wird übersprungen — die Schranke bleibt beim vorigen echten Sprung."""
    stunden = [WallboxStunde(_h(k), 1.0) for k in range(1, 8)]
    bloecke = bilde_ladebloecke(stunden, [FahrzeugSprung(1, _h(3), 2.0), FahrzeugSprung(2, _h(5), 0.0),
                                          FahrzeugSprung(3, _h(7), 5.0)])
    assert [b.inv_id for b in bloecke] == [1, 3]
    # Schranke = Sprungstunde 3 (einschließlich): Stunde 3 ist vom ersten Block verbraucht, 4…7 bleiben
    assert [s.beginn for s in bloecke[1].stunden] == [_h(4), _h(5), _h(6), _h(7)]


def test_rf80_winziger_sprung_nimmt_keine_stunde():
    """Bedarf unter 1e-9 in der eigenen Sprungstunde ⇒ Entnahme ≤ EPS ⇒ Block ohne Blockstunde."""
    (block,) = bilde_ladebloecke([WallboxStunde(_h(2), 2.0, pv_anteil=0.5)], [FahrzeugSprung(1, _h(2), 1e-10)])
    assert block.stunden == ()
    assert block.pv_kwh is None
    assert block.beginn == _h(2)


def test_rf80_blockstunde_die_auf_null_rundet_liefert_keinen_pv_anteil():
    """``round(take, 6)`` = 0 ⇒ Basis ≤ EPS ⇒ kein PV-Anteil, obwohl die Stunde einen hat."""
    (block,) = bilde_ladebloecke([WallboxStunde(_h(2), 1e-8, pv_anteil=0.5)], [FahrzeugSprung(1, _h(2), 1e-8)])
    assert len(block.stunden) == 1 and block.stunden[0].kwh == 0.0
    assert block.pv_kwh is None


def test_rf80_toleranz_null_komma_null_fuenf_in_frueheren_stunden():
    """Frühere Stunden geben höchstens Bedarf + 0,05 her; die eigene Sprungstunde höchstens den Bedarf."""
    (block,) = bilde_ladebloecke([WallboxStunde(_h(2), 5.0), WallboxStunde(_h(5), 1.0)], [FahrzeugSprung(1, _h(5), 3.0)])
    assert [(s.beginn, s.kwh) for s in block.stunden] == [(_h(2), 2.05), (_h(5), 1.0)]


# ── RF-77 _fetch_solcast_ha_auto ──────────────────────────────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, status, payload, wirft=False):
        self._r = _Resp(status, payload)
        self._wirft = wirft

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, *_a, **_k):
        if self._wirft:
            raise ConnectionError("HA weg")
        return self._r


class _Ha:
    is_available = True
    api_url = "http://ha.local/api"
    token = "t"


def _stelle_solcast(monkeypatch, *, entities, states, status=200, cache=None, wirft=False):
    import httpx

    from backend.services import solcast_service

    async def fake_resolve():
        return dict(entities)

    gesetzt = []
    monkeypatch.setattr(solcast_service, "_resolve_solcast_entities", fake_resolve)
    monkeypatch.setattr(solcast_service, "_cache_get", lambda *_a, **_k: cache)
    monkeypatch.setattr(solcast_service, "_cache_set", lambda *a, **_k: gesetzt.append(a))
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: _Ha())
    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_kw: _Client(status, states, wirft))
    monkeypatch.setattr(solcast_service, "date", _FesterTag)
    return gesetzt


def _st(eid, value, detailed=None, **attrs):
    a = dict(attrs)
    if detailed is not None:
        a["detailedForecast"] = detailed
    return {"entity_id": eid, "state": value, "attributes": a}


def _bucket(dt, kw):
    return {"period_start": dt.isoformat(), "pv_estimate": kw, "pv_estimate10": kw / 2, "pv_estimate90": kw * 2}


@pytest.mark.asyncio
async def test_rf77_cache_treffer_kommt_ohne_ha_zurueck(monkeypatch):
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    _stelle_solcast(monkeypatch, entities={}, states=[], cache="GECACHT")
    assert await _fetch_solcast_ha_auto() == "GECACHT"


@pytest.mark.asyncio
@pytest.mark.parametrize("entities", [{}, {"morgen": "sensor.m"}])
async def test_rf77_ohne_heute_entity_kein_ergebnis(monkeypatch, entities):
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    _stelle_solcast(monkeypatch, entities=entities, states=[_st("sensor.m", "8.0")])
    assert await _fetch_solcast_ha_auto() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fall", ["status_500", "unknown", "keine_zahl", "abruf_wirft", "fremd"])
async def test_rf77_heute_state_fehlt_kein_ergebnis(monkeypatch, fall):
    """Status ≠ 200, State «unknown» oder keine Zahl, Abruf-Ausnahme (still) und fremde Entities lassen den
    Heute-Sensor leer ⇒ None."""
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    states = [_st("sensor.h", {"unknown": "unknown", "keine_zahl": "abc"}.get(fall, "20.0"))]
    if fall == "fremd":
        states = [_st("sensor.fremd", "20.0")]
    _stelle_solcast(monkeypatch, entities={"heute": "sensor.h"}, states=states,
                    status=500 if fall == "status_500" else 200, wirft=fall == "abruf_wirft")
    assert await _fetch_solcast_ha_auto() is None


@pytest.mark.asyncio
async def test_rf77_nullrueckfall_naive_zeit_tagesrand_und_kaputter_eintrag(monkeypatch):
    """estimate10/90 fehlt ⇒ 0; naive ``period_start`` = Berlin; 23:30 gehört zu Slot 0 des Folgetags (fällt beim
    Heute-Sensor weg); unlesbarer Eintrag wird übersprungen; × 0,5 je 30-Min-Bucket."""
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    heute = HEUTE
    mittag = datetime.combine(heute, datetime.min.time()) + timedelta(hours=12)
    detailed = [
        {"period_start": mittag.isoformat(), "pv_estimate": 3.0},              # naiv, ohne p10/p90
        {"period_start": "kaputt", "pv_estimate": 9.0},
        _bucket(datetime.combine(heute, datetime.min.time(), tzinfo=TZ) + timedelta(hours=23, minutes=30), 5.0),
    ]
    gesetzt = _stelle_solcast(monkeypatch, entities={"heute": "sensor.h"}, states=[_st("sensor.h", "20.04", detailed)])
    r = await _fetch_solcast_ha_auto()
    assert r is not None
    assert (r.daily_kwh, r.daily_p10_kwh, r.daily_p90_kwh) == (20.0, 0.0, 0.0)
    assert r.hourly_kw[13] == 1.5 and r.hourly_p10_kw[13] == 0.0
    assert sum(r.hourly_kw) == 1.5, "23:30 gehört zum Folgetag, «kaputt» fällt weg"
    assert r.tomorrow_kwh == 0 and isinstance(r.tomorrow_kwh, int)
    assert len(gesetzt) == 1 and gesetzt[0][2] == 300


@pytest.mark.asyncio
async def test_rf77_profil_ohne_werte_wird_nicht_eingetragen(monkeypatch):
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    t = datetime.combine(HEUTE, datetime.min.time(), tzinfo=TZ) + timedelta(hours=12)
    _stelle_solcast(monkeypatch, entities={"heute": "sensor.h"}, states=[_st("sensor.h", "1.0", [_bucket(t, 0.0)])])
    r = await _fetch_solcast_ha_auto()
    assert r is not None and r.stundenprofile == {}
    assert r.hourly_kw == [0.0] * 24


@pytest.mark.asyncio
async def test_rf77_morgen_ist_der_tag_heute_plus_eins(monkeypatch):
    """N-776: «Morgen» ist der Tag ``heute + 1``. Ist der Morgen-Sensor nicht lesbar, ist ``tomorrow_kwh`` 0 — nicht
    der nächste gelesene Tag (Tag 3, so bis N-776 über `tage_voraus[1]`). Heute bleibt Heute; Tag 3 bleibt in der Liste."""
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    _stelle_solcast(monkeypatch, entities={"heute": "sensor.h", "morgen": "sensor.m", "tag_3": "sensor.d3"},
                    states=[_st("sensor.h", "20.0", estimate10=9), _st("sensor.m", "unavailable"),
                            _st("sensor.d3", "7.0", estimate10=3)])
    r = await _fetch_solcast_ha_auto()
    assert [t["kwh"] for t in r.tage_voraus] == [20.0, 7.0]
    assert r.tage_voraus[1]["datum"] == (HEUTE + timedelta(days=2)).isoformat()
    assert (r.tomorrow_kwh, r.tomorrow_p10_kwh, r.tomorrow_p90_kwh) == (0, 0, 0)
    assert (r.daily_kwh, r.daily_p10_kwh) == (20.0, 9.0)


@pytest.mark.asyncio
async def test_rf77_morgen_lesbar_ist_morgen(monkeypatch):
    """Gegenprobe N-776: lesbarer Morgen-Sensor ⇒ sein Wert, auch wenn Tag 3 fehlt."""
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    _stelle_solcast(monkeypatch, entities={"heute": "sensor.h", "morgen": "sensor.m", "tag_3": "sensor.d3"},
                    states=[_st("sensor.h", "20.0"), _st("sensor.m", "11.0", estimate10=4), _st("sensor.d3", "unavailable")])
    r = await _fetch_solcast_ha_auto()
    assert (r.tomorrow_kwh, r.tomorrow_p10_kwh) == (11.0, 4.0)


@pytest.mark.asyncio
async def test_rf77_ausnahme_im_rumpf_liefert_none_mit_warnung(monkeypatch, caplog):
    """``period_start`` None wirft ``AttributeError`` (nicht im inneren ``except``) ⇒ äußere Warnung, None."""
    from backend.services.solcast_service import _fetch_solcast_ha_auto

    _stelle_solcast(monkeypatch, entities={"heute": "sensor.h"},
                    states=[_st("sensor.h", "20.0", [{"period_start": None, "pv_estimate": 1.0}])])
    with caplog.at_level("WARNING"):
        assert await _fetch_solcast_ha_auto() is None
    assert any("Solcast HA Fehler: AttributeError" in r.getMessage() for r in caplog.records)


# ── RF-78 loese_integration_auf ───────────────────────────────────────────────────────────────────────────────────────


def _stelle_aufl(monkeypatch, menge, registry):
    from backend.services import ha_integration_aufloeser as aufl

    async def _m(_domain):
        return menge

    async def _r():
        return registry

    monkeypatch.setattr(aufl, "integration_entity_ids", _m)
    monkeypatch.setattr(aufl, "entity_registry_unique_ids", _r)
    return aufl


@pytest.mark.asyncio
async def test_rf78_leere_unique_id_faellt_auf_die_naechste_stufe(monkeypatch):
    aufl = _stelle_aufl(monkeypatch, {"sensor.a"}, {"sensor.a": ""})
    e = await aufl.loese_integration_auf(
        domain="x", praefixe=[], unique_kerne={"forecast_today": "heute"}, namens_kerne={"prognose_heute": "heute"},
        muster=[], states=[{"entity_id": "sensor.a", "attributes": {"friendly_name": "Prognose heute"}}],
    )
    assert e.treffer["heute"].stufe == "name"
    assert (e.rolle_quelle, e.menge_quelle, e.anzahl_entities) == ("name", "integration_entities", 1)


@pytest.mark.asyncio
async def test_rf78_stufen_reihenfolge_je_rolle(monkeypatch):
    """unique_id vor Name vor Muster — je Rolle; eine besetzte Rolle wird nicht überschrieben."""
    aufl = _stelle_aufl(monkeypatch, None, {"sensor.p_c": "id_forecast_today"})
    states = [{"entity_id": "sensor.p_a", "attributes": {"friendly_name": "Prognose heute"}},
              {"entity_id": "sensor.p_b_morgen", "attributes": {}},
              {"entity_id": "sensor.p_c", "attributes": {"friendly_name": "Prognose morgen"}}]
    e = await aufl.loese_integration_auf(
        domain="x", praefixe=["sensor.p_"], unique_kerne={"forecast_today": "heute"},
        namens_kerne={"prognose_heute": "heute", "prognose_morgen": "morgen"},
        muster=[("_morgen", "morgen"), ("_a", "heute")], states=states,
    )
    assert {r: (t.entity_id, t.stufe) for r, t in e.treffer.items()} == {
        "heute": ("sensor.p_c", "unique_id"), "morgen": ("sensor.p_c", "name")}
    assert (e.rolle_quelle, e.menge_quelle) == ("unique_id", "praefix")


@pytest.mark.asyncio
async def test_rf78_alte_ha_ohne_registry_und_ohne_namenskerne_greift_das_muster(monkeypatch):
    """Registry ``None`` (alte HA) und leere ``namens_kerne`` ⇒ Stufe 1 und 2 greifen nicht; das Muster trägt."""
    aufl = _stelle_aufl(monkeypatch, {"sensor.x_heute"}, None)
    e = await aufl.loese_integration_auf(
        domain="x", praefixe=[], unique_kerne={"forecast_today": "heute"}, namens_kerne={},
        muster=[("_heute", "heute")], states=[{"entity_id": "sensor.x_heute", "attributes": {"friendly_name": "Prognose heute"}}],
    )
    assert {r: t.stufe for r, t in e.treffer.items()} == {"heute": "muster"}
    assert e.rolle_quelle == "muster"


# ── RF-79 baue_investitions_serien ────────────────────────────────────────────────────────────────────────────────────


def _inv(typ, **k):
    return SimpleNamespace(typ=typ, parameter=k.get("parameter", {}), parent_investition_id=k.get("parent"))


def test_rf79_ohne_leistung_und_unbekannter_typ_keine_serie():
    serien, entities = baue_investitions_serien(
        {"1": {"soc": "sensor.soc"}, "2": {"leistung_w": "sensor.x"}, "3": {"leistung_w": "sensor.pv"}},
        {"1": _inv("speicher"), "2": _inv("unbekannt"), "3": _inv("pv-module")},
    )
    assert [s.key for s in serien] == ["pv_3"]
    assert entities == {"pv_3": ["sensor.pv"]}


def test_rf79_wallbox_nicht_in_betrieb_verdraengt_das_auto_nicht():
    class _Wb(SimpleNamespace):
        def ist_aktiv_an(self, _tag):
            return False

    serien, _ = baue_investitions_serien(
        {"1": {"leistung_w": "sensor.ea"}, "2": {"leistung_w": "sensor.wb"}},
        {"1": _inv("e-auto"), "2": _Wb(typ="wallbox", parameter={}, parent_investition_id=None)},
        tag=date(2026, 8, 6),
    )
    assert [s.key for s in serien] == ["wallbox_2", "eauto_1"]


def test_rf79_reihenfolge_wallbox_vor_eauto_vor_rest_stabil():
    serien, _ = baue_investitions_serien(
        {k: {"leistung_w": f"sensor.{k}"} for k in ("1", "2", "3", "4")},
        {"1": _inv("pv-module"), "2": _inv("e-auto"), "3": _inv("speicher"), "4": _inv("wallbox")},
    )
    assert [s.key for s in serien] == ["wallbox_4", "pv_1", "batterie_3"]
