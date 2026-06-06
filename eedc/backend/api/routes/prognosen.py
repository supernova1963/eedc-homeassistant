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
from backend.core.berechnungen import summe_pv_bkw_kwh
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.utils import wetter_symbol_aus_tag
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.services.solcast_service import get_solcast_forecast, get_solcast_status
from backend.services.solar_forecast_service import fetch_gti_forecast, _solar_noon_hour
from backend.api.routes.live_wetter import _get_lernfaktor, _get_lernfaktor_detail
from backend.services.pv_orientation import resolve_system_losses
from backend.services.prognose_adapter import (
    StundenProfil,
    ist_profil,
    openmeteo_gti_profil,
    sfml_profil,
    sfml_stundenprofil_aus_hours,
    sfml_stundenprofile_aus_forecast,
    solcast_profil,
)
from backend.services.prognose_router import resolve_prognose_quelle

logger = logging.getLogger(__name__)

# DEFAULT_SYSTEM_LOSSES: zentral in services/pv_orientation.py
# TEMP_COEFFICIENT: in den Prognose-Adapter (services/prognose_adapter) gewandert.

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
    # Doppel-Variante O1+O2 (Trim-Mean + Recency-Boost) — läuft parallel zu Diagnose-
    # Zwecken neben dem Legacy-Faktor. Live-Pfad nutzt nur eedc_lernfaktor.
    eedc_lernfaktor_o12: Optional[float] = None
    eedc_lernfaktor_o12_delta_pct: Optional[float] = None  # 100 * (O12 - Legacy) / Legacy
    eedc_prognose_basis: str = "eedc"  # "eedc" oder "solcast" (für EEDC-Diagnose)
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

    # SFML / Tom-HA (nur HA-Add-on, wenn als Quelle gewählt) — echtes
    # mehrtägiges Stundenprofil, KEIN Cross-Quellen-Ranking (#110 „A").
    sfml_verfuegbar: bool = False
    sfml_heute_kwh: Optional[float] = None
    sfml_morgen_kwh: Optional[float] = None
    sfml_uebermorgen_kwh: Optional[float] = None
    sfml_stundenprofil: List[StundenProfilEintrag] = []
    sfml_tageshaelften: List[Optional[TageshaelfteSchema]] = []

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
    eedc_kwh: Optional[float] = None
    solcast_kwh: Optional[float] = None
    ist_kwh: Optional[float] = None
    # Repräsentatives Tages-Wettersymbol (aus Stundenprofil aggregiert, #296 #2)
    wetter_symbol: Optional[str] = None
    temperatur_max_c: Optional[float] = None
    # Tag mit großer Abweichung (max |Prognose−IST| über alle Quellen > Schwelle).
    # Wird NIE still weggerechnet (#296 #9) — nur markiert; Ausschluss aus MAE/MBE
    # nur auf ausdrücklichen Wunsch (ausreisser_ausblenden=True).
    ist_ausreisser: bool = False


class AsymmetrieEintrag(BaseModel):
    """Asymmetrie-Diagnostik: über vs. unter IST getrennt aggregiert.

    Zeigt ob die Streuung symmetrisch (Rauschen) oder einseitig (systematische
    Über-/Unterschätzung in bestimmten Wettersituationen) ist.
    """
    over_count: int = 0
    over_avg_prozent: Optional[float] = None
    under_count: int = 0
    under_avg_prozent: Optional[float] = None


