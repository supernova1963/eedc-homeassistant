"""
Live Dashboard API - Echtzeit-Leistungsdaten.

GET /api/live/{anlage_id} — Aktuelle Leistungswerte für eine Anlage.
GET /api/live/{anlage_id}?demo=true — Simulierte Demo-Daten (Entwicklung).
GET /api/live/{anlage_id}/wetter — Aktuelles Wetter + PV-Prognose + Verbrauchsprofil.
"""

import asyncio
import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.solar_forecast_service import _solar_noon_hour
from backend.services.live_power_service import get_live_power_service
from backend.services.wetter_service import wetter_code_zu_symbol

logger = logging.getLogger(__name__)


router = APIRouter()


# ── Response Models ──────────────────────────────────────────────────────────

class LiveKomponente(BaseModel):
    """Eine Zeile in der Energiebilanz-Tabelle."""
    key: str
    label: str
    icon: str
    erzeugung_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    parent_key: Optional[str] = None


class LiveGauge(BaseModel):
    """Ein Gauge-Chart (SoC, Netz-Richtung, Autarkie)."""
    key: str
    label: str
    wert: float
    min_wert: float = 0
    max_wert: float = 100
    einheit: str = "%"


class LiveDashboardResponse(BaseModel):
    anlage_id: int
    anlage_name: str
    zeitpunkt: str
    verfuegbar: bool

    komponenten: list[LiveKomponente]
    summe_erzeugung_kw: float
    summe_verbrauch_kw: float

    gauges: list[LiveGauge]

    heute_pv_kwh: Optional[float] = None
    heute_einspeisung_kwh: Optional[float] = None
    heute_netzbezug_kwh: Optional[float] = None
    heute_eigenverbrauch_kwh: Optional[float] = None

    gestern_pv_kwh: Optional[float] = None
    gestern_einspeisung_kwh: Optional[float] = None
    gestern_netzbezug_kwh: Optional[float] = None
    gestern_eigenverbrauch_kwh: Optional[float] = None

    heute_kwh_pro_komponente: Optional[dict[str, float]] = None

    warmwasser_temperatur_c: Optional[float] = None


class TagesverlaufSerie(BaseModel):
    """Beschreibung einer Kurve im Tagesverlauf-Chart."""
    key: str              # z.B. "pv_3", "batterie_5", "wallbox_6", "netz", "haushalt"
    label: str            # z.B. "PV Süd", "BYD HVS 10.2"
    kategorie: str        # "pv", "batterie", "wallbox", "waermepumpe", "sonstige", "netz", "haushalt"
    farbe: str            # Hex-Farbe, z.B. "#eab308"
    seite: str            # "quelle" (positiv) oder "senke" (negativ)
    bidirektional: bool = False  # Speicher/Netz: wechselt dynamisch die Seite


class TagesverlaufPunkt(BaseModel):
    """Ein Stunden-Datenpunkt im Tagesverlauf."""
    zeit: str  # "14:00"
    werte: dict[str, float] = {}  # {serie_key: kW-Wert mit Vorzeichen}


class TagesverlaufResponse(BaseModel):
    anlage_id: int
    datum: str  # "2026-03-14"
    serien: list[TagesverlaufSerie] = []
    punkte: list[TagesverlaufPunkt] = []


# ── Demo-Daten ───────────────────────────────────────────────────────────────

def _generate_demo_data(anlage_id: int, anlage_name: str) -> dict:
    """Simulierte Live-Daten mit Multi-Sensor (2 PV-Strings, benannte Komponenten)."""
    def jitter(base: float, pct: float = 0.1) -> float:
        return round(base * (1 + random.uniform(-pct, pct)), 2)

    # Zwei PV-Strings
    pv_a_kw = jitter(2.8)
    pv_b_kw = jitter(1.4)
    pv_kw = pv_a_kw + pv_b_kw

    einsp_kw = jitter(1.1)
    bezug_kw = jitter(0.3, 0.3)
    batt_kw = jitter(0.5)
    ist_ladung = random.random() > 0.4
    wallbox_kw = jitter(7.4) if random.random() > 0.25 else 0
    eauto_kw = round(wallbox_kw * random.uniform(0.85, 0.95), 2) if wallbox_kw > 0 else 0
    wp_kw = jitter(1.8)
    batt_soc = min(100, max(0, 72 + random.randint(-5, 5)))
    eauto_soc = min(100, max(0, 45 + random.randint(-3, 3)))

    # Energiebilanz
    summe_erz = pv_kw + bezug_kw + (batt_kw if not ist_ladung else 0)
    bekannte_vrb = einsp_kw + (batt_kw if ist_ladung else 0) + wallbox_kw + wp_kw
    haushalt_kw = max(0, round(summe_erz - bekannte_vrb, 2))
    summe_vrb = bekannte_vrb + haushalt_kw

    eigenverbrauch = pv_kw - einsp_kw
    gesamt_verbrauch = eigenverbrauch + bezug_kw
    autarkie = round(eigenverbrauch / gesamt_verbrauch * 100, 0) if gesamt_verbrauch > 0 else 0

    netto_w = round((bezug_kw - einsp_kw) * 1000, 0)
    max_netz = max(einsp_kw, bezug_kw) * 1000

    return {
        "anlage_id": anlage_id,
        "anlage_name": anlage_name,
        "zeitpunkt": datetime.now().isoformat(),
        "verfuegbar": True,
        "komponenten": [
            # Zwei PV-Strings (wie bei SMA mit pv_a + pv_b)
            {"key": "pv_1", "label": "PV Süd (String A)", "icon": "sun",
             "erzeugung_kw": pv_a_kw, "verbrauch_kw": None},
            {"key": "pv_2", "label": "PV Ost (String B)", "icon": "sun",
             "erzeugung_kw": pv_b_kw, "verbrauch_kw": None},
            {"key": "netz", "label": "Stromnetz", "icon": "zap",
             "erzeugung_kw": bezug_kw if bezug_kw > 0 else None,
             "verbrauch_kw": einsp_kw if einsp_kw > 0 else None},
            {"key": "batterie_3", "label": "BYD HVS 10.2", "icon": "battery",
             "erzeugung_kw": batt_kw if not ist_ladung else None,
             "verbrauch_kw": batt_kw if ist_ladung else None},
            {"key": "wallbox_6", "label": "go-eCharger", "icon": "plug",
             "erzeugung_kw": None, "verbrauch_kw": wallbox_kw},
            {"key": "eauto_4", "label": "VW ID.4", "icon": "car",
             "erzeugung_kw": None, "verbrauch_kw": eauto_kw,
             "parent_key": "wallbox_6"},
            {"key": "waermepumpe_5", "label": "Viessmann Vitocal", "icon": "flame",
             "erzeugung_kw": None, "verbrauch_kw": wp_kw},
            {"key": "haushalt", "label": "Haushalt", "icon": "home",
             "erzeugung_kw": None, "verbrauch_kw": haushalt_kw},
        ],
        "summe_erzeugung_kw": round(summe_erz, 2),
        "summe_verbrauch_kw": round(summe_vrb, 2),
        "gauges": [
            {"key": "netz", "label": "Netz", "wert": netto_w,
             "min_wert": -max_netz, "max_wert": max_netz, "einheit": "W"},
            {"key": "soc_3", "label": "BYD HVS 10.2", "wert": batt_soc,
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "soc_4", "label": "VW ID.4", "wert": eauto_soc,
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "autarkie", "label": "Autarkie", "wert": min(autarkie, 100),
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "eigenverbrauch", "label": "Eigenverbr.", "wert": min(round(eigenverbrauch / pv_kw * 100, 0) if pv_kw > 0 else 0, 100),
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "pv_leistung", "label": "PV-Leistung", "wert": round(pv_kw / 10.0 * 100, 0),
             "min_wert": 0, "max_wert": 120, "einheit": "% kWp"},
        ],
        "heute_pv_kwh": round(18.3 + random.uniform(-1, 1), 1),
        "heute_einspeisung_kwh": round(9.2 + random.uniform(-0.5, 0.5), 1),
        "heute_netzbezug_kwh": round(3.1 + random.uniform(-0.3, 0.3), 1),
        "heute_eigenverbrauch_kwh": round(9.1 + random.uniform(-0.5, 0.5), 1),
        "gestern_pv_kwh": round(22.5 + random.uniform(-2, 2), 1),
        "gestern_einspeisung_kwh": round(12.1 + random.uniform(-1, 1), 1),
        "gestern_netzbezug_kwh": round(4.2 + random.uniform(-0.5, 0.5), 1),
        "gestern_eigenverbrauch_kwh": round(10.4 + random.uniform(-1, 1), 1),
        "heute_kwh_pro_komponente": {
            "pv_1": round(12.1 + random.uniform(-1, 1), 1),
            "pv_2": round(6.2 + random.uniform(-0.5, 0.5), 1),
            "netz_bezug": round(3.1 + random.uniform(-0.3, 0.3), 1),
            "netz_einspeisung": round(9.2 + random.uniform(-0.5, 0.5), 1),
            "batterie_3": round(4.5 + random.uniform(-0.5, 0.5), 1),
            "wallbox_6": round(14.7 + random.uniform(-1, 1), 1),
            "eauto_4": round(8.3 + random.uniform(-0.5, 0.5), 1),
            "waermepumpe_5": round(5.2 + random.uniform(-0.3, 0.3), 1),
            "haushalt": round(9.1 + random.uniform(-0.5, 0.5), 1),
        },
    }


