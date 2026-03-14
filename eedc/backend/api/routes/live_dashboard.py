"""
Live Dashboard API - Echtzeit-Leistungsdaten.

GET /api/live/{anlage_id} — Aktuelle Leistungswerte für eine Anlage.
GET /api/live/{anlage_id}?demo=true — Simulierte Demo-Daten (Entwicklung).
GET /api/live/{anlage_id}/wetter — Aktuelles Wetter + PV-Prognose + Verbrauchsprofil.
"""

import logging
import random
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.anlage import Anlage
from backend.models.investition import Investition
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


class TagesverlaufPunkt(BaseModel):
    """Ein Stunden-Datenpunkt im Tagesverlauf."""
    zeit: str  # "14:00"
    pv: Optional[float] = None
    einspeisung: Optional[float] = None
    netzbezug: Optional[float] = None
    batterie: Optional[float] = None
    eauto: Optional[float] = None
    waermepumpe: Optional[float] = None
    haushalt: Optional[float] = None
    verbrauch_gesamt: Optional[float] = None


class TagesverlaufResponse(BaseModel):
    anlage_id: int
    datum: str  # "2026-03-14"
    punkte: list[TagesverlaufPunkt]


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
    eauto_kw = jitter(3.7) if random.random() > 0.3 else 0
    wp_kw = jitter(1.8)
    batt_soc = min(100, max(0, 72 + random.randint(-5, 5)))
    eauto_soc = min(100, max(0, 45 + random.randint(-3, 3)))

    # Energiebilanz
    summe_erz = pv_kw + bezug_kw + (batt_kw if not ist_ladung else 0)
    bekannte_vrb = einsp_kw + (batt_kw if ist_ladung else 0) + eauto_kw + wp_kw
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
            {"key": "eauto_4", "label": "VW ID.4", "icon": "car",
             "erzeugung_kw": None, "verbrauch_kw": eauto_kw},
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
    port = int(config.get("port", 1883))
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
            topics_resp = await get_mqtt_topics(db)
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
            "waermepumpe": [("stromverbrauch_kwh", "Stromverbrauch (kWh)")],
            "e-auto": [("ladung_kwh", "Ladung (kWh)")],
            "wallbox": [("ladung_kwh", "Ladung (kWh)")],
            "balkonkraftwerk": [("pv_erzeugung_kwh", "Erzeugung (kWh)")],
        }

        for inv in investitionen:
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

            # Energy-Topics
            for key, label in energy_keys_by_typ.get(inv.typ, []):
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
    port = int(config.get("port", 1883))
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
    """Simulierter Tagesverlauf für Demo-Modus."""
    import math

    now = datetime.now()
    punkte = []

    for h in range(24):
        if h > now.hour:
            break

        # PV: Glockenkurve mit Peak bei 13 Uhr
        pv_base = max(0, 8.0 * math.exp(-((h - 13) ** 2) / 18))
        pv = round(pv_base * (0.85 + random.uniform(0, 0.3)), 2) if pv_base > 0.1 else 0

        # Verbrauch: BDEW H0 Profil
        lastprofil = {
            0: 0.2, 1: 0.18, 2: 0.15, 3: 0.15, 4: 0.15, 5: 0.2,
            6: 0.25, 7: 0.45, 8: 0.55, 9: 0.40, 10: 0.35,
            11: 0.38, 12: 0.50, 13: 0.45, 14: 0.35, 15: 0.33,
            16: 0.35, 17: 0.50, 18: 0.65, 19: 0.70, 20: 0.55,
            21: 0.40, 22: 0.30, 23: 0.22,
        }
        haushalt = round(lastprofil.get(h, 0.3) * (0.8 + random.uniform(0, 0.4)), 2)

        # E-Auto: Zufällig nachmittags laden
        eauto = round(random.uniform(3, 7), 2) if (15 <= h <= 17 and random.random() > 0.4) else 0

        # WP: Morgens und abends
        wp = round(random.uniform(1.2, 2.5), 2) if (h in [6, 7, 8, 17, 18, 19]) else round(0.3 * random.uniform(0.5, 1.5), 2)

        verbrauch_gesamt = round(haushalt + eauto + wp, 2)

        # Netz: Differenz PV - Verbrauch
        netto = pv - verbrauch_gesamt
        einspeisung = round(max(0, netto), 2)
        netzbezug = round(max(0, -netto), 2)

        # Batterie: Laden wenn Überschuss, Entladen abends
        batt = 0.0
        if 10 <= h <= 15 and pv > verbrauch_gesamt + 0.5:
            batt = round(min(pv - verbrauch_gesamt - einspeisung * 0.3, 3.0), 2)
        elif 18 <= h <= 22 and netzbezug > 0.3:
            batt = round(-min(netzbezug * 0.6, 2.5), 2)

        punkte.append({
            "zeit": f"{h:02d}:00",
            "pv": pv if pv > 0 else None,
            "einspeisung": einspeisung if einspeisung > 0 else None,
            "netzbezug": netzbezug if netzbezug > 0 else None,
            "batterie": batt if abs(batt) > 0.01 else None,
            "eauto": eauto if eauto > 0 else None,
            "waermepumpe": wp if wp > 0.05 else None,
            "haushalt": haushalt,
            "verbrauch_gesamt": verbrauch_gesamt,
        })

    return {
        "anlage_id": anlage_id,
        "datum": now.strftime("%Y-%m-%d"),
        "punkte": punkte,
    }


# ── Tagesverlauf Endpoint ────────────────────────────────────────────────────