class GenauigkeitsResponse(BaseModel):
    """Response für Genauigkeits-Tracking.

    MAE = Mean Absolute Error (mit abs()) — Streuung
    MBE = Mean Bias Error (ohne abs(), vorzeichenbehaftet) — systematischer Bias
    Asymmetrie = MBE aufgeteilt in „darüber" / „darunter" (Rainer-Mockup #151)
    Alle Werte in Prozent vom IST.
    """
    tage: List[GenauigkeitsEintrag] = []
    openmeteo_mae_prozent: Optional[float] = None
    openmeteo_mbe_prozent: Optional[float] = None
    openmeteo_asymmetrie: Optional[AsymmetrieEintrag] = None
    eedc_mae_prozent: Optional[float] = None
    eedc_mbe_prozent: Optional[float] = None
    eedc_asymmetrie: Optional[AsymmetrieEintrag] = None
    solcast_mae_prozent: Optional[float] = None
    solcast_mbe_prozent: Optional[float] = None
    solcast_asymmetrie: Optional[AsymmetrieEintrag] = None
    anzahl_tage: int = 0
    # Anzahl als Ausreißer markierter Tage (>Schwelle Abweichung), #296 #9
    anzahl_ausreisser: int = 0
    # Schwelle in % (für UI-Text)
    ausreisser_schwelle_prozent: float = 50.0


# =============================================================================
# Helpers
# =============================================================================

def _berechne_tageshaelfte(
    stundenprofil: List[StundenProfilEintrag],
    solar_noon: float,
) -> TageshaelfteSchema:
    """Splittet Stundenprofil an Solar Noon proportional (Backward-Slot-Konvention).

    Slot ``stunde=h`` repräsentiert die Produktion im Intervall ``[h-1, h]``:
    - Liegt das Intervall komplett vor Solar Noon → VM
    - Liegt es komplett dahinter → NM
    - Enthält es Solar Noon → proportional aufteilen (frac_vm = noon - (h-1))

    NULL-Stunden (z.B. IST-Lücken ohne Zähler, Issue #135) werden übersprungen.
    """
    vm = 0.0
    nm = 0.0
    for s in stundenprofil:
        if s.kw is None:
            continue
        slot_start = s.stunde - 1
        slot_end = s.stunde
        if slot_end <= solar_noon:
            vm += s.kw
        elif slot_start >= solar_noon:
            nm += s.kw
        else:
            frac_vm = max(0.0, min(1.0, solar_noon - slot_start))
            vm += s.kw * frac_vm
            nm += s.kw * (1 - frac_vm)
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

def _eintraege_zu_array(eintraege: list[StundenProfilEintrag]) -> list[float]:
    """Variabel langes Stundenprofil → 24-Slot-kW-Array (fehlende Slots = 0).

    NULL-Slots (IST-Lücken ohne Zähler, Issue #135) zählen als 0.
    """
    arr = [0.0] * 24
    for s in eintraege:
        if s.kw is not None and 0 <= s.stunde < 24:
            arr[s.stunde] = s.kw
    return arr


def _tagesprojektion(
    ist_kwh: float,
    stunden_kw: Optional[list[float]],
    aktuelle_stunde: int,
) -> Optional[float]:
    """Tagesprojektion = IST bisher + Σ Prognose-Slots der Stunden > aktuelle_stunde.

    Einheitliches „Verbleibend"-Verfahren für alle Quellen-Spalten (#296):
    funktioniert auch bei ``ist_kwh == 0`` (liefert dann die volle Restprognose).
    Gibt ``None`` zurück, wenn die Quelle kein Stundenprofil hat.
    """
    if not stunden_kw:
        return None
    rest = sum(
        stunden_kw[h]
        for h in range(aktuelle_stunde + 1, 24)
        if h < len(stunden_kw) and stunden_kw[h] is not None
    )
    return round(ist_kwh + rest, 1)