# ── MQTT-Inbound Endpoints (VOR /{anlage_id} damit kein Wildcard-Match) ───

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

    # Nach Zeitpunkt sortieren (neueste zuerst)
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
        # Topics generieren und leere retained Messages publishen
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
        # Defaults aus Env-Vars
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

    # Validierung
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

    # Bestehende Settings laden (Passwort behalten wenn "***")
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

    # Subscriber (re)starten
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

        # Initialwerte auf alle Topics publishen (retained)
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
    """Erzeugt einen MQTT-Topic-sicheren Slug aus einem Namen.

    Beispiel: "BYD HVS 10.2" → "BYD_HVS_10.2"
    """
    import re as _re
    # Leerzeichen → Unterstrich, alles außer Wort-Zeichen/Punkt/Minus entfernen
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

        # Live Basis-Topics
        topics.append({
            "topic": f"{live_prefix}/einspeisung_w",
            "label": "Einspeisung (W)",
            "anlage": aname,
            "typ": "basis",
        })
        topics.append({
            "topic": f"{live_prefix}/netzbezug_w",
            "label": "Netzbezug (W)",
            "anlage": aname,
            "typ": "basis",
        })
        topics.append({
            "topic": f"{live_prefix}/netz_kombi_w",
            "label": "Netz-Kombi (W, positiv=Bezug, negativ=Einspeisung)",
            "anlage": aname,
            "typ": "basis",
        })
        topics.append({
            "topic": f"{live_prefix}/pv_gesamt_w",
            "label": "PV Gesamt (W, Fallback wenn kein Modul-Sensor)",
            "anlage": aname,
            "typ": "basis",
        })
        # Solar Forecast ML (Basis)
        topics.append({
            "topic": f"{live_prefix}/sfml_today_kwh",
            "label": "Solar Forecast ML – Prognose heute (kWh)",
            "anlage": aname,
            "typ": "basis",
        })
        topics.append({
            "topic": f"{live_prefix}/sfml_tomorrow_kwh",
            "label": "Solar Forecast ML – Prognose morgen (kWh)",
            "anlage": aname,
            "typ": "basis",
        })
        topics.append({
            "topic": f"{live_prefix}/sfml_accuracy_pct",
            "label": "Solar Forecast ML – Modellgenauigkeit (%)",
            "anlage": aname,
            "typ": "basis",
        })

        # Energy Basis-Topics (kWh Monatswerte)
        topics.append({
            "topic": f"{energy_prefix}/pv_gesamt_kwh",
            "label": "PV-Erzeugung Monat (kWh)",
            "anlage": aname,
            "typ": "energy",
        })
        topics.append({
            "topic": f"{energy_prefix}/einspeisung_kwh",
            "label": "Einspeisung Monat (kWh)",
            "anlage": aname,
            "typ": "energy",
        })
        topics.append({
            "topic": f"{energy_prefix}/netzbezug_kwh",
            "label": "Netzbezug Monat (kWh)",
            "anlage": aname,
            "typ": "energy",
        })

        # Investitions-Topics
        investitionen = (await db.execute(
            select(Investition).where(
                Investition.anlage_id == aid,
                Investition.aktiv == True,
            )
        )).scalars().all()

        soc_typen = {"speicher", "e-auto"}

        # Investitions-spezifische Energy-Keys nach Typ
        energy_keys_by_typ = {
            "pv-module": [("pv_erzeugung_kwh", "PV-Erzeugung (kWh)")],
            "speicher": [("ladung_kwh", "Ladung (kWh)"), ("entladung_kwh", "Entladung (kWh)")],
            "waermepumpe": [
                ("stromverbrauch_kwh", "Stromverbrauch (kWh)"),
                ("heizenergie_kwh", "Heizenergie (kWh)"),
                ("warmwasser_kwh", "Warmwasser (kWh)"),
            ],
            "e-auto": [
                ("ladung_kwh", "Ladung (kWh)"),
                ("km_gefahren", "Gefahrene km"),
                ("v2h_entladung_kwh", "V2H-Entladung (kWh)"),
            ],
            "wallbox": [
                ("ladung_kwh", "Ladung (kWh)"),
                ("ladevorgaenge", "Ladevorgaenge (Anzahl)"),
            ],
            "balkonkraftwerk": [
                ("pv_erzeugung_kwh", "Erzeugung (kWh)"),
                ("eigenverbrauch_kwh", "Eigenverbrauch (kWh)"),
                ("speicher_ladung_kwh", "Speicher Ladung (kWh)"),
                ("speicher_entladung_kwh", "Speicher Entladung (kWh)"),
            ],
        }

        # Wechselrichter überspringen — die PV-Erzeugung kommt von den Modulen,
        # der WR ist nur Durchleiter und würde doppelt zählen.
        skip_typen = {"wechselrichter"}

        for inv in investitionen:
            if inv.typ in skip_typen:
                continue

            islug = _mqtt_slug(inv.bezeichnung)
            inv_live = f"{live_prefix}/inv/{inv.id}_{islug}"
            inv_energy = f"{energy_prefix}/inv/{inv.id}_{islug}"

            # Live-Topics
            topics.append({
                "topic": f"{inv_live}/leistung_w",
                "label": f"{inv.bezeichnung} – Leistung (W)",
                "anlage": aname,
                "typ": inv.typ,
            })
            if inv.typ in soc_typen:
                topics.append({
                    "topic": f"{inv_live}/soc",
                    "label": f"{inv.bezeichnung} – SoC (%)",
                    "anlage": aname,
                    "typ": inv.typ,
                })
            if inv.typ == "waermepumpe":
                topics.append({
                    "topic": f"{inv_live}/leistung_heizen_w",
                    "label": f"{inv.bezeichnung} – Heizleistung (W)",
                    "anlage": aname,
                    "typ": inv.typ,
                })
                topics.append({
                    "topic": f"{inv_live}/leistung_warmwasser_w",
                    "label": f"{inv.bezeichnung} – Warmwasser-Leistung (W)",
                    "anlage": aname,
                    "typ": inv.typ,
                })
                topics.append({
                    "topic": f"{inv_live}/warmwasser_temperatur_c",
                    "label": f"{inv.bezeichnung} – Warmwasser-Temperatur (°C)",
                    "anlage": aname,
                    "typ": inv.typ,
                })

            # Energy-Topics
            energy_keys = list(energy_keys_by_typ.get(inv.typ, []))

            # Sonstiges: kategorie-abhängige Felder
            if inv.typ == "sonstiges":
                param = inv.parameter if isinstance(inv.parameter, dict) else {}
                kategorie = param.get("kategorie", "verbraucher")
                if kategorie == "erzeuger":
                    energy_keys = [("erzeugung_kwh", "Erzeugung (kWh)")]
                elif kategorie == "speicher":
                    energy_keys = [
                        ("erzeugung_kwh", "Erzeugung/Entladung (kWh)"),
                        ("verbrauch_sonstig_kwh", "Verbrauch/Ladung (kWh)"),
                    ]
                else:
                    energy_keys = [("verbrauch_sonstig_kwh", "Verbrauch (kWh)")]

            for key, label in energy_keys:
                topics.append({
                    "topic": f"{inv_energy}/{key}",
                    "label": f"{inv.bezeichnung} – {label}",
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

    # Maskiertes Passwort → aus DB laden
    if password == "***":
        from backend.models.settings import Settings as SettingsModel
        # Kein db-Parameter hier, aber wir können es aus dem Service holen
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


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/{anlage_id}", response_model=LiveDashboardResponse)
async def get_live_data(
    anlage_id: int,
    demo: bool = Query(False, description="Demo-Modus mit simulierten Daten"),
    db: AsyncSession = Depends(get_db),
):
    """Aktuelle Leistungsdaten für eine Anlage."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if demo:
        return _generate_demo_data(anlage.id, anlage.anlagenname)

    service = get_live_power_service()
    return await service.get_live_data(anlage, db)


# ── Tagesverlauf Demo-Daten ──────────────────────────────────────────────────

def _generate_demo_tagesverlauf(anlage_id: int) -> dict:
    """Simulierter Tagesverlauf für Demo-Modus (Butterfly-Chart)."""
    import math

    now = datetime.now()

    # Demo-Serien: Zwei PV-Strings, Batterie, Wallbox, WP, Netz, Haushalt
    serien = [
        {"key": "pv_1", "label": "PV Süd (String A)", "kategorie": "pv",
         "farbe": "#eab308", "seite": "quelle", "bidirektional": False},
        {"key": "pv_2", "label": "PV Ost (String B)", "kategorie": "pv",
         "farbe": "#ca8a04", "seite": "quelle", "bidirektional": False},
        {"key": "batterie_3", "label": "BYD HVS 10.2", "kategorie": "batterie",
         "farbe": "#3b82f6", "seite": "quelle", "bidirektional": True},
        {"key": "wallbox_6", "label": "go-eCharger", "kategorie": "wallbox",
         "farbe": "#a855f7", "seite": "senke", "bidirektional": False},
        {"key": "waermepumpe_5", "label": "Viessmann Vitocal", "kategorie": "waermepumpe",
         "farbe": "#f97316", "seite": "senke", "bidirektional": False},
        {"key": "netz", "label": "Stromnetz", "kategorie": "netz",
         "farbe": "#ef4444", "seite": "quelle", "bidirektional": True},
        {"key": "haushalt", "label": "Haushalt", "kategorie": "haushalt",
         "farbe": "#10b981", "seite": "senke", "bidirektional": False},
    ]

    punkte = []
    lastprofil = {
        0: 0.2, 1: 0.18, 2: 0.15, 3: 0.15, 4: 0.15, 5: 0.2,
        6: 0.25, 7: 0.45, 8: 0.55, 9: 0.40, 10: 0.35,
        11: 0.38, 12: 0.50, 13: 0.45, 14: 0.35, 15: 0.33,
        16: 0.35, 17: 0.50, 18: 0.65, 19: 0.70, 20: 0.55,
        21: 0.40, 22: 0.30, 23: 0.22,
    }

    for h in range(24):
        if h > now.hour:
            break

        werte: dict[str, float] = {}

        # PV: Glockenkurve, String A (Süd) stärker als String B (Ost, Peak früher)
        pv_a_base = max(0, 5.5 * math.exp(-((h - 13) ** 2) / 18))
        pv_b_base = max(0, 2.8 * math.exp(-((h - 11) ** 2) / 14))
        pv_a = round(pv_a_base * (0.85 + random.uniform(0, 0.3)), 2) if pv_a_base > 0.1 else 0
        pv_b = round(pv_b_base * (0.85 + random.uniform(0, 0.3)), 2) if pv_b_base > 0.1 else 0
        pv_total = pv_a + pv_b

        if pv_a > 0:
            werte["pv_1"] = pv_a  # Quelle → positiv
        if pv_b > 0:
            werte["pv_2"] = pv_b  # Quelle → positiv

        # Haushalt (BDEW H0)
        haushalt = round(lastprofil.get(h, 0.3) * (0.8 + random.uniform(0, 0.4)), 2)

        # Wallbox: Nachmittags laden
        wallbox = round(random.uniform(3, 7), 2) if (15 <= h <= 17 and random.random() > 0.4) else 0

        # WP: Morgens und abends stärker
        wp = round(random.uniform(1.2, 2.5), 2) if h in (6, 7, 8, 17, 18, 19) else round(0.3 * random.uniform(0.5, 1.5), 2)

        verbrauch_gesamt = haushalt + wallbox + wp

        # Batterie: Laden bei PV-Überschuss, Entladen abends
        batt = 0.0
        if 10 <= h <= 15 and pv_total > verbrauch_gesamt + 0.5:
            batt = round(min(pv_total - verbrauch_gesamt, 3.0) * random.uniform(0.4, 0.8), 2)
            # Ladung → negativ (Senke)
            werte["batterie_3"] = round(-batt, 2)
        elif 18 <= h <= 22 and pv_total < verbrauch_gesamt:
            batt = round(min(verbrauch_gesamt - pv_total, 2.5) * random.uniform(0.3, 0.7), 2)
            # Entladung → positiv (Quelle)
            werte["batterie_3"] = round(batt, 2)

        # Netz: Residual aus PV + Batterie-Entladung - Verbrauch - Batterie-Ladung
        quellen = pv_total + (batt if werte.get("batterie_3", 0) > 0 else 0)
        senken = verbrauch_gesamt + (batt if werte.get("batterie_3", 0) < 0 else 0)
        netto = quellen - senken
        # Positiv = Einspeisung (Senke), Negativ = Bezug (Quelle)
        if abs(netto) > 0.01:
            # Netz: Bezug positiv (Quelle), Einspeisung negativ (Senke)
            werte["netz"] = round(-netto, 2)

        # Senken als negative Werte
        if wallbox > 0.01:
            werte["wallbox_6"] = round(-wallbox, 2)
        if wp > 0.05:
            werte["waermepumpe_5"] = round(-wp, 2)
        werte["haushalt"] = round(-haushalt, 2)

        punkte.append({"zeit": f"{h:02d}:00", "werte": werte})

    return {
        "anlage_id": anlage_id,
        "datum": now.strftime("%Y-%m-%d"),
        "serien": serien,
        "punkte": punkte,
    }


# ── Tagesverlauf Endpoint ────────────────────────────────────────────────────

@router.get("/{anlage_id}/tagesverlauf", response_model=TagesverlaufResponse)
async def get_tagesverlauf(
    anlage_id: int,
    demo: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Stündlicher Leistungsverlauf für heute (Butterfly-Chart: Quellen +, Senken -)."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if demo:
        return _generate_demo_tagesverlauf(anlage.id)

    service = get_live_power_service()
    tv_data = await service.get_tagesverlauf(anlage, db)

    return {
        "anlage_id": anlage.id,
        "datum": datetime.now().strftime("%Y-%m-%d"),
        "serien": tv_data.get("serien", []),
        "punkte": tv_data.get("punkte", []),
    }


# ── Wetter Models ─────────────────────────────────────────────────────────────

class WetterStunde(BaseModel):
    """Wetterdaten für eine Stunde."""
    zeit: str  # "14:00"
    temperatur_c: Optional[float] = None
    wetter_code: Optional[int] = None
    wetter_symbol: str = "unknown"
    bewoelkung_prozent: Optional[int] = None
    niederschlag_mm: Optional[float] = None
    globalstrahlung_wm2: Optional[float] = None


class VerbrauchsStunde(BaseModel):
    """Stündliches Erzeugung/Verbrauch-Profil."""
    zeit: str  # "14:00"
    pv_ertrag_kw: float
    verbrauch_kw: float
    pv_ml_prognose_kw: Optional[float] = None  # Solar Forecast ML (optional)


class LiveWetterResponse(BaseModel):
    anlage_id: int
    verfuegbar: bool
    aktuell: Optional[WetterStunde] = None
    stunden: list[WetterStunde] = []
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    sonnenstunden: Optional[float] = None
    pv_prognose_kwh: Optional[float] = None
    grundlast_kw: Optional[float] = None
    verbrauchsprofil: list[VerbrauchsStunde] = []
    profil_typ: str = "bdew_h0"  # "individuell_werktag", "individuell_wochenende", "bdew_h0"
    profil_quelle: Optional[str] = None  # "ha", "mqtt" — woher die History kam
    profil_tage: Optional[int] = None  # Anzahl Tage die ins individuelle Profil einflossen
    sfml_prognose_kwh: Optional[float] = None  # Solar Forecast ML Tagesprognose
    sfml_tomorrow_kwh: Optional[float] = None  # Solar Forecast ML Morgen-Prognose
    sfml_accuracy_pct: Optional[float] = None  # Solar Forecast ML Modellgenauigkeit
    solar_noon: Optional[str] = None  # Solar Noon als "HH:MM" (z.B. "12:27")
    sunrise: Optional[str] = None  # Sonnenaufgang als "HH:MM"
    sunset: Optional[str] = None  # Sonnenuntergang als "HH:MM"


# ── Typisches Haushaltsprofil (BDEW H0) ──────────────────────────────────────

# Normierter Stundenverbrauch eines 4000 kWh/a Haushalts (kW, Werktag Übergang)
# Quelle: BDEW Standardlastprofil H0, vereinfacht auf Stundenwerte
_LASTPROFIL_KW = {
    6: 0.25, 7: 0.45, 8: 0.55, 9: 0.40, 10: 0.35,
    11: 0.38, 12: 0.50, 13: 0.45, 14: 0.35, 15: 0.33,
    16: 0.35, 17: 0.50, 18: 0.65, 19: 0.70, 20: 0.55,
}

DEFAULT_SYSTEM_LOSSES = 0.14  # Kabel, Wechselrichter, Verschmutzung


def _extract_time(values: Optional[list]) -> Optional[str]:
    """Extrahiert HH:MM aus Open-Meteo ISO-Zeitstring (z.B. '2026-03-23T06:15')."""
    if not values or not values[0]:
        return None
    try:
        return values[0].split("T")[1][:5]
    except (IndexError, AttributeError):
        return None


def _format_solar_noon(longitude: Optional[float]) -> Optional[str]:
    """Solar Noon als 'HH:MM' String für heute."""
    if longitude is None:
        return None
    noon = _solar_noon_hour(date.today().isoformat(), longitude)
    h = int(noon)
    m = int((noon - h) * 60)
    return f"{h:02d}:{m:02d}"
TEMP_COEFFICIENT = 0.004  # -0.4%/°C über 25°C (typisch Silizium)

# Ausrichtungs-Text → Azimut (0=Süd, -90=Ost, 90=West)
_AUSRICHTUNG_ZU_AZIMUT = {
    "süd": 0, "s": 0, "south": 0, "sued": 0,
    "südost": -45, "so": -45, "suedost": -45,
    "ost": -90, "o": -90, "east": -90,
    "nordost": -135, "no": -135,
    "nord": 180, "n": 180, "north": 180,
    "nordwest": 135, "nw": 135,
    "west": 90, "w": 90,
    "südwest": 45, "sw": 45, "suedwest": 45,
}


def _get_pv_orientierungsgruppen(pv_module: list) -> list[dict]:
    """
    Gruppiert PV-Module nach Orientierung (Neigung + Ausrichtung).

    Returns:
        Liste von Gruppen: [{"neigung": int, "ausrichtung": int, "kwp": float}, ...]
        Bei nur einer Gruppe = alle Module gleich ausgerichtet.
        Leere Liste falls keine PV-Module vorhanden.
    """
    if not pv_module:
        return []

    # Module einzeln auflösen
    module_configs = []
    for pv in pv_module:
        kwp = pv.leistung_kwp or 0
        if kwp <= 0:
            continue

        # Neigung: Direkt-Feld > Parameter > Default 35°
        neigung = pv.neigung_grad
        if neigung is None:
            params = pv.parameter or {}
            neigung = params.get("neigung_grad")
            if neigung is None:
                neigung = params.get("neigung", 35)

        # Ausrichtung: parameter.ausrichtung_grad (numerisch) > Direkt-Feld (Text) > 0
        params = pv.parameter or {}
        azimut = params.get("ausrichtung_grad")
        if azimut is None:
            text = pv.ausrichtung or ""
            azimut = _AUSRICHTUNG_ZU_AZIMUT.get(text.lower(), 0)

        module_configs.append({
            "neigung": round(float(neigung)),
            "ausrichtung": round(float(azimut)),
            "kwp": kwp,
        })

    if not module_configs:
        return []

    # Nach (neigung, ausrichtung) gruppieren und kWp summieren
    gruppen: dict[tuple[int, int], float] = {}
    for m in module_configs:
        key = (m["neigung"], m["ausrichtung"])
        gruppen[key] = gruppen.get(key, 0) + m["kwp"]

    return [
        {"neigung": n, "ausrichtung": a, "kwp": kwp}
        for (n, a), kwp in gruppen.items()
    ]


def _berechne_verbrauchsprofil(
    stunden: list[dict],
    kwp: float,
    jahresverbrauch_kwh: float = 4000,
    individuelles_profil: Optional[dict] = None,
) -> tuple[list[dict], Optional[float], Optional[float], bool]:
    """
    Berechnet stündliches PV-Ertrag + Verbrauchsprofil.

    PV-Ertrag: Nutzt GTI (Global Tilted Irradiance) falls verfügbar,
    sonst Fallback auf GHI (shortwave_radiation).
    Temperaturkorrektur: -0.4%/°C über 25°C Modultemperatur.

    Args:
        individuelles_profil: Stundenwerte {0: kW, 1: kW, ..., 23: kW} oder None

    Returns:
        (profil, pv_prognose_kwh, grundlast_kw, ist_individuell)
    """
    ist_individuell = individuelles_profil is not None
    tages_faktor = jahresverbrauch_kwh / 4000  # Nur für BDEW-Fallback

    profil = []
    pv_summe_kwh = 0.0

    for s in stunden:
        h = int(s["zeit"].split(":")[0])

        # GTI bevorzugen (auf Modulebene geneigt), sonst GHI-Fallback
        strahlung = s.get("gti_wm2") or s.get("globalstrahlung_wm2") or 0

        if strahlung > 0 and kwp > 0:
            # Basis-Ertrag: Strahlung/1000 × kWp × (1 - Systemverluste)
            pv_kw = strahlung * kwp * (1 - DEFAULT_SYSTEM_LOSSES) / 1000

            # Temperaturkorrektur
            temp = s.get("temperatur_c")
            if temp is not None:
                aufheizung = min(25, strahlung / 40)  # ~25°C bei 1000 W/m²
                modul_temp = temp + aufheizung
                if modul_temp > 25:
                    pv_kw *= (1 - (modul_temp - 25) * TEMP_COEFFICIENT)

            pv_kw = round(max(0, pv_kw), 2)
        else:
            pv_kw = 0.0

        pv_summe_kwh += pv_kw  # 1h x kW = kWh

        if individuelles_profil is not None:
            # Individuelles Profil: Schlüssel sind int oder str
            verbrauch_kw = round(individuelles_profil.get(h, individuelles_profil.get(str(h), 0.3)), 2)
        else:
            # BDEW H0 Fallback
            verbrauch_kw = round(_LASTPROFIL_KW.get(h, 0.3) * tages_faktor, 2)

        profil.append({
            "zeit": s["zeit"],
            "pv_ertrag_kw": pv_kw,
            "verbrauch_kw": verbrauch_kw,
        })

    # Grundlast: Median der Nachtstunden (0-5 Uhr) — kein PV das die Bilanz verfälscht,
    # Median ist robust gegen einzelne Ausreißer/Messfehler
    nacht_verbrauch = sorted([
        p["verbrauch_kw"] for p in profil
        if int(p["zeit"].split(":")[0]) <= 5 and p["verbrauch_kw"] > 0
    ])
    if nacht_verbrauch:
        mid = len(nacht_verbrauch) // 2
        grundlast = round(
            nacht_verbrauch[mid] if len(nacht_verbrauch) % 2
            else (nacht_verbrauch[mid - 1] + nacht_verbrauch[mid]) / 2,
            2,
        )
    else:
        grundlast = None

    return profil, round(pv_summe_kwh, 1) if pv_summe_kwh > 0 else None, grundlast, ist_individuell


# ── Wetter Demo-Daten ─────────────────────────────────────────────────────────

def _generate_demo_wetter(kwp: float = 10.0) -> dict:
    """Simuliertes Wetter für Demo-Modus."""
    now = datetime.now()
    alle_stunden = []  # 0-23 für Verbrauchsprofil
    stunden = []       # 6-20 für Wetter-Timeline

    for h in range(24):
        strahlung = max(0, 800 * max(0, 1 - ((h - 13) / 5) ** 2))
        strahlung *= (0.85 + random.uniform(0, 0.3))

        temp = 8 + 10 * max(0, 1 - ((h - 15) / 7) ** 2)
        temp += random.uniform(-1, 1)

        bewoelkung = max(0, min(100, int(100 - strahlung / 10 + random.randint(-10, 20))))

        if bewoelkung < 25:
            code = 0
        elif bewoelkung < 60:
            code = random.choice([1, 2])
        else:
            code = random.choice([2, 3, 61])

        niederschlag = round(random.uniform(0, 0.5), 1) if code >= 61 else 0.0

        # GTI simulieren: ~10% mehr als GHI bei optimaler Südausrichtung 35°
        gti = round(strahlung * 1.1, 0) if strahlung > 0 else 0

        stunde = {
            "zeit": f"{h:02d}:00",
            "temperatur_c": round(temp, 1),
            "wetter_code": code,
            "wetter_symbol": wetter_code_zu_symbol(code),
            "bewoelkung_prozent": bewoelkung,
            "niederschlag_mm": niederschlag,
            "globalstrahlung_wm2": round(strahlung, 0),
            "gti_wm2": gti,
        }
        alle_stunden.append(stunde)
        if 6 <= h <= 20:
            stunden.append(stunde)

    aktuelle_stunde = None
    for s in stunden:
        h = int(s["zeit"].split(":")[0])
        if h <= now.hour:
            aktuelle_stunde = s
    if aktuelle_stunde is None and stunden:
        aktuelle_stunde = stunden[0]

    temps = [s["temperatur_c"] for s in stunden]

    # Simuliertes individuelles Profil — Gesamtverbrauch inkl. WP, Wallbox, Haushalt
    # (In Realität berechnet aus: PV + Netzbezug - Einspeisung über 14 Tage)
    ist_wochenende = now.weekday() >= 5
    demo_profil = {
        # Wochenende: später aufstehen, WP morgens/abends, mittags kochen, kein Wallbox
        0: 0.55, 1: 0.45, 2: 0.40, 3: 0.40, 4: 0.40, 5: 0.50,
        6: 1.80, 7: 2.20, 8: 2.50, 9: 1.40, 10: 0.90,
        11: 1.10, 12: 1.80, 13: 1.20, 14: 0.80, 15: 0.75,
        16: 0.85, 17: 2.30, 18: 2.80, 19: 2.50, 20: 1.20,
        21: 0.80, 22: 0.60, 23: 0.55,
    } if ist_wochenende else {
        # Werktag: WP-Spitzen 6-8 + 17-19, Wallbox 15-17, Haushalt-Grundlast
        0: 0.50, 1: 0.40, 2: 0.35, 3: 0.35, 4: 0.35, 5: 0.45,
        6: 2.10, 7: 2.80, 8: 1.60, 9: 0.70, 10: 0.55,
        11: 0.60, 12: 0.90, 13: 0.70, 14: 0.55, 15: 4.20,
        16: 4.50, 17: 2.80, 18: 2.90, 19: 2.60, 20: 1.30,
        21: 0.85, 22: 0.60, 23: 0.50,
    }

    profil, pv_prognose, grundlast, _ = _berechne_verbrauchsprofil(
        alle_stunden, kwp, individuelles_profil=demo_profil,
    )

    return {
        "anlage_id": 0,
        "verfuegbar": True,
        "aktuell": aktuelle_stunde,
        "stunden": stunden,
        "temperatur_min_c": round(min(temps), 1),
        "temperatur_max_c": round(max(temps), 1),
        "sonnenstunden": round(sum(1 for s in stunden if (s["globalstrahlung_wm2"] or 0) > 120) * 0.9, 1),
        "pv_prognose_kwh": pv_prognose,
        "grundlast_kw": grundlast,
        "verbrauchsprofil": profil,
        "profil_typ": "individuell_wochenende" if ist_wochenende else "individuell_werktag",
        "profil_quelle": "demo",
        "profil_tage": 14,
    }


# ── Multi-String GTI-Fetch ────────────────────────────────────────────────────

async def _fetch_gti_for_gruppe(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    neigung: int,
    ausrichtung: int,
) -> Optional[list]:
    """
    Holt stündliche GTI-Werte für eine Orientierungsgruppe von Open-Meteo.

    Returns:
        Liste mit 24 stündlichen GTI-Werten (W/m²) oder None bei Fehler.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "global_tilted_irradiance",
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
        "tilt": neigung,
        "azimuth": ausrichtung,
    }
    try:
        resp = await client.get(
            f"{settings.open_meteo_api_url}/forecast", params=params
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("hourly", {}).get("global_tilted_irradiance", [])
    except Exception as e:
        logger.warning(f"GTI-Fetch Neigung={neigung}° Azimut={ausrichtung}°: {e}")
        return None


async def _fetch_multi_string_gti(
    latitude: float,
    longitude: float,
    gruppen: list[dict],
) -> list:
    """
    Berechnet gewichtete GTI-Werte für mehrere Orientierungsgruppen.

    Bei nur einer Gruppe: Einzelner API-Call (in den Haupt-Request integriert).
    Bei mehreren Gruppen: Parallele API-Calls, kWp-gewichtete Kombination.

    Returns:
        Liste mit 24 kombinierten GTI-Werten (W/m²).
    """
    kwp_gesamt = sum(g["kwp"] for g in gruppen)
    if kwp_gesamt <= 0:
        return []

    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [
            _fetch_gti_for_gruppe(client, latitude, longitude, g["neigung"], g["ausrichtung"])
            for g in gruppen
        ]
        ergebnisse = await asyncio.gather(*tasks)

    # kWp-gewichtete Kombination der GTI-Werte
    n_stunden = 24
    kombiniert = [0.0] * n_stunden

    for gruppe, gti_values in zip(gruppen, ergebnisse):
        if not gti_values:
            continue
        gewicht = gruppe["kwp"] / kwp_gesamt
        for i in range(min(n_stunden, len(gti_values))):
            val = gti_values[i]
            if val is not None:
                kombiniert[i] += val * gewicht

    return kombiniert


# ── Lernfaktor ────────────────────────────────────────────────────────────────

async def _get_lernfaktor(anlage_id: int, db: AsyncSession) -> Optional[float]:
    """
    Berechnet einen Korrekturfaktor aus historischen IST/Prognose-Vergleichen.

    Nutzt die TagesZusammenfassung der letzten 30 Tage:
    - IST = Summe aller PV-Komponenten-kWh (positive Werte in komponenten_kwh)
    - Prognose = pv_prognose_kwh (gespeichert beim Wetter-Abruf)

    Returns:
        Korrekturfaktor (z.B. 0.92 = Anlage liefert 8% weniger als Prognose)
        oder None wenn nicht genug Daten (< 7 Tage).
    """
    vor_30_tagen = date.today() - timedelta(days=30)

    result = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= vor_30_tagen,
            TagesZusammenfassung.datum < date.today(),  # Heute ausschließen (noch nicht komplett)
            TagesZusammenfassung.pv_prognose_kwh.isnot(None),
            TagesZusammenfassung.pv_prognose_kwh > 0,
        )
    )
    tage = result.scalars().all()

    ratios = []
    for tag in tage:
        # IST: Summe der positiven Werte in komponenten_kwh (= PV-Erzeugung)
        ist_kwh = 0.0
        if tag.komponenten_kwh:
            ist_kwh = sum(v for v in tag.komponenten_kwh.values() if v > 0)

        if ist_kwh > 0.5 and tag.pv_prognose_kwh > 0.5:  # Nur Tage mit relevanter Produktion
            ratios.append(ist_kwh / tag.pv_prognose_kwh)

    if len(ratios) < 7:
        return None

    # Median statt Mean — robust gegen einzelne Ausreißer (Schnee, Schatten, Störung)
    ratios.sort()
    mid = len(ratios) // 2
    median = ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2

    # Faktor auf realistischen Bereich begrenzen (0.5 – 1.3)
    faktor = max(0.5, min(1.3, median))

    logger.info(
        f"Lernfaktor Anlage {anlage_id}: {faktor:.3f} "
        f"(Median aus {len(ratios)} Tagen, Range {min(ratios):.2f}–{max(ratios):.2f})"
    )

    return round(faktor, 3)


