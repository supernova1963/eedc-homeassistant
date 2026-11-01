"""Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.2/§1.3/§1.7) — Routen, Quellen-Route, Fläche, Topic-Registry, Aufräumen.

Über die echten Routen-Funktionen und eine In-Memory-DB:

* die sechs Themen-Routen — Typ ohne «Überblick» ⇒ 400 (P8), unbekannt ⇒ 404, Protokollzeile mit Klartext;
* H2 (Nachlauf 4.2.0): die fünf Routen an einem Thema nennen das Gerät (``investition_id``, Pflicht ⇒ 422); zwei Geräte
  mit denselben Kennungen ``t1``/``e2`` stören sich nicht; ein Gerät ohne dieses Thema ⇒ 404;
* die Quellen-Route an ``inv_thema_…`` — unbekannter Eintrag ⇒ 404, Quelle in ``quellen``, **kein** Historie-Vermerk,
  Label «Gerät – Thema · Label», Gateway-Ziel ``…/thema_<e>``, ``friendly_name`` beim ersten HA-Pick;
* Entfernen räumt ``quellen`` und die Gateway-Zeile; **Gerät löschen räumt ``inv_thema_<id>_``** (P4), **JSON-Import
  remapped die Kennung** (P5);
* ``GET /felder``: ``themen`` je Gerätegruppe, die Themen-Topics nicht in der Feldliste;
* Topic-Registry trägt den Eintrag, der Daten-Checker erwartet ihn nicht; HA-Picker ``alle``.

Schwesterdateien: test_themen_store.py, test_themen_live.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.api.routes import datenquellen as dq
from backend.api.routes import datenquellen_themen as th
from backend.api.routes import mqtt_gateway as gw_route
from backend.api.routes.datenquellen import QuelleSetRequest, get_datenquellen_felder, set_feld_quelle
from backend.api.routes.import_export.sensor_mapping_remap import remap_investitionen_ids
from backend.api.routes.investitionen.crud import delete_investition
from backend.models import Anlage
from backend.models.activity_log import ActivityLog
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.mqtt_topic_registry import build_expected_topics


class _Gateway:
    def __init__(self):
        self.reloads: list[list] = []

    async def reload(self, mappings):
        self.reloads.append(list(mappings))
        return True


@pytest.fixture(autouse=True)
def gateway(monkeypatch):
    g = _Gateway()
    monkeypatch.setattr(gw_route, "get_mqtt_gateway_service", lambda: g)
    return g


@pytest.fixture(autouse=True)
def ohne_ha(monkeypatch):
    """Kein HA, kein Inbound — ein Test, der Werte braucht, setzt sie selbst."""
    async def _keine(db, ids):  # noqa: ARG001
        return {}
    monkeypatch.setattr(dq, "_ha_states_detail", _keine)
    monkeypatch.setattr(th, "_ha_states_detail", _keine)
    monkeypatch.setattr("backend.services.mqtt_inbound_service.get_mqtt_inbound_service", lambda: None)


async def _anlage(db, typ: str = "e-auto", name: str = "Ioniq") -> tuple[Anlage, Investition]:
    a = Anlage(anlagenname="Themen", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1), sensor_mapping={})
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ=typ, bezeichnung=name, anschaffungsdatum=date(2024, 1, 1))
    db.add(inv)
    await db.flush()
    return a, inv


async def _thema_mit_eintrag(db, a, inv, name="Fahrzeugzustand", label="Türen") -> tuple[str, str]:
    antwort = await th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=inv.id, name=name), db)
    t_id = antwort["themen"][-1]["id"]
    antwort = await th.eintrag_anlegen(a.id, t_id, inv.id, th.EintragAnlegenRequest(label=label), db)
    return t_id, antwort["themen"][-1]["eintraege"][-1]["id"]


async def _protokoll(db) -> list[str]:
    return [z.details for z in (await db.execute(
        select(ActivityLog).where(ActivityLog.kategorie == "sensor_mapping").order_by(ActivityLog.id)
    )).scalars().all()]


# ── Routen ────────────────────────────────────────────────────────────────────

async def test_p8_typ_ohne_ueberblick_ist_400(db):
    a, speicher = await _anlage(db, "speicher", "Akku")
    with pytest.raises(HTTPException) as e:
        await th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=speicher.id), db)
    assert e.value.status_code == 400


async def test_unbekannt_ist_404(db):
    a, inv = await _anlage(db)
    for aufruf in (
        th.thema_anlegen(999, th.ThemaAnlegenRequest(investition_id=inv.id), db),
        th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=999), db),
        th.thema_aendern(a.id, "t9", inv.id, th.ThemaAendernRequest(name="x"), db),
        th.thema_entfernen(a.id, "t9", inv.id, db),
        th.eintrag_anlegen(a.id, "t9", inv.id, th.EintragAnlegenRequest(), db),
    ):
        with pytest.raises(HTTPException) as e:
            await aufruf
        assert e.value.status_code == 404
    t_id, _e = await _thema_mit_eintrag(db, a, inv)
    with pytest.raises(HTTPException) as e:
        await th.eintrag_entfernen(a.id, t_id, "e99", inv.id, db)
    assert e.value.status_code == 404


async def test_name_zu_lang_ist_400(db):
    a, inv = await _anlage(db)
    with pytest.raises(HTTPException) as e:
        await th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=inv.id, name="x" * 41), db)
    assert e.value.status_code == 400


async def test_anlegen_umbenennen_verschieben_mit_protokoll(db):
    a, inv = await _anlage(db)
    t1, e1 = await _thema_mit_eintrag(db, a, inv)
    antwort = await th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=inv.id), db)
    assert [t["name"] for t in antwort["themen"]] == ["Fahrzeugzustand", "Thema 2"]
    antwort = await th.thema_aendern(
        a.id, antwort["themen"][1]["id"], inv.id, th.ThemaAendernRequest(name="Service", position=0), db,
    )
    assert [t["name"] for t in antwort["themen"]] == ["Service", "Fahrzeugzustand"]
    antwort = await th.eintrag_aendern(a.id, t1, e1, inv.id, th.EintragAendernRequest(label="Türschloss"), db)
    assert antwort["themen"][1]["eintraege"][0]["label"] == "Türschloss"
    zeilen = await _protokoll(db)
    assert "Themen · Ioniq: Thema «Fahrzeugzustand» angelegt" in zeilen
    assert "Themen · Ioniq: Eintrag «Türen» angelegt" in zeilen
    assert any("Thema «Thema 2» umbenannt in «Service»" in z for z in zeilen)
    assert any("Eintrag «Türen» umbenannt in «Türschloss»" in z for z in zeilen)


# ── Quellen-Route ─────────────────────────────────────────────────────────────

async def test_quelle_unbekannter_eintrag_ist_404(db):
    a, inv = await _anlage(db)
    with pytest.raises(HTTPException) as e:
        await set_feld_quelle(a.id, f"inv_thema_{inv.id}_e7", QuelleSetRequest(quelle="keine"), db)
    assert e.value.status_code == 404
    assert "quellen" not in (a.sensor_mapping or {}) or not a.sensor_mapping["quellen"]


async def test_quelle_setzen_ohne_historie_vermerk_mit_label(db):
    a, inv = await _anlage(db)
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 10, 1)))  # Historie vorhanden
    await db.flush()
    t_id, e_id = await _thema_mit_eintrag(db, a, inv)
    fid = f"inv_thema_{inv.id}_{e_id}"
    antwort = await set_feld_quelle(a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id="lock.carport"), db)
    assert a.sensor_mapping["quellen"][fid] == {"quelle": "ha_app", "entity_id": "lock.carport"}
    assert antwort["historie_hinweis"] is None, "ein Thema hat keine Historie"
    # Die klassische Struktur bekommt nichts (kein Registry-Feld).
    assert set(a.sensor_mapping["investitionen"][str(inv.id)]) == {"themen"}
    assert (await _protokoll(db))[-1] == (
        "Themen · Ioniq – Fahrzeugzustand · Türen: Standard (MQTT-Inbound) → HA-Sensor lock.carport"
    )
    # Gegenprobe: ein Feld derselben Anlage bekommt den Vermerk weiter.
    antwort = await set_feld_quelle(
        a.id, f"inv_live_{inv.id}_leistung_w", QuelleSetRequest(quelle="ha_app", entity_id="sensor.p"), db,
    )
    assert antwort["historie_hinweis"] is not None


async def test_erster_ha_pick_uebernimmt_friendly_name(db, monkeypatch):
    a, inv = await _anlage(db)
    antwort = await th.thema_anlegen(a.id, th.ThemaAnlegenRequest(investition_id=inv.id), db)
    t_id = antwort["themen"][0]["id"]
    e_id = (await th.eintrag_anlegen(a.id, t_id, inv.id, th.EintragAnlegenRequest(), db))["themen"][0]["eintraege"][0]["id"]

    async def _detail(db, ids):  # noqa: ARG001
        return {eid: {"friendly_name": "Carport Türschloss", "wert_text": "locked"} for eid in ids}
    monkeypatch.setattr(dq, "_ha_states_detail", _detail)
    fid = f"inv_thema_{inv.id}_{e_id}"
    await set_feld_quelle(a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id="lock.carport"), db)
    themen = a.sensor_mapping["investitionen"][str(inv.id)]["themen"]["liste"]
    assert themen[0]["eintraege"][0]["label"] == "Carport Türschloss"
    # Ein zweiter Pick ändert das nun eigene Label nicht mehr.
    async def _anders(db, ids):  # noqa: ARG001
        return {eid: {"friendly_name": "Anderes Schloss"} for eid in ids}
    monkeypatch.setattr(dq, "_ha_states_detail", _anders)
    await set_feld_quelle(a.id, fid, QuelleSetRequest(quelle="ha_app", entity_id="lock.tuer"), db)
    assert a.sensor_mapping["investitionen"][str(inv.id)]["themen"]["liste"][0]["eintraege"][0]["label"] == (
        "Carport Türschloss"
    )


async def test_gateway_ziel_und_entfernen_raeumt_quelle_und_zeile(db, gateway):
    a, inv = await _anlage(db)
    t_id, e_id = await _thema_mit_eintrag(db, a, inv)
    fid = f"inv_thema_{inv.id}_{e_id}"
    await set_feld_quelle(a.id, fid, QuelleSetRequest(quelle="mqtt_gateway", quell_topic="evcc/vehicle/tuer"), db)
    (zeile,) = (await db.execute(select(MqttGatewayMapping))).scalars().all()
    assert zeile.ziel_key == f"live/inv/{inv.id}_Ioniq/thema_{e_id}", "W9: das Gateway trifft das Themen-Topic"
    await th.eintrag_entfernen(a.id, t_id, e_id, inv.id, db)
    assert fid not in a.sensor_mapping["quellen"]
    assert (await db.execute(select(MqttGatewayMapping))).scalars().all() == []
    assert gateway.reloads[-1] == []


async def test_thema_entfernen_raeumt_alle_eintraege(db):
    a, inv = await _anlage(db)
    t_id, e1 = await _thema_mit_eintrag(db, a, inv)
    e2 = (await th.eintrag_anlegen(a.id, t_id, inv.id, th.EintragAnlegenRequest(label="Reifen"), db))["themen"][0]["eintraege"][1]["id"]
    for e in (e1, e2):
        await set_feld_quelle(a.id, f"inv_thema_{inv.id}_{e}", QuelleSetRequest(quelle="keine"), db)
    antwort = await th.thema_entfernen(a.id, t_id, inv.id, db)
    assert antwort["themen"] == []
    assert not [k for k in a.sensor_mapping["quellen"] if k.startswith("inv_thema_")]
    assert (await _protokoll(db))[-1] == "Themen · Ioniq: Thema «Fahrzeugzustand» entfernt"


# ── P4 / P5 ───────────────────────────────────────────────────────────────────

async def test_p4_geraet_loeschen_raeumt_themen_und_gateway(db, gateway):
    a, inv = await _anlage(db)
    _t, e_id = await _thema_mit_eintrag(db, a, inv)
    await set_feld_quelle(a.id, f"inv_thema_{inv.id}_{e_id}",
                          QuelleSetRequest(quelle="mqtt_gateway", quell_topic="x/y"), db)
    await delete_investition(inv.id, db)
    await db.commit()
    assert not [k for k in (a.sensor_mapping.get("quellen") or {}) if k.startswith(f"inv_thema_{inv.id}_")]
    assert str(inv.id) not in (a.sensor_mapping.get("investitionen") or {})
    assert (await db.execute(select(MqttGatewayMapping))).scalars().all() == []


def test_p5_json_import_remapped_die_kennung():
    mapping = {
        "investitionen": {"7": {"themen": {"naechste_id": 3, "liste": [
            {"id": "t1", "name": "Zustand", "eintraege": [{"id": "e2", "label": "Türen"}]}]}}},
        "quellen": {"inv_thema_7_e2": {"quelle": "ha_app", "entity_id": "lock.x"}},
    }
    remap_investitionen_ids(mapping, {7: 12})
    assert mapping["quellen"] == {"inv_thema_12_e2": {"quelle": "ha_app", "entity_id": "lock.x"}}
    assert mapping["investitionen"]["12"]["themen"]["liste"][0]["name"] == "Zustand"


# ── H2 (Nachlauf 4.2.0): die Routen nennen das Gerät ──────────────────────────
# Kennungen ``t<n>``/``e<n>`` zählen je Gerät ab 1 — zwei Geräte tragen beide ``t1``/``e2``. Über HTTP gefahren,
# damit der Pflicht-Query-Parameter ``investition_id`` mitgeprüft ist (Routing + Validierung, nicht nur die Funktion).

@pytest.fixture
async def themen_client(db):
    import httpx
    from fastapi import FastAPI

    from backend.api.deps import get_db

    app = FastAPI()
    app.include_router(th.router, prefix="/api/datenquellen")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _geraete_stand(a: Anlage, inv: Investition) -> str:
    """Themen-Knoten und Quellen eines Geräts als Text — der byte-gleiche Vergleich der Probe."""
    import json

    mapping = a.sensor_mapping or {}
    quellen = {k: v for k, v in (mapping.get("quellen") or {}).items() if k.startswith(f"inv_thema_{inv.id}_")}
    return json.dumps({"themen": mapping["investitionen"][str(inv.id)], "quellen": quellen}, sort_keys=True)


async def _zwei_geraete_mit_t1_e2(db, client) -> tuple[Anlage, Investition, Investition]:
    a, erstes = await _anlage(db, "wallbox", "Carport")
    zweites = Investition(anlage_id=a.id, typ="e-auto", bezeichnung="Ioniq", anschaffungsdatum=date(2024, 1, 1))
    db.add(zweites)
    await db.flush()
    dq_pfad = f"/api/datenquellen/{a.id}"
    for inv, name, label in ((erstes, "Ladepunkt", "Kabel"), (zweites, "Fahrzeugzustand", "Türen")):
        r = await client.post(f"{dq_pfad}/themen", json={"investition_id": inv.id, "name": name})
        assert r.status_code == 200, r.text
        r = await client.post(f"{dq_pfad}/themen/t1/eintraege", params={"investition_id": inv.id}, json={"label": label})
        assert r.status_code == 200, r.text
        assert r.json()["investition_id"] == inv.id
        await set_feld_quelle(
            a.id, f"inv_thema_{inv.id}_e2", QuelleSetRequest(quelle="ha_app", entity_id=f"sensor.{inv.typ}_x"), db,
        )
    for inv in (erstes, zweites):  # Vorbedingung: beide Geräte tragen dieselben Kennungen
        (thema,) = a.sensor_mapping["investitionen"][str(inv.id)]["themen"]["liste"]
        assert thema["id"] == "t1" and [e["id"] for e in thema["eintraege"]] == ["e2"]
    return a, erstes, zweites


async def test_h2_routen_am_zweiten_geraet_lassen_das_erste_unberuehrt(db, themen_client):
    """Zwei Geräte mit je ``t1``/``e2``: PATCH Name, POST/PATCH/DELETE Eintrag und DELETE Thema am **zweiten** Gerät
    treffen das zweite — das erste bleibt byte-gleich (Themen-Knoten und Quellen)."""
    a, erstes, zweites = await _zwei_geraete_mit_t1_e2(db, themen_client)
    vorher = _geraete_stand(a, erstes)
    pfad = f"/api/datenquellen/{a.id}/themen/t1"
    q = {"investition_id": zweites.id}

    def _zweites() -> dict:
        (thema,) = a.sensor_mapping["investitionen"][str(zweites.id)]["themen"]["liste"]
        return thema

    r = await themen_client.patch(pfad, params=q, json={"name": "Zustand"})
    assert r.status_code == 200, r.text
    assert r.json()["investition_id"] == zweites.id and _zweites()["name"] == "Zustand"
    assert _geraete_stand(a, erstes) == vorher

    r = await themen_client.post(f"{pfad}/eintraege", params=q, json={"label": "Reifen"})
    assert r.status_code == 200, r.text
    assert [e["label"] for e in _zweites()["eintraege"]] == ["Türen", "Reifen"]
    assert _geraete_stand(a, erstes) == vorher

    r = await themen_client.patch(f"{pfad}/eintraege/e2", params=q, json={"label": "Türschloss"})
    assert r.status_code == 200, r.text
    assert _zweites()["eintraege"][0]["label"] == "Türschloss"
    assert _geraete_stand(a, erstes) == vorher

    r = await themen_client.delete(f"{pfad}/eintraege/e2", params=q)
    assert r.status_code == 200, r.text
    assert [e["label"] for e in _zweites()["eintraege"]] == ["Reifen"]
    assert f"inv_thema_{zweites.id}_e2" not in a.sensor_mapping["quellen"]
    assert _geraete_stand(a, erstes) == vorher

    r = await themen_client.delete(pfad, params=q)
    assert r.status_code == 200, r.text
    assert r.json() == {"investition_id": zweites.id, "themen": []}
    assert _geraete_stand(a, erstes) == vorher
    assert f"inv_thema_{erstes.id}_e2" in a.sensor_mapping["quellen"]


async def test_h2_ohne_investition_id_ist_422(db, themen_client):
    a, _erstes, _zweites = await _zwei_geraete_mit_t1_e2(db, themen_client)
    pfad = f"/api/datenquellen/{a.id}/themen/t1"
    for aufruf in (
        themen_client.patch(pfad, json={"name": "x"}),
        themen_client.delete(pfad),
        themen_client.post(f"{pfad}/eintraege", json={}),
        themen_client.patch(f"{pfad}/eintraege/e2", json={"label": "x"}),
        themen_client.delete(f"{pfad}/eintraege/e2"),
    ):
        r = await aufruf
        assert r.status_code == 422, r.text


async def test_h2_geraet_ohne_dieses_thema_ist_404(db, themen_client):
    a, erstes, zweites = await _zwei_geraete_mit_t1_e2(db, themen_client)
    drittes = Investition(anlage_id=a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1))
    db.add(drittes)
    await db.flush()
    vorher = (_geraete_stand(a, erstes), _geraete_stand(a, zweites))
    pfad = f"/api/datenquellen/{a.id}/themen/t1"
    q = {"investition_id": drittes.id}
    for aufruf in (
        themen_client.patch(pfad, params=q, json={"name": "x"}),
        themen_client.delete(pfad, params=q),
        themen_client.post(f"{pfad}/eintraege", params=q, json={}),
        themen_client.patch(f"{pfad}/eintraege/e2", params=q, json={"label": "x"}),
        themen_client.delete(f"{pfad}/eintraege/e2", params=q),
    ):
        r = await aufruf
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Thema nicht gefunden"
    assert (_geraete_stand(a, erstes), _geraete_stand(a, zweites)) == vorher


# ── Fläche, Registry, Checker, Picker ─────────────────────────────────────────

async def test_felder_tragen_themen_je_geraet(db):
    a, inv = await _anlage(db)
    speicher = Investition(anlage_id=a.id, typ="speicher", bezeichnung="Akku", anschaffungsdatum=date(2024, 1, 1))
    db.add(speicher)
    await db.flush()
    _t, e_id = await _thema_mit_eintrag(db, a, inv)
    antwort = await get_datenquellen_felder(a.id, db)
    gruppen = {g["id"]: g for g in antwort["gruppen"]}
    (thema,) = gruppen[f"inv:{inv.id}"]["themen"]
    (zeile,) = thema["eintraege"]
    assert zeile["feld_id"] == f"inv_thema_{inv.id}_{e_id}"
    assert zeile["quelle"] == "keine" and zeile["wert_text"] is None
    assert zeile["standard_topic"].endswith(f"/live/inv/{inv.id}_Ioniq/thema_{e_id}")
    assert gruppen[f"inv:{speicher.id}"]["themen"] == []
    assert "themen" not in gruppen["basis"]
    # Die Themen-Topics stehen nicht in der Feldliste.
    assert not [f for g in antwort["gruppen"] for f in g["felder"] if f["feld"].startswith("thema_")]


async def test_registry_traegt_den_eintrag_als_text_topic(db):
    a, inv = await _anlage(db)
    _t, e_id = await _thema_mit_eintrag(db, a, inv)
    (e,) = [t for t in await build_expected_topics(db, a, investitionen=[inv]) if t.get("abschnitt") == "themen"]
    assert e["match_key"] == ("inv_live", str(inv.id), f"thema_{e_id}")
    assert e["zustand"] is True and e["text"] is True
    assert e["label"] == "Ioniq – Fahrzeugzustand · Türen"


async def test_daten_checker_erwartet_kein_themen_topic(db, monkeypatch):
    """Abdeckungsprüfung (#134): sie filtert über die Registry ``not e.get("zustand")`` — gemessen 1.11.2026; das
    Themen-Topic trägt ``zustand: True`` und fällt heraus, auch mit einem Inbound-Stempel auf seiner Registry-ID."""
    from backend.services.daten_checker import DatenChecker

    class _Cache:
        def get_all_live_raw(self):
            return {}

        def get_all_energy_raw(self):
            return {}

    class _Svc:
        _running = True
        cache = _Cache()

    a, inv = await _anlage(db)
    _t, e_id = await _thema_mit_eintrag(db, a, inv)
    monkeypatch.setattr("backend.services.mqtt_inbound_service.get_mqtt_inbound_service", lambda: _Svc())
    a.sensor_mapping = {**a.sensor_mapping, "quellen": {
        f"inv_live_{inv.id}_thema_{e_id}": {"quelle": "mqtt_inbound_standard"},
        f"inv_thema_{inv.id}_{e_id}": {"quelle": "mqtt_inbound_standard"},
    }}
    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(a)
    assert not [b for b in befunde if "thema_" in (b.details or "")]

    # Gegenprobe: ohne die Zustands-Weiche stünde das Topic in der Meldung — die Probe misst also den Filter.
    from backend.services import mqtt_topic_registry as reg

    original = reg._themen_topics
    monkeypatch.setattr(reg, "_themen_topics", lambda *a, **k: [{**e, "zustand": False} for e in original(*a, **k)])
    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(a)
    assert [b for b in befunde if f"thema_{e_id}" in (b.details or "")]


async def test_picker_alle_laesst_jede_entitaet_mit_state_durch():
    states = [
        {"entity_id": "lock.carport", "state": "locked", "attributes": {"friendly_name": "Carport"}},
        {"entity_id": "sensor.reifen", "state": "2.4", "attributes": {"unit_of_measurement": "bar"}},
        {"entity_id": "binary_sensor.tuer", "state": "", "attributes": {}},
    ]
    assert [s["entity_id"] for s in states if dq._ha_sensor_relevant(s, True, alle=True)] == [
        "lock.carport", "sensor.reifen",
    ]
    # Ohne `alle` greift der Bestand: `lock.` fällt am Domain-Test heraus.
    assert not dq._ha_sensor_relevant(states[0], False)


async def test_picker_route_alle_ohne_assistenz(db, monkeypatch):
    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return [{"entity_id": "lock.carport", "state": "locked", "attributes": {}}]

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    async def _ha(db):  # noqa: ARG001
        return "http://ha/api", "t", "ha_app"
    monkeypatch.setattr(dq, "_resolve_ha", _ha)
    monkeypatch.setattr(dq.httpx, "AsyncClient", _Client)
    antwort = await dq.get_ha_sensoren(1, alle=True, db=db)
    assert [(s.entity_id, s.domain) for s in antwort.sensoren] == [("lock.carport", "lock")]
    assert antwort.vorschlaege == [] and antwort.warnungen == {}
