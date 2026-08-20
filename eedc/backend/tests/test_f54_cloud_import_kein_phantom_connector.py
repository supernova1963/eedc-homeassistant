"""F-54 (#390): Ein Cloud-Import ist kein Geräte-Connector.

`Anlage.connector_config` ist ein **Mehrzweckfeld** — dieselbe Spalte trägt den
Geräte-Connector (`connector_id`, `host`, `meter_snapshots` …) **und** die
Cloud-Import-Quellen (`cloud_import`, `services/cloud_import/quellen.py`).
Vier Stellen fragten „Spalte nicht leer?" statt „Geräte-Connector da?":

* `GET /connectors/status/{id}` meldete `configured: true` mit leerem Gerät,
  leerem Host und 0 Snapshots — die Fläche zeigte „Connector aktiv".
* Der Daten-Checker meldete „Connector „Connector" liefert für MM/JJJJ keinen
  Wert" für ein Gerät, das nie eingerichtet wurde (P-6: unauflösbar).
* `POST /connectors/fetch/{id}` endete mit „Unbekannter Connector: None".
* `DELETE /connectors/{id}` setzte die ganze Spalte auf `None` und nahm damit
  die **Cloud-Import-Zugangsdaten** mit — Datenverlust durch einen Klick auf
  einen Knopf, der neben einem Phantom-Gerät stand.

Gemeldet von gruaGit (Discussion #390, 19./20.08.2026, vier Bilder gesehen).

⭐ **Die Proben stellen den Zustand über den ECHTEN Schreibpfad her** —
`setze_quelle` aus dem Cloud-Import, nicht ein von Hand gebautes Dict. Genau
daran hing der Fehler: keine Fixture hatte diesen Zustand je erzeugt, weil
niemand ihn für erreichbar hielt. [[feedback_probe_unerreichbarer_zustand]]
"""

from __future__ import annotations

import pytest

from backend.models import Anlage
from backend.services.cloud_import.quellen import lade_quellen, setze_quelle
from backend.services.connectors.fetch_service import (
    ConnectorNotConfigured,
    fetch_and_store_snapshot,
    hat_geraete_connector,
    ohne_geraete_connector,
)


def _nur_cloud_import() -> dict:
    """Der Zustand aus #390 — über den produktiven Schreibpfad erzeugt."""
    return setze_quelle(
        None,
        provider_id="ecoflow_powerocean",
        credentials={"access_key": "AAA", "secret_key": "BBB", "serial": "SN123"},
    )


def _geraete_connector() -> dict:
    """So und nur so schreibt `POST /connectors/setup` — beide Felder."""
    return {
        "connector_id": "fronius_solar_api",
        "host": "192.168.1.50",
        "username": "customer",
        "password": "",
        "geraet_name": "Fronius GEN24",
        "meter_snapshots": {},
        "last_fetch": None,
    }


# ---------------------------------------------------------------- Prädikat

def test_cloud_import_allein_ist_kein_geraete_connector():
    config = _nur_cloud_import()
    # Gegenprobe: die Spalte ist nicht leer — genau daran scheiterte `if not config`.
    assert config, "Der Schreibpfad muss etwas hinterlassen, sonst prüft der Test nichts"
    assert len(lade_quellen(config)) == 1
    assert hat_geraete_connector(config) is False


def test_geraete_connector_wird_erkannt():
    assert hat_geraete_connector(_geraete_connector()) is True


@pytest.mark.parametrize("config", [
    None,
    {},
    {"connector_id": "fronius_solar_api"},          # ohne Host kein Abruf möglich
    {"host": "192.168.1.50"},                       # ohne Typ kein Connector
    {"connector_id": "", "host": "192.168.1.50"},   # leer ist nicht gesetzt
])
def test_unvollstaendiges_gilt_nicht_als_eingerichtet(config):
    assert hat_geraete_connector(config) is False


# ------------------------------------------------------- Abruf (E5) + Status

async def test_abruf_nennt_die_fehlende_einrichtung_statt_none():
    anlage = Anlage(
        anlagenname="Nur Cloud", leistung_kwp=10.0,
        connector_config=_nur_cloud_import(),
    )
    with pytest.raises(ConnectorNotConfigured) as exc:
        await fetch_and_store_snapshot(anlage)
    # Der alte Text war „Unbekannter Connector: None" — eine Aussage über ein
    # Gerät, das der Anwender nie angelegt hat.
    assert "None" not in str(exc.value)
    assert "Geräte-Connector" in str(exc.value)


async def test_checker_schweigt_ohne_geraete_connector():
    from backend.services.daten_checker import DatenChecker

    anlage = Anlage(
        anlagenname="Nur Cloud", leistung_kwp=10.0,
        connector_config=_nur_cloud_import(),
    )
    assert await DatenChecker(db=None)._check_connector_monatswert(anlage) == []


