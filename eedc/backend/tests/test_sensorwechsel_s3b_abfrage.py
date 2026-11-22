"""Sensorwechsel mit Grund, Sitzung 3b — Abfrage in allen Wegen (Bauplan B-2, B-10, §7 Nr. 15, §8 Nr. 17, §9 Nr. 26, §10 Nr. 40).

**Die eine Prüf-Funktion** (``services/zuordnung_wechsel/abfrage.pruefe``): Maßstab ist die wirksame Quelle vor und nach der
Änderung (samt Gateway-Zeile); gefragt wird, wenn der Schlüssel eigene Werte hat, die neue Quelle Werte liefern kann und sie
sich von der letzten Quelle mit Werten unterscheidet. Proben aus dem Bauplan §4 zu B-2: Gateway-Topic A → B derselben Zeile ⇒
Rückfrage · Faktor 1 → 0,001 ⇒ Rückfrage · klassische Zuordnung ohne ``quellen``-Eintrag: gleiche Entität ⇒ keine, andere ⇒
Rückfrage; dazu A → «Keine» → B / → A, Schlüssel ohne eigene Werte, 422 je Route, Überspringen mit Nennung, die Prüf-Routen
schreiben nichts (Zeilenzählung je Tabelle), Vorschau = Lauf über den Dialog-Weg (mit Home Assistant), Fortsetzung trägt den
Grund. **Robustheit des Korrektur-Laufs** (§10 Nr. 40): eine Aufgabe je Lauf auch beim Fortsetzen, Füllen nach dem Commit
wiederholbar, keine zweite gleiche Korrektur-Zeile, Aufräumen, Diagnose-Paket, Fortschritts-Route, Spiegel hinter einer
verworfenen Quelle derselben Entität. **Einstieg «Zähler getauscht»** (§9 Nr. 26): HA mit Spiegel ⇒ Weg in Home Assistant,
nichts eingetragen; MQTT «Eigene Summe» ⇒ Fortsetzung mit Nachtrag.

Die Sprengsätze (bewusst falsche Bausteine, gegen die je Probe rot gemessen) stehen im Bericht der Sitzung
(``opus-berichte/SENSORWECHSEL-S3B-2026-11-17.md``); Gegenproben stehen im selben Test.

Schwesterdateien: test_sensorwechsel_s1_verzeichnen.py (Verzeichnen je Weg), test_sensorwechsel_s3_korrektur.py (der Dienst der
Korrektur), test_sensorwechsel_s3ak_proben.py (Proben 3a-K), test_sensorwechsel_s2_naht.py (Naht und Nachtrag bei MQTT).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import and_, func, select, text

from backend.api.routes.datenquellen import (
    EnergyUebernahmeRequest,
    QuelleSetRequest,
    pruefe_feld_quelle,
    set_feld_quelle,
    uebernehme_energy_vorschlaege,
)
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.settings import Settings
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import korrektur as kr
from backend.services.zuordnung_wechsel import korrektur_lauf as kl
from backend.tests import ha_lts_helfer
from backend.tests.test_kanal_nachfuellen import (  # noqa: F401 — Fixtures

    ZEIT,
    _ts,
    datei,
    ha,
)
from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage, _zeilen

GW = "inv_energy_2_ladung_kwh"
GW_KEY = "inv:2:ladung_kwh"
TABELLEN = ("anlagen", "zuordnung_wechsel", "mqtt_gateway_mappings", "sensor_snapshots", "mqtt_energy_snapshots",
            "kanal", "kanal_quelle", "kanal_statistik", "tages_zusammenfassung", "settings", "activity_log")


async def _zaehlung(db) -> dict[str, tuple]:
    """Je Tabelle die Zeilen (Inhalt) — die Prüf-Routen ändern keine."""
    out = {}
    for t in TABELLEN:
        out[t] = tuple(tuple(r) for r in (await db.execute(text(f"SELECT * FROM {t} ORDER BY 1"))).all())
    return out


async def _pruefe(db, aid, fid=NETZ, **kw) -> dict:
    return await pruefe_feld_quelle(aid, fid, QuelleSetRequest(**kw), db)


async def _setze(db, aid, fid=NETZ, **kw) -> dict:
    return await set_feld_quelle(aid, fid, QuelleSetRequest(**kw), db)


async def _ablehnung(coro) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        await coro
    return e.value


# ═══ Die Prüf-Funktion je Lage (Bauplan §4 zu B-2) ════════════════════════════════════════════════════════════════════

async def test_gateway_topic_derselben_zeile_und_faktor_fragen(db):
    a = await _anlage(db, werte=())
    aid = a.id
    await _setze(db, aid, GW, quelle="mqtt_gateway", quell_topic="evcc/a")       # erste Zuordnung: keine Werte
    db.add(SensorSnapshot(anlage_id=aid, sensor_key=GW_KEY, zeitpunkt=datetime(2026, 9, 1, 12), wert_kwh=5.0, quelle="mqtt"))
    await db.commit()
    assert (await _pruefe(db, aid, GW, quelle="mqtt_gateway", quell_topic="evcc/b"))["grund_erforderlich"] is True
    assert (await _pruefe(db, aid, GW, quelle="mqtt_gateway", quell_topic="evcc/a", faktor=0.001))["grund_erforderlich"]
    assert (await _pruefe(db, aid, GW, quelle="mqtt_gateway", quell_topic="evcc/a"))["grund_erforderlich"] is False
    e = await _ablehnung(_setze(db, aid, GW, quelle="mqtt_gateway", quell_topic="evcc/b"))
    assert e.status_code == 422 and "eigene Werte" in e.detail
    assert await _zeilen(db, aid) == []


async def test_klassische_zuordnung_gleiche_entitaet_keine_andere_frage(db):
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    gleich = await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.a")
    assert (gleich["grund_erforderlich"], gleich["verzeichnet"]) == (False, False)
    anders = await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b")
    assert anders["grund_erforderlich"] is True and anders["sensor_key"] == NETZ_KEY and anders["tage"] == 1
    assert anders["erster_wert"] == "2026-09-01T12:00:00"


async def test_a_keine_b_fragt_bei_b_a_keine_a_nicht(db):
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    keine = await _pruefe(db, aid, quelle="keine")
    assert (keine["grund_erforderlich"], keine["verzeichnet"]) == (False, True)       # → «Keine»: ohne Frage verzeichnet
    await _setze(db, aid, quelle="keine")
    assert [(w.nachher, w.grund) for w in await _zeilen(db, aid)] == [({"art": "keine"}, None)]
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.a"))["grund_erforderlich"] is False   # → A
    assert (await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b"))["grund_erforderlich"] is True    # → B


async def test_schluessel_ohne_eigene_werte_weder_gefragt_noch_verzeichnet(db):
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}}, werte=())
    aid = a.id
    await db.commit()
    p = await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b")
    assert (p["grund_erforderlich"], p["verzeichnet"], p["sensor_key"]) == (False, False, None)
    await _setze(db, aid, quelle="ha_app", entity_id="sensor.b")
    assert await _zeilen(db, aid) == []


async def test_pruef_route_schreibt_nichts(db):
    """Zeilenzählung je Tabelle vor und nach der Prüfung — auch mit Gateway-Zeile, Grund und Korrektur-Vorschau."""
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    vorher = await _zaehlung(db)
    await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b")
    await _pruefe(db, aid, quelle="mqtt_gateway", quell_topic="x/1")
    p = await _pruefe(db, aid, quelle="ha_app", entity_id="sensor.b", grund="loeschen")      # Weg B: «löschen» statt Korrektur
    assert p["loeschen"]["saetze"] and "korrektur" not in p
    assert await _zaehlung(db) == vorher


# ═══ Mit Grund ════════════════════════════════════════════════════════════════════════════════════════════════════════

async def test_fortsetzung_traegt_den_grund(db):
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    r = await _setze(db, aid, quelle="ha_app", entity_id="sensor.b", grund="fortsetzung")
    assert r["korrektur"] == []
    assert [(w.grund, w.vorher, w.nachher) for w in await _zeilen(db, aid)] == [
        ("fortsetzung", {"art": "ha", "entity_id": "sensor.a"}, {"art": "ha", "entity_id": "sensor.b"})]


async def test_loeschen_ohne_home_assistant_nur_dieses_feld(db):
    """Weg B (Bauplan Nr. 176–180; bis Sitzung B1 an dieser Stelle die Korrektur mit «falsch seit»): «Daten vor der Änderung
    löschen» löscht die Zählerstände dieses Felds vor der Änderung, verzeichnet nichts und startet den Lauf (Art «loeschen»);
    «korrektur» ist an der Feld-Route kein Grund mehr (400); ohne Antwort 422."""
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    for tag in (1, 5, 20):
        db.add(SensorSnapshot(anlage_id=aid, sensor_key=NETZ_KEY, zeitpunkt=datetime(2026, 10, tag, 3), wert_kwh=tag,
                              quelle="ha_statistics"))
    db.add(SensorSnapshot(anlage_id=aid, sensor_key="basis:einspeisung", zeitpunkt=datetime(2026, 10, 1, 3), wert_kwh=1.0,
                          quelle="ha_statistics"))
    await db.commit()
    e = await _ablehnung(_setze(db, aid, quelle="ha_app", entity_id="sensor.b", grund="korrektur"))
    assert e.status_code == 400
    await db.rollback()
    e = await _ablehnung(_setze(db, aid, quelle="ha_app", entity_id="sensor.b"))
    assert e.status_code == 422 and "gelöscht" in e.detail
    await db.rollback()                                  # wie ``deps.get_db`` nach einer Ausnahme
    r = await _setze(db, aid, quelle="ha_app", entity_id="sensor.b", grund="loeschen")
    assert [(x["art"], x["zaehlerstaende_geloescht"]) for x in r["korrektur"]] == [("loeschen", 4)]
    staende = (await db.execute(select(SensorSnapshot.sensor_key).where(SensorSnapshot.anlage_id == aid))).scalars().all()
    assert staende == ["basis:einspeisung"]                      # nur dieses Feld
    assert await _zeilen(db, aid) == []


async def test_loeschen_ohne_erreichbares_home_assistant(db, monkeypatch):
    """«löschen» braucht Home Assistant nicht (bis B1: die Korrektur lehnte dann ab) — der Lauf holt die Geschichte später."""
    def nicht(_svc=None):
        raise kr.KorrekturNichtStartbar("Home Assistant ist nicht erreichbar — …")
    monkeypatch.setattr(kr, "ha_dienst", nicht)
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    r = await _setze(db, aid, quelle="ha_app", entity_id="sensor.b", grund="loeschen")
    assert r["gespeichert"] and r["korrektur"][0]["art"] == "loeschen" and await _zeilen(db, aid) == []


# ═══ Wege: Preset, Energie-Vorschläge, Gateway-Zeile ════════════════════════════════════════════════════════════════════

async def test_preset_pruefen_schreibt_nichts_422_ohne_grund_und_mit_grund(db):
    from backend.api.routes.mqtt_presets import ApplyPresetRequest, apply_preset, pruefe_preset

    a = await _anlage(db, {"investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}}},
                           "quellen": {GW: {"quelle": "ha_app", "entity_id": "sensor.wb"}}}, werte=(GW_KEY,))
    aid = a.id
    await db.commit()
    req = dict(preset_id="evcc_ladepunkt", anlage_id=aid, variablen={}, investition_id=2)
    vorher = await _zaehlung(db)
    p = await pruefe_preset(ApplyPresetRequest(**req), db)
    assert p["grund_erforderlich"] is True and [f["sensor_key"] for f in p["felder"] if f["grund_erforderlich"]] == [GW_KEY]
    assert await _zaehlung(db) == vorher
    e = await _ablehnung(apply_preset(ApplyPresetRequest(**req), db))
    assert e.status_code == 422
    await db.rollback()
    await apply_preset(ApplyPresetRequest(**req, gruende={GW_KEY: {"grund": "fortsetzung"}}), db)
    assert [(w.sensor_key, w.grund) for w in await _zeilen(db, aid)] == [(GW_KEY, "fortsetzung")]


async def test_energie_vorschlaege_ueberspringen_und_nennen(db, monkeypatch):
    from backend.api.routes import datenquellen as dq

    async def verbunden(_db):
        return "http://ha", "tok", "ha_app"
    monkeypatch.setattr(dq, "_resolve_ha", verbunden)
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.alt"}}})
    aid = a.id
    r = await uebernehme_energy_vorschlaege(aid, EnergyUebernahmeRequest(basis={"netzbezug": "sensor.neu"}), db)
    assert (r["anzahl"], [u["field_id"] for u in r["uebersprungen"]]) == (0, [NETZ])
    r = await uebernehme_energy_vorschlaege(aid, EnergyUebernahmeRequest(basis={"netzbezug": "sensor.alt"}), db)
    assert (r["anzahl"], r["uebersprungen"]) == (1, [])                                # gleiche Entität: keine Frage


async def test_gateway_zeile_anlegen_und_loeschen_lehnen_ab_aendern_ueberspringt(db):
    from backend.api.routes.mqtt_gateway import MappingCreate, MappingUpdate, create_mapping, delete_mapping, update_mapping

    a = await _anlage(db, werte=(GW_KEY,))
    aid = a.id
    e = await _ablehnung(create_mapping(MappingCreate(anlage_id=aid, quell_topic="x/1", ziel_key="energy/inv/2/ladung_kwh"), db))
    assert e.status_code == 422 and GW_KEY in e.detail
    await db.rollback()
    leer = await _anlage(db, werte=())
    leer_id = leer.id
    zeile = (await create_mapping(MappingCreate(anlage_id=leer_id, quell_topic="x/1",
                                                ziel_key="energy/inv/2/ladung_kwh"), db))["mapping"]
    r = await update_mapping(zeile["id"], MappingUpdate(faktor=0.001), db)              # ohne Werte: geht durch
    assert r["uebersprungen"] == [] and r["mapping"]["faktor"] == 0.001
    db.add(SensorSnapshot(anlage_id=leer_id, sensor_key=GW_KEY, zeitpunkt=datetime(2026, 9, 1), wert_kwh=1.0, quelle="mqtt"))
    await db.flush()
    r = await update_mapping(zeile["id"], MappingUpdate(faktor=1.0), db)
    assert r["uebersprungen"] == [GW_KEY] and r["mapping"]["faktor"] == 0.001
    e = await _ablehnung(delete_mapping(zeile["id"], db))
    assert e.status_code == 422


# ═══ B-10: der Hinweis-Block entfällt ══════════════════════════════════════════════════════════════════════════════════

async def test_hinweis_vermerk_entfaellt_in_allen_antworten(db):
    from backend.api.routes.datenquellen import InvertSetRequest, get_datenquellen_felder, set_feld_invert
    from backend.main import app

    a = await _anlage(db, {"historie_hinweis": {"felder": [{"id": NETZ, "label": "Netz"}], "seit": "2026-09-27"}}, werte=())
    aid = a.id
    await db.commit()
    assert "historie_hinweis" not in await get_datenquellen_felder(aid, db)
    assert "historie_hinweis" not in await set_feld_invert(aid, NETZ, InvertSetRequest(invertieren=True), db)
    assert "historie_hinweis" not in await _setze(db, aid, quelle="ha_app", entity_id="sensor.x")
    assert not [r for r in app.routes if "historie-hinweis" in getattr(r, "path", "")]
    # Ein gespeicherter Alt-Vermerk bleibt im Mapping (Sitzung 4 überführt ihn); eedc schreibt keinen neuen.
    await db.refresh(a)
    assert a.sensor_mapping["historie_hinweis"]["felder"] == [{"id": NETZ, "label": "Netz"}]


# ═══ Robustheit des Korrektur-Laufs (§10 Nr. 40) ════════════════════════════════════════════════════════════════════════

def _sitzungen_von(db):
    return kr.sitzungen_wie(db, None)


async def test_fortsetzen_nach_dem_start_neben_einer_laufenden_aufgabe(datei, monkeypatch):
    sitzungen, _p, aid, _g = datei
    async with sitzungen() as s:
        await kl.anlegen(s, "L1", aid, NETZ_KEY, [datetime(2026, 4, 2).date()])
    aufrufe: list[str] = []
    halt = asyncio.Event()

    async def tage(_s, lauf):
        aufrufe.append(lauf)
        await halt.wait()
    monkeypatch.setattr(kl, "tage_neu_bilden", tage)
    erste = kl.starten("L1", sitzungen=sitzungen)
    await asyncio.sleep(0)
    zweite = asyncio.create_task(kl.fortsetzen_nach_dem_start(warte_s=0, sitzungen=sitzungen))
    await asyncio.sleep(0.05)
    halt.set()
    await erste
    assert await zweite == ["L1"]
    assert aufrufe == ["L1"]                                    # höchstens eine Aufgabe je Lauf
    kl._AUFGABEN.clear()


async def test_aufraeumen_und_diagnose_paket_und_fortschritt(db):
    from backend.api.routes.sensorwechsel import korrektur_lauf_stand
    from backend.services.diagnose_paket.lage import LageErgebnis, einstellungen

    a = await _anlage(db, werte=())
    aid = a.id
    await kl.anlegen(db, "alt", aid, NETZ_KEY, [])
    await kl.anlegen(db, "neu", aid, NETZ_KEY, [datetime(2026, 10, 1).date()])
    await kl.anlegen(db, "fremd", aid + 1, NETZ_KEY, [])
    alt = (await db.execute(select(Settings).where(Settings.key == "korrektur_lauf:alt"))).scalar_one()
    alt.value = {**alt.value, "status": kl.FERTIG, "ende": "2026-09-01T00:00:00"}
    await db.commit()
    assert await kl.aufraeumen(db, jetzt=datetime(2026, 10, 15)) == 1
    await db.commit()
    assert await kl.stand(db, "alt") is None and await kl.stand(db, "neu") is not None   # nur der fertige alte Lauf
    stand = await korrektur_lauf_stand(aid, "neu", db)
    assert (stand["status"], stand["tage"], stand["erledigt"]) == ("laeuft", 1, 0)
    with pytest.raises(HTTPException):
        await korrektur_lauf_stand(aid, "fremd", db)

    class _S:
        def __init__(self, s):
            self.s = s

        async def __aenter__(self):
            return self.s

        async def __aexit__(self, *_a):
            return False
    erg = LageErgebnis()
    out = await einstellungen(lambda: _S(db), aid, erg)
    assert out["korrektur_lauf:neu"] == {"sensor_key": NETZ_KEY, "status": "laeuft", "erledigt": 0, "tage": 1, "fehler": 0,
                                         "beginn": out["korrektur_lauf:neu"]["beginn"], "ende": None, "fuellen": None}
    assert "korrektur_lauf:fremd" not in out and not [k for k in erg.einstellungen_unbekannt if k.startswith("korrektur")]


async def test_spiegel_hinter_verworfener_quelle_derselben_entitaet_beginnt_neu(ha, datei):
    """``schreiber._spiegel``: ist die jüngste Quelle verworfen (Korrektur), beginnt der Stundenlauf auch bei gleicher Entität
    eine neue Quelle — sonst lägen die neuen Zeilen im verworfenen Abschnitt und gälten als nicht voll."""
    from backend.services.kanal.nachfuellen import nachfuellen_spiegel
    from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _kanal, _quellen, _stundenlauf

    svc, _r = ha
    sitzungen, _p, aid, _g = datei
    t = ZEIT + timedelta(days=5)
    await nachfuellen_spiegel(sitzungen, aid, jetzt=t, ha_svc=svc)
    k = await _kanal(sitzungen, aid, "basis:einspeisung")
    async with sitzungen() as s:
        for q in (await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all():
            q.verworfen_ts = _ts(t)
    await _stundenlauf(sitzungen, aid, svc, t + timedelta(hours=6))
    qs = await _quellen(sitzungen, k.id)
    assert [(q.statistic_id, q.verworfen_ts is None) for q in qs] == [("sensor.einsp", False), ("sensor.einsp", True)]
    async with sitzungen() as s:
        erste_neu = (await s.execute(select(func.min(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= qs[1].gueltig_ab)))).scalar_one()
    assert qs[1].gueltig_ab == erste_neu


# ═══ Einstieg «Zähler getauscht (gleiche Quelle)» (§9 Nr. 26) ══════════════════════════════════════════════════════════

async def test_zaehler_getauscht_ha_mit_spiegel_nur_weg_in_home_assistant(db):
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht, zaehler_getauscht

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    p = await pruefe_zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(), db)
    assert (p["weg"], p["eintragen"]) == ("home_assistant", False) and "Summe anpassen" in p["saetze"][0]
    r = await zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(), db)
    assert r["eingetragen"] is False and await _zeilen(db, aid) == []


async def test_zaehler_getauscht_mqtt_eigene_summe_traegt_fortsetzung_mit_nachtrag_ein(db):
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, zaehler_getauscht

    a = await _anlage(db, werte=(NETZ_KEY,))                       # ohne HA-Zuordnung: MQTT-Inbound
    aid = a.id
    k = Kanal(anlage_id=aid, key=NETZ_KEY, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    t0 = datetime(2026, 11, 10, 8)
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(t0), familie="mitschrift", statistic_id="netzbezug_kwh", offset=0.0))
    for i, wert in enumerate((100.0, 101.0, 2101.5, 2102.5)):     # Tausch in der Stunde 10:00 (Sprung +2 000)
        db.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(t0 + timedelta(hours=i)), sum=wert, state=wert, familie="mitschrift"))
    await db.commit()
    getauscht = t0 + timedelta(hours=2, minutes=15)
    r = await zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(getauscht_am=getauscht), db)
    assert (r["weg"], r["eingetragen"]) == ("fortsetzung", True) and len(r["saetze"]) == 3   # U3 a (G3): kein fester Tageswert
    assert r["saetze"][2] == "Bisher zählt sie 2.000,50 kWh."           # §11 Nr. 49: der bisherige Zuwachs der Stunde
    (w,) = await _zeilen(db, aid)
    assert (w.grund, w.erklaert_ts, w.ab_ts, w.vorher == w.nachher) == ("fortsetzung", getauscht, t0 + timedelta(hours=3), True)
    q = (await db.execute(select(KanalQuelle).where(and_(KanalQuelle.kanal_id == k.id,
                                                         KanalQuelle.gueltig_ab == _ts(t0 + timedelta(hours=2)))))).scalar_one()
    assert q.offset == pytest.approx(-2000.5)                     # die Tausch-Stunde zählt keinen Zuwachs
    zweimal = await zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(getauscht_am=getauscht), db)
    assert zweimal["eingetragen"] is False and len(await _zeilen(db, aid)) == 1


async def test_zaehler_getauscht_ohne_werte_und_zukunft(db):
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, pruefe_zaehler_getauscht

    a = await _anlage(db, werte=())
    aid = a.id
    p = await pruefe_zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(), db)
    assert p["weg"] == "ohne_werte" and p["eintragen"] is False
    e = await _ablehnung(pruefe_zaehler_getauscht(aid, NETZ, ZaehlerGetauschtRequest(
        getauscht_am=datetime(2099, 1, 1)), db))   # fest in der Zukunft
    assert e.status_code == 400


