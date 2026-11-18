"""Sensorwechsel mit Grund, Sitzung 1 — Tabelle ``zuordnung_wechsel`` (B-1), wirksame Quelle, Verzeichnen, Überführung, Räumen.

**Verzeichnet** wird jede Änderung der **wirksamen** Quelle eines Zählerschlüssels (``services/zuordnung_wechsel/quelle.py``:
HA-Entität · MQTT-Schlüssel mit Topic, Pfad, Faktor, Offset der Gateway-Zeile · «keine»), mit ``herkunft = wechsel`` — in
jedem Schreibweg: Feld-Route (W1), Preset (W2), Energie-Vorschläge (W3), Gateway-Zeile ändern (W4), anlegen (W5), löschen
(W6). Nicht verzeichnet: die erste Zuordnung (keine eigenen Werte, keine vorige Quelle), ein erneutes Speichern derselben
Quelle, die klassische Zuordnung, die ``quellen`` nur nachträgt. **Seit Sitzung 3b** fragt eedc bei einer Änderung mit eigenen
Werten nach dem Grund (``test_sensorwechsel_s3b_abfrage.py``): die Feld-Route und das Preset tragen hier ``fortsetzung`` (die
Zeile führt ihn), Energie-Vorschläge und Gateway-``PUT`` überspringen, Gateway-Zeile anlegen/löschen lehnt ab.

**Überführung** aus dem Aktivitäts-Protokoll (``herkunft = altbestand``): nur sicher wirksame Änderungen mit eigenen Werten;
zweimal = einmal. **Räumen**: Gerät, Innengerät, Anlage (``ON DELETE CASCADE``).

Schwesterdateien: test_sensorwechsel_s1_zeitpunkt.py (B-0 an den Schreibern), test_n556_datenquellen_protokoll.py (Protokoll
derselben Schreibwege), test_p433_2b_k4_fahrt_pvanteil.py (Preset), test_diagnose_paket_register.py (W-7).
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from backend.api.routes.datenquellen import (
    EnergyUebernahmeRequest,
    QuelleSetRequest,
    set_feld_quelle,
    uebernehme_energy_vorschlaege,
)
from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel.quelle import wirksame_quellen

NETZ = "basis_energy_netzbezug_kwh"
NETZ_KEY = "basis:netzbezug"


async def _anlage(db, mapping: dict | None = None, *, werte: tuple[str, ...] = (NETZ_KEY,)) -> Anlage:
    a = Anlage(anlagenname="Wechsel", leistung_kwp=10.0, sensor_mapping=mapping or {})
    db.add(a)
    await db.flush()
    if (await db.execute(select(Investition.id).where(Investition.id == 2))).scalar_one_or_none() is None:
        db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 1, 1)))
    for key in werte:   # eigene Werte vor der Änderung
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=datetime(2026, 9, 1, 12), wert_kwh=10.0,
                              quelle="ha_statistics"))
    await db.flush()
    return a


async def _zeilen(db, anlage_id: int) -> list[ZuordnungWechsel]:
    return list((await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == anlage_id)
                                  .order_by(ZuordnungWechsel.id))).scalars().all())


async def _quelle(db, aid, fid=NETZ, **kw):
    return await set_feld_quelle(aid, fid, QuelleSetRequest(**kw), db)


# ═══ Wirksame Quelle (rein) ════════════════════════════════════════════════════════════════════════════════════════════

def _gw(id, ziel, topic="t/a", faktor=1.0, aktiv=True, **kw):
    return MqttGatewayMapping(id=id, anlage_id=1, quell_topic=topic, ziel_key=ziel, payload_typ=kw.get("payload_typ", "plain"),
                              json_pfad=kw.get("json_pfad"), array_index=None, faktor=faktor, offset=0.0, aktiv=aktiv)


def test_wirksame_quelle_je_weg():
    klassisch = {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.alt"}}}
    assert wirksame_quellen(klassisch)[NETZ_KEY] == {"art": "ha", "entity_id": "sensor.alt"}
    # `quellen` ersetzt die klassische Zuordnung (Read-Through des Schreibers)
    mit = {**klassisch, "quellen": {NETZ: {"quelle": "ha_app", "entity_id": "sensor.neu"}}}
    assert wirksame_quellen(mit)[NETZ_KEY] == {"art": "ha", "entity_id": "sensor.neu"}
    assert wirksame_quellen({"quellen": {NETZ: {"quelle": "keine"}}})[NETZ_KEY] == {"art": "keine"}
    # Gateway über mapping_id — und eine aktive Zeile wirkt auch ohne `quellen`-Eintrag (W5)
    gw = {"quellen": {"inv_energy_2_ladung_kwh": {"quelle": "mqtt_gateway", "mapping_id": 5}}}
    q = wirksame_quellen(gw, [_gw(5, "energy/inv/2_WB/ladung_kwh", topic="evcc/lp/1/total", faktor=0.001)])
    assert q["inv:2:ladung_kwh"] == {"art": "mqtt", "mqtt_key": "inv/2/ladung_kwh", "topic": "evcc/lp/1/total",
                                     "payload_typ": "plain", "json_pfad": None, "array_index": None, "faktor": 0.001,
                                     "offset": 0.0}
    assert wirksame_quellen({}, [_gw(6, "energy/inv/2/ladung_kwh")])["inv:2:ladung_kwh"]["topic"] == "t/a"
    assert "inv:2:ladung_kwh" not in wirksame_quellen({}, [_gw(6, "energy/inv/2/ladung_kwh", aktiv=False)])
    assert "inv:2:leistung_w" not in wirksame_quellen({}, [_gw(7, "live/inv/2/leistung_w")])   # kein Zählerschlüssel


# ═══ W1 Feld-Route ═════════════════════════════════════════════════════════════════════════════════════════════════════

async def test_w1_ha_wechsel_wird_verzeichnet_mit_grund(db):
    a = await _anlage(db)
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.a", grund="fortsetzung")   # eigene Werte (MQTT) ⇒ Grund
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.a")          # dieselbe Wahl erneut: keine Änderung
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.b", grund="fortsetzung")
    z = await _zeilen(db, a.id)
    assert [(w.sensor_key, w.vorher, w.nachher, w.grund, w.herkunft) for w in z] == [
        (NETZ_KEY, {"art": "mqtt", "mqtt_key": "netzbezug_kwh", "topic": None}, {"art": "ha", "entity_id": "sensor.a"},
         "fortsetzung", "wechsel"),
        (NETZ_KEY, {"art": "ha", "entity_id": "sensor.a"}, {"art": "ha", "entity_id": "sensor.b"}, "fortsetzung", "wechsel")]
    assert z[1].ab_ts == z[1].erklaert_ts.replace(minute=0, second=0) + timedelta(
        hours=0 if z[1].erklaert_ts.minute == z[1].erklaert_ts.second == 0 else 1)


async def test_w1_ohne_eigene_werte_wird_nichts_verzeichnet(db):
    """Bauplan §8 Nr. 17: ohne eigene Werte ist eine Änderung kein Wechsel — erste Zuordnung, A → B und → «Keine»;
    Gegenprobe im selben Test: sobald der Schlüssel Werte hat, wird verzeichnet."""
    a = await _anlage(db, werte=())
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.a")
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.b")          # A → B ohne Werte
    await _quelle(db, a.id, quelle="keine")                                  # → «Keine» ohne Werte
    assert await _zeilen(db, a.id) == []
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.b")
    db.add(SensorSnapshot(anlage_id=a.id, sensor_key=NETZ_KEY, zeitpunkt=datetime(2026, 9, 1, 12), wert_kwh=1.0,
                          quelle="ha_statistics"))
    await db.flush()
    await _quelle(db, a.id, quelle="keine")                                  # jetzt mit Werten
    assert [(w.vorher, w.nachher) for w in await _zeilen(db, a.id)] == [({"art": "ha", "entity_id": "sensor.b"},
                                                                         {"art": "keine"})]


async def test_w1_erstwahl_ohne_werte_korrigiert_resnap_liest_die_heutige(db):
    """Nachmessung §8 (Regression gegen HEAD): A → B ohne eigene Werte, danach «Tag neu aggregieren» eines alten Tags liest B
    (wie HEAD), nicht die verworfene Erstwahl A."""
    from unittest.mock import patch

    from backend.services.snapshot.reaggregator import resnap_anlage_range
    from backend.tests import ha_lts_helfer

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}}, werte=())
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.b")
    assert await _zeilen(db, a.id) == []
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    t0 = datetime(2026, 9, 20, 10)
    for eid, wert in (("sensor.a", 1.0), ("sensor.b", 2.0)):
        mid = ha_lts_helfer.sensor(svc, eid, "kWh", has_sum=True)
        ha_lts_helfer.zeile(svc, mid, t0 - timedelta(hours=1), state=wert, sum_wert=wert)
    with patch("backend.services.snapshot.writer.get_ha_statistics_service", lambda: svc):
        await resnap_anlage_range(db, a, von=t0, bis=t0 + timedelta(hours=1), include_5min=False)
    wert = (await db.execute(select(SensorSnapshot.wert_kwh).where(SensorSnapshot.anlage_id == a.id))).scalar_one()
    assert wert == 2.0


async def test_w1_klassische_zuordnung_ohne_quellen_eintrag(db):
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.a")          # gleiche Entität ⇒ keine Zeile
    assert await _zeilen(db, a.id) == []
    a2 = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    await _quelle(db, a2.id, quelle="ha_app", entity_id="sensor.b", grund="fortsetzung")   # andere ⇒ vorher = klassisch
    assert [(w.vorher, w.nachher) for w in await _zeilen(db, a2.id)] == [
        ({"art": "ha", "entity_id": "sensor.a"}, {"art": "ha", "entity_id": "sensor.b"})]


async def test_w1_gateway_topic_wechsel_derselben_zeile_und_faktor(db):
    a = await _anlage(db, werte=("inv:2:ladung_kwh",))
    fid = "inv_energy_2_ladung_kwh"
    await _quelle(db, a.id, fid, quelle="mqtt_gateway", quell_topic="evcc/a", grund="fortsetzung")
    await _quelle(db, a.id, fid, quelle="mqtt_gateway", quell_topic="evcc/b", grund="fortsetzung")
    await _quelle(db, a.id, fid, quelle="mqtt_gateway", quell_topic="evcc/b", faktor=0.001, grund="fortsetzung")
    z = await _zeilen(db, a.id)
    assert [(w.vorher.get("topic"), w.nachher.get("topic"), w.nachher.get("faktor")) for w in z] == [
        (None, "evcc/a", 1.0), ("evcc/a", "evcc/b", 1.0), ("evcc/b", "evcc/b", 0.001)]
    # Der alte Maßstab (``ist_echte_aenderung``, verglich den ``quellen``-Eintrag ohne ``mapping_id``) sah im Topic-Wechsel
    # derselben Zeile nichts; er ist mit dem Hinweis-Block in Sitzung 3b entfallen.


# ═══ W2 Preset · W3 Energie-Vorschläge · W4–W6 Gateway-Zeile ════════════════════════════════════════════════════════════

async def test_w2_preset_verzeichnet_den_zaehler(db):
    from backend.api.routes.mqtt_presets import ApplyPresetRequest, apply_preset

    a = await _anlage(db, {"investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}}},
                           "quellen": {"inv_energy_2_ladung_kwh": {"quelle": "ha_app", "entity_id": "sensor.wb"}}},
                      werte=("inv:2:ladung_kwh",))
    await apply_preset(ApplyPresetRequest(preset_id="evcc_ladepunkt", anlage_id=a.id, variablen={}, investition_id=2,
                                          gruende={"inv:2:ladung_kwh": {"grund": "fortsetzung"}}), db)
    z = await _zeilen(db, a.id)
    assert [(w.sensor_key, w.vorher, w.nachher["topic"]) for w in z] == [
        ("inv:2:ladung_kwh", {"art": "ha", "entity_id": "sensor.wb"}, "evcc/loadpoints/1/chargeTotalImport")]


async def test_w3_energie_vorschlaege(db, monkeypatch):
    """Seit Sitzung 3b überspringt die Übernahme ein Feld mit eigenen Werten, dessen Quelle wechseln würde (sie nennt es);
    ein Feld ohne eigene Werte übernimmt sie (nichts verzeichnet, §8 Nr. 17)."""
    from backend.api.routes import datenquellen as dq

    async def ha(_db):
        return "http://ha", "tok", "ha_app"
    monkeypatch.setattr(dq, "_resolve_ha", ha)
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.alt"}}})
    r = await uebernehme_energy_vorschlaege(
        a.id, EnergyUebernahmeRequest(basis={"netzbezug": "sensor.neu", "einspeisung": "sensor.e"}), db)
    assert await _zeilen(db, a.id) == []
    assert r["felder"] == ["basis_energy_einspeisung_kwh"]
    assert [u["field_id"] for u in r["uebersprungen"]] == [NETZ]
    assert wirksame_quellen(a.sensor_mapping)[NETZ_KEY] == {"art": "ha", "entity_id": "sensor.alt"}


async def test_w4_w5_w6_gateway_zeile_anlegen_aendern_loeschen(db):
    """Ohne eigene Werte verzeichnet keine der drei Routen etwas (§8 Nr. 17). Mit eigenen Werten (Sitzung 3b): ändern
    überspringt und nennt, anlegen und löschen lehnen ab (422); eine Änderung ohne Wirkung geht durch."""
    import pytest
    from fastapi import HTTPException

    from backend.api.routes.mqtt_gateway import MappingCreate, MappingUpdate, create_mapping, delete_mapping, update_mapping

    a = await _anlage(db, werte=())
    neu = await create_mapping(MappingCreate(anlage_id=a.id, quell_topic="x/1", ziel_key="energy/inv/2/ladung_kwh"), db)
    mid = neu["mapping"]["id"]
    assert await _zeilen(db, a.id) == []
    db.add(SensorSnapshot(anlage_id=a.id, sensor_key="inv:2:ladung_kwh", zeitpunkt=datetime(2026, 9, 1, 12), wert_kwh=1.0,
                          quelle="mqtt"))
    await db.flush()
    r = await update_mapping(mid, MappingUpdate(quell_topic="x/2"), db)
    assert r["uebersprungen"] == ["inv:2:ladung_kwh"] and r["mapping"]["quell_topic"] == "x/1"
    r = await update_mapping(mid, MappingUpdate(beschreibung="nur Text"), db)   # ohne Wirkung ⇒ geht durch, keine Zeile
    assert r["uebersprungen"] == [] and r["mapping"]["beschreibung"] == "nur Text"
    with pytest.raises(HTTPException) as e:
        await delete_mapping(mid, db)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        await create_mapping(MappingCreate(anlage_id=a.id, quell_topic="x/3", ziel_key="energy/inv/2/ladung_kwh"), db)
    assert e.value.status_code == 422
    assert await _zeilen(db, a.id) == []


# ═══ Überführung aus dem Protokoll ═════════════════════════════════════════════════════════════════════════════════════

async def _protokoll(db, aid, ts, field_id, vorher, nachher):
    db.add(ActivityLog(timestamp=ts, kategorie="sensor_mapping", aktion="Datenquelle zugeordnet", anlage_id=aid,
                       details_json={"field_id": field_id, "vorher": vorher, "nachher": nachher}))
    await db.flush()


async def test_ueberfuehrung_nur_sichere_wirksame_aenderungen_zweimal_gleich_einmal(db):
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre

    a = await _anlage(db, werte=("inv:2:ladung_kwh", NETZ_KEY))
    ha = lambda e: {"quelle": "ha_app", "entity_id": e}                   # noqa: E731
    t = datetime(2026, 10, 18, 10, 47, 42, 123456)
    await _protokoll(db, a.id, t, "inv_energy_2_ladung_kwh", ha("sensor.evcc"), ha("sensor.wb"))      # überführt
    # null → X mit Kanal-Quelle X: wirksam unverändert (klassische Zuordnung, Messblatt M-H)
    k = Kanal(anlage_id=a.id, key=NETZ_KEY, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(datetime(2026, 3, 27).timestamp()), familie="spiegel",
                       statistic_id="sensor.x", offset=0.0))
    db.add(KanalStatistik(kanal_id=k.id, start_ts=int(datetime(2026, 3, 27, 5).timestamp()), sum=1.0, familie="spiegel"))
    await _protokoll(db, a.id, datetime(2026, 9, 27, 10, 33, 31), NETZ, None, ha("sensor.x"))
    # «keine» → HA ohne eigene Werte davor: erste Zuordnung
    await _protokoll(db, a.id, datetime(2026, 9, 27, 10, 32, 13), "inv_energy_2_verbrauch_kwh", {"quelle": "keine"},
                     ha("sensor.fahrt"))
    # null ohne Kanal und ohne Reihe: nicht entscheidbar
    await _protokoll(db, a.id, datetime(2026, 9, 28, 9), "basis_energy_einspeisung_kwh", None, ha("sensor.e"))
    # Vorzeichen und ein gelöschtes Gerät
    await _protokoll(db, a.id, datetime(2026, 9, 29, 9), NETZ, False, True)
    await _protokoll(db, a.id, datetime(2026, 9, 30, 9), "inv_energy_9_ladung_kwh", ha("s.1"), ha("s.2"))
    erste = await ueberfuehre(db)
    zweite = await ueberfuehre(db)
    z = await _zeilen(db, a.id)
    assert [(w.sensor_key, w.erklaert_ts, w.ab_ts, w.herkunft, w.grund) for w in z] == [
        ("inv:2:ladung_kwh", datetime(2026, 10, 18, 10, 47, 42), datetime(2026, 10, 18, 11), "altbestand", None)]
    assert dict(erste) == {"ueberfuehrt": 1, "wirksam_unveraendert": 1, "ohne_eigene_werte": 1, "vorher_unbekannt": 1,
                           "geraet_geloescht": 1}
    assert dict(zweite) == {"schon_ueberfuehrt": 1, "wirksam_unveraendert": 1, "ohne_eigene_werte": 1,
                            "vorher_unbekannt": 1, "geraet_geloescht": 1}


async def test_ueberfuehrung_als_start_migration_einmal(tmp_path, monkeypatch):
    """Der Startpfad (`init_db` → `_run_data_migrations`) legt die Tabelle an und überführt genau einmal."""
    import backend.core.database as dbmod
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(dbmod.Base.metadata.create_all)
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with macher() as s:
        a = await _anlage(s, werte=("inv:2:ladung_kwh",))
        await _protokoll(s, a.id, datetime(2026, 10, 18, 10, 47, 42), "inv_energy_2_ladung_kwh",
                         {"quelle": "ha_app", "entity_id": "s.a"}, {"quelle": "ha_app", "entity_id": "s.b"})
        await s.commit()
    monkeypatch.setattr(dbmod, "async_session_maker", macher)
    for _ in range(2):
        await dbmod._run_data_migrations()
    async with macher() as s:
        assert len(await _zeilen(s, a.id)) == 1
    await engine.dispose()


# ═══ Räumen ════════════════════════════════════════════════════════════════════════════════════════════════════════════

async def test_loeschen_eines_geraets_raeumt_seine_zeilen(db):
    from backend.api.routes.investitionen.crud import delete_investition

    a = await _anlage(db)
    for key in ("inv:2:ladung_kwh", "inv:2:ladung_pv_kwh", NETZ_KEY):
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=datetime(2026, 10, 1), ab_ts=datetime(2026, 10, 1),
                                herkunft="wechsel"))
    await db.flush()
    await delete_investition(2, db)
    assert [w.sensor_key for w in await _zeilen(db, a.id)] == [NETZ_KEY]


async def test_entferntes_innengeraet_raeumt_nur_seine_zeilen(db):
    from backend.api.routes.investitionen.crud import _raeume_innengeraete_zuordnungen

    a = Anlage(anlagenname="WP", leistung_kwp=5.0, sensor_mapping={"investitionen": {"3": {"felder": {}}}})
    db.add(a)
    await db.flush()
    wp = Investition(id=3, anlage_id=a.id, typ="waermepumpe", bezeichnung="Split",
                     parameter={"innengeraete": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]})
    db.add(wp)
    for key in ("inv:3:betriebsart_strom_kuehlen_kwh-1", "inv:3:betriebsart_strom_kuehlen_kwh-2", "inv:3:stromverbrauch_kwh"):
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=datetime(2026, 10, 1), ab_ts=datetime(2026, 10, 1),
                                herkunft="wechsel"))
    await db.flush()
    await _raeume_innengeraete_zuordnungen(db, wp, neu_parameter={"innengeraete": [{"id": 1, "name": "A"}]})
    assert sorted(w.sensor_key for w in await _zeilen(db, a.id)) == [
        "inv:3:betriebsart_strom_kuehlen_kwh-1", "inv:3:stromverbrauch_kwh"]


def test_loeschen_der_anlage_raeumt_ueber_cascade():
    """``ON DELETE CASCADE`` mit ``PRAGMA foreign_keys=ON`` (wie ``core/database.py::set_sqlite_pragma``)."""
    from sqlalchemy import create_engine

    from backend.core.database import Base

    pfad = Path(tempfile.mkdtemp()) / "c.db"
    Base.metadata.create_all(create_engine(f"sqlite:///{pfad}"))
    con = sqlite3.connect(pfad)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("INSERT INTO anlagen (id, anlagenname, leistung_kwp, created_at, updated_at) "
                "VALUES (1, 'x', 1.0, '2026-01-01', '2026-01-01')")
    con.execute("INSERT INTO zuordnung_wechsel (anlage_id, sensor_key, erklaert_ts, ab_ts, herkunft) "
                "VALUES (1, 'basis:netzbezug', '2026-10-01 00:00:00', '2026-10-01 00:00:00', 'wechsel')")
    con.execute("DELETE FROM anlagen WHERE id = 1")
    assert con.execute("SELECT COUNT(*) FROM zuordnung_wechsel").fetchone()[0] == 0
    con.close()


# ═══ Korrekturrunde 17.11. (Nachmessung §2, §9; Bauplan §7 Nr. 15, §8 Nr. 21) ═════════════════════════════════════════

async def test_merkliste_der_sitzung_sieht_einen_eben_verzeichneten_wechsel(db, monkeypatch):
    """``merke_neu``: ein Lauf, der die Wechsel schon geladen hat, sieht einen Wechsel derselben Sitzung — Gegenprobe ohne
    ``merke_neu``: die Merkliste bleibt alt, bis ``vergiss``."""
    from backend.services.zuordnung_wechsel import verzeichnen
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel, vergiss

    a = await _anlage(db, werte=(NETZ_KEY, "basis:einspeisung"))
    assert await lade_wechsel(db, a.id) == {}
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.a", grund="fortsetzung")
    assert list(await lade_wechsel(db, a.id)) == [NETZ_KEY]
    monkeypatch.setattr(verzeichnen, "merke_neu", lambda *_a: None)
    await _quelle(db, a.id, "basis_energy_einspeisung_kwh", quelle="ha_app", entity_id="sensor.e", grund="fortsetzung")
    assert list(await lade_wechsel(db, a.id)) == [NETZ_KEY]                        # Gegenprobe: ohne merke_neu alt
    vergiss(db, a.id)
    assert sorted(await lade_wechsel(db, a.id)) == ["basis:einspeisung", NETZ_KEY]


async def test_raeumen_verwirft_die_merkliste(db, monkeypatch):
    """Nach dem Räumen eines Geräts sieht ein Lauf derselben Sitzung dessen Wechsel nicht mehr (``vergiss``); Gegenprobe:
    ohne ``vergiss`` bliebe der Wechsel der gelöschten Investition in der Merkliste."""
    from backend.api.routes.investitionen.crud import delete_investition
    from backend.services.zuordnung_wechsel import raeumen
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    a = await _anlage(db)
    db.add(Investition(id=3, anlage_id=a.id, typ="wallbox", bezeichnung="WB2", anschaffungsdatum=date(2024, 1, 1)))
    for key in ("inv:2:ladung_kwh", "inv:3:ladung_kwh"):
        db.add(ZuordnungWechsel(anlage_id=a.id, sensor_key=key, erklaert_ts=datetime(2026, 10, 1), ab_ts=datetime(2026, 10, 1),
                                herkunft="wechsel"))
    await db.flush()
    assert sorted(await lade_wechsel(db, a.id)) == ["inv:2:ladung_kwh", "inv:3:ladung_kwh"]
    with monkeypatch.context() as m:
        m.setattr(raeumen, "vergiss", lambda *_a: None)
        await delete_investition(3, db)
        assert "inv:3:ladung_kwh" in await lade_wechsel(db, a.id)                     # Gegenprobe: veraltet
    await delete_investition(2, db)
    assert await lade_wechsel(db, a.id) == {}


async def test_ueberfuehrung_leeres_vorher_nimmt_die_kanal_quelle_vor_der_stunde(db):
    """§8 Nr. 21 (Nachmessung §9): neue Kanal-Quelle ab 10:00, Eintrag 10:47 mit leerem ``vorher`` ⇒ überführt, ``vorher`` =
    die Quelle davor. Gegenprobe im selben Test: ohne Quelle davor ⇒ nicht entscheidbar über den Kanal."""
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre

    a = await _anlage(db, werte=(NETZ_KEY, "basis:einspeisung"))
    for key, alt in ((NETZ_KEY, "sensor.alt"), ("basis:einspeisung", None)):
        k = Kanal(anlage_id=a.id, key=key, einheit="kWh", art="sum")
        db.add(k)
        await db.flush()
        if alt:
            db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(datetime(2026, 3, 27).timestamp()), familie="spiegel",
                               statistic_id=alt, offset=0.0))
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(datetime(2026, 10, 18, 10).timestamp()), familie="spiegel",
                           statistic_id="sensor.neu", offset=-208.214))
    await db.flush()
    ha = {"quelle": "ha_app", "entity_id": "sensor.neu"}
    await _protokoll(db, a.id, datetime(2026, 10, 18, 10, 47, 42), NETZ, None, ha)
    await _protokoll(db, a.id, datetime(2026, 10, 18, 10, 47, 43), "basis_energy_einspeisung_kwh", None, ha)
    zaehlung = await ueberfuehre(db)
    assert [(w.sensor_key, w.vorher, w.nachher) for w in await _zeilen(db, a.id)] == [
        (NETZ_KEY, {"art": "ha", "entity_id": "sensor.alt"}, {"art": "ha", "entity_id": "sensor.neu"})]
    # Einspeisung: keine Kanal-Quelle davor ⇒ Rückfall auf die Reihe (Art «ha» ohne Entität) ⇒ nicht entscheidbar
    assert dict(zaehlung) == {"ueberfuehrt": 1, "vorher_unbekannt": 1}


async def test_w7_w8_w9_verzeichnen_nicht(db):
    """§7 Nr. 15: GET ``/felder`` (Materialisierung, W7), ``/invert`` (W8), Stilllegung und Innengeräte (W9) verzeichnen
    nichts. Gegenprobe im selben Test: eine echte Änderung derselben Anlage wird verzeichnet."""
    from backend.api.routes.datenquellen import InvertSetRequest, get_datenquellen_felder, set_feld_invert
    from backend.api.routes.investitionen.crud import update_investition
    from backend.api.routes.investitionen.schemas import InvestitionUpdate

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}},
                           "investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor",
                                                                             "sensor_id": "sensor.wb"}}}}},
                      werte=(NETZ_KEY, "inv:2:ladung_kwh"))
    await get_datenquellen_felder(a.id, db)
    await db.refresh(a)
    assert NETZ in (a.sensor_mapping.get("quellen") or {})                           # W7 hat festgeschrieben …
    await set_feld_invert(a.id, NETZ, InvertSetRequest(invertieren=True), db)
    await update_investition(2, InvestitionUpdate(stilllegungsdatum=date(2026, 1, 1)), db)
    assert await _zeilen(db, a.id) == []                                              # … und nichts verzeichnet
    await _quelle(db, a.id, quelle="ha_app", entity_id="sensor.b", grund="fortsetzung")
    assert len(await _zeilen(db, a.id)) == 1                                          # Gegenprobe