@router.get("/{anlage_id}/tagesverlauf", response_model=TagesverlaufResponse)
async def get_tagesverlauf(
    anlage_id: int,
    demo: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Stündlicher Leistungsverlauf für heute."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if demo:
        return _generate_demo_tagesverlauf(anlage.id)

    service = get_live_power_service()
    punkte = await service.get_tagesverlauf(anlage, db)

    return {
        "anlage_id": anlage.id,
        "datum": datetime.now().strftime("%Y-%m-%d"),
        "punkte": punkte,
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


# ── Typisches Haushaltsprofil (BDEW H0) ──────────────────────────────────────

# Normierter Stundenverbrauch eines 4000 kWh/a Haushalts (kW, Werktag Übergang)
# Quelle: BDEW Standardlastprofil H0, vereinfacht auf Stundenwerte
_LASTPROFIL_KW = {
    6: 0.25, 7: 0.45, 8: 0.55, 9: 0.40, 10: 0.35,
    11: 0.38, 12: 0.50, 13: 0.45, 14: 0.35, 15: 0.33,
    16: 0.35, 17: 0.50, 18: 0.65, 19: 0.70, 20: 0.55,
}

PERFORMANCE_RATIO = 0.85  # Typisch: Kabel, WR, Temperatur, Verschmutzung


def _berechne_verbrauchsprofil(
    stunden: list[dict], kwp: float, jahresverbrauch_kwh: float = 4000
) -> tuple[list[dict], Optional[float], Optional[float]]:
    """
    Berechnet stündliches PV-Ertrag + Verbrauchsprofil.

    PV-Ertrag: Strahlung(W/m²) x kWp x PR / 1000
    Verbrauch: BDEW H0 Lastprofil, skaliert auf Jahresverbrauch.

    Returns:
        (profil, pv_prognose_kwh, grundlast_kw)
    """
    tages_faktor = jahresverbrauch_kwh / 4000  # Normiert auf 4000 kWh/a

    profil = []
    pv_summe_kwh = 0.0

    for s in stunden:
        h = int(s["zeit"].split(":")[0])
        strahlung = s.get("globalstrahlung_wm2") or 0

        # PV: Bei 1000 W/m2 STC liefert 1 kWp genau 1 kW
        pv_kw = round(strahlung * kwp * PERFORMANCE_RATIO / 1000, 2)
        pv_summe_kwh += pv_kw  # 1h x kW = kWh

        verbrauch_kw = round(_LASTPROFIL_KW.get(h, 0.3) * tages_faktor, 2)

        profil.append({
            "zeit": s["zeit"],
            "pv_ertrag_kw": pv_kw,
            "verbrauch_kw": verbrauch_kw,
        })

    grundlast = round(min(p["verbrauch_kw"] for p in profil), 2) if profil else None

    return profil, round(pv_summe_kwh, 1) if pv_summe_kwh > 0 else None, grundlast


# ── Wetter Demo-Daten ─────────────────────────────────────────────────────────

def _generate_demo_wetter(kwp: float = 10.0) -> dict:
    """Simuliertes Wetter für Demo-Modus."""
    now = datetime.now()
    stunden = []

    for h in range(6, 21):
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

        stunden.append({
            "zeit": f"{h:02d}:00",
            "temperatur_c": round(temp, 1),
            "wetter_code": code,
            "wetter_symbol": wetter_code_zu_symbol(code),
            "bewoelkung_prozent": bewoelkung,
            "niederschlag_mm": niederschlag,
            "globalstrahlung_wm2": round(strahlung, 0),
        })

    aktuelle_stunde = None
    for s in stunden:
        h = int(s["zeit"].split(":")[0])
        if h <= now.hour:
            aktuelle_stunde = s
    if aktuelle_stunde is None and stunden:
        aktuelle_stunde = stunden[0]

    temps = [s["temperatur_c"] for s in stunden]
    profil, pv_prognose, grundlast = _berechne_verbrauchsprofil(stunden, kwp)

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
    }


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

    kwp = anlage.leistung_kwp or 10.0

    if demo:
        data = _generate_demo_wetter(kwp)
        data["anlage_id"] = anlage.id
        return data

    if not anlage.latitude or not anlage.longitude:
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}

    try:
        params = {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "hourly": ",".join([
                "temperature_2m", "weather_code", "cloud_cover",
                "precipitation", "shortwave_radiation",
            ]),
            "daily": "sunshine_duration,temperature_2m_max,temperature_2m_min",
            "timezone": "Europe/Berlin",
            "forecast_days": 1,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.open_meteo_api_url}/forecast", params=params
            )
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        now = datetime.now()

        stunden = []
        for i, t in enumerate(times):
            h = int(t[11:13])
            if h < 6 or h > 20:
                continue

            code = hourly.get("weather_code", [None] * len(times))[i]
            stunden.append({
                "zeit": f"{h:02d}:00",
                "temperatur_c": hourly.get("temperature_2m", [None] * len(times))[i],
                "wetter_code": code,
                "wetter_symbol": wetter_code_zu_symbol(code),
                "bewoelkung_prozent": hourly.get("cloud_cover", [None] * len(times))[i],
                "niederschlag_mm": hourly.get("precipitation", [None] * len(times))[i],
                "globalstrahlung_wm2": hourly.get("shortwave_radiation", [None] * len(times))[i],
            })

        aktuelle_stunde = None
        for s in stunden:
            h = int(s["zeit"].split(":")[0])
            if h <= now.hour:
                aktuelle_stunde = s

        daily = data.get("daily", {})
        sunshine_s = (daily.get("sunshine_duration", [None]) or [None])[0]

        profil, pv_prognose, grundlast = _berechne_verbrauchsprofil(stunden, kwp)

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
        }

    except Exception as e:
        logger.warning(f"Live-Wetter Fehler: {e}")
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}


# ── MQTT-Inbound Status ─────────────────────────────────────────────────────