async def _speichere_prognose(
    anlage_id: int,
    datum: date,
    prognose_kwh: float,
    sfml_kwh: float | None = None,
):
    """
    Speichert die PV-Tagesprognose in TagesZusammenfassung (Upsert).

    Nutzt eine eigene DB-Session (fire-and-forget aus dem Request-Kontext).
    Falls der Tag schon existiert (z.B. durch Scheduler), wird nur pv_prognose_kwh aktualisiert.
    Falls nicht, wird ein minimaler Eintrag angelegt.
    """
    from backend.core.database import get_session

    try:
        async with get_session() as db:
            result = await db.execute(
                select(TagesZusammenfassung).where(
                    TagesZusammenfassung.anlage_id == anlage_id,
                    TagesZusammenfassung.datum == datum,
                )
            )
            tz = result.scalar_one_or_none()

            if tz:
                tz.pv_prognose_kwh = prognose_kwh
                if sfml_kwh is not None:
                    tz.sfml_prognose_kwh = sfml_kwh
            else:
                tz = TagesZusammenfassung(
                    anlage_id=anlage_id,
                    datum=datum,
                    pv_prognose_kwh=prognose_kwh,
                    sfml_prognose_kwh=sfml_kwh,
                    stunden_verfuegbar=0,
                    datenquelle="wetter_prognose",
                )
                db.add(tz)

            await db.commit()
    except Exception as e:
        logger.debug(f"Prognose speichern fehlgeschlagen: {e}")