def _profil_zu_eintraegen(p: StundenProfil) -> list[StundenProfilEintrag]:
    """Kanonisches ``StundenProfil`` (Adapter-Layer) → API-Schema-Liste.

    Gibt nur die ``present_stunden`` aus (in deren Reihenfolge) — so bleibt die
    variabel lange Ausgabe des Vergleich-Tabs erhalten (IST: nur abgelaufene
    Stunden; OpenMeteo: nur Indizes mit GTI-Wert). p10/p90 nur, wenn die Quelle
    ein Band trägt (Solcast).
    """
    return [
        StundenProfilEintrag(
            stunde=h,
            kw=p.slots_kw[h],
            p10_kw=p.p10_kw[h] if p.p10_kw is not None else None,
            p90_kw=p.p90_kw[h] if p.p90_kw is not None else None,
        )
        for h in p.present_stunden
    ]


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
    system_losses = resolve_system_losses(pvgis)

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
                wetter_symbol=wetter_symbol_aus_tag(
                    tag["wetter_code"],
                    tag.get("bewoelkung_prozent"),
                    tag.get("niederschlag_mm"),
                ),
            ))

    openmeteo_heute_kwh = openmeteo_tage[0].pv_prognose_kwh if len(openmeteo_tage) >= 1 else None
    openmeteo_morgen_kwh = openmeteo_tage[1].pv_prognose_kwh if len(openmeteo_tage) >= 2 else None
    openmeteo_uebermorgen_kwh = openmeteo_tage[2].pv_prognose_kwh if len(openmeteo_tage) >= 3 else None

    # ── OpenMeteo GTI-Stundenprofile (3 Tage, zentraler Adapter) ──
    # gti_data enthält bis zu 72 Stundenwerte (3×24h). OpenMeteo-GTI ist
    # preceding-hour-Mittel: Wert@Index h deckt [h-1, h) ab = bereits Backward-
    # Slot h (Issue #297, KEIN Shift — slot_konvention). Solcast/IST nutzen
    # dasselbe Raster, daher liegen alle Quellen im Vergleich deckungsgleich.
    # Formel + Temperatur-Korrektur in prognose_adapter.openmeteo_gti_profil.
    openmeteo_stundenprofil = []  # Heute (erste 24h)
    openmeteo_tagesprofile: list[list[StundenProfilEintrag]] = [[], [], []]  # [heute, morgen, übermorgen]
    if gti_data:
        hourly = gti_data.get("hourly", {})
        gti_values = hourly.get("global_tilted_irradiance", [])
        temps = hourly.get("temperature_2m", [])
        for tag_idx in range(3):
            profil = openmeteo_gti_profil(
                gti_values, temps, tag_idx,
                kwp=anlagenleistung_kwp, system_losses=system_losses,
                datum=heute + timedelta(days=tag_idx),
            )
            eintraege = _profil_zu_eintraegen(profil)
            openmeteo_tagesprofile[tag_idx] = eintraege
            if tag_idx == 0:
                openmeteo_stundenprofil = eintraege

    # ── EEDC = OpenMeteo × Lernfaktor (MOS-Kaskade: saisonal → quartal → gesamt) ──
    # EEDC nutzt immer OpenMeteo als Basis — Solcast/SFML sind eigene Quellen.
    lf_result = await _get_lernfaktor_detail(anlage_id, db, quelle="openmeteo")
    lernfaktor = lf_result.faktor
    eedc_stundenprofil = []
    eedc_tagesprofile: list[list[StundenProfilEintrag]] = [[], [], []]
    _eedc_basis_om = True  # EEDC basiert immer auf OpenMeteo
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

    # ── SFML / Tom-HA: echtes mehrtägiges Stundenprofil (wenn als Quelle gewählt) ──
    # Einzelquellen-Treue (#110 „A"): bei gewählter SFML-Quelle SFMLs eigene
    # Kurvenform (evcc `forecast`, 3 Tage stündlich) statt GTI-Schmier. Nur
    # HA-Add-on; KEIN Cross-Quellen-Genauigkeits-Ranking.
    pq = resolve_prognose_quelle(anlage)
    sfml_tagesprofile: list[list[float]] = [[], [], []]  # kWh-Slots je Tag (Backward)
    sfml_heute_kwh = None
    sfml_morgen_kwh = None
    sfml_uebermorgen_kwh = None
    if pq.ist_sfml:
        try:
            from backend.services.prognose_discovery import discover_prognose_sensoren
            sfml_disc = await discover_prognose_sensoren("sfml")
            if sfml_disc.gefunden:
                sfml_heute_kwh = sfml_disc.wert("heute_kwh")
                sfml_morgen_kwh = sfml_disc.wert("morgen_kwh")
                sfml_uebermorgen_kwh = sfml_disc.wert("uebermorgen_kwh")
                forecast_attr = sfml_disc.attribut("stundenprofil")
                if forecast_attr:
                    sfml_tagesprofile = sfml_stundenprofile_aus_forecast(forecast_attr, heute)
                else:
                    hours_attr = sfml_disc.attribut("heute_kwh")
                    if hours_attr:
                        sfml_tagesprofile = [sfml_stundenprofil_aus_hours(hours_attr), [], []]
        except Exception as e:
            logger.debug(f"SFML-Discovery (Prognosen-Tab) fehlgeschlagen: {e}")
    sfml_verfuegbar = bool(sfml_tagesprofile and sfml_tagesprofile[0] and any(sfml_tagesprofile[0]))
    # Tagessummen aus dem Profil ableiten, wenn die State-Skalare fehlen.
    if sfml_verfuegbar and sfml_heute_kwh is None:
        sfml_heute_kwh = round(sum(sfml_tagesprofile[0]), 1)
    if sfml_morgen_kwh is None and len(sfml_tagesprofile) > 1 and any(sfml_tagesprofile[1] or []):
        sfml_morgen_kwh = round(sum(sfml_tagesprofile[1]), 1)
    if sfml_uebermorgen_kwh is None and len(sfml_tagesprofile) > 2 and any(sfml_tagesprofile[2] or []):
        sfml_uebermorgen_kwh = round(sum(sfml_tagesprofile[2]), 1)
    sfml_tagesprofile_eintraege = [
        _profil_zu_eintraegen(sfml_profil(tag, datum=heute + timedelta(days=i)))
        if (tag and any(tag)) else []
        for i, tag in enumerate(sfml_tagesprofile)
    ]
    sfml_stundenprofil = sfml_tagesprofile_eintraege[0] if sfml_tagesprofile_eintraege else []

    # ── IST-Ertrag heute (zentraler Adapter) ──
    # Issue #135: pv_kw kann None sein (kein Zähler gemappt / Datenlücke). None-
    # Stunden fließen NICHT in die Summe ein und bleiben im Profil als Lücke
    # (kw=None). Eine Lücke in einer bereits abgelaufenen Stunde setzt
    # unvollstaendig=True; die gerade abgeschlossene Stunde bewusst nicht (HA
    # schreibt die Hourly-Row erst am Stundenende). Logik in prognose_adapter.
    ist_p = ist_profil(ist_rows, jetzt_stunde=now.hour, datum=heute)
    ist_stundenprofil = _profil_zu_eintraegen(ist_p)
    ist_heute_kwh = ist_p.tageswert_kwh  # roh/ungerundet — für verbleibend-Rechnung
    ist_unvollstaendig = ist_p.unvollstaendig

    # ── Verbleibend = Tagesprojektion (IST bisher + Reststunden der Quelle) ──
    # Einheitliches Verfahren für ALLE Spalten (#296 #3/#5/#6):
    #   • #6: nicht mehr „Tagesprognose − IST" je Quelle vs. „IST + Reststunden"
    #     gesamt, sondern durchgängig IST + Σ Reststunden-Slots der Quelle.
    #   • #3: die Gesamtspalte konsumiert die in den Einstellungen aktive Quelle
    #     (pq.quelle), nicht mehr hardcodiert Solcast→OpenMeteo.
    #   • #5: IST + Rest funktioniert auch bei ist_heute_kwh==0 (frühmorgens) —
    #     keine „—"-Lücke mehr in den Pro-Quellen-Spalten.
    aktuelle_stunde = now.hour

    def _projektion(arr: Optional[list[float]]) -> Optional[float]:
        return _tagesprojektion(ist_heute_kwh, arr, aktuelle_stunde)

    om_arr = _eintraege_zu_array(openmeteo_stundenprofil)
    eedc_arr = _eintraege_zu_array(eedc_stundenprofil)
    sc_arr = list(solcast.hourly_kw) if solcast else None
    sfml_arr = list(sfml_tagesprofile[0]) if sfml_verfuegbar else None

    verbleibend_om_kwh = _projektion(om_arr) if openmeteo_stundenprofil else None
    verbleibend_eedc_kwh = _projektion(eedc_arr) if eedc_stundenprofil else None
    verbleibend_solcast_kwh = _projektion(sc_arr)

    # Gesamtspalte: gewählte Quelle (#3) mit Fallback-Kaskade.
    if pq.ist_sfml and sfml_arr:
        verbleibend_kwh = _projektion(sfml_arr)
    elif pq.ist_solcast and verbleibend_solcast_kwh is not None:
        verbleibend_kwh = verbleibend_solcast_kwh
    elif pq.ist_eedc and verbleibend_eedc_kwh is not None:
        verbleibend_kwh = verbleibend_eedc_kwh
    else:
        # Fallback wenn die gewählte Quelle keine Daten hat: Solcast (feinste
        # Auflösung) → eedc → OpenMeteo.
        verbleibend_kwh = (
            verbleibend_solcast_kwh
            if verbleibend_solcast_kwh is not None
            else verbleibend_eedc_kwh
            if verbleibend_eedc_kwh is not None
            else verbleibend_om_kwh
        )

    # ── Solcast aufbereiten ──
    solcast_stundenprofil = []
    solcast_tage = []
    solcast_morgen_p10 = None
    solcast_morgen_p90 = None
    solcast_uebermorgen_kwh = None

    if solcast:
        # Zentraler Adapter: 24-Slot-Profil + p10/p90-Band, fehlende Slots → 0.
        solcast_stundenprofil = _profil_zu_eintraegen(solcast_profil(solcast, datum=heute))
        solcast_tage = [SolcastTagSchema(**t) for t in solcast.tage_voraus]
        morgen_str = (heute + timedelta(days=1)).isoformat()
        uebermorgen_str = (heute + timedelta(days=2)).isoformat()
        for t in solcast.tage_voraus:
            if t["datum"] == morgen_str:
                solcast_morgen_p10 = t["p10"]
                solcast_morgen_p90 = t["p90"]
            if t["datum"] == uebermorgen_str:
                solcast_uebermorgen_kwh = t["kwh"]

    # ── Tageshälften (je 3 Einträge: heute, morgen, übermorgen) ──
    # Solar Noon pro Tag (Equation of Time) — Split an astronomischer Tagesmitte,
    # nicht an 12:00 Clockzeit. Konsistent zu solar_forecast_service.
    solar_noons = [
        _solar_noon_hour((heute + timedelta(days=d)).isoformat(), anlage.longitude)
        for d in range(3)
    ]
    om_ths = [
        _berechne_tageshaelfte(p, solar_noons[i]) if p else None
        for i, p in enumerate(openmeteo_tagesprofile)
    ]
    eedc_ths = [
        _berechne_tageshaelfte(p, solar_noons[i]) if p else None
        for i, p in enumerate(eedc_tagesprofile)
    ]
    # SFML VM/NM pro Tag direkt aus dem echten Stundenprofil (kein Schätzen nötig)
    sfml_ths: list[Optional[TageshaelfteSchema]] = [
        _berechne_tageshaelfte(p, solar_noons[i]) if p else None
        for i, p in enumerate(sfml_tagesprofile_eintraege[:3])
    ]
    while len(sfml_ths) < 3:
        sfml_ths.append(None)

    # Solcast VM/NM pro Tag aus tage_voraus berechnen (Stundenwerte nur für heute vorhanden,
    # für Morgen/Übermorgen approximieren wir aus den 30-Min-Daten im SolcastForecast)
    sc_ths: list[Optional[TageshaelfteSchema]] = [None, None, None]
    if solcast_stundenprofil:
        sc_ths[0] = _berechne_tageshaelfte(solcast_stundenprofil, solar_noons[0])
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

    ist_th = _berechne_tageshaelfte(ist_stundenprofil, solar_noons[0]) if ist_stundenprofil else None

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
        eedc_lernfaktor_o12=lf_result.faktor_o12,
        eedc_lernfaktor_o12_delta_pct=lf_result.delta_o12_pct,
        eedc_prognose_basis="eedc",  # EEDC basiert immer auf OpenMeteo
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
        sfml_verfuegbar=sfml_verfuegbar,
        sfml_heute_kwh=sfml_heute_kwh,
        sfml_morgen_kwh=sfml_morgen_kwh,
        sfml_uebermorgen_kwh=sfml_uebermorgen_kwh,
        sfml_stundenprofil=sfml_stundenprofil,
        sfml_tageshaelften=sfml_ths,
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
    ausreisser_ausblenden: bool = Query(
        default=False,
        description="Ausreißer-Tage (große Abweichung) aus MAE/MBE ausschließen (#296 #9, Default aus)",
    ),
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

    # ── Repräsentatives Tages-Wettersymbol je Tag (#296 #2) ──
    # TagesZusammenfassung trägt keinen WMO-Code; er liegt nur stündlich im
    # TagesEnergieProfil. Pro Tag: mittlere Bewölkung + Tagessumme Niederschlag +
    # Code der Mittagsstunde → SoT-Helper wetter_symbol_aus_tag (gleiche Symbole
    # wie der Forecast-Pfad, damit Rück- und Vorausschau konsistent aussehen).
    tep_result = await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum < date.today(),
        )
    )
    _bew: dict = {}
    _nieder: dict = {}
    _codes: dict = {}
    for row in tep_result.scalars().all():
        if row.bewoelkung_prozent is not None:
            _bew.setdefault(row.datum, []).append(row.bewoelkung_prozent)
        if row.niederschlag_mm is not None:
            _nieder[row.datum] = _nieder.get(row.datum, 0.0) + row.niederschlag_mm
        if row.wetter_code is not None:
            _codes.setdefault(row.datum, []).append((row.stunde, row.wetter_code))
    wetter_pro_tag: dict = {}
    for d in set(_bew) | set(_nieder) | set(_codes):
        codes = _codes.get(d)
        # Code der Stunde, die am nächsten an der Mittagsstunde (13 Uhr) liegt.
        mittag_code = min(codes, key=lambda c: abs(c[0] - 13))[1] if codes else None
        bews = _bew.get(d)
        bew = sum(bews) / len(bews) if bews else None
        wetter_pro_tag[d] = wetter_symbol_aus_tag(mittag_code, bew, _nieder.get(d))

    # Lernfaktor für EEDC-Genauigkeit (immer OpenMeteo-basiert)
    lernfaktor = await _get_lernfaktor(anlage_id, db, quelle="openmeteo")

    eintraege = []
    om_signed = []  # vorzeichenbehaftete relative Fehler (Prognose - IST) / IST * 100
    eedc_signed = []
    sc_signed = []
    # Ausreißer-Schwelle: ein Tag, an dem irgendeine Quelle > 50 % daneben lag,
    # gilt als Ausreißer (Sensor-Aussetzer, Datenlücke …). Bewusst KEIN stiller
    # Cap (#296 #9) — die Tage bleiben sichtbar, MAE/MBE schließt sie nur auf
    # Wunsch aus.
    AUSREISSER_SCHWELLE = 50.0
    anzahl_ausreisser = 0

    # PV-IST über den SoT-Helper `summe_pv_bkw_kwh` — Whitelist und v>0-Filter
    # gehören zentral nach `core/berechnungen/energie.py` (ADR-001, BKW-Drift-
    # Klasse 2026-05-19, Rainer-PN). Frontend-Pendant: `PV_KOMPONENTEN_PREFIXE`
    # in `frontend/src/lib/constants.ts`.
    for tz in tage_daten:
        ist_kwh = None
        if tz.komponenten_kwh:
            ist_kwh = summe_pv_bkw_kwh(tz.komponenten_kwh)

        # EEDC = OpenMeteo × Lernfaktor (historisch)
        eedc_kwh = None
        if lernfaktor is not None and tz.pv_prognose_kwh and tz.pv_prognose_kwh > 0:
            eedc_kwh = tz.pv_prognose_kwh * lernfaktor

        # Vorzeichenbehaftete relative Tagesfehler je Quelle (nur bei brauchbarem IST)
        om_err = eedc_err = sc_err = None
        if ist_kwh is not None and ist_kwh > 0.5:
            if tz.pv_prognose_kwh and tz.pv_prognose_kwh > 0:
                om_err = (tz.pv_prognose_kwh - ist_kwh) / ist_kwh * 100
            if eedc_kwh is not None and eedc_kwh > 0:
                eedc_err = (eedc_kwh - ist_kwh) / ist_kwh * 100
            if tz.solcast_prognose_kwh and tz.solcast_prognose_kwh > 0:
                sc_err = (tz.solcast_prognose_kwh - ist_kwh) / ist_kwh * 100

        abweichungen = [abs(e) for e in (om_err, eedc_err, sc_err) if e is not None]
        ist_ausreisser = bool(abweichungen) and max(abweichungen) > AUSREISSER_SCHWELLE
        if ist_ausreisser:
            anzahl_ausreisser += 1

        eintraege.append(GenauigkeitsEintrag(
            datum=tz.datum.isoformat(),
            openmeteo_kwh=round(tz.pv_prognose_kwh, 1) if tz.pv_prognose_kwh is not None else None,
            eedc_kwh=round(eedc_kwh, 1) if eedc_kwh is not None else None,
            solcast_kwh=round(tz.solcast_prognose_kwh, 1) if tz.solcast_prognose_kwh is not None else None,
            ist_kwh=round(ist_kwh, 1) if ist_kwh is not None else None,
            wetter_symbol=wetter_pro_tag.get(tz.datum),
            temperatur_max_c=round(tz.temperatur_max_c) if tz.temperatur_max_c is not None else None,
            ist_ausreisser=ist_ausreisser,
        ))

        # Auf Wunsch Ausreißer-Tage aus der MAE/MBE-Aggregation ausschließen (#296 #9).
        if ausreisser_ausblenden and ist_ausreisser:
            continue
        if om_err is not None:
            om_signed.append(om_err)
        if eedc_err is not None:
            eedc_signed.append(eedc_err)
        if sc_err is not None:
            sc_signed.append(sc_err)

    def _mae(xs):
        return round(sum(abs(x) for x in xs) / len(xs), 1) if xs else None

    def _mbe(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    def _asymmetrie(xs) -> AsymmetrieEintrag:
        """Splittet signed errors an 0 in „darüber" (Prognose > IST) und „darunter"."""
        over = [x for x in xs if x > 0]
        under = [x for x in xs if x < 0]
        return AsymmetrieEintrag(
            over_count=len(over),
            over_avg_prozent=round(sum(over) / len(over), 1) if over else None,
            under_count=len(under),
            under_avg_prozent=round(sum(under) / len(under), 1) if under else None,
        )

    return GenauigkeitsResponse(
        tage=eintraege,
        openmeteo_mae_prozent=_mae(om_signed),
        openmeteo_mbe_prozent=_mbe(om_signed),
        openmeteo_asymmetrie=_asymmetrie(om_signed),
        eedc_mae_prozent=_mae(eedc_signed),
        eedc_mbe_prozent=_mbe(eedc_signed),
        eedc_asymmetrie=_asymmetrie(eedc_signed),
        solcast_mae_prozent=_mae(sc_signed),
        solcast_mbe_prozent=_mbe(sc_signed),
        solcast_asymmetrie=_asymmetrie(sc_signed),
        anzahl_tage=len(eintraege),
        anzahl_ausreisser=anzahl_ausreisser,
        ausreisser_schwelle_prozent=AUSREISSER_SCHWELLE,
    )
