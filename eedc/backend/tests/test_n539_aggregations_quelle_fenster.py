"""N-539 — die Vorbedingung des Tages-Laufs fragt nach DIESEM Tag, nicht nach „irgendwann danach".

`ermittle_aggregations_quelle` hatte von #135 (22.04.2026) bis N-539 keine obere Fenstergrenze:
`timestamp >= Vortag` — jeder Tag bis zum letzten MQTT-Snapshot galt als „Quelle vorhanden".
Gemessen an einer r28-Kopie (20.09.2026): `aggregate_day(SCHEDULER)` schrieb fuer einen Tag
Monate vor dem ersten Snapshot 24 leere Stunden und ersetzte eine gefuellte `ha_sensor`-Tageszeile
(peak_pv 7,425 kW) durch dieselbe leere Zeile. Drei Aufrufer teilen die Bedingung: der Aggregator
(steigt aus oder schreibt), der Tag-Status (nennt den Grund) und der Daten-Checker (bietet den
Reparatur-Knopf fuer den aeltesten Befund-Tag an oder nicht).

Die Proben hier stellen je einen Tag IM Fenster (Quelle da) und einen Tag AUSSERHALB (nur spaeter
oder nur frueher Snapshots) — Sprengsatz ist die entfernte obere Grenze.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.aggregations_quelle import ermittle_aggregations_quelle
from backend.services.energie_profil.source import Source

TAG = date(2026, 5, 15)


async def _anlage_ohne_leistungszuordnung(db) -> Anlage:
    anlage = Anlage(anlagenname="N-539", leistung_kwp=10.0, standort_plz="10115",
                    standort_land="DE", sensor_mapping={})
    db.add(anlage)
    await db.flush()
    return anlage


async def _snapshot(db, anlage_id: int, wann: datetime) -> None:
    db.add(MqttEnergySnapshot(anlage_id=anlage_id, timestamp=wann, energy_key="netzbezug", value_kwh=100.0))
    await db.flush()


def _um(tag: date, stunde: int = 12) -> datetime:
    return datetime.combine(tag, datetime.min.time()) + timedelta(hours=stunde)


@pytest.mark.asyncio
@pytest.mark.parametrize("wann", [_um(TAG - timedelta(days=1), 23), _um(TAG, 0), _um(TAG, 23)],
                         ids=["vortag-23h", "tag-00h", "tag-23h"])
async def test_snapshot_im_fenster_ist_eine_quelle(db, wann):
    anlage = await _anlage_ohne_leistungszuordnung(db)
    await _snapshot(db, anlage.id, wann)
    q = await ermittle_aggregations_quelle(db, anlage, TAG)
    assert q.mqtt_energie is True and q.vorhanden is True


@pytest.mark.asyncio
@pytest.mark.parametrize("wann", [_um(TAG + timedelta(days=1), 0), _um(TAG + timedelta(days=30)),
                                  _um(TAG - timedelta(days=2), 23)],
                         ids=["folgetag-00h", "30-tage-spaeter", "vorvortag"])
async def test_snapshot_ausserhalb_ist_keine_quelle(db, wann):
    """Der Kern von N-539: ein Snapshot Wochen SPAETER machte den Tag bisher zur versorgten Quelle."""
    anlage = await _anlage_ohne_leistungszuordnung(db)
    await _snapshot(db, anlage.id, wann)
    q = await ermittle_aggregations_quelle(db, anlage, TAG)
    assert q.mqtt_energie is False and q.vorhanden is False


_PATCHES = dict(
    tv="backend.services.live_power_service.LivePowerService.get_tagesverlauf",
    komp="backend.services.snapshot.aggregator.get_komponenten_tageskwh",
    counter="backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
)


async def _aggregate(anlage, db):
    from backend.services.energie_profil.aggregator import aggregate_day
    with patch(_PATCHES["tv"], new=AsyncMock(return_value={"serien": [], "punkte": []})), \
         patch(_PATCHES["komp"], new=AsyncMock(return_value={})), \
         patch(_PATCHES["counter"], new=AsyncMock(return_value={})):
        return await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER)


@pytest.mark.asyncio
async def test_aggregate_day_laesst_einen_tag_ohne_quelle_unangetastet(db):
    """Die gefuellte Tageszeile (aus HA-Statistik) ueberlebt einen Lauf, der nichts holen kann."""
    anlage = await _anlage_ohne_leistungszuordnung(db)
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=TAG, stunden_verfuegbar=24,
                                datenquelle="ha_sensor", peak_pv_kw=7.425, source_provenance={}))
    await _snapshot(db, anlage.id, _um(TAG + timedelta(days=30)))
    await db.commit()

    assert await _aggregate(anlage, db) is None

    tz = (await db.execute(
        __import__("sqlalchemy").select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == TAG)
    )).scalar_one()
    assert tz.datenquelle == "ha_sensor" and tz.peak_pv_kw == 7.425


@pytest.mark.asyncio
async def test_aggregate_day_schreibt_weiter_wenn_der_tag_eine_quelle_hat(db):
    """Gegenrichtung: mit Snapshot im Fenster laeuft der synthetische Slot-Pfad wie bisher."""
    anlage = await _anlage_ohne_leistungszuordnung(db)
    await _snapshot(db, anlage.id, _um(TAG - timedelta(days=1), 23))
    await db.commit()
    tz = await _aggregate(anlage, db)
    assert tz is not None and tz.datum == TAG


@pytest.mark.asyncio
async def test_tag_status_nennt_die_luecke_ohne_reparaturweg(db):
    """Der Tag-Status bietet fuer einen Tag ohne Quelle keinen Knopf an, der nichts holen wuerde."""
    from backend.services.energie_profil.tag_status import baue_tag_status
    anlage = await _anlage_ohne_leistungszuordnung(db)
    await _snapshot(db, anlage.id, _um(TAG + timedelta(days=30)))
    await db.commit()
    with patch("backend.services.energie_profil.tag_status._erwartete_keys",
               new=AsyncMock(return_value=({}, {"netzbezug"}))), \
         patch("backend.services.energie_profil.tag_status._ha_tageswerte",
               new=AsyncMock(return_value={"netzbezug": 5.0})):
        status = await baue_tag_status(db, anlage, TAG)
    assert status.lage == "luecke_ohne_reparaturweg", status.lage
    assert status.aktion_kind is None
