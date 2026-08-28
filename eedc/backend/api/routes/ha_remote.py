"""
HA-Remote-Verbindung — Basis (Datenquellen-V4 / B4a).

SoT: docs/KONZEPT-DATENQUELLEN-V4.md §2a/§3a.

Ermöglicht eedc-Standalone, eine ENTFERNTE Home-Assistant-Installation per
Basis-URL + Long-Lived-Token zu hinterlegen und die Verbindung zu **testen**.
Analog zum MQTT-Broker-Block ist das der Verbindungs-Baustein — „Verbindung"
getrennt von „was darüber fließt".

**Speichern + Testen der Verbindung** (Gernot 2026-07-13). Dieser Router ist
**immer** gemountet (Standalone-tauglich) und verändert weder das Gate noch die
HA-Routen.

⛔ Hier stand bis 2026-08-28: „Die eigentliche Nutzbarmachung … bleibt P3
(~20 Guard-Stellen)." **P3 ist abgeschlossen.** HA-Sensoren sind im Standalone
nutzbar; die aktive Verbindung liefert `services/ha_connection.resolve_ha_connection`
(Supervisor **oder** die hier hinterlegte Remote-Verbindung), und
`aktualisiere_ha_verbindung` reicht sie an beide HA-Singletons weiter.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.services.ha_connection import aktualisiere_ha_verbindung

logger = logging.getLogger(__name__)

router = APIRouter()

HA_REMOTE_SETTINGS_KEY = "ha_remote"


async def _load(db: AsyncSession) -> dict:
    """Rohwerte des `ha_remote`-Settings-Keys (leer wenn nie gespeichert)."""
    from backend.models.settings import Settings as SettingsModel

    result = await db.execute(
        select(SettingsModel).where(SettingsModel.key == HA_REMOTE_SETTINGS_KEY)
    )
    setting = result.scalar_one_or_none()
    return dict(setting.value) if setting and setting.value else {}


def _normalize_base_url(raw: str) -> str:
    """Trimmt und entfernt ein optionales trailing `/` (und ein `/api`-Suffix)."""
    url = (raw or "").strip().rstrip("/")
    if url.endswith("/api"):
        url = url[: -len("/api")]
    return url


@router.get("/remote/settings")
async def get_ha_remote_settings(db: AsyncSession = Depends(get_db)):
    """Gespeicherte Remote-HA-Verbindung (Token maskiert) + Supervisor-Verfügbarkeit.

    `supervisor_verfuegbar=true` (HA-App) → der Block zeigt read-only den
    Supervisor-Status; sonst (Standalone) das URL-/Token-Formular.
    """
    val = await _load(db)
    return {
        "enabled": val.get("enabled", False),
        "base_url": val.get("base_url", ""),
        "token": "***" if val.get("token") else "",
        "supervisor_verfuegbar": HA_INTEGRATION_AVAILABLE,
    }


async def _mqtt_import_auf_default(db: AsyncSession) -> dict:
    """Setzt beim **Aktivieren** der HA-Verbindung den MQTT-Import auf den Default
    (aus) — „MQTT nur für Export + HA-Discovery" (Gernot-Weiche 2026-07-16).

    **Evidenz-Schranke: aktive MQTT-Gateway-Mappings.** Sie sind die einzige
    Zuordnung, bei der echte *Konfiguration* verloren ginge (Fremd-Topic, Transform,
    JSON-Pfad). Der Inbound-Pfad dagegen ist immer derselbe Standard-Topic-Satz —
    dort geht nichts kaputt, ein Klick auf „Daten über MQTT empfangen" stellt ihn
    wieder her (Gernots Präzisierung).

    ⚠️ Am selben Schalter hängen laut `main.py` auch **Geräte-Connectoren**
    (Anker/EcoFlow/Zendure publishen auf die Inbound-Topics). Die blockieren den
    Default NICHT — aber wir melden sie zurück, damit der Nutzer weiß, was mit
    abgeschaltet wurde. Sonst stünde die Ursache in einem anderen Block als die
    ausbleibenden Werte.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    from backend.models.settings import Settings as SettingsModel
    from backend.services.mqtt_broker_settings import MQTT_SETTINGS_KEY, import_aktiviert

    if not await import_aktiviert(db):
        return {"abgeschaltet": False, "grund": "import_war_schon_aus"}

    gateways = len(
        (
            await db.execute(
                select(MqttGatewayMapping).where(MqttGatewayMapping.aktiv == True)  # noqa: E712
            )
        ).scalars().all()
    )
    if gateways:
        return {"abgeschaltet": False, "grund": "gateway_in_benutzung", "gateway_mappings": gateways}

    row = (
        await db.execute(select(SettingsModel).where(SettingsModel.key == MQTT_SETTINGS_KEY))
    ).scalar_one_or_none()
    if row and row.value:
        row.value = {**row.value, "enabled": False}   # Zugangsdaten behalten — der Export nutzt sie
        flag_modified(row, "value")
    else:
        db.add(SettingsModel(key=MQTT_SETTINGS_KEY, value={"enabled": False}))

    connectors = 0
    try:
        from backend.services.connector_mqtt_bridge import build_targets_from_db

        connectors = len(await build_targets_from_db(db))
    except Exception:  # noqa: BLE001 — nur für den Hinweistext, nie den Save kippen
        connectors = 0

    return {"abgeschaltet": True, "connectoren": connectors}


