"""
Live Wetter Router — Aktuelles Wetter + PV-Prognose + Verbrauchsprofil.

Ausgelagert aus live_dashboard.py (Router-Split).
GET /api/live/{anlage_id}/wetter
"""

import asyncio
import logging
import random
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
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
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.solar_forecast_service import _solar_noon_hour
from backend.services.live_power_service import get_live_power_service
from backend.services.wetter.utils import wetter_code_zu_symbol
from backend.services.wetter.cache import (
    _cache_get, _cache_set, _error_cache_check, _error_cache_set,
    ERROR_TTL_RATE_LIMIT, ERROR_TTL_SERVER_ERROR, ERROR_TTL_NETWORK,
)
from backend.services.wetter.models import WETTER_MODELLE

logger = logging.getLogger(__name__)

router = APIRouter()

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
    sonnenstunden_bisher: Optional[float] = None  # Ist-Sonnenstunden bis aktuelle Stunde
    sonnenstunden_rest: Optional[float] = None    # Prognostizierte Sonnenstunden ab aktueller Stunde
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
    wp_profil: Optional[dict] = None,
    referenz_temp_c: Optional[float] = None,
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

            # WP-Temperaturkorrektur: WP-Anteil mit Forecast-Temperatur skalieren
            if wp_profil and referenz_temp_c is not None:
                temp = s.get("temperatur_c")
                nenn = max(1.0, 15.0 - referenz_temp_c)
                if temp is not None:
                    faktor = max(0.3, min(3.0, (15.0 - temp) / nenn))
                    wp_kw = wp_profil.get(h, wp_profil.get(str(h), 0.0))
                    haus_kw = max(0.0, verbrauch_kw - wp_kw)
                    verbrauch_kw = round(max(0.0, haus_kw + wp_kw * faktor), 2)
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
    now = datetime.now(ZoneInfo("Europe/Berlin"))
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
    for s in alle_stunden:
        h = int(s["zeit"].split(":")[0])
        if h <= now.hour:
            aktuelle_stunde = s

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
        logger.warning(f"GTI-Fetch Neigung={neigung}° Azimut={ausrichtung}°: {type(e).__name__}: {e}")
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


# ── Lernfaktor (mit täglichem Cache) ─────────────────────────────────────────

_lernfaktor_cache: dict[int, tuple[str, Optional[float]]] = {}  # {anlage_id: (datum_str, faktor)}


