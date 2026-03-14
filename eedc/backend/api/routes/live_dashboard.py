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


# ── Demo-Daten ───────────────────────────────────────────────────────────────

def _generate_demo_data(anlage_id: int, anlage_name: str) -> dict:
    """Simulierte Live-Daten mit leichten Zufallsschwankungen."""
    def jitter(base: float, pct: float = 0.1) -> float:
        return round(base * (1 + random.uniform(-pct, pct)), 2)

    pv_kw = jitter(4.2)
    einsp_kw = jitter(1.1)
    bezug_kw = jitter(0.3, 0.3)
    batt_kw = jitter(0.5)
    ist_ladung = random.random() > 0.4
    eauto_kw = jitter(3.7) if random.random() > 0.3 else 0
    wp_kw = jitter(1.8)
    batt_soc = min(100, max(0, 72 + random.randint(-5, 5)))
    eauto_soc = min(100, max(0, 45 + random.randint(-3, 3)))

    # Energiebilanz: Summe Quellen == Summe Verbrauch
    # Quellen: PV, Netzbezug, Batterie-Entladung
    # Verbrauch: Einspeisung, Batterie-Ladung, E-Auto, WP, Haushalt (Rest)
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
            {"key": "pv", "label": "PV-Anlage", "icon": "sun",
             "erzeugung_kw": pv_kw, "verbrauch_kw": None},
            {"key": "netz", "label": "Stromnetz", "icon": "zap",
             "erzeugung_kw": bezug_kw if bezug_kw > 0 else None,
             "verbrauch_kw": einsp_kw if einsp_kw > 0 else None},
            {"key": "batterie", "label": "Speicher", "icon": "battery",
             "erzeugung_kw": batt_kw if not ist_ladung else None,
             "verbrauch_kw": batt_kw if ist_ladung else None},
            {"key": "eauto", "label": "E-Auto", "icon": "car",
             "erzeugung_kw": None, "verbrauch_kw": eauto_kw},
            {"key": "waermepumpe", "label": "Wärmepumpe", "icon": "flame",
             "erzeugung_kw": None, "verbrauch_kw": wp_kw},
            {"key": "haushalt", "label": "Haushalt", "icon": "home",
             "erzeugung_kw": None, "verbrauch_kw": haushalt_kw},
        ],
        "summe_erzeugung_kw": round(summe_erz, 2),
        "summe_verbrauch_kw": round(summe_vrb, 2),
        "gauges": [
            {"key": "netz", "label": "Netz", "wert": netto_w,
             "min_wert": -max_netz, "max_wert": max_netz, "einheit": "W"},
            {"key": "batterie_soc", "label": "Speicher", "wert": batt_soc,
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "eauto_soc", "label": "E-Auto", "wert": eauto_soc,
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "autarkie", "label": "Autarkie", "wert": min(autarkie, 100),
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
        ],
        "heute_pv_kwh": round(18.3 + random.uniform(-1, 1), 1),
        "heute_einspeisung_kwh": round(9.2 + random.uniform(-0.5, 0.5), 1),
        "heute_netzbezug_kwh": round(3.1 + random.uniform(-0.3, 0.3), 1),
        "heute_eigenverbrauch_kwh": round(9.1 + random.uniform(-0.5, 0.5), 1),
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