@router.post("/remote/settings")
async def save_ha_remote_settings(config: dict, db: AsyncSession = Depends(get_db)):
    """Speichert die Remote-HA-Verbindung (URL + Long-Lived-Token).

    Nur Persistenz (Basis) — kein Gate-/Router-Effekt. Bei `enabled` wird die
    URL SSRF-geprüft (LAN erlaubt, Loopback/Metadata blockiert).

    B7-5c: Beim **Übergang** inaktiv → aktiv wird der MQTT-Import auf den Default
    gesetzt (siehe `_mqtt_import_auf_default`). Bewusst nur beim Übergang: sonst
    würde jedes erneute Speichern (Token-Wechsel, URL-Korrektur) einen bewusst
    eingeschalteten Import wieder abwürgen.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from backend.models.settings import Settings as SettingsModel

    enabled = bool(config.get("enabled", False))
    base_url = _normalize_base_url(config.get("base_url", ""))
    token = (config.get("token") or "").strip()

    if enabled and not base_url:
        raise HTTPException(status_code=400, detail="Basis-URL ist erforderlich")
    if enabled and base_url:
        _ssrf_check(base_url)

    existing = await _load(db)
    if token == "***":  # Platzhalter → bestehenden Token behalten
        token = existing.get("token", "")
    if enabled and not token:
        raise HTTPException(status_code=400, detail="Long-Lived-Token ist erforderlich")

    new_value = {"enabled": enabled, "base_url": base_url, "token": token}
    wird_aktiviert = enabled and not existing.get("enabled", False)

    result = await db.execute(
        select(SettingsModel).where(SettingsModel.key == HA_REMOTE_SETTINGS_KEY)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = new_value
        flag_modified(setting, "value")
    else:
        db.add(SettingsModel(key=HA_REMOTE_SETTINGS_KEY, value=new_value))

    mqtt_import = await _mqtt_import_auf_default(db) if wird_aktiviert else None
    await db.commit()

    # Die Langzeitstatistik liest ohne Datenbank-Zugang über diese Verbindung
    # (`services/ha_statistics_ws.py`). Sie ist ein synchroner Singleton und
    # kann die Zeile nicht selbst nachschlagen — also wird sie hier informiert,
    # sonst greift eine geänderte Verbindung erst nach einem Neustart.
    await aktualisiere_ha_verbindung(db)

    return {
        "gespeichert": True,
        "base_url": base_url,
        "enabled": enabled,
        "mqtt_import": mqtt_import,
    }


@router.post("/remote/test")
async def test_ha_remote(config: dict, db: AsyncSession = Depends(get_db)):
    """Testet URL + Token gegen `GET {base_url}/api/` (HA meldet „API running.")."""
    base_url = _normalize_base_url(config.get("base_url", ""))
    token = (config.get("token") or "").strip()
    if not base_url:
        return {"connected": False, "error": "Basis-URL fehlt"}
    if token == "***":
        token = (await _load(db)).get("token", "")
    if not token:
        return {"connected": False, "error": "Long-Lived-Token fehlt"}

    try:
        _ssrf_check(base_url)
    except HTTPException as exc:
        return {"connected": False, "error": str(exc.detail)}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{base_url}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as exc:  # noqa: BLE001 — jede Netzwerk-/TLS-Ausnahme als Fehltest melden
        return {"connected": False, "error": f"Verbindungsfehler: {exc}"}

    if resp.status_code == 200:
        return {"connected": True, "message": f"Verbunden mit {base_url}"}
    if resp.status_code in (401, 403):
        return {"connected": False, "error": "Token ungültig oder ohne Rechte"}
    return {"connected": False, "error": f"Unerwartete Antwort: HTTP {resp.status_code}"}


def _ssrf_check(base_url: str) -> None:
    """Wiederverwendung des Connector-SSRF-Guards (LAN erlaubt, Loopback/Metadata blockiert)."""
    from backend.api.routes.connector import _validate_connector_host

    _validate_connector_host(base_url)