async def _get_lernfaktor(anlage_id: int, db: AsyncSession) -> Optional[float]:
    """
    Berechnet einen Korrekturfaktor aus historischen IST/Prognose-Vergleichen.

    Nutzt die TagesZusammenfassung der letzten 30 Tage:
    - IST = Summe aller PV-Komponenten-kWh (positive Werte in komponenten_kwh)
    - Prognose = pv_prognose_kwh (gespeichert beim Wetter-Abruf)

    Produktionsgewichtete Berechnung: Σ(IST) / Σ(Prognose) statt Median der
    Tages-Ratios. Damit dominieren ertragsstarke (sonnige) Tage automatisch,
    und bewölkte Phasen verzerren den Faktor nicht mehr nach unten.

    Ergebnis wird tageweise gecacht (ändert sich max 1x/Tag nach Tagesabschluss).

    Returns:
        Korrekturfaktor (z.B. 0.92 = Anlage liefert 8% weniger als Prognose)
        oder None wenn nicht genug Daten (< 7 Tage).
    """
    # Cache prüfen
    heute = date.today().isoformat()
    if anlage_id in _lernfaktor_cache:
        cached_datum, cached_faktor = _lernfaktor_cache[anlage_id]
        if cached_datum == heute:
            return cached_faktor

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

    sum_ist = 0.0
    sum_prognose = 0.0
    tage_count = 0

    for tag in tage:
        # IST: Summe der positiven Werte in komponenten_kwh (= PV-Erzeugung)
        ist_kwh = 0.0
        if tag.komponenten_kwh:
            ist_kwh = sum(v for v in tag.komponenten_kwh.values() if v > 0)

        if ist_kwh > 0.5 and tag.pv_prognose_kwh > 0.5:  # Nur Tage mit relevanter Produktion
            sum_ist += ist_kwh
            sum_prognose += tag.pv_prognose_kwh
            tage_count += 1

    if tage_count < 7 or sum_prognose < 1:
        _lernfaktor_cache[anlage_id] = (heute, None)
        return None

    # Produktionsgewichtet: Σ(IST) / Σ(Prognose)
    # Sonnige Tage dominieren automatisch (mehr kWh → mehr Gewicht)
    raw_faktor = sum_ist / sum_prognose

    # Faktor auf realistischen Bereich begrenzen (0.5 – 1.3)
    faktor = max(0.5, min(1.3, raw_faktor))

    logger.info(
        f"Lernfaktor Anlage {anlage_id}: {faktor:.3f} "
        f"(produktionsgewichtet aus {tage_count} Tagen, "
        f"Σ IST={sum_ist:.1f} kWh / Σ Prognose={sum_prognose:.1f} kWh)"
    )

    faktor = round(faktor, 3)
    _lernfaktor_cache[anlage_id] = (heute, faktor)
    return faktor


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
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            aktiv_jetzt(),
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

    # Haupt-Wetter-Request (Wetterdaten + GHI)
    # Bei nur einer Orientierungsgruppe: GTI direkt mit abfragen
    hat_multi_string = len(gruppen) > 1
    haupt_neigung = gruppen[0]["neigung"] if gruppen else 35
    haupt_azimut = gruppen[0]["ausrichtung"] if gruppen else 0

    # Cache prüfen (60 Min TTL — Open-Meteo aktualisiert stündlich, ICON-D2 3-stündlich)
    LIVE_WETTER_CACHE_TTL = 3600  # 60 Minuten
    wetter_modell_key = getattr(anlage, "wetter_modell", "auto") or "auto"
    cache_key = (
        f"live_wetter:{anlage.latitude:.2f}:{anlage.longitude:.2f}"
        f":{haupt_neigung}:{haupt_azimut}:multi={hat_multi_string}:m={wetter_modell_key}"
    )

    try:
        cached_wetter = _cache_get(cache_key)

        if cached_wetter is not None:
            data, multi_gti = cached_wetter
        elif _error_cache_check(cache_key):
            logger.debug(f"Live-Wetter: Negative-Cache-Hit für Anlage {anlage_id}")
            return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}
        else:
            hourly_vars = [
                "temperature_2m", "weather_code", "cloud_cover",
                "precipitation", "shortwave_radiation", "sunshine_duration",
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

            # Wettermodell der Anlage berücksichtigen
            wetter_modell = getattr(anlage, "wetter_modell", "auto") or "auto"
            model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
            if model_name:
                params["models"] = model_name

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

            _cache_set(cache_key, (data, multi_gti), LIVE_WETTER_CACHE_TTL)

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        # GTI-Werte: Bei Single-String aus Haupt-Request, bei Multi-String aus gewichtetem Ergebnis
        if multi_gti:
            gti_values = multi_gti
        else:
            gti_values = hourly.get("global_tilted_irradiance", [])

        now = datetime.now(ZoneInfo("Europe/Berlin"))

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
        for s in alle_stunden:
            h = int(s["zeit"].split(":")[0])
            if h <= now.hour:
                aktuelle_stunde = s

        daily = data.get("daily", {})

        # Sonnenstunden: Tagessumme + Ist (bis jetzt) + Rest (ab jetzt)
        # Aktuelle Stunde wird anteilig nach Minuten aufgeteilt (Minuten-Präzision)
        hourly_sunshine = hourly.get("sunshine_duration", [])
        sunshine_s = sum(s for s in hourly_sunshine if s is not None) if hourly_sunshine else None
        sunshine_bisher_s = None
        sunshine_remaining_s = None
        if hourly_sunshine:
            current_h = now.hour
            minute_fraction = now.minute / 60  # Anteil der aktuellen Stunde (0.0–1.0)
            # Vergangene vollständige Stunden
            sunshine_bisher_s = sum(
                s for i, s in enumerate(hourly_sunshine)
                if s is not None and i < current_h
            )
            # Aktuell laufende Stunde anteilig dazu
            if current_h < len(hourly_sunshine) and hourly_sunshine[current_h] is not None:
                sunshine_bisher_s += hourly_sunshine[current_h] * minute_fraction
                sunshine_remaining_s = (
                    sum(s for i, s in enumerate(hourly_sunshine)
                        if s is not None and i > current_h)
                    + hourly_sunshine[current_h] * (1 - minute_fraction)
                )
            else:
                sunshine_remaining_s = sum(
                    s for i, s in enumerate(hourly_sunshine)
                    if s is not None and i > current_h
                )

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

        wp_stunden_profil = None
        referenz_temp_c = None
        if ind_profil_data:
            wp_key = "wp_wochenende" if now.weekday() >= 5 else "wp_werktag"
            wp_stunden_profil = ind_profil_data.get(wp_key)
            referenz_temp_c = ind_profil_data.get("referenz_temp_c")

        profil, pv_prognose, grundlast, ist_ind = _berechne_verbrauchsprofil(
            alle_stunden, kwp, individuelles_profil=ind_stunden_profil,
            wp_profil=wp_stunden_profil, referenz_temp_c=referenz_temp_c,
        )

        # ── HA-Sensoren parallel lesen (Temperatur + SFML in 1 Batch-Call) ──
        basis_live = (anlage.sensor_mapping or {}).get("basis", {}).get("live", {})
        temp_entity = basis_live.get("aussentemperatur_c") if basis_live else None
        sfml_entity = basis_live.get("sfml_today_kwh") if basis_live else None
        tomorrow_entity = basis_live.get("sfml_tomorrow_kwh") if basis_live else None
        accuracy_entity = basis_live.get("sfml_accuracy_pct") if basis_live else None

        sfml_kwh = None
        sfml_tomorrow = None
        sfml_accuracy = None
        ha_temp_found = False

        ha_entities = [e for e in [temp_entity, sfml_entity, tomorrow_entity, accuracy_entity] if e]
        if ha_entities:
            try:
                from backend.services.ha_state_service import get_ha_state_service
                ha_svc = get_ha_state_service()
                ha_batch = await ha_svc.get_sensor_states_batch(ha_entities)

                # Außentemperatur
                if temp_entity and ha_batch.get(temp_entity):
                    ha_temp = ha_batch[temp_entity][0]
                    if aktuelle_stunde is not None:
                        aktuelle_stunde["temperatur_c"] = ha_temp
                        ha_temp_found = True

                # SFML
                if sfml_entity and ha_batch.get(sfml_entity):
                    sfml_kwh = ha_batch[sfml_entity][0]
                if tomorrow_entity and ha_batch.get(tomorrow_entity):
                    sfml_tomorrow = ha_batch[tomorrow_entity][0]
                if accuracy_entity and ha_batch.get(accuracy_entity):
                    sfml_accuracy = ha_batch[accuracy_entity][0]

                # Tages-kWh auf GTI-Kurvenform verteilen
                if sfml_kwh is not None and sfml_kwh > 0 and profil:
                    gti_summe = sum(p["pv_ertrag_kw"] for p in profil)
                    if gti_summe > 0:
                        sfml_factor = sfml_kwh / gti_summe
                        for p in profil:
                            p["pv_ml_prognose_kw"] = round(p["pv_ertrag_kw"] * sfml_factor, 2)
            except Exception as e:
                logger.debug(f"HA-Sensoren (Wetter) nicht lesbar: {e}")

        # ── MQTT-Fallback für Außentemperatur (Standalone / HA-Sensor nicht erreichbar) ──
        if not ha_temp_found and aktuelle_stunde is not None:
            try:
                from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
                mqtt_svc = get_mqtt_inbound_service()
                if mqtt_svc and mqtt_svc.cache.has_data(anlage.id):
                    mqtt_basis = mqtt_svc.cache.get_live_basis(anlage.id)
                    mqtt_temp = mqtt_basis.get("aussentemperatur_c")
                    if mqtt_temp is not None:
                        aktuelle_stunde["temperatur_c"] = mqtt_temp
            except Exception:
                pass

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
            "sonnenstunden_bisher": round(sunshine_bisher_s / 3600, 1) if sunshine_bisher_s is not None else None,
            "sonnenstunden_rest": round(sunshine_remaining_s / 3600, 1) if sunshine_remaining_s is not None else None,
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

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.warning(f"Live-Wetter Fehler: HTTP {status}")
        _error_cache_set(cache_key, ttl)
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}
    except Exception as e:
        logger.warning(f"Live-Wetter Fehler: {type(e).__name__}: {e}")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return {"anlage_id": anlage.id, "verfuegbar": False, "stunden": []}


# ── MQTT-Inbound Status ─────────────────────────────────────────────────────