async def test_checker_meldet_weiterhin_beim_echten_connector():
    """Gegenprobe: die Regel darf nicht alles stumm schalten."""
    from datetime import datetime, timedelta, timezone
    from backend.services.daten_checker import DatenChecker

    alt = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    config = _geraete_connector()
    config["meter_snapshots"] = {alt: {"pv_erzeugung_kwh": 800.0}}
    anlage = Anlage(anlagenname="Echt", leistung_kwp=10.0, connector_config=config)

    befunde = await DatenChecker(db=None)._check_connector_monatswert(anlage)
    assert len(befunde) == 1


# ------------------------------------------------------------ Entfernen (E4)

def test_entfernen_laesst_die_cloud_import_quellen_stehen():
    config = _nur_cloud_import()
    config.update(_geraete_connector())
    assert hat_geraete_connector(config) is True

    rest = ohne_geraete_connector(config)

    assert hat_geraete_connector(rest) is False
    assert "host" not in rest and "meter_snapshots" not in rest
    # Der Kern: die Zugangsdaten überleben das Entfernen des Geräts.
    assert len(lade_quellen(rest)) == 1
    assert lade_quellen(rest)[0]["provider_id"] == "ecoflow_powerocean"


def test_entfernen_ohne_fremde_schluessel_raeumt_vollstaendig_ab():
    """Ohne Cloud-Import bleibt nichts übrig — die Route setzt dann `None`."""
    assert ohne_geraete_connector(_geraete_connector()) == {}


# ------------------------------------- Die zwei Routen, die der Melder sah

async def _anlage_in_db(db, config: dict) -> Anlage:
    anlage = Anlage(anlagenname="Nur Cloud", leistung_kwp=10.0, connector_config=config)
    db.add(anlage)
    await db.flush()
    return anlage


async def test_status_route_meldet_keinen_connector_bei_reinem_cloud_import(db):
    """Bild 1 aus #390: „Connector aktiv", Gerät –, Host leer, 0 Snapshots."""
    from backend.api.routes.connector import get_connector_status

    anlage = await _anlage_in_db(db, _nur_cloud_import())
    antwort = await get_connector_status(anlage.id, db=db)
    assert antwort == {"configured": False}


async def test_status_route_meldet_den_echten_connector_weiterhin(db):
    from backend.api.routes.connector import get_connector_status

    anlage = await _anlage_in_db(db, _geraete_connector())
    antwort = await get_connector_status(anlage.id, db=db)
    assert antwort["configured"] is True
    assert antwort["connector_id"] == "fronius_solar_api"


async def test_entfernen_route_ruehrt_den_cloud_import_nicht_an(db):
    from fastapi import HTTPException
    from backend.api.routes.connector import remove_connector

    anlage = await _anlage_in_db(db, _nur_cloud_import())
    with pytest.raises(HTTPException) as exc:
        await remove_connector(anlage.id, db=db)
    assert exc.value.status_code == 400
    # Der Kern: die Zugangsdaten sind noch da, nicht `None`.
    assert len(lade_quellen(anlage.connector_config)) == 1


async def test_entfernen_route_loescht_nur_das_geraet(db):
    from backend.api.routes.connector import remove_connector

    config = _nur_cloud_import()
    config.update(_geraete_connector())
    anlage = await _anlage_in_db(db, config)

    assert (await remove_connector(anlage.id, db=db))["erfolg"] is True

    assert hat_geraete_connector(anlage.connector_config) is False
    assert len(lade_quellen(anlage.connector_config)) == 1


async def test_entfernen_route_leert_die_spalte_ohne_fremde_schluessel(db):
    """Ohne Cloud-Import bleibt das bisherige Verhalten: Spalte auf `None`."""
    from backend.api.routes.connector import remove_connector

    anlage = await _anlage_in_db(db, _geraete_connector())
    await remove_connector(anlage.id, db=db)
    assert anlage.connector_config is None


def test_entfernliste_ist_benannt_nicht_invertiert():
    """Ein unbekannter Schlüssel darf einen Rest kosten, nie einen Verlust.

    Wäre `ohne_geraete_connector` als „alles außer bekannt" gebaut, würde jede
    künftige Nutzung derselben Spalte beim Entfernen des Geräts mitgelöscht —
    dieselbe Klasse wie der Fehler, den F-54 behebt.
    """
    config = _geraete_connector()
    config["irgendwas_neues"] = {"wichtig": True}
    assert ohne_geraete_connector(config) == {"irgendwas_neues": {"wichtig": True}}
