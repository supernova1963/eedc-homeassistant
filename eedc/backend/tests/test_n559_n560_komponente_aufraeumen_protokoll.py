"""N-559 und N-560 — was mit einer Komponente in `sensor_mapping` und im Protokoll geschieht.

**N-559.** Die Datenquellen-Fläche legt eine Zuordnung unter der Feld-ID ab
(`inv_energy_<id>_<feld>`, `inv_live_<id>_<key>`) — in `quellen` und, für die
Vorzeichen-Umkehr, in `invertieren`; bei einem HA-Sensor zusätzlich im klassischen
`investitionen[<id>]`. Das Aufräumen beim Entfernen eines Innengeräts suchte bis
25.09.2026 nach `inv:<id>:<feld>` und fand nie etwas; das Löschen einer Komponente
räumte nur den klassischen Teil. Die Proben gehen deshalb **über die echte Fläche**
(Routen `set_feld_quelle`/`set_feld_invert`), nicht über eine gebaute Form.

⚠ **Warum das mehr als Ordnung ist:** SQLite vergibt die ID der zuletzt angelegten
Investition nach dem Löschen wieder (das Schema trägt kein `AUTOINCREMENT`,
gemessen §13). Eine liegengebliebene Zuordnung gälte dann für die nächste Komponente.

**N-560.** Anlegen, Löschen und die Änderungen, die über die Zugehörigkeit zu
Auswertungen entscheiden (Typ · Aktiv · Anschaffung · Stilllegung), stehen im
Aktivitätsprotokoll — in der Sitzung des Aufrufers (N-532).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes.datenquellen import (
    InvertSetRequest,
    QuelleSetRequest,
    set_feld_invert,
    set_feld_quelle,
)
from backend.api.routes.investitionen.crud import (
    InvestitionCreate,
    InvestitionUpdate,
    create_investition,
    delete_investition,
    update_investition,
)
from backend.models import Anlage, Investition
from backend.models.activity_log import ActivityLog
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.services.datenquellen_mapping_sync import feld_id, inv_feld_der_investition
from backend.tests.test_263_innengeraete import MIT_LISTE


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="Aufräumen", leistung_kwp=10.0, installationsdatum=date(2024, 1, 1))
    db.add(a)
    await db.flush()
    return a


async def _wallbox(db, anlage, name="WB") -> Investition:
    return await create_investition(InvestitionCreate(
        anlage_id=anlage.id, typ="wallbox", bezeichnung=name,
        anschaffungsdatum=date(2024, 1, 1),
    ), db)


async def _ordne_zu(db, anlage, inv_id):
    """Drei Ablagen über die Fläche: HA-Energie, Gateway-Live, Vorzeichen."""
    await set_feld_quelle(anlage.id, feld_id(("inv_energy", inv_id, "ladung_kwh")),
                          QuelleSetRequest(quelle="ha_app", entity_id=f"sensor.wb{inv_id}"), db)
    await set_feld_quelle(anlage.id, feld_id(("inv_live", inv_id, "leistung_w")),
                          QuelleSetRequest(quelle="mqtt_gateway", quell_topic=f"wb/{inv_id}/p"), db)
    await set_feld_invert(anlage.id, feld_id(("inv_live", inv_id, "leistung_w")),
                          InvertSetRequest(invertieren=True), db)


def _reste(mapping: dict, inv_id: int) -> dict:
    return {
        ablage: [f for f in (mapping.get(ablage) or {}) if inv_feld_der_investition(f, inv_id) is not None]
        for ablage in ("quellen", "invertieren")
    } | {"investitionen": [k for k in (mapping.get("investitionen") or {}) if k == str(inv_id)]}


# ─── N-559 ───────────────────────────────────────────────────────────────────

def test_feld_der_investition_trennt_7_von_70():
    assert inv_feld_der_investition("inv_live_7_leistung_w-3", 7) == "leistung_w-3"
    assert inv_feld_der_investition("inv_live_70_leistung_w", 7) is None
    assert inv_feld_der_investition("inv_energy_7_ladung_kwh", "7") == "ladung_kwh"
    assert inv_feld_der_investition("basis_energy_netzbezug_kwh", 7) is None


async def test_loeschen_raeumt_alle_drei_ablagen_und_laesst_die_nachbarin(db):
    a = await _anlage(db)
    weg = await _wallbox(db, a, "Weg")
    bleibt = await _wallbox(db, a, "Bleibt")
    await _ordne_zu(db, a, weg.id)
    await _ordne_zu(db, a, bleibt.id)
    await db.refresh(a)
    assert all(_reste(a.sensor_mapping, weg.id).values()), "Vorbedingung: die Fläche hat alle drei Ablagen beschrieben"

    await delete_investition(weg.id, db)
    await db.commit()
    await db.refresh(a)

    assert _reste(a.sensor_mapping, weg.id) == {"quellen": [], "invertieren": [], "investitionen": []}
    rest_nachbar = _reste(a.sensor_mapping, bleibt.id)
    assert rest_nachbar["quellen"] and rest_nachbar["invertieren"] and rest_nachbar["investitionen"]


async def test_wiederverwendete_id_erbt_keine_zuordnung(db):
    """Die Folge, gegen die N-559 baut: dieselbe ID, eine andere Komponente."""
    a = await _anlage(db)
    alt = await _wallbox(db, a, "Alt")
    await _ordne_zu(db, a, alt.id)
    alt_id = alt.id
    await delete_investition(alt_id, db)
    await db.commit()

    neu = await _wallbox(db, a, "Neu")
    await db.commit()
    assert neu.id == alt_id, "SQLite vergibt die höchste ID nach dem Löschen wieder (kein AUTOINCREMENT)"
    await db.refresh(a)
    assert _reste(a.sensor_mapping, neu.id) == {"quellen": [], "invertieren": [], "investitionen": []}


async def test_innengeraet_entfernen_ueber_die_flaeche(db):
    a = await _anlage(db)
    wp = await create_investition(InvestitionCreate(
        anlage_id=a.id, typ="waermepumpe", bezeichnung="Klima",
        anschaffungsdatum=date(2025, 1, 1), parameter=MIT_LISTE,
    ), db)
    for gid in (1, 3):
        await set_feld_quelle(a.id, feld_id(("inv_energy", wp.id, f"betriebsart_strom_kuehlen_kwh-{gid}")),
                              QuelleSetRequest(quelle="ha_app", entity_id=f"sensor.k{gid}"), db)
        await set_feld_quelle(a.id, feld_id(("inv_live", wp.id, f"leistung_w-{gid}")),
                              QuelleSetRequest(quelle="keine"), db)
        await set_feld_invert(a.id, feld_id(("inv_live", wp.id, f"leistung_w-{gid}")),
                              InvertSetRequest(invertieren=True), db)
    await db.commit()

    await update_investition(wp.id, InvestitionUpdate(parameter={
        "wp_art": "luft_luft", "innengeraete": [{"id": 1, "bezeichnung": "Büro"}]}), db=db)
    await db.commit()
    await db.refresh(a)

    for ablage in ("quellen", "invertieren"):
        felder = [inv_feld_der_investition(f, wp.id) for f in (a.sensor_mapping.get(ablage) or {})]
        assert not [f for f in felder if f and f.endswith("-3")], (ablage, felder)
        assert [f for f in felder if f and f.endswith("-1")], (ablage, "Innengerät 1 bleibt")


# ─── N-560 ───────────────────────────────────────────────────────────────────

async def _zeilen(db, anlage_id):
    return list((await db.execute(
        select(ActivityLog).where(ActivityLog.kategorie == "investitionen",
                                  ActivityLog.anlage_id == anlage_id).order_by(ActivityLog.id)
    )).scalars().all())


async def test_anlegen_protokolliert_in_der_sitzung(db):
    a = await _anlage(db)
    await _wallbox(db, a)
    # kein Commit: die Zeile ist in DIESER Sitzung schon da (N-532); eine eigene
    # Verbindung schriebe in die Wegwerf-Datenbank des Laufs (N-414).
    zeilen = await _zeilen(db, a.id)
    assert [z.aktion for z in zeilen] == ["Komponente angelegt"]
    assert zeilen[0].details == "Aufräumen · Wallbox · WB"


async def test_aendern_protokolliert_nur_die_zugehoerigkeit(db):
    a = await _anlage(db)
    wb = await _wallbox(db, a)
    await update_investition(wb.id, InvestitionUpdate(bezeichnung="WB2", parameter={"x": 1}), db=db)
    assert [z.aktion for z in await _zeilen(db, a.id)] == ["Komponente angelegt"]

    await update_investition(wb.id, InvestitionUpdate(
        aktiv=False, stilllegungsdatum=date(2026, 9, 1)), db=db)
    zeilen = await _zeilen(db, a.id)
    assert [z.aktion for z in zeilen] == ["Komponente angelegt", "Komponente geändert"]
    assert zeilen[1].details == "Aufräumen · Wallbox · WB2 · Aktiv: ja → nein · Stilllegung: — → 01.09.2026"


async def test_gleicher_wert_ist_keine_aenderung(db):
    a = await _anlage(db)
    wb = await _wallbox(db, a)
    await update_investition(wb.id, InvestitionUpdate(aktiv=True, anschaffungsdatum=date(2024, 1, 1)), db=db)
    assert [z.aktion for z in await _zeilen(db, a.id)] == ["Komponente angelegt"]


async def test_loeschen_protokolliert(db):
    a = await _anlage(db)
    wb = await _wallbox(db, a)
    await delete_investition(wb.id, db)
    zeilen = await _zeilen(db, a.id)
    assert [z.aktion for z in zeilen] == ["Komponente angelegt", "Komponente gelöscht"]
    assert zeilen[1].details == "Aufräumen · Wallbox · WB"
