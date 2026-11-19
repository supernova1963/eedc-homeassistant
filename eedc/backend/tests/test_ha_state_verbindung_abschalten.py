"""Remote-Verbindung abschalten erreicht den Zustands-Dienst (Beipack B-1 zu Sensorwechsel U2 a1, 19.11.2026).

**Befund (veröffentlichter Bestand, gemessen in der Korrekturrunde U1-K und hier über die Route):**
``HAStateService.setze_ha_verbindung(None, None)`` kehrte ohne Wirkung zurück. Schaltet ein Standalone-Anwender die
Remote-Verbindung in den Einstellungen ab (``save_ha_remote_settings`` mit ``enabled: False`` →
``ha_connection.aktualisiere_ha_verbindung`` → ``setze_ha_verbindung(None, None)``), behielt der Zustands-Dienst Adresse und
Token: ``is_available`` blieb ``True``, und eedc fragte Home Assistant bis zum nächsten Neustart weiter nach Zuständen,
Einheiten und Verlauf (der Statistik-Dienst räumte schon).

**Regel jetzt:** eine Verbindung, die der Dienst über ``setze_ha_verbindung`` bekommen hat, endet mit ``(None, None)`` — der
Dienst kehrt zum Stand von ``__init__`` zurück (Supervisor-Token bzw. ohne Token). Ein Supervisor-Stand, der nicht über den
Setter kam, bleibt unberührt (``test_ha_verbindung_remote_erreicht_beide_dienste.py::test_2``).

Jede Probe trägt ihren **Sprengsatz** (``sprengsatz=True``: der Setter von vorher) — dann wird sie rot.

Schwesterdateien: test_ha_verbindung_remote_erreicht_beide_dienste.py, test_ha_aktivierung_mqtt_default_b7_5c.py.
"""

from __future__ import annotations

from typing import Optional

import pytest

TOKEN = "t" * 20
URL = "http://192.168.1.13:8123"          # privates IP-Literal: der SSRF-Guard braucht kein DNS (wie b7_5c)


def _alter_setter(self, api_url: Optional[str], token: Optional[str]) -> None:
    """Der Setter vor B-1 (wörtlich): ohne Verbindung kehrt er zurück."""
    if not (api_url and token):
        return
    if token != self.token or api_url != self.api_url:
        self._unit_cache.clear()
    self.api_url = api_url
    self.token = token


@pytest.fixture
def ohne_supervisor(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "supervisor_token", None, raising=False)


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["regel", "sprengsatz"])
async def test_abschalten_ueber_die_route_macht_den_zustandsdienst_unverfuegbar(db, monkeypatch, ohne_supervisor, sprengsatz):
    """Verbindung an (Route) ⇒ verfügbar, ein Abruf geht an HA; Verbindung aus (Route) ⇒ nicht verfügbar, kein Abruf mehr."""
    import backend.services.ha_state_service as hst
    from backend.api.routes.ha_remote import save_ha_remote_settings

    if sprengsatz:
        monkeypatch.setattr(hst.HAStateService, "setze_ha_verbindung", _alter_setter)
    abrufe: list[tuple] = []

    async def abruf(api_url, token, entity_ids):
        abrufe.append((api_url, token, tuple(entity_ids)))
        return {eid: {"state": "1.5", "attributes": {"unit_of_measurement": "kWh"}} for eid in entity_ids}
    monkeypatch.setattr(hst, "fetch_selected_states", abruf)

    svc = hst.get_ha_state_service()
    assert svc.is_available is False                          # Vorbedingung: Standalone ohne Verbindung

    await save_ha_remote_settings({"enabled": True, "base_url": URL, "token": TOKEN}, db)
    assert svc.is_available is True and svc.api_url == f"{URL}/api"
    assert await svc.get_sensor_state("sensor.x") == pytest.approx(1.5)
    assert len(abrufe) == 1

    await save_ha_remote_settings({"enabled": False, "base_url": URL, "token": TOKEN}, db)
    if sprengsatz:                                            # der Befund: Adresse und Token bleiben, HA wird weiter gefragt
        assert svc.is_available is True and svc.token == TOKEN
        assert await svc.get_sensor_state("sensor.x") == pytest.approx(1.5) and len(abrufe) == 2
        return
    assert svc.is_available is False and svc.token is None and svc.api_url != f"{URL}/api"
    assert await svc.get_sensor_state("sensor.x") is None
    assert len(abrufe) == 1                                   # kein Abruf mehr nach dem Abschalten


@pytest.mark.parametrize("sprengsatz", [False, True], ids=["regel", "sprengsatz"])
def test_abschalten_kehrt_zum_supervisor_stand_zurueck(monkeypatch, sprengsatz):
    """Add-on mit Supervisor-Token: eine Remote-Verbindung und ihr Ende — danach gilt wieder der Supervisor-Stand
    (``settings``), nicht die Remote-Adresse; gemerkte Einheiten der anderen Instanz sind verworfen."""
    import backend.services.ha_state_service as hst
    from backend.core.config import settings

    monkeypatch.setattr(settings, "supervisor_token", "supervisor-token", raising=False)
    if sprengsatz:
        monkeypatch.setattr(hst.HAStateService, "setze_ha_verbindung", _alter_setter)
    svc = hst.HAStateService()
    supervisor_url = svc.api_url
    svc.setze_ha_verbindung("http://10.0.0.5:8123/api", "remote-token")
    svc._unit_cache["sensor.x"] = (0.0, "kWh")
    svc.setze_ha_verbindung(None, None)
    if sprengsatz:
        assert svc.token == "remote-token"
        return
    assert (svc.token, svc.api_url) == ("supervisor-token", supervisor_url)
    assert svc._unit_cache == {}


def test_ohne_verbindung_vom_setter_bleibt_alles():
    """Gegenprobe: ``(None, None)`` ohne vorherige Verbindung über den Setter ändert nichts (der Start ohne Remote-Verbindung
    im Add-on) — der Stand aus ``__init__`` bleibt, auch ein gemerkter Einheiten-Cache."""
    from backend.services.ha_state_service import HAStateService

    svc = HAStateService()
    vorher = (svc.api_url, svc.token)
    svc._unit_cache["sensor.x"] = (0.0, "kWh")
    svc.setze_ha_verbindung(None, None)
    assert (svc.api_url, svc.token) == vorher and "sensor.x" in svc._unit_cache
