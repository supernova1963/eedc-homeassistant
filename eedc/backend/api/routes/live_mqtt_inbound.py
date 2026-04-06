"""
MQTT-Inbound Endpoints — Status, Values, Settings, Topics, Test.

Ausgelagert aus live_dashboard.py (Router-Split).
Registriert unter /api/live (wie zuvor).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.core.field_definitions import (
    get_alle_felder_fuer_investition,
    get_live_felder_fuer_investition,
    SOC_TYPEN,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MQTT_SETTINGS_KEY = "mqtt_inbound"


@router.get("/mqtt/status")
async def get_mqtt_inbound_status():
    """Status des MQTT-Inbound-Subscribers."""
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    svc = get_mqtt_inbound_service()
    if not svc:
        return {
            "verfuegbar": False,
            "subscriber_aktiv": False,
            "grund": "MQTT nicht aktiviert",
        }
    return svc.get_status()


@router.get("/mqtt/values")
async def get_mqtt_inbound_values():
    """Gibt alle aktuell im Cache befindlichen MQTT-Werte zurück (für Monitor-Anzeige)."""
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    svc = get_mqtt_inbound_service()
    if not svc:
        return {"werte": []}

    cache = svc.cache
    werte = []

    # Live-Werte
    for anlage_id, data in cache._live.items():
        for key, (val, ts) in data.get("basis", {}).items():
            werte.append({
                "topic": f"eedc/{anlage_id}/live/{key}",
                "wert": val,
                "zeitpunkt": ts.isoformat(),
                "kategorie": "live",
            })
        for inv_id, inv_data in data.get("inv", {}).items():
            for key, (val, ts) in inv_data.items():
                werte.append({
                    "topic": f"eedc/{anlage_id}/live/inv/{inv_id}/{key}",
                    "wert": val,
                    "zeitpunkt": ts.isoformat(),
                    "kategorie": "live",
                })

    # Energy-Werte
    for anlage_id, energy_data in cache._energy.items():
        for key, (val, ts) in energy_data.items():
            werte.append({
                "topic": f"eedc/{anlage_id}/energy/{key}",
                "wert": val,
                "zeitpunkt": ts.isoformat(),
                "kategorie": "energy",
            })

    werte.sort(key=lambda w: w["zeitpunkt"], reverse=True)
    return {"werte": werte}


@router.delete("/mqtt/cache")
async def delete_mqtt_cache(
    anlage_id: Optional[int] = Query(None, description="Nur Cache einer Anlage löschen"),
    clear_retained: bool = Query(False, description="Auch Retained Messages am Broker löschen"),
    db: AsyncSession = Depends(get_db),
):
    """Löscht den MQTT-Inbound-Cache und optional Retained Messages am Broker."""
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    svc = get_mqtt_inbound_service()
    if not svc:
        return {"geloescht": 0, "hinweis": "MQTT-Inbound nicht aktiv"}

    count = svc.cache.clear_cache(anlage_id)
    retained_cleared = 0

    if clear_retained:
        topics_resp = await get_mqtt_topics(db=db, anlage_id=anlage_id)
        topic_list = [t["topic"] for t in topics_resp.get("topics", [])]
        if topic_list:
            retained_cleared = await _clear_retained_messages(
                svc.host, svc.port, svc.username, svc.password, topic_list,
            )

    return {
        "geloescht": count,
        "retained_geloescht": retained_cleared,
        "anlage_id": anlage_id,
    }


@router.get("/mqtt/settings")
async def get_mqtt_settings(db: AsyncSession = Depends(get_db)):
    """Gibt die gespeicherten MQTT-Inbound-Einstellungen zurück."""
    from backend.models.settings import Settings as SettingsModel
    result = await db.execute(
        select(SettingsModel).where(SettingsModel.key == MQTT_SETTINGS_KEY)
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        return {
            "enabled": settings.mqtt_enabled,
            "host": settings.mqtt_host,
            "port": settings.mqtt_port,
            "username": settings.mqtt_username,
            "password": "***" if settings.mqtt_password else "",
            "quelle": "env",
        }
    val = setting.value
    return {
        "enabled": val.get("enabled", False),
        "host": val.get("host", "localhost"),
        "port": val.get("port", 1883),
        "username": val.get("username", ""),
        "password": "***" if val.get("password") else "",
        "quelle": "db",
    }


async def _clear_retained_messages(
    host: str, port: int,
    username: Optional[str], password: Optional[str],
    topics: list[str],
) -> int:
    """Löscht Retained Messages am Broker (leere Payload mit Retain-Flag)."""
    try:
        import aiomqtt
    except ImportError:
        return 0

    try:
        async with aiomqtt.Client(
            hostname=host, port=port,
            username=username, password=password,
        ) as client:
            for topic in topics:
                await client.publish(topic, payload=b"", retain=True)
            return len(topics)
    except Exception as e:
        logger.warning("MQTT-Inbound: Retained Messages löschen fehlgeschlagen: %s", e)
        return 0


async def _publish_initial_values(
    host: str, port: int,
    username: Optional[str], password: Optional[str],
    topics: list[str],
) -> int:
    """Publisht Initialwert 0 auf alle Topics (retained), damit sie am Broker sichtbar sind."""
    try:
        import aiomqtt
    except ImportError:
        return 0

    try:
        async with aiomqtt.Client(
            hostname=host, port=port,
            username=username, password=password,
        ) as client:
            for topic in topics:
                await client.publish(topic, payload="0", retain=True)
            return len(topics)
    except Exception as e:
        logger.warning("MQTT-Inbound: Initialwerte publish fehlgeschlagen: %s", e)
        return 0


@router.post("/mqtt/settings")
async def save_mqtt_settings(
    config: dict,
    db: AsyncSession = Depends(get_db),
):
    """Speichert MQTT-Inbound-Einstellungen in der DB und (re)startet den Subscriber."""
    from backend.models.settings import Settings as SettingsModel
    from sqlalchemy.orm.attributes import flag_modified

    host = config.get("host", "").strip()
    try:
        port = int(config.get("port", 1883))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Port muss eine Zahl sein")
    username = config.get("username", "").strip()
    password = config.get("password", "").strip()
    enabled = bool(config.get("enabled", False))

    if enabled and not host:
        raise HTTPException(status_code=400, detail="Host ist erforderlich")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Port muss zwischen 1 und 65535 liegen")

    result = await db.execute(
        select(SettingsModel).where(SettingsModel.key == MQTT_SETTINGS_KEY)
    )
    setting = result.scalar_one_or_none()
    old_password = ""
    if setting and setting.value:
        old_password = setting.value.get("password", "")

    if password == "***":
        password = old_password

    new_value = {
        "enabled": enabled,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }

    if setting:
        setting.value = new_value
        flag_modified(setting, "value")
    else:
        setting = SettingsModel(key=MQTT_SETTINGS_KEY, value=new_value)
        db.add(setting)

    await db.commit()

    from backend.services.mqtt_inbound_service import (
        get_mqtt_inbound_service, init_mqtt_inbound_service
    )
    svc = get_mqtt_inbound_service()

    if enabled:
        if svc:
            await svc.stop()
        svc = init_mqtt_inbound_service(
            host=host, port=port,
            username=username or None,
            password=password or None,
        )
        started = await svc.start()

        if started:
            topics_resp = await get_mqtt_topics(db=db, anlage_id=None)
            topic_list = [t["topic"] for t in topics_resp.get("topics", [])]
            if topic_list:
                published = await _publish_initial_values(
                    host, port, username or None, password or None, topic_list,
                )
                logger.info("MQTT-Inbound: %d Topics mit Initialwert published", published)

        return {
            "gespeichert": True,
            "subscriber_gestartet": started,
            "broker": f"{host}:{port}",
        }
    else:
        if svc:
            await svc.stop()
        return {"gespeichert": True, "subscriber_gestartet": False}


def _mqtt_slug(name: str) -> str:
    """Erzeugt einen MQTT-Topic-sicheren Slug aus einem Namen."""
    import re as _re
    slug = name.strip().replace(" ", "_")
    slug = _re.sub(r"[^\w.\-]", "", slug)
    return slug or "unnamed"


@router.get("/mqtt/topics")
async def get_mqtt_topics(
    db: AsyncSession = Depends(get_db),
    anlage_id: Optional[int] = Query(None, description="Filter auf eine Anlage"),
):
    """Generiert die vollständige Topic-Liste mit konkreten Anlage- und Investitions-IDs."""
    if anlage_id is not None:
        anlagen = (await db.execute(
            select(Anlage).where(Anlage.id == anlage_id)
        )).scalars().all()
    else:
        anlagen = (await db.execute(select(Anlage))).scalars().all()
    if not anlagen:
        return {"topics": []}

    topics = []
    for anlage in anlagen:
        aid = anlage.id
        aname = anlage.anlagenname or f"Anlage {aid}"
        aslug = _mqtt_slug(aname)
        live_prefix = f"eedc/{aid}_{aslug}/live"
        energy_prefix = f"eedc/{aid}_{aslug}/energy"

        topics.append({"topic": f"{live_prefix}/einspeisung_w", "label": "Einspeisung (W)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/netzbezug_w", "label": "Netzbezug (W)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/netz_kombi_w", "label": "Netz-Kombi (W, positiv=Bezug, negativ=Einspeisung)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/pv_gesamt_w", "label": "PV Gesamt (W, Fallback wenn kein Modul-Sensor)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/sfml_today_kwh", "label": "Solar Forecast ML – Prognose heute (kWh)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/sfml_tomorrow_kwh", "label": "Solar Forecast ML – Prognose morgen (kWh)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/sfml_accuracy_pct", "label": "Solar Forecast ML – Modellgenauigkeit (%)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{live_prefix}/aussentemperatur_c", "label": "Außentemperatur (°C)", "anlage": aname, "typ": "basis"})
        topics.append({"topic": f"{energy_prefix}/pv_gesamt_kwh", "label": "PV-Erzeugung Monat (kWh)", "anlage": aname, "typ": "energy"})
        topics.append({"topic": f"{energy_prefix}/einspeisung_kwh", "label": "Einspeisung Monat (kWh)", "anlage": aname, "typ": "energy"})
        topics.append({"topic": f"{energy_prefix}/netzbezug_kwh", "label": "Netzbezug Monat (kWh)", "anlage": aname, "typ": "energy"})

        investitionen = (await db.execute(
            select(Investition).where(
                Investition.anlage_id == aid,
                Investition.aktiv == True,
            )
        )).scalars().all()

        # energy_keys_by_typ und soc_typen werden aus Registry abgeleitet —
        # kein hardcodierter Block mehr. Neue Felder nur in field_definitions eintragen.
        skip_typen = {"wechselrichter"}

        for inv in investitionen:
            if inv.typ in skip_typen:
                continue

            islug = _mqtt_slug(inv.bezeichnung)
            inv_live = f"{live_prefix}/inv/{inv.id}_{islug}"
            inv_energy = f"{energy_prefix}/inv/{inv.id}_{islug}"

            # Live-Topics aus Registry (leistung_w, soc, WP-spezifische, etc.)
            for live_feld in get_live_felder_fuer_investition(inv.typ, inv.parameter):
                topics.append({
                    "topic": f"{inv_live}/{live_feld['key']}",
                    "label": f"{inv.bezeichnung} – {live_feld['label']} ({live_feld['einheit']})",
                    "anlage": aname,
                    "typ": inv.typ,
                })

            # Energy-Topics aus Registry (kWh/km/€-Monatswerte)
            for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
                einheit_str = f" ({feld['einheit']})" if feld.get("einheit") else ""
                topics.append({
                    "topic": f"{inv_energy}/{feld['feld']}",
                    "label": f"{inv.bezeichnung} – {feld['label']}{einheit_str}",
                    "anlage": aname,
                    "typ": "energy",
                })

    return {"topics": topics}


@router.post("/mqtt/test")
async def test_mqtt_connection(config: dict):
    """Testet die MQTT-Verbindung ohne zu speichern."""
    try:
        import aiomqtt
    except ImportError:
        return {"connected": False, "error": "aiomqtt nicht installiert"}

    host = config.get("host", "").strip()
    try:
        port = int(config.get("port", 1883))
    except (ValueError, TypeError):
        return {"connected": False, "error": "Ungültiger Port"}
    username = config.get("username", "").strip() or None
    password = config.get("password", "").strip() or None

    if password == "***":
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        svc = get_mqtt_inbound_service()
        if svc:
            password = svc.password

    if not host:
        return {"connected": False, "error": "Host ist erforderlich"}

    try:
        async with aiomqtt.Client(
            hostname=host, port=port,
            username=username, password=password,
        ) as client:
            return {
                "connected": True,
                "broker": f"{host}:{port}",
                "message": "Verbindung erfolgreich",
            }
    except Exception as e:
        return {
            "connected": False,
            "broker": f"{host}:{port}",
            "error": str(e),
        }
