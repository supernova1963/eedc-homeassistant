"""
Prognosen-Vergleich API Routes — OpenMeteo + Solcast + IST.

Ausgelagert aus aussichten.py (Router-Split).
Evaluierungs-Cockpit für PV-Prognosen.

GET /api/aussichten/prognosen/{anlage_id}
GET /api/aussichten/prognosen/{anlage_id}/genauigkeit
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.utils import wetter_code_zu_symbol
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.services.solcast_service import get_solcast_forecast, get_solcast_status
from backend.services.solar_forecast_service import fetch_gti_forecast
from backend.api.routes.live_wetter import _get_lernfaktor, _get_lernfaktor_detail

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_LOSSES = 0.14
TEMP_COEFFICIENT = 0.004

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class TagesPrognoseSchema(BaseModel):
    datum: str
    pv_prognose_kwh: float
    globalstrahlung_kwh_m2: Optional[float]
    sonnenstunden: Optional[float]
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str


class StundenProfilEintrag(BaseModel):
    stunde: int
    # kw=None → Datenlücke (z.B. IST-Stunde ohne gemappten Zähler, Issue #135)
    kw: Optional[float] = None
    p10_kw: Optional[float] = None
    p90_kw: Optional[float] = None


class SolcastTagSchema(BaseModel):
    datum: str
    kwh: float
    p10: float
    p90: float


class TageshaelfteSchema(BaseModel):
    """Vormittag/Nachmittag-Aufteilung."""
    vormittag_kwh: float = 0  # 0:00–12:59
    nachmittag_kwh: float = 0  # 13:00–23:59


class PrognosenVergleichResponse(BaseModel):
    """Response für den Prognosen-Vergleich-Tab."""
    # OpenMeteo roh (immer verfügbar)
    openmeteo_heute_kwh: Optional[float] = None
    openmeteo_morgen_kwh: Optional[float] = None
    openmeteo_uebermorgen_kwh: Optional[float] = None
    openmeteo_tage: List[TagesPrognoseSchema] = []
    # VM/NM pro Tag: [heute, morgen, übermorgen] — jeweils {vormittag_kwh, nachmittag_kwh}
    openmeteo_tageshaelften: List[Optional[TageshaelfteSchema]] = []

    # EEDC = OpenMeteo × Lernfaktor (kalibriert mit historischen IST-Daten)
    eedc_heute_kwh: Optional[float] = None
    eedc_morgen_kwh: Optional[float] = None
    eedc_uebermorgen_kwh: Optional[float] = None
    eedc_stundenprofil: List[StundenProfilEintrag] = []
    eedc_lernfaktor: Optional[float] = None  # z.B. 0.92 = Anlage liefert 8% weniger
    eedc_lernfaktor_stufe: Optional[str] = None  # z.B. "saisonal April (23 Tage)"
    eedc_prognose_basis: str = "openmeteo"  # "openmeteo" oder "solcast"
    eedc_tageshaelften: List[Optional[TageshaelfteSchema]] = []

    # Solcast (wenn konfiguriert)
    solcast_verfuegbar: bool = False
    solcast_quelle: Optional[str] = None
    solcast_status: Optional[str] = None  # "ok", "nicht_konfiguriert", "tageslimit", "auth_fehler", "ha_nicht_erreichbar", "fehler"
    solcast_hinweis: Optional[str] = None  # Benutzerfreundliche Fehlerbeschreibung
    solcast_heute_kwh: Optional[float] = None
    solcast_p10_kwh: Optional[float] = None
    solcast_p90_kwh: Optional[float] = None
    solcast_morgen_kwh: Optional[float] = None
    solcast_morgen_p10_kwh: Optional[float] = None
    solcast_morgen_p90_kwh: Optional[float] = None
    solcast_uebermorgen_kwh: Optional[float] = None
    solcast_stundenprofil: List[StundenProfilEintrag] = []
    solcast_tage: List[SolcastTagSchema] = []
    solcast_tageshaelften: List[Optional[TageshaelfteSchema]] = []

    # IST-Ertrag heute (aus TagesEnergieProfil)
    ist_heute_kwh: Optional[float] = None
    ist_stundenprofil: List[StundenProfilEintrag] = []
    ist_tageshaelfte: Optional[TageshaelfteSchema] = None
    # True wenn mindestens eine Stunde des Tages pv_kw=None hatte
    # (kein kumulativer Zähler gemappt — Issue #135)
    ist_unvollstaendig: bool = False

    # Verbleibend: Hochrechnung basierend auf IST + beste Prognose für Rest
    verbleibend_kwh: Optional[float] = None
    verbleibend_om_kwh: Optional[float] = None
    verbleibend_eedc_kwh: Optional[float] = None
    verbleibend_solcast_kwh: Optional[float] = None

    # OpenMeteo Stundenprofil (GTI-basiert, roh)
    openmeteo_stundenprofil: List[StundenProfilEintrag] = []

    # Meta
    solcast_letzter_abruf: Optional[str] = None
    openmeteo_modell: Optional[str] = None
    aktuelle_stunde: Optional[int] = None


class GenauigkeitsEintrag(BaseModel):
    datum: str
    openmeteo_kwh: Optional[float] = None
    solcast_kwh: Optional[float] = None
    ist_kwh: Optional[float] = None


class GenauigkeitsResponse(BaseModel):
    """Response für Genauigkeits-Tracking."""
    tage: List[GenauigkeitsEintrag] = []
    openmeteo_mae_prozent: Optional[float] = None
    solcast_mae_prozent: Optional[float] = None
    anzahl_tage: int = 0


# =============================================================================
# Helpers
# =============================================================================

def _berechne_tageshaelfte(stundenprofil: List[StundenProfilEintrag]) -> TageshaelfteSchema:
    """Teilt Stundenprofil in Vormittag (0–12) und Nachmittag (13–23).

    NULL-Stunden (z.B. IST-Lücken ohne Zähler, Issue #135) werden übersprungen.
    """
    vm = sum(s.kw for s in stundenprofil if s.stunde <= 12 and s.kw is not None)
    nm = sum(s.kw for s in stundenprofil if s.stunde > 12 and s.kw is not None)
    return TageshaelfteSchema(
        vormittag_kwh=round(vm, 1),
        nachmittag_kwh=round(nm, 1),
    )


async def _lade_anlage_mit_pv(db: AsyncSession, anlage_id: int):
    """Lädt Anlage + aktive PV-Module/BKW und berechnet Gesamtleistung."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")
    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten")

    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            aktiv_jetzt()
        )
    )
    alle_pv = result.scalars().all()
    pv_module = [i for i in alle_pv if i.typ == "pv-module"]
    balkonkraftwerke = [i for i in alle_pv if i.typ == "balkonkraftwerk"]
    kwp = sum(m.leistung_kwp or 0 for m in pv_module) + sum(b.leistung_kwp or 0 for b in balkonkraftwerke)
    if kwp <= 0:
        kwp = anlage.leistung_kwp or 0
    return anlage, pv_module, balkonkraftwerke, kwp


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/prognosen/{anlage_id}", response_model=PrognosenVergleichResponse)
async def get_prognosen_vergleich(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Prognosen-Vergleich: OpenMeteo + Solcast + IST.

    Evaluierungs-Cockpit mit Vormittag/Nachmittag-Split.
    Ziel: Optimales Zusammenspiel beider Quellen erarbeiten.
    """
    anlage, pv_module, _, anlagenleistung_kwp = await _lade_anlage_mit_pv(db, anlage_id)

    if anlagenleistung_kwp <= 0:
        raise HTTPException(status_code=400, detail="Keine PV-Leistung konfiguriert")

    # Systemverluste aus PVGIS
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = result.scalar_one_or_none()
    system_losses = pvgis.system_losses / 100 if pvgis and pvgis.system_losses else DEFAULT_SYSTEM_LOSSES

    # Wettermodell + Orientierung
    wetter_modell = anlage.wetter_modell or "auto"
    model_name, max_days = WETTER_MODELLE.get(wetter_modell, (None, 16))

    haupt_neigung = 35
    haupt_azimut = 0
    for pv in pv_module:
        if pv.neigung_grad is not None:
            haupt_neigung = int(pv.neigung_grad)
        params = pv.parameter or {}
        if params.get("ausrichtung_grad") is not None:
            haupt_azimut = int(params["ausrichtung_grad"])
        break

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    heute = date.today()

    # ── Wetter-Abruf: Kaskade bei Modellen mit kurzem Horizont (z.B. icon_d2 = 2 Tage) ──
    needs_fallback = wetter_modell != "auto" and 14 > max_days

    async def _fetch_wetter_mit_fallback():
        """Primary-Modell + best_match Fallback parallel abrufen und mergen."""
        primary, fallback = await asyncio.gather(
            fetch_open_meteo_forecast(
                latitude=anlage.latitude, longitude=anlage.longitude,
                days=max_days, skip_jitter=True, model=model_name,
            ),
            fetch_open_meteo_forecast(
                latitude=anlage.latitude, longitude=anlage.longitude,
                days=14, skip_jitter=True, model=None,
            ),
        )
        if not primary and not fallback:
            return None
        if not primary:
            return fallback
        if not fallback:
            return primary
        # Beide verfügbar → Primary-Tage haben Vorrang, Fallback füllt auf
        primary_dates = {t["datum"] for t in primary.get("tage", [])}
        merged_tage = list(primary.get("tage", []))
        merged_tage.extend(t for t in fallback.get("tage", []) if t["datum"] not in primary_dates)
        merged_tage.sort(key=lambda t: t["datum"])
        return {**primary, "tage": merged_tage}

    # ── Parallele Datenabrufe (return_exceptions: ein API-Timeout crasht nicht alles) ──
    wetter, gti_data, solcast, ist_rows = await asyncio.gather(
        _fetch_wetter_mit_fallback() if needs_fallback else fetch_open_meteo_forecast(
            latitude=anlage.latitude, longitude=anlage.longitude,
            days=14, skip_jitter=True, model=model_name,
        ),
        fetch_gti_forecast(
            latitude=anlage.latitude, longitude=anlage.longitude,
            neigung=haupt_neigung, ausrichtung=haupt_azimut,
            days=3, skip_jitter=True, model=model_name,
        ),
        get_solcast_forecast(anlage),
        db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum == heute,
            ).order_by(TagesEnergieProfil.stunde)
        ),
        return_exceptions=True,
    )
    # Exceptions → None/leeres Ergebnis (Endpoint liefert was verfügbar ist)
    if isinstance(wetter, BaseException):
        logger.warning(f"OpenMeteo Forecast fehlgeschlagen: {wetter}")
        wetter = None
    if isinstance(gti_data, BaseException):
        logger.warning(f"GTI Forecast fehlgeschlagen: {gti_data}")
        gti_data = None
    if isinstance(solcast, BaseException):
        logger.warning(f"Solcast Forecast fehlgeschlagen: {solcast}")
        solcast = None
    if isinstance(ist_rows, BaseException):
        logger.warning(f"IST-Daten Abfrage fehlgeschlagen: {ist_rows}")
        ist_rows = None
    ist_rows = ist_rows.scalars().all() if ist_rows is not None else []

    # ── OpenMeteo Tageswerte ──
    openmeteo_tage = []
    if wetter:
        for tag in wetter["tage"]:
            pv_kwh = berechne_pv_ertrag_tag(
                globalstrahlung_kwh_m2=tag["globalstrahlung_kwh_m2"],
                anlagenleistung_kwp=anlagenleistung_kwp,
                temperatur_max_c=tag["temperatur_max_c"],
                system_losses=system_losses,
            )
            openmeteo_tage.append(TagesPrognoseSchema(
                datum=tag["datum"], pv_prognose_kwh=pv_kwh,
                globalstrahlung_kwh_m2=tag["globalstrahlung_kwh_m2"],
                sonnenstunden=tag["sonnenstunden"],
                temperatur_max_c=tag["temperatur_max_c"],
                temperatur_min_c=tag["temperatur_min_c"],
                niederschlag_mm=tag["niederschlag_mm"],
                bewoelkung_prozent=tag["bewoelkung_prozent"],
                wetter_symbol=wetter_code_zu_symbol(tag["wetter_code"]),
            ))

    openmeteo_heute_kwh = openmeteo_tage[0].pv_prognose_kwh if len(openmeteo_tage) >= 1 else None
    openmeteo_morgen_kwh = openmeteo_tage[1].pv_prognose_kwh if len(openmeteo_tage) >= 2 else None
    openmeteo_uebermorgen_kwh = openmeteo_tage[2].pv_prognose_kwh if len(openmeteo_tage) >= 3 else None

    # ── OpenMeteo GTI-Stundenprofile (3 Tage) ──
    # gti_data enthält bis zu 72 Stundenwerte (3×24h)
    openmeteo_stundenprofil = []  # Heute (erste 24h)
    openmeteo_tagesprofile: list[list[StundenProfilEintrag]] = [[], [], []]  # [heute, morgen, übermorgen]
    if gti_data:
        hourly = gti_data.get("hourly", {})
        gti_values = hourly.get("global_tilted_irradiance", [])
        temps = hourly.get("temperature_2m", [])
        for i in range(min(72, len(gti_values))):
            tag_idx = i // 24  # 0=heute, 1=morgen, 2=übermorgen
            h = i % 24
            gti = gti_values[i] or 0
            if gti > 0 and anlagenleistung_kwp > 0:
                pv_kw = gti * anlagenleistung_kwp * (1 - system_losses) / 1000
                temp = temps[i] if i < len(temps) and temps[i] is not None else None
                if temp is not None:
                    aufheizung = min(25, gti / 40)
                    modul_temp = temp + aufheizung
                    if modul_temp > 25:
                        pv_kw *= (1 - (modul_temp - 25) * TEMP_COEFFICIENT)
                pv_kw = max(0, pv_kw)
            else:
                pv_kw = 0
            entry = StundenProfilEintrag(stunde=h, kw=round(pv_kw, 2))
            if tag_idx < 3:
                openmeteo_tagesprofile[tag_idx].append(entry)
            if tag_idx == 0:
                openmeteo_stundenprofil.append(entry)

    # ── EEDC = Basis × Lernfaktor (MOS-Kaskade: saisonal → quartal → gesamt) ──
    prognose_basis = getattr(anlage, "prognose_basis", None) or "openmeteo"
    lf_result = await _get_lernfaktor_detail(anlage_id, db, quelle=prognose_basis)
    lernfaktor = lf_result.faktor
    eedc_stundenprofil = []
    eedc_tagesprofile: list[list[StundenProfilEintrag]] = [[], [], []]
    # Basis-Werte abhängig von prognose_basis (Solcast-Stundenprofil wird weiter unten gefüllt,
    # daher hier vorab merken — die endgültige EEDC-Berechnung erfolgt nach Solcast-Aufbereitung)
    _eedc_basis_om = prognose_basis == "openmeteo"
    if _eedc_basis_om and lernfaktor is not None:
        for s in openmeteo_stundenprofil:
            eedc_stundenprofil.append(StundenProfilEintrag(
                stunde=s.stunde, kw=round(s.kw * lernfaktor, 2)
            ))
        for tag_idx, profil in enumerate(openmeteo_tagesprofile):
            for s in profil:
                eedc_tagesprofile[tag_idx].append(StundenProfilEintrag(
                    stunde=s.stunde, kw=round(s.kw * lernfaktor, 2)
                ))
    eedc_heute_kwh = None
    eedc_morgen_kwh = None
    eedc_uebermorgen_kwh = None
    if _eedc_basis_om and lernfaktor is not None:
        eedc_heute_kwh = round(openmeteo_heute_kwh * lernfaktor, 1) if openmeteo_heute_kwh is not None else None
        eedc_morgen_kwh = round(openmeteo_morgen_kwh * lernfaktor, 1) if openmeteo_morgen_kwh is not None else None
        eedc_uebermorgen_kwh = round(openmeteo_uebermorgen_kwh * lernfaktor, 1) if openmeteo_uebermorgen_kwh is not None else None

    # ── IST-Ertrag heute ──
    # Issue #135: pv_kw kann None sein (kein Zähler gemappt / Datenlücke).
    # None-Stunden fließen NICHT in die Summe ein und werden im Stundenprofil
    # als Lücke markiert (kw=None). Frontend zeigt ist_unvollstaendig=True an.
    ist_stundenprofil = []
    ist_heute_kwh = 0.0
    ist_unvollstaendig = False
    jetzt_stunde = now.hour
    for row in ist_rows:
        if row.pv_kw is None:
            # Nur vergangene Stunden als "fehlend" werten; noch nicht
            # aggregierte Zukunft-Stunden sind kein Datenproblem
            if row.stunde <= jetzt_stunde:
                ist_unvollstaendig = True
            ist_stundenprofil.append(StundenProfilEintrag(stunde=row.stunde, kw=None))
            continue
        kw = row.pv_kw
        ist_stundenprofil.append(StundenProfilEintrag(stunde=row.stunde, kw=round(kw, 2)))
        ist_heute_kwh += kw

    # ── Verbleibend ──
    aktuelle_stunde = now.hour
    verbleibend_kwh = None
    verbleibend_om_kwh = None
    verbleibend_eedc_kwh = None
    verbleibend_solcast_kwh = None
    if ist_heute_kwh > 0 or openmeteo_stundenprofil:
        rest_prognose = 0.0
        for h in range(aktuelle_stunde + 1, 24):
            if solcast and h < len(solcast.hourly_kw):
                rest_prognose += solcast.hourly_kw[h]
            elif h < len(openmeteo_stundenprofil):
                rest_prognose += openmeteo_stundenprofil[h].kw
        verbleibend_kwh = round(ist_heute_kwh + rest_prognose, 1)
    # Pro Quelle: Tagesprognose - bisheriger IST
    if openmeteo_heute_kwh is not None and ist_heute_kwh > 0:
        verbleibend_om_kwh = round(max(0, openmeteo_heute_kwh - ist_heute_kwh), 1)
    if eedc_heute_kwh is not None and ist_heute_kwh > 0:
        verbleibend_eedc_kwh = round(max(0, eedc_heute_kwh - ist_heute_kwh), 1)
    if solcast and solcast.daily_kwh is not None and ist_heute_kwh > 0:
        verbleibend_solcast_kwh = round(max(0, solcast.daily_kwh - ist_heute_kwh), 1)

    # ── Solcast aufbereiten ──
    solcast_stundenprofil = []
    solcast_tage = []
    solcast_morgen_p10 = None
    solcast_morgen_p90 = None
    solcast_uebermorgen_kwh = None

    if solcast:
        for h in range(24):
            solcast_stundenprofil.append(StundenProfilEintrag(
                stunde=h,
                kw=solcast.hourly_kw[h] if h < len(solcast.hourly_kw) else 0,
                p10_kw=solcast.hourly_p10_kw[h] if h < len(solcast.hourly_p10_kw) else 0,
                p90_kw=solcast.hourly_p90_kw[h] if h < len(solcast.hourly_p90_kw) else 0,
            ))
        solcast_tage = [SolcastTagSchema(**t) for t in solcast.tage_voraus]
        morgen_str = (heute + timedelta(days=1)).isoformat()
        uebermorgen_str = (heute + timedelta(days=2)).isoformat()
        for t in solcast.tage_voraus:
            if t["datum"] == morgen_str:
                solcast_morgen_p10 = t["p10"]
                solcast_morgen_p90 = t["p90"]
            if t["datum"] == uebermorgen_str:
                solcast_uebermorgen_kwh = t["kwh"]

    # ── EEDC auf Solcast-Basis (wenn prognose_basis == "solcast") ──
    if not _eedc_basis_om and solcast and solcast_stundenprofil:
        if lernfaktor is not None:
            for s in solcast_stundenprofil:
                eedc_stundenprofil.append(StundenProfilEintrag(
                    stunde=s.stunde, kw=round(s.kw * lernfaktor, 2)
                ))
            eedc_heute_kwh = round(solcast.daily_kwh * lernfaktor, 1) if solcast.daily_kwh is not None else None
            eedc_morgen_kwh = round(solcast.tomorrow_kwh * lernfaktor, 1) if solcast.tomorrow_kwh is not None else None
            eedc_uebermorgen_kwh = round(solcast_uebermorgen_kwh * lernfaktor, 1) if solcast_uebermorgen_kwh is not None else None
        else:
            # Solcast als Basis ohne Lernfaktor: Rohwerte als EEDC übernehmen
            eedc_stundenprofil = list(solcast_stundenprofil)
            eedc_heute_kwh = round(solcast.daily_kwh, 1) if solcast.daily_kwh is not None else None
            eedc_morgen_kwh = round(solcast.tomorrow_kwh, 1) if solcast.tomorrow_kwh is not None else None
            eedc_uebermorgen_kwh = round(solcast_uebermorgen_kwh, 1) if solcast_uebermorgen_kwh is not None else None

    # ── Tageshälften (je 3 Einträge: heute, morgen, übermorgen) ──
    om_ths = [_berechne_tageshaelfte(p) if p else None for p in openmeteo_tagesprofile]
    eedc_ths = [_berechne_tageshaelfte(p) if p else None for p in eedc_tagesprofile]

    # Solcast VM/NM pro Tag aus tage_voraus berechnen (Stundenwerte nur für heute vorhanden,
    # für Morgen/Übermorgen approximieren wir aus den 30-Min-Daten im SolcastForecast)
    sc_ths: list[Optional[TageshaelfteSchema]] = [None, None, None]
    if solcast_stundenprofil:
        sc_ths[0] = _berechne_tageshaelfte(solcast_stundenprofil)
    # Für Morgen/Übermorgen: Solcast liefert nur Tageswerte, kein Stundenprofil
    # → VM/NM aus OpenMeteo-Verteilung schätzen (proportional)
    for day_idx in [1, 2]:
        sc_tag = next((t for t in solcast.tage_voraus if t["datum"] == (heute + timedelta(days=day_idx)).isoformat()), None) if solcast else None
        om_day_th = om_ths[day_idx] if day_idx < len(om_ths) else None
        if sc_tag and om_day_th and (om_day_th.vormittag_kwh + om_day_th.nachmittag_kwh) > 0:
            om_total = om_day_th.vormittag_kwh + om_day_th.nachmittag_kwh
            vm_anteil = om_day_th.vormittag_kwh / om_total
            sc_ths[day_idx] = TageshaelfteSchema(
                vormittag_kwh=round(sc_tag["kwh"] * vm_anteil, 1),
                nachmittag_kwh=round(sc_tag["kwh"] * (1 - vm_anteil), 1),
            )

    ist_th = _berechne_tageshaelfte(ist_stundenprofil) if ist_stundenprofil else None

    # ── Solcast-Status ermitteln ──
    sc_status, sc_hinweis = get_solcast_status(anlage)
    # Wenn Solcast Daten da sind, ist der Status immer "ok"
    if solcast is not None:
        sc_status = "ok"
        sc_hinweis = ""

    return PrognosenVergleichResponse(
        openmeteo_heute_kwh=openmeteo_heute_kwh,
        openmeteo_morgen_kwh=openmeteo_morgen_kwh,
        openmeteo_uebermorgen_kwh=openmeteo_uebermorgen_kwh,
        openmeteo_tage=openmeteo_tage,
        openmeteo_tageshaelften=om_ths,
        eedc_heute_kwh=eedc_heute_kwh,
        eedc_morgen_kwh=eedc_morgen_kwh,
        eedc_uebermorgen_kwh=eedc_uebermorgen_kwh,
        eedc_stundenprofil=eedc_stundenprofil,
        eedc_tageshaelften=eedc_ths,
        eedc_lernfaktor=lernfaktor,
        eedc_lernfaktor_stufe=lf_result.label,
        eedc_prognose_basis=prognose_basis,
        solcast_verfuegbar=solcast is not None,
        solcast_status=sc_status,
        solcast_hinweis=sc_hinweis if sc_hinweis else None,
        solcast_quelle=solcast.quelle if solcast else None,
        solcast_heute_kwh=solcast.daily_kwh if solcast else None,
        solcast_p10_kwh=solcast.daily_p10_kwh if solcast else None,
        solcast_p90_kwh=solcast.daily_p90_kwh if solcast else None,
        solcast_morgen_kwh=solcast.tomorrow_kwh if solcast else None,
        solcast_morgen_p10_kwh=solcast_morgen_p10,
        solcast_morgen_p90_kwh=solcast_morgen_p90,
        solcast_uebermorgen_kwh=solcast_uebermorgen_kwh,
        solcast_stundenprofil=solcast_stundenprofil,
        solcast_tage=solcast_tage,
        solcast_tageshaelften=sc_ths,
        ist_heute_kwh=round(ist_heute_kwh, 1) if ist_heute_kwh > 0 else None,
        ist_stundenprofil=ist_stundenprofil,
        ist_tageshaelfte=ist_th,
        ist_unvollstaendig=ist_unvollstaendig,
        verbleibend_kwh=verbleibend_kwh,
        verbleibend_om_kwh=verbleibend_om_kwh,
        verbleibend_eedc_kwh=verbleibend_eedc_kwh,
        verbleibend_solcast_kwh=verbleibend_solcast_kwh,
        openmeteo_stundenprofil=openmeteo_stundenprofil,
        solcast_letzter_abruf=datetime.now().isoformat(),
        openmeteo_modell=wetter_modell,
        aktuelle_stunde=aktuelle_stunde,
    )


@router.get("/prognosen/{anlage_id}/genauigkeit", response_model=GenauigkeitsResponse)
async def get_prognosen_genauigkeit(
    anlage_id: int,
    tage: int = Query(default=30, ge=7, le=90, description="Anzahl Tage für Genauigkeit"),
    db: AsyncSession = Depends(get_db),
):
    """
    Genauigkeits-Tracking: Prognose vs. IST für die letzten N Tage.

    Nutzt TagesZusammenfassung:
    - pv_prognose_kwh (OpenMeteo) vs. IST (aus komponenten_kwh)
    - solcast_prognose_kwh vs. IST
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    von = date.today() - timedelta(days=tage)
    result = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum < date.today(),
        ).order_by(TagesZusammenfassung.datum)
    )
    tage_daten = result.scalars().all()

    eintraege = []
    om_errors = []
    sc_errors = []

    # Schlüssel die keine PV-Erzeugung sind (Strompreis in ct, Netzbezug, Einspeisung)
    _NICHT_PV = {"strompreis", "netzbezug", "einspeisung"}

    for tz in tage_daten:
        ist_kwh = None
        if tz.komponenten_kwh:
            ist_kwh = sum(
                v for k, v in tz.komponenten_kwh.items()
                if v > 0 and k not in _NICHT_PV
            )

        eintraege.append(GenauigkeitsEintrag(
            datum=tz.datum.isoformat(),
            openmeteo_kwh=round(tz.pv_prognose_kwh, 1) if tz.pv_prognose_kwh is not None else None,
            solcast_kwh=round(tz.solcast_prognose_kwh, 1) if tz.solcast_prognose_kwh is not None else None,
            ist_kwh=round(ist_kwh, 1) if ist_kwh is not None else None,
        ))

        if ist_kwh is not None and ist_kwh > 0.5:
            if tz.pv_prognose_kwh and tz.pv_prognose_kwh > 0:
                om_errors.append(abs(tz.pv_prognose_kwh - ist_kwh) / ist_kwh * 100)
            if tz.solcast_prognose_kwh and tz.solcast_prognose_kwh > 0:
                sc_errors.append(abs(tz.solcast_prognose_kwh - ist_kwh) / ist_kwh * 100)

    return GenauigkeitsResponse(
        tage=eintraege,
        openmeteo_mae_prozent=round(sum(om_errors) / len(om_errors), 1) if om_errors else None,
        solcast_mae_prozent=round(sum(sc_errors) / len(sc_errors), 1) if sc_errors else None,
        anzahl_tage=len(eintraege),
    )
