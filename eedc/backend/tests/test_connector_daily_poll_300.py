"""Täglicher Connector-Poll unabhängig vom MQTT-Inbound (#300, Safi105).

Der automatische Connector-Abruf hing bis v3.40.0 an der MQTT-Bridge, die
nur bei aktivem MQTT-Inbound startet. Ohne MQTT blieben die Snapshots leer
und der Monatsabschluss-Vorschlag füllte sich nur über manuelles
„Aktuelle Daten anfordern".

Getestet wird der Scheduler-Job `connector_daily_poll_job` über den
gemeinsamen Fetch-Pfad (`fetch_service.fetch_and_store_snapshot`, gleiche
Logik wie POST /connectors/fetch):
  - Snapshot + last_fetch werden geschrieben
  - Anlagen ohne Connector-Config werden übersprungen
  - eine fehlerhafte Anlage bricht die Schleife nicht ab
  - zweiter Lauf am selben Tag erzeugt keinen Drift in der Monats-Differenz
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage
from backend.services.connectors.base import MeterSnapshot
from backend.services.connectors.fetch_service import (
    ConnectorNotConfigured,
    fetch_and_store_snapshot,
)
from backend.services.scheduler import connector_daily_poll_job


def _config(host: str = "192.168.1.50") -> dict:
    return {
        "connector_id": "fronius_solar_api",
        "host": host,
        "username": "User",
        "password": base64.b64encode(b"geheim").decode(),
        "meter_snapshots": {},
    }


class _FakeConnector:
    """Liefert feste Zählerstände; Host 'kaputt' simuliert einen Lesefehler."""

    def __init__(self, pv_kwh: float = 1000.0):
        self.pv_kwh = pv_kwh

    async def read_meters(self, host, username, password):
        if host == "kaputt":
            raise ConnectionError("Gerät nicht erreichbar")
        return MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=self.pv_kwh,
            einspeisung_kwh=400.0,
            netzbezug_kwh=200.0,
        )


@pytest.fixture
def fake_connector(monkeypatch):
    connector = _FakeConnector()
    monkeypatch.setattr(
        "backend.services.connectors.fetch_service.get_connector",
        lambda connector_id: connector,
    )
    return connector


@pytest.fixture
def patched_session(monkeypatch, db: AsyncSession):
    """Lenkt das `get_session` des Scheduler-Jobs auf die Test-DB um."""

    @asynccontextmanager
    async def _fake_get_session():
        yield db
        await db.commit()

    monkeypatch.setattr("backend.core.database.get_session", _fake_get_session)
    return db


async def test_job_schreibt_snapshots_und_ueberlebt_fehler_anlage(
    db: AsyncSession, fake_connector, patched_session
):
    # Fehler-Anlage zuerst (niedrigere ID) — beweist, dass die Schleife weiterläuft
    kaputt = Anlage(anlagenname="Kaputt", leistung_kwp=5.0,
                    connector_config=_config(host="kaputt"))
    ohne = Anlage(anlagenname="OhneConnector", leistung_kwp=5.0)
    ok = Anlage(anlagenname="Safi", leistung_kwp=10.0, connector_config=_config())
    db.add_all([kaputt, ohne, ok])
    await db.commit()

    await connector_daily_poll_job()

    await db.refresh(ok)
    await db.refresh(kaputt)
    await db.refresh(ohne)

    snaps = ok.connector_config["meter_snapshots"]
    assert len(snaps) == 1
    snap = next(iter(snaps.values()))
    assert snap["pv_erzeugung_kwh"] == 1000.0
    assert ok.connector_config["last_fetch"] in snaps

    assert kaputt.connector_config["meter_snapshots"] == {}
    assert "last_fetch" not in kaputt.connector_config
    assert ohne.connector_config is None


async def test_zweiter_lauf_am_selben_tag_erzeugt_keinen_drift(
    db: AsyncSession, fake_connector, patched_session
):
    anlage = Anlage(anlagenname="Safi", leistung_kwp=10.0, connector_config=_config())
    db.add(anlage)
    await db.commit()

    await connector_daily_poll_job()
    await connector_daily_poll_job()  # Zählerstand unverändert

    await db.refresh(anlage)
    snaps = anlage.connector_config["meter_snapshots"]
    assert len(snaps) == 2

    # Monats-Differenz aus den Snapshots (Read-Pfad von Monatsabschluss +
    # /connectors/monatswerte): unveränderte Zähler → Differenz 0, kein Drift.
    from backend.api.routes.connector import _calc_month_delta

    now = datetime.now(timezone.utc)
    delta = _calc_month_delta(snaps, now.year, now.month)
    assert delta is not None
    assert all(v == 0 for v in delta.werte.values())
    # Die gemessene Abdeckung wandert mit (beide Snapshots von heute).
    assert delta.abdeckung_von <= delta.abdeckung_bis


async def test_fetch_service_ohne_config_wirft_connector_not_configured(
    db: AsyncSession,
):
    anlage = Anlage(anlagenname="Leer", leistung_kwp=5.0)
    db.add(anlage)
    await db.commit()

    with pytest.raises(ConnectorNotConfigured):
        await fetch_and_store_snapshot(anlage)


async def test_fetch_service_berechnet_differenz_zum_vorherigen_snapshot(
    db: AsyncSession, fake_connector
):
    anlage = Anlage(anlagenname="Safi", leistung_kwp=10.0, connector_config=_config())
    db.add(anlage)
    await db.commit()

    await fetch_and_store_snapshot(anlage)
    fake_connector.pv_kwh = 1012.5  # Tagesproduktion 12.5 kWh
    result = await fetch_and_store_snapshot(anlage)

    assert result["differenz"]["pv_erzeugung_kwh"] == 12.5
    assert len(anlage.connector_config["meter_snapshots"]) == 2
