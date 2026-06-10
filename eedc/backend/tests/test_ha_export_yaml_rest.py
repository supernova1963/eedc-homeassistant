"""REST-Export-YAML: erreichbarer Host statt Pseudo-Template — rapahl 2026-06-10.

Das generierte Snippet enthielt wörtlich `http://{{ eedc_addon_host }}:8099/…`.
HA wertet in `rest: resource:` keine Templates aus — 1:1 eingefügt war die URL
ungültig, das rest-Setup schlug fehl und es entstanden KEINE Entitäten; die
200er im eedc-Log stammten vom eigenen Browser auf der Export-Seite.

Fix: Host-Auflösung ?host=-Override → Request-Host (direkter Aufruf) →
Platzhalter `<EEDC-IP>` (nur hinter Ingress, mit Klartext-Anleitung).
Dazu: Port-8099-Freigabe-Hinweis im Snippet selbst, keine leeren
`unit_of_measurement: ""`-Zeilen mehr.
"""

from __future__ import annotations

from datetime import date

from starlette.requests import Request

from backend.api.routes.ha_export import get_ha_yaml_snippet
from backend.models import Anlage, Monatsdaten


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/ha/export/yaml/1",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


async def _anlage_mit_daten(db) -> Anlage:
    anlage = Anlage(anlagenname="YAML-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=5,
        einspeisung_kwh=600.0, netzbezug_kwh=100.0,
    ))
    await db.commit()
    return anlage


async def test_direkter_aufruf_uebernimmt_request_host(db):
    anlage = await _anlage_mit_daten(db)
    req = _make_request({"host": "192.168.1.10:8099"})

    res = await get_ha_yaml_snippet(anlage.id, req, host=None, db=db)

    assert f'resource: "http://192.168.1.10:8099/api/ha/export/sensors/{anlage.id}"' in res.yaml
    assert "{{ eedc_addon_host }}" not in res.yaml
    assert "<EEDC-IP>" not in res.yaml
    # Port-Freigabe-Hinweis steht im Snippet selbst, nicht nur im Response-Feld.
    assert "Port 8099" in res.yaml
    assert res.sensor_count > 0


async def test_ingress_faellt_auf_platzhalter_mit_anleitung(db):
    anlage = await _anlage_mit_daten(db)
    req = _make_request({
        "host": "homeassistant.local:8123",
        "x-ingress-path": "/api/hassio_ingress/abc123",
    })

    res = await get_ha_yaml_snippet(anlage.id, req, host=None, db=db)

    # Der HA-Proxy-Host darf NICHT in die resource-Zeile.
    assert "homeassistant.local:8123" not in res.yaml
    assert f'resource: "http://<EEDC-IP>:8099/api/ha/export/sensors/{anlage.id}"' in res.yaml
    assert "WICHTIG" in res.yaml
    assert "Ingress" in res.hinweis


async def test_host_override_gewinnt_und_ergaenzt_port(db):
    anlage = await _anlage_mit_daten(db)
    req = _make_request({
        "host": "homeassistant.local:8123",
        "x-ingress-path": "/api/hassio_ingress/abc123",
    })

    res = await get_ha_yaml_snippet(anlage.id, req, host="10.0.0.2", db=db)

    assert f'resource: "http://10.0.0.2:8099/api/ha/export/sensors/{anlage.id}"' in res.yaml
    assert "<EEDC-IP>" not in res.yaml


async def test_keine_leeren_unit_zeilen(db):
    anlage = await _anlage_mit_daten(db)
    req = _make_request({"host": "192.168.1.10:8099"})

    res = await get_ha_yaml_snippet(anlage.id, req, host=None, db=db)

    assert 'unit_of_measurement: ""' not in res.yaml


# ── M-A: MQTT-Auto-Publish Start-Publish (Scheduler) ────────────────────────

async def test_mqtt_auto_publish_job_feuert_zeitnah_nach_boot(monkeypatch):
    """Der Auto-Publish-Job darf nicht erst nach einem vollen Intervall feuern —
    neue Sensor-Definitionen wären nach einem Add-on-Update sonst bis zu 60 min
    unsichtbar (Rainer/Gernot 2026-06-10). Pin: erster Lauf deutlich vor dem
    Intervall-Default."""
    from datetime import datetime, timedelta

    from backend.core.config import settings as app_settings
    from backend.services.scheduler import EEDCScheduler

    monkeypatch.setattr(app_settings, "mqtt_auto_publish", True, raising=False)

    scheduler = EEDCScheduler()
    assert scheduler.start(), "Scheduler-Start fehlgeschlagen (APScheduler fehlt?)"
    try:
        job = scheduler._scheduler.get_job("mqtt_auto_publish")
        assert job is not None, "mqtt_auto_publish-Job nicht registriert"
        first_run = job.next_run_time.replace(tzinfo=None)
        assert first_run <= datetime.now() + timedelta(minutes=5), (
            f"Erster Lauf erst um {first_run} — Start-Publish fehlt"
        )
    finally:
        scheduler._scheduler.shutdown(wait=False)


async def test_mqtt_export_aktiviert_impliziert_auto_publish(monkeypatch):
    """M-B (Gernot 2026-06-10): Wer den MQTT-Export einschaltet (mqtt.enabled),
    bekommt Auto-Publish automatisch — die separate Default-aus-Option
    mqtt.auto_publish war die Ursache für „Sensoren aktualisieren nur per Klick"."""
    from backend.core.config import settings as app_settings
    from backend.services.scheduler import EEDCScheduler

    monkeypatch.setattr(app_settings, "mqtt_auto_publish", False, raising=False)
    monkeypatch.setattr(app_settings, "mqtt_enabled", True, raising=False)

    scheduler = EEDCScheduler()
    assert scheduler.start()
    try:
        assert scheduler._scheduler.get_job("mqtt_auto_publish") is not None, (
            "mqtt.enabled=true muss den Auto-Publish-Job registrieren"
        )
    finally:
        scheduler._scheduler.shutdown(wait=False)