# ── Wetter Endpoint ──────────────────────────────────────────────────────────

@router.get("/{anlage_id}/wetter", response_model=LiveWetterResponse)
async def get_live_wetter(
    anlage_id: int,
    demo: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Aktuelles Wetter + PV-Prognose + Verbrauchsprofil für heute."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # PV-Module laden für Orientierung und kWp
    pv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            Investition.aktiv == True,
        )
    )
    pv_module = list(pv_result.scalars().all())
    gruppen = _get_pv_orientierungsgruppen(pv_module)
    kwp = sum(g["kwp"] for g in gruppen) if gruppen else (anlage.leistung_kwp or 10.0)

    if demo:
        data = _generate_demo_wetter(kwp)
        data["anlage_id"] = anlage.id
        return data

    if not anlage.latitude or not anlage.longitude:
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}

    try:
        # Haupt-Wetter-Request (Wetterdaten + GHI)
        # Bei nur einer Orientierungsgruppe: GTI direkt mit abfragen
        hat_multi_string = len(gruppen) > 1
        haupt_neigung = gruppen[0]["neigung"] if gruppen else 35
        haupt_azimut = gruppen[0]["ausrichtung"] if gruppen else 0

        hourly_vars = [
            "temperature_2m", "weather_code", "cloud_cover",
            "precipitation", "shortwave_radiation",
        ]
        if not hat_multi_string:
            hourly_vars.append("global_tilted_irradiance")

        params = {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "hourly": ",".join(hourly_vars),
            "daily": "sunshine_duration,temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "timezone": "Europe/Berlin",
            "forecast_days": 1,
        }
        if not hat_multi_string:
            params["tilt"] = haupt_neigung
            params["azimuth"] = haupt_azimut

        # Bei Multi-String: paralleler GTI-Fetch + Haupt-Request gleichzeitig
        async with httpx.AsyncClient(timeout=15.0) as client:
            if hat_multi_string:
                haupt_task = client.get(
                    f"{settings.open_meteo_api_url}/forecast", params=params
                )
                gti_task = _fetch_multi_string_gti(
                    anlage.latitude, anlage.longitude, gruppen
                )
                haupt_resp, multi_gti = await asyncio.gather(haupt_task, gti_task)
                haupt_resp.raise_for_status()
                data = haupt_resp.json()
            else:
                resp = await client.get(
                    f"{settings.open_meteo_api_url}/forecast", params=params
                )
                resp.raise_for_status()
                data = resp.json()
                multi_gti = None

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        # GTI-Werte: Bei Single-String aus Haupt-Request, bei Multi-String aus gewichtetem Ergebnis
        if multi_gti:
            gti_values = multi_gti
        else:
            gti_values = hourly.get("global_tilted_irradiance", [])

        now = datetime.now()

        # Lernfaktor laden (historischer IST/Prognose-Vergleich)
        lernfaktor = await _get_lernfaktor(anlage_id, db)

        alle_stunden = []  # 0-23 für Verbrauchsprofil
        stunden = []       # 6-20 für Wetter-Timeline
        for i, t in enumerate(times):
            h = int(t[11:13])

            code = hourly.get("weather_code", [None] * len(times))[i]
            gti = gti_values[i] if i < len(gti_values) else None

            # Lernfaktor auf GTI anwenden (skaliert die Strahlung, nicht den Ertrag,
            # damit Temperaturkorrektur weiterhin korrekt greift)
            if gti is not None and lernfaktor is not None:
                gti = gti * lernfaktor

            stunde = {
                "zeit": f"{h:02d}:00",
                "temperatur_c": hourly.get("temperature_2m", [None] * len(times))[i],
                "wetter_code": code,
                "wetter_symbol": wetter_code_zu_symbol(code),
                "bewoelkung_prozent": hourly.get("cloud_cover", [None] * len(times))[i],
                "niederschlag_mm": hourly.get("precipitation", [None] * len(times))[i],
                "globalstrahlung_wm2": hourly.get("shortwave_radiation", [None] * len(times))[i],
                "gti_wm2": gti,
            }
            alle_stunden.append(stunde)
            if 6 <= h <= 20:
                stunden.append(stunde)

        aktuelle_stunde = None
        for s in stunden:
            h = int(s["zeit"].split(":")[0])
            if h <= now.hour:
                aktuelle_stunde = s

        daily = data.get("daily", {})
        sunshine_s = (daily.get("sunshine_duration", [None]) or [None])[0]

        # Individuelles Verbrauchsprofil laden (Werktag/Wochenende)
        service = get_live_power_service()
        ind_profil_data = await service.get_verbrauchsprofil(anlage, db)

        ind_stunden_profil = None
        profil_typ = "bdew_h0"
        profil_tage = None

        if ind_profil_data:
            ist_wochenende = now.weekday() >= 5
            if ist_wochenende and ind_profil_data.get("wochenende"):
                ind_stunden_profil = ind_profil_data["wochenende"]
                profil_typ = "individuell_wochenende"
                profil_tage = ind_profil_data["tage_wochenende"]
            elif not ist_wochenende and ind_profil_data.get("werktag"):
                ind_stunden_profil = ind_profil_data["werktag"]
                profil_typ = "individuell_werktag"
                profil_tage = ind_profil_data["tage_werktag"]

        profil, pv_prognose, grundlast, ist_ind = _berechne_verbrauchsprofil(
            alle_stunden, kwp, individuelles_profil=ind_stunden_profil,
        )

        # ── SFML: Solar Forecast ML (optional) ──
        sfml_kwh = None
        sfml_tomorrow = None
        sfml_accuracy = None
        basis_live = (anlage.sensor_mapping or {}).get("basis", {}).get("live", {})
        sfml_entity = basis_live.get("sfml_today_kwh") if basis_live else None

        if sfml_entity:
            try:
                from backend.services.ha_state_service import get_ha_state_service
                ha_svc = get_ha_state_service()
                sfml_kwh = await ha_svc.get_sensor_state(sfml_entity)

                tomorrow_entity = basis_live.get("sfml_tomorrow_kwh")
                if tomorrow_entity:
                    sfml_tomorrow = await ha_svc.get_sensor_state(tomorrow_entity)

                accuracy_entity = basis_live.get("sfml_accuracy_pct")
                if accuracy_entity:
                    sfml_accuracy = await ha_svc.get_sensor_state(accuracy_entity)

                # Tages-kWh auf GTI-Kurvenform verteilen
                if sfml_kwh is not None and sfml_kwh > 0 and profil:
                    gti_summe = sum(p["pv_ertrag_kw"] for p in profil)
                    if gti_summe > 0:
                        sfml_factor = sfml_kwh / gti_summe
                        for p in profil:
                            p["pv_ml_prognose_kw"] = round(p["pv_ertrag_kw"] * sfml_factor, 2)
            except Exception as e:
                logger.debug(f"SFML-Sensoren nicht lesbar: {e}")

        # Prognose für Lernfaktor-Berechnung + SFML speichern (fire-and-forget)
        if pv_prognose is not None and pv_prognose > 0:
            asyncio.create_task(
                _speichere_prognose(anlage.id, date.today(), pv_prognose, sfml_kwh)
            )

        return {
            "anlage_id": anlage.id,
            "verfuegbar": len(stunden) > 0,
            "aktuell": aktuelle_stunde,
            "stunden": stunden,
            "temperatur_min_c": (daily.get("temperature_2m_min", [None]) or [None])[0],
            "temperatur_max_c": (daily.get("temperature_2m_max", [None]) or [None])[0],
            "sonnenstunden": round(sunshine_s / 3600, 1) if sunshine_s is not None else None,
            "pv_prognose_kwh": pv_prognose,
            "grundlast_kw": grundlast,
            "verbrauchsprofil": profil,
            "profil_typ": profil_typ if ist_ind else "bdew_h0",
            "profil_quelle": ind_profil_data.get("quelle") if ind_profil_data and ist_ind else None,
            "profil_tage": profil_tage,
            "sfml_prognose_kwh": round(sfml_kwh, 1) if sfml_kwh is not None else None,
            "sfml_tomorrow_kwh": round(sfml_tomorrow, 1) if sfml_tomorrow is not None else None,
            "sfml_accuracy_pct": round(sfml_accuracy, 1) if sfml_accuracy is not None else None,
            "solar_noon": _format_solar_noon(anlage.longitude),
            "sunrise": _extract_time(daily.get("sunrise", [None])),
            "sunset": _extract_time(daily.get("sunset", [None])),
        }

    except Exception as e:
        logger.warning(f"Live-Wetter Fehler: {e}")
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}


# ── MQTT-Inbound Status ─────────────────────────────────────────────────────

