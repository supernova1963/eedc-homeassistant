"""
Live Dashboard API - Echtzeit-Leistungsdaten.

GET /api/live/{anlage_id} — Aktuelle Leistungswerte für eine Anlage.
GET /api/live/{anlage_id}/tagesverlauf — Stündlicher Leistungsverlauf.
"""

import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.live_power_service import get_live_power_service

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
    summe_pv_kw: float = 0

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
        "summe_pv_kw": round(pv_kw, 2),
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

    for m in range(144):
        h_int = m * 10 // 60
        min_int = m * 10 % 60
        if h_int > now.hour or (h_int == now.hour and min_int > now.minute):
            break

        h_float = m / 6.0
        werte: dict[str, float] = {}

        # PV: Glockenkurve, String A (Süd) stärker als String B (Ost, Peak früher)
        pv_a_base = max(0, 5.5 * math.exp(-((h_float - 13) ** 2) / 18))
        pv_b_base = max(0, 2.8 * math.exp(-((h_float - 11) ** 2) / 14))
        pv_a = round(pv_a_base * (0.85 + random.uniform(0, 0.3)), 2) if pv_a_base > 0.1 else 0
        pv_b = round(pv_b_base * (0.85 + random.uniform(0, 0.3)), 2) if pv_b_base > 0.1 else 0
        pv_total = pv_a + pv_b

        if pv_a > 0:
            werte["pv_1"] = pv_a  # Quelle → positiv
        if pv_b > 0:
            werte["pv_2"] = pv_b  # Quelle → positiv

        # Haushalt (BDEW H0)
        haushalt = round(lastprofil.get(h_int, 0.3) * (0.8 + random.uniform(0, 0.4)), 2)

        # Wallbox: Nachmittags laden
        wallbox = round(random.uniform(3, 7), 2) if (15 <= h_float <= 17 and random.random() > 0.4) else 0

        # WP: Morgens und abends stärker
        wp = round(random.uniform(1.2, 2.5), 2) if h_int in (6, 7, 8, 17, 18, 19) else round(0.3 * random.uniform(0.5, 1.5), 2)

        verbrauch_gesamt = haushalt + wallbox + wp

        # Batterie: Laden bei PV-Überschuss, Entladen abends
        batt = 0.0
        if 10 <= h_float <= 15 and pv_total > verbrauch_gesamt + 0.5:
            batt = round(min(pv_total - verbrauch_gesamt, 3.0) * random.uniform(0.4, 0.8), 2)
            # Ladung → negativ (Senke)
            werte["batterie_3"] = round(-batt, 2)
        elif 18 <= h_float <= 22 and pv_total < verbrauch_gesamt:
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

        punkte.append({"zeit": f"{h_int:02d}:{min_int:02d}", "werte": werte})

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



