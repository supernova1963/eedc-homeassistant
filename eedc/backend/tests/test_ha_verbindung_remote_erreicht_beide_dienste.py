"""Die aktive HA-Verbindung erreicht beide HA-Singletons (N-156).

`HAStateService` las bis 2026-08-05 ausschließlich `settings.supervisor_token`.
Für eine Remote-/Standalone-Verbindung stand `is_available` damit still auf
`False` — obwohl `resolve_ha_connection` diesen Fall längst auflöste. Die
Aufrufer lieferten wortlos leer:

  · `daten_checker/sensoren.py` — der **kW≠kWh-Check** (#200/#674) schaltete
    sich mit dem Kommentar „HA nicht erreichbar (Standalone)“ ab. HA war
    erreichbar; nur der Zugriffsweg war der falsche. Und zwar bei genau den
    Anwendern, die die Slot-Verwechslung am ehesten machen.
  · `live_history_service.py` — Live-Tagesverlauf ohne Kurve.
  · `solcast_service.py`, `prognose_discovery.py`, Speicher-SoC-Historie.

Standalone:
    eedc/backend/venv/bin/python \\
        eedc/backend/tests/test_ha_verbindung_remote_erreicht_beide_dienste.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.ha_state_service import HAStateService  # noqa: E402
from backend.services.ha_statistics_service import HAStatisticsService  # noqa: E402


def test_1_remote_verbindung_macht_den_state_service_verfuegbar():
    """Ohne Supervisor-Token, aber mit Remote-Verbindung: verfügbar."""
    svc = HAStateService()
    svc.token = None          # Standalone: kein Supervisor
    svc.api_url = None
    assert svc.is_available is False, "Vorbedingung: ohne Token nicht verfügbar"

    svc.setze_ha_verbindung("http://10.0.0.5:8123/api", "ll-token")

    assert svc.is_available is True, "Remote-Verbindung muss den Dienst verfügbar machen"
    assert svc.api_url == "http://10.0.0.5:8123/api"
    print("  ✓ 1. Remote-Verbindung macht den State-Service verfügbar")


def test_2_leere_verbindung_laesst_den_supervisor_stand_stehen():
    """Ohne auflösbare Verbindung bleibt der Add-on-Betrieb unberührt.

    Sonst würde ein Aufruf ohne Ergebnis eine funktionierende
    Supervisor-Verbindung löschen — der Fix wäre teurer als der Fehler.
    """
    svc = HAStateService()
    svc.token = "supervisor-token"
    svc.api_url = "http://supervisor/core/api"

    svc.setze_ha_verbindung(None, None)

    assert svc.token == "supervisor-token", "Supervisor-Stand wurde überschrieben"
    assert svc.is_available is True
    print("  ✓ 2. Leere Verbindung lässt den Supervisor-Stand stehen")


def test_3_verbindungswechsel_verwirft_gemerkte_einheiten():
    """Zwischen zwei HA-Instanzen sagt dieselbe Entity nicht dasselbe."""
    svc = HAStateService()
    svc.setze_ha_verbindung("http://alt:8123/api", "token-alt")
    svc._unit_cache["sensor.x"] = (0.0, "kWh")

    svc.setze_ha_verbindung("http://neu:8123/api", "token-neu")

    assert svc._unit_cache == {}, "Einheiten der alten Instanz überlebt"
    print("  ✓ 3. Verbindungswechsel verwirft gemerkte Einheiten")


def test_4_derselbe_token_laesst_den_cache_stehen():
    """Ein wiederholter Aufruf mit gleicher Verbindung wirft nichts weg.

    Gegenprobe zu 3: der Setter läuft bei **jedem** Speichern der
    HA-Verbindung — würde er dabei immer leeren, wäre der Einheiten-Cache
    (TTL 1 h) praktisch wirkungslos.
    """
    svc = HAStateService()
    svc.setze_ha_verbindung("http://gleich:8123/api", "token")
    svc._unit_cache["sensor.x"] = (0.0, "kWh")

    svc.setze_ha_verbindung("http://gleich:8123/api", "token")

    assert "sensor.x" in svc._unit_cache, "Cache ohne Verbindungswechsel geleert"
    print("  ✓ 4. Gleiche Verbindung lässt den Cache stehen")


def test_5_ein_aufruf_versorgt_beide_dienste():
    """`aktualisiere_ha_verbindung` erreicht State- **und** Statistik-Dienst.

    Beide hingen an derselben Wurzel; sie getrennt zu versorgen hieße, den
    nächsten Aufrufer wieder zu vergessen.
    """
    from backend.services import ha_connection, ha_state_service, ha_statistics_service

    state = HAStateService()
    state.token = None
    stats = HAStatisticsService()
    stats._initialized, stats._engine = True, None

    echte_state, echte_stats = (
        ha_state_service.get_ha_state_service,
        ha_statistics_service.get_ha_statistics_service,
    )
    echtes_resolve = ha_connection.resolve_ha_connection

    async def _resolve(_db):
        return ("http://10.0.0.5:8123/api", "ll-token", ha_connection.HA_CONNECTOR)

    ha_state_service.get_ha_state_service = lambda: state
    ha_statistics_service.get_ha_statistics_service = lambda: stats
    ha_connection.resolve_ha_connection = _resolve
    try:
        gesetzt = asyncio.run(ha_connection.aktualisiere_ha_verbindung(None))
    finally:
        ha_state_service.get_ha_state_service = echte_state
        ha_statistics_service.get_ha_statistics_service = echte_stats
        ha_connection.resolve_ha_connection = echtes_resolve

    assert gesetzt is True
    assert state.is_available is True, "State-Dienst nicht versorgt"
    assert stats._ws_client is not None, "Statistik-Dienst nicht versorgt"
    assert stats._ws_client.ws_url == "ws://10.0.0.5:8123/api/websocket", (
        stats._ws_client.ws_url
    )
    print("  ✓ 5. Ein Aufruf versorgt beide Dienste")
