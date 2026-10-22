"""N-762 (#430, Mathek): die WS-Metadaten-Liste erneuert sich nach einem Fehlschlag.

Ohne Recorder-Datei liest eedc `recorder/list_statistic_ids` über die
WebSocket-API und hält die Liste im Client (`HAStatisticsWebsocket.metadaten`).
Bis N-762 wurde sie einmal je Prozess geholt und nie erneuert: ein Sensor, dessen
Langzeitstatistik nach dem eedc-Start begann (Melder: Utility-Meter-Tarife am
19.10. um 11:00 angelegt), blieb für Snapshots, Tag und Daten-Checker bis zum
Neustart «nicht in der HA-Statistik». Im DB-Zweig (`statistics_meta` per SQL)
gab es das nie.

Jetzt holt `_ws_meta` die Liste bei einem Fehlschlag **einmal je
`_META_CACHE_TTL`** (300 s) neu. Die Probe läuft durch den echten Client (eigener
`_befehl` statt Netz, echte sync→async-Brücke) und stellt die Uhr des Service
(`time.monotonic` im Modul), kein `sleep`.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import backend.services.ha_statistics_service as ha_mod
from backend.models import Anlage, Investition  # noqa: F401
from backend.services.daten_checker import CheckSeverity
from backend.services.ha_statistics_service import HAStatisticsService
from backend.services.ha_statistics_ws import HAStatisticsWebsocket

NEU = "sensor.wp_strom_heizen_tarif"   # Statistik beginnt erst nach dem Start
ALT = "sensor.netzbezug"               # von Anfang an in der Statistik


def _eintrag(sid: str) -> dict:
    return {
        "statistic_id": sid, "statistics_unit_of_measurement": "kWh",
        "display_unit_of_measurement": "kWh", "has_sum": True, "has_mean": False,
        "source": "recorder",
    }


class _Ha:
    """Was HA auf `recorder/list_statistic_ids` antwortet — veränderlich, mit Zähler."""

    def __init__(self, sids: list[str]):
        self.sids = list(sids)
        self.listen_abrufe = 0

    async def befehl(self, payload):
        assert payload["type"] == "recorder/list_statistic_ids", payload
        self.listen_abrufe += 1
        return [_eintrag(s) for s in self.sids]


@pytest.fixture
def uhr(monkeypatch):
    """Monotone Uhr des Service-Moduls — nur dort, asyncio bleibt unberührt."""
    stand = {"t": 1000.0}
    monkeypatch.setattr(ha_mod, "time", SimpleNamespace(monotonic=lambda: stand["t"]))
    return stand


def _service(ha: _Ha) -> HAStatisticsService:
    """Service ohne Recorder-DB mit echtem WS-Client, dessen Befehle `ha` beantwortet."""
    svc = HAStatisticsService()
    svc._initialized = True
    svc._engine = None
    client = HAStatisticsWebsocket("http://testhost:8123/api", "geheim")
    client._befehl = ha.befehl  # type: ignore[assignment]
    svc._ws_client = client
    return svc


def test_fehlender_sensor_bleibt_none_und_fragt_innerhalb_des_ttl_nur_einmal_nach(uhr):
    ha = _Ha([ALT])
    svc = _service(ha)

    assert svc.get_metadata(None, NEU) is None
    # Erstabruf der Liste + eine Erneuerung beim ersten Fehlschlag.
    assert ha.listen_abrufe == 2

    uhr["t"] += 120
    ha.sids.append(NEU)   # HA hat die Statistik inzwischen — eedc fragt noch nicht
    assert svc.get_metadata(None, NEU) is None
    assert svc.get_metadata(None, "sensor.gibt_es_nicht") is None
    assert ha.listen_abrufe == 2, "innerhalb des TTL darf kein Fehlschlag die Liste erneut holen"


def test_neuer_sensor_wirkt_nach_ablauf_des_ttl_ohne_neustart(uhr):
    ha = _Ha([ALT])
    svc = _service(ha)
    assert svc.get_metadata(None, NEU) is None

    ha.sids.append(NEU)
    uhr["t"] += svc._META_CACHE_TTL + 1
    meta = svc.get_metadata(None, NEU)
    assert meta is not None and meta.has_sum is True and meta.unit == "kWh"
    assert ha.listen_abrufe == 3

    # Die Zählung und die Erreichbarkeitsprobe lesen dieselbe (erneuerte) Liste.
    assert svc.count_statistics_sensors() == 2
    assert svc._ws_client.erreichbar() is True
    assert ha.listen_abrufe == 3, "Zählung/erreichbar dürfen keinen zweiten Cache füllen"


def test_treffer_holen_die_liste_nicht_neu(uhr):
    """Bitgleich wie vorher: ohne Fehlschlag keine Erneuerung, auch nach Stunden."""
    ha = _Ha([ALT, NEU])
    svc = _service(ha)
    for _ in range(3):
        assert svc.get_metadata(None, ALT) is not None
        assert svc.get_metadata(None, NEU) is not None
        uhr["t"] += 3600
    assert ha.listen_abrufe == 1


def test_filter_valid_sensor_ids_sieht_den_neuen_sensor_nach_ablauf(uhr):
    ha = _Ha([ALT])
    svc = _service(ha)
    assert svc.filter_valid_sensor_ids([ALT, NEU]) == ([ALT], [NEU])

    ha.sids.append(NEU)
    uhr["t"] += svc._META_CACHE_TTL + 1
    assert svc.filter_valid_sensor_ids([ALT, NEU]) == ([ALT, NEU], [])


def test_verbindungswechsel_setzt_die_erneuerung_zurueck(uhr):
    ha = _Ha([ALT])
    svc = _service(ha)
    assert svc.get_metadata(None, NEU) is None
    assert svc._ws_meta_erneuert is not None
    svc.setze_ha_verbindung(None, None)
    assert svc._ws_meta_erneuert is None


async def test_daten_checker_sieht_den_neuen_sensor_nach_ablauf(db, monkeypatch, uhr):
    """`_check_sensor_mapping_lts` → `filter_summen_faehige_sensor_ids` → `get_metadata`:
    vor Ablauf «nicht in HA-Long-Term-Statistics», danach OK — ohne Neustart."""
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="NIBE S1256",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": ALT}},
        "investitionen": {str(inv.id): {"felder": {
            "stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": NEU},
        }}},
    }
    await db.commit()
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()

    ha = _Ha([ALT])
    svc = _service(ha)
    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: svc)

    vorher = await DatenChecker(db)._check_sensor_mapping_lts(anlage)
    warnungen = [r for r in vorher if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1 and "nicht in HA-Long-Term-Statistics" in warnungen[0].meldung, (
        [r.meldung for r in vorher]
    )
    assert NEU in (warnungen[0].details or "")

    ha.sids.append(NEU)
    uhr["t"] += svc._META_CACHE_TTL + 1
    nachher = await DatenChecker(db)._check_sensor_mapping_lts(anlage)
    assert [r.schwere for r in nachher] == [CheckSeverity.OK], [r.meldung for r in nachher]
