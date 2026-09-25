"""N-561 — Gateway-Zuordnungen gehen mit, wenn die Komponente geht.

Eine MQTT-Gateway-Zuordnung der Datenquellen-Fläche besteht aus zwei Teilen:
dem `quellen`-Eintrag (`{"quelle": "mqtt_gateway", "mapping_id": N}`) und der
Zeile N in `mqtt_gateway_mappings`, die der Gateway abonniert. N-559 räumte den
Eintrag, die Zeile blieb **aktiv** (gemessen §13.8) — der Gateway abonnierte das
Topic einer Komponente, die es nicht mehr gab, und weil SQLite die höchste ID
wiederverwendet (§13.2), zielte die Zeile auf die nächste neue Komponente.

Geprüft über die echte Fläche und den echten Reload-Weg; der Gateway-Dienst ist
ein Stellvertreter, der mitschreibt, was er beim Reload abonnieren soll.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes import mqtt_gateway as gw_route
from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle
from backend.api.routes.investitionen.crud import (
    InvestitionCreate,
    InvestitionUpdate,
    create_investition,
    delete_investition,
    update_investition,
)
from backend.api.routes.mqtt_gateway import delete_mapping
from backend.models import Anlage
from backend.models.activity_log import ActivityLog
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_mapping_sync import feld_id
from backend.tests.test_263_innengeraete import MIT_LISTE


class _Gateway:
    """Stellvertreter des Gateway-Dienstes: merkt sich jeden Reload."""
    def __init__(self):
        self.reloads: list[list] = []

    async def reload(self, mappings):
        self.reloads.append(list(mappings))
        return True

    @property
    def abonniert(self) -> set[str]:
        return {m.quell_topic for m in self.reloads[-1]} if self.reloads else set()


@pytest.fixture
def gateway(monkeypatch):
    g = _Gateway()
    monkeypatch.setattr(gw_route, "get_mqtt_gateway_service", lambda: g)
    return g


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="Gateway", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    return a


async def _wallbox(db, anlage, name):
    return await create_investition(InvestitionCreate(
        anlage_id=anlage.id, typ="wallbox", bezeichnung=name, anschaffungsdatum=date(2024, 1, 1),
    ), db)


async def _gateway_zuordnen(db, anlage, inv_id, feld, topic):
    await set_feld_quelle(anlage.id, feld_id(("inv_live", inv_id, feld)),
                          QuelleSetRequest(quelle="mqtt_gateway", quell_topic=topic), db)


async def _zeilen(db):
    return list((await db.execute(select(MqttGatewayMapping))).scalars().all())


async def test_loeschen_entfernt_die_gateway_zeile_und_laedt_neu(db, gateway):
    a = await _anlage(db)
    weg = await _wallbox(db, a, "Weg")
    bleibt = await _wallbox(db, a, "Bleibt")
    await _gateway_zuordnen(db, a, weg.id, "leistung_w", "wb/weg/p")
    await _gateway_zuordnen(db, a, bleibt.id, "leistung_w", "wb/bleibt/p")
    assert gateway.abonniert == {"wb/weg/p", "wb/bleibt/p"}, "Vorbedingung"

    await delete_investition(weg.id, db)
    await db.commit()

    assert [z.quell_topic for z in await _zeilen(db)] == ["wb/bleibt/p"]
    assert gateway.abonniert == {"wb/bleibt/p"}, "der Gateway abonniert das Topic nicht mehr"
    zeile = (await db.execute(select(ActivityLog).where(
        ActivityLog.kategorie == "investitionen", ActivityLog.aktion == "Komponente gelöscht",
    ))).scalar_one()
    assert zeile.details == "Gateway · Wallbox · Weg · MQTT-Gateway-Zuordnung entfernt (wb/weg/p)"


async def test_loeschen_ohne_gateway_nennt_keinen_halbsatz_und_laedt_nicht(db, gateway):
    a = await _anlage(db)
    wb = await _wallbox(db, a, "Ohne")
    await delete_investition(wb.id, db)
    zeile = (await db.execute(select(ActivityLog).where(ActivityLog.aktion == "Komponente gelöscht"))).scalar_one()
    assert zeile.details == "Gateway · Wallbox · Ohne"
    assert gateway.reloads == []


async def test_innengeraet_entfernen_entfernt_nur_seine_gateway_zeile(db, gateway):
    a = await _anlage(db)
    wp = await create_investition(InvestitionCreate(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), parameter=MIT_LISTE,
    ), db)
    await _gateway_zuordnen(db, a, wp.id, "leistung_w-1", "klima/buero/p")
    await _gateway_zuordnen(db, a, wp.id, "leistung_w-3", "klima/wohnen/p")
    await db.commit()

    await update_investition(wp.id, InvestitionUpdate(parameter={
        "wp_art": "luft_luft", "innengeraete": [{"id": 1, "bezeichnung": "Büro"}]}), db=db)
    await db.commit()

    assert [z.quell_topic for z in await _zeilen(db)] == ["klima/buero/p"]
    assert gateway.abonniert == {"klima/buero/p"}


async def test_wiederverwendete_id_bekommt_keine_gateway_werte(db, gateway):
    a = await _anlage(db)
    alt = await _wallbox(db, a, "Alt")
    await _gateway_zuordnen(db, a, alt.id, "leistung_w", "wb/alt/p")
    alt_id = alt.id
    await delete_investition(alt_id, db)
    await db.commit()

    neu = await _wallbox(db, a, "Neu")
    await db.commit()
    assert neu.id == alt_id, "SQLite vergibt die höchste ID wieder (§13.2)"
    ziel = f"inv/{neu.id}_"
    assert not [z for z in await _zeilen(db) if ziel in (z.ziel_key or "")]
    assert not [m for m in gateway.reloads[-1] if ziel in (m.ziel_key or "")], \
        "kein abonniertes Topic zielt auf die neue Komponente"


async def test_gateway_route_loescht_weiter_und_meldet_404(db, gateway):
    """Der herausgezogene Helfer trägt auch `DELETE /mqtt/gateway/mappings/{id}`."""
    from fastapi import HTTPException

    a = await _anlage(db)
    wb = await _wallbox(db, a, "Route")
    await _gateway_zuordnen(db, a, wb.id, "leistung_w", "wb/route/p")
    mid = (await _zeilen(db))[0].id
    antwort = await delete_mapping(mid, db)
    assert antwort["geloescht"] is True and await _zeilen(db) == []
    with pytest.raises(HTTPException) as e:
        await delete_mapping(mid, db)
    assert e.value.status_code == 404
