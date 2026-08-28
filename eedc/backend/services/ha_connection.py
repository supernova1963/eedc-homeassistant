"""
HA-Verbindungs-Auflösung (Datenquellen-V4) — EIN zentraler Helper.

Liefert (api_url, token, quelle_kind) der aktiven HA-Verbindung:
Supervisor-Token (HA-App) hat Vorrang, sonst die konfigurierte Remote-HA-
Verbindung (`ha_remote`/B4a, Long-Lived-Token). Genutzt von der Datenquellen-
Route (Entity-Discovery + Wert-Anzeige) UND der Live-Engine (C2a: HA-Felder
lesen) — eine Quelle der Wahrheit, kein Drift zwischen den Aufrufern.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

HA_APP = "ha_app"
HA_CONNECTOR = "ha_connector"
HA_REMOTE_SETTINGS_KEY = "ha_remote"


async def resolve_ha_connection(db: AsyncSession) -> tuple:
    """(api_url, token, kind) der aktiven HA-Verbindung — sonst (None, None, None).

    kind ∈ {"ha_app", "ha_connector"}. Supervisor bevorzugt (mit LTS-Zugriff),
    sonst Remote-HA per LL-Token (nur REST). Unabhängig vom Supervisor-gebundenen
    `HA_INTEGRATION_AVAILABLE`-Gate.

    ⛔ Hier stand bis 2026-08-28 „(das bleibt P3)". **P3 ist abgeschlossen** (Entscheid
    Gernot, s. KONZEPT-DATENQUELLEN-V4.md): Das Gate trägt nur noch die echten
    Add-on-Pfade (Supervisor-API-Router, Supervisor-Logs, Quellenart `ha_app` vs.
    `ha_connector`) — es ist keine offene Restschuld mehr, sondern die Antwort auf
    eine andere Frage: „läuft eedc als Add-on?" statt „steht eine HA-Verbindung?".
    """
    from backend.core.config import settings
    if settings.supervisor_token:
        return (settings.ha_api_url, settings.supervisor_token, HA_APP)

    from backend.models.settings import Settings as SettingsModel
    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == HA_REMOTE_SETTINGS_KEY))
    ).scalar_one_or_none()
    val = dict(row.value) if row and row.value else {}
    if val.get("enabled") and val.get("base_url") and val.get("token"):
        base = (val["base_url"] or "").strip().rstrip("/")
        if base.endswith("/api"):
            base = base[: -len("/api")]
        return (f"{base}/api", val["token"], HA_CONNECTOR)

    return (None, None, None)


async def aktualisiere_ha_verbindung(db: AsyncSession) -> bool:
    """Reicht die aktive HA-Verbindung an die beiden HA-Singletons weiter.

    Betroffen sind `HAStatisticsService` (Langzeitstatistik über die
    WebSocket-API, wenn kein Recorder-Zugang besteht) und `HAStateService`
    (aktuelle States, Einheiten, Sensorhistorie). Beide sind Singletons ohne
    DB-Session — `HAStatisticsService` ist zusätzlich durchgehend synchron —,
    können `resolve_ha_connection` also nicht selbst rufen. Die Verbindung wird
    ihnen hereingereicht.

    Zwei Aufrufer, und beide sind nötig: der Start (sonst wirkt eine bestehende
    Verbindung erst nach dem nächsten Speichern) und das Speichern der
    Remote-Verbindung (sonst erst nach dem nächsten Start).

    Returns:
        True, wenn eine Verbindung gesetzt wurde.
    """
    api_url, token, _ = await resolve_ha_connection(db)

    from backend.services.ha_state_service import get_ha_state_service
    from backend.services.ha_statistics_service import get_ha_statistics_service

    get_ha_statistics_service().setze_ha_verbindung(api_url, token)
    get_ha_state_service().setze_ha_verbindung(api_url, token)
    return bool(api_url and token)
