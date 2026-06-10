"""
Aussichten API Routes

Prognosen und Vorhersagen für PV-Erträge:
- Kurzfristig (7-16 Tage): Basierend auf Wettervorhersagen
- Langfristig (Monate): Basierend auf PVGIS TMY und Trends
- Trend-Analyse: Historische Entwicklung
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_jetzt, aktiv_im_zeitraum
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.strompreis import Strompreis
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.core.berechnungen import (
    FinanzMonatsZeile,
    berechne_finanz_aggregat,
    berechne_verbrauchs_kennzahlen,
    einspeise_erloes_euro,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.core.calculations import berechne_ust_eigenverbrauch
from backend.core.field_definitions import get_emob_pv_netz_kwh, get_wp_strom_kwh
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_PV_ANTEIL_DEFAULT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
)
from backend.services.speicher_wirtschaftlichkeit import (
    berechne_effektiver_ladepreis,
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    ist_dienstlich,
)
from backend.utils.sonstige_positionen import berechne_sonstige_netto
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.utils import wetter_symbol_aus_tag
from backend.services.wetter.pvgis import get_pvgis_tmy_defaults
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.services.pv_orientation import resolve_system_losses

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class TagesPrognoseSchema(BaseModel):
    """Prognose für einen einzelnen Tag."""
    datum: str
    pv_prognose_kwh: float
    globalstrahlung_kwh_m2: Optional[float]
    sonnenstunden: Optional[float]
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str


class KurzfristPrognoseResponse(BaseModel):
    """Response für Kurzfrist-Prognose (7-16 Tage)."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    prognose_zeitraum: dict
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[TagesPrognoseSchema]
    datenquelle: str
    abgerufen_am: str
    system_losses_prozent: float


class MonatsPrognoseSchema(BaseModel):
    """Prognose für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    pvgis_prognose_kwh: float
    trend_korrigiert_kwh: float
    konfidenz_min_kwh: float
    konfidenz_max_kwh: float
    historische_performance_ratio: Optional[float]


class TrendAnalyseSchema(BaseModel):
    """Trend-Analyse-Informationen."""
    durchschnittliche_performance_ratio: float
    trend_richtung: str
    datenbasis_monate: int


class LangfristPrognoseResponse(BaseModel):
    """Response für Langfrist-Prognose (Monate)."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    prognose_zeitraum: dict
    jahresprognose_kwh: float
    monatswerte: List[MonatsPrognoseSchema]
    trend_analyse: TrendAnalyseSchema
    datenquellen: List[str]


class JahresVergleichSchema(BaseModel):
    """Jahresvergleich-Daten."""
    jahr: int
    gesamt_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    performance_ratio: Optional[float]
    anzahl_monate: int  # Anzahl Monate mit Daten
    ist_vollstaendig: bool  # True wenn 12 Monate Daten vorhanden


class SaisonaleMusterSchema(BaseModel):
    """Saisonale Muster."""
    beste_monate: List[str]
    schlechteste_monate: List[str]


class DegradationSchema(BaseModel):
    """Degradations-Informationen."""
    geschaetzt_prozent_jahr: Optional[float]
    hinweis: str
    methode: Optional[str] = None  # "vollstaendig" oder "tmy_ergaenzt"
    zuverlaessig: bool = False  # True erst ab 3+ Jahren


class TrendAnalyseResponse(BaseModel):
    """Response für Trend-Analyse."""
    anlage_id: int
    anlagenname: str
    anlagenleistung_kwp: float
    analyse_zeitraum: dict
    jahres_vergleich: List[JahresVergleichSchema]
    saisonale_muster: SaisonaleMusterSchema
    degradation: DegradationSchema
    datenquellen: List[str]


class WetterVorhersageTag(BaseModel):
    """Wettervorhersage für einen Tag."""
    datum: str
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    sonnenstunden: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str


class WetterVorhersageResponse(BaseModel):
    """Response für reine Wettervorhersage."""
    anlage_id: int
    standort: dict
    tage: List[WetterVorhersageTag]
    abgerufen_am: str


# Finanzen-Schemas
class FinanzPrognoseMonatSchema(BaseModel):
    """Finanzprognose für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    pv_erzeugung_kwh: float
    eigenverbrauch_kwh: float
    einspeisung_kwh: float
    einspeise_erloes_euro: float
    ev_ersparnis_euro: float
    netto_ertrag_euro: float
    # Komponenten-Details
    speicher_beitrag_kwh: float = 0  # Zusätzlicher EV durch Speicher
    v2h_beitrag_kwh: float = 0  # Zusätzlicher EV durch V2H
    wp_verbrauch_kwh: float = 0  # Wärmepumpe-Stromverbrauch


class KomponentenBeitragSchema(BaseModel):
    """Beitrag einer Komponente zur Finanzprognose."""
    typ: str
    bezeichnung: str
    beitrag_kwh_jahr: float
    beitrag_euro_jahr: float
    beschreibung: str


class FinanzPrognoseResponse(BaseModel):
    """Response für Finanzprognose."""
    anlage_id: int
    anlagenname: str
    prognose_zeitraum: dict

    # Strompreise
    einspeiseverguetung_cent_kwh: float
    netzbezug_preis_cent_kwh: float
    grundpreis_euro_monat: float = 0

    # Jahresprognose
    jahres_erzeugung_kwh: float
    jahres_eigenverbrauch_kwh: float
    jahres_einspeisung_kwh: float
    eigenverbrauchsquote_prozent: float

    # Finanzen
    jahres_einspeise_erloes_euro: float
    jahres_ev_ersparnis_euro: float
    ust_eigenverbrauch_euro: Optional[float] = None  # USt auf Eigenverbrauch (nur bei Regelbesteuerung)
    jahres_netto_ertrag_euro: float

    # Komponenten-Beiträge (NEU)
    komponenten_beitraege: List[KomponentenBeitragSchema] = []

    # Speicher-spezifisch
    speicher_ev_erhoehung_kwh: float = 0
    speicher_ev_erhoehung_euro: float = 0

    # E-Auto/V2H-spezifisch
    v2h_rueckspeisung_kwh: float = 0
    v2h_ersparnis_euro: float = 0
    eauto_ladung_pv_kwh: float = 0
    eauto_ersparnis_euro: float = 0

    # Wärmepumpe-spezifisch
    wp_stromverbrauch_kwh: float = 0
    wp_pv_anteil_kwh: float = 0
    wp_pv_ersparnis_euro: float = 0

    # Alternativkosten-Einsparungen (NEU)
    wp_alternativ_ersparnis_euro: float = 0  # vs. Gas/Öl
    eauto_alternativ_ersparnis_euro: float = 0  # vs. Benzin

    # Investitionen (erweitert mit Alternativkosten-Berechnung)
    investition_pv_system_euro: float = 0  # PV, Speicher, Wallbox
    investition_wp_mehrkosten_euro: float = 0  # WP-Kosten minus Gasheizung
    investition_eauto_mehrkosten_euro: float = 0  # E-Auto minus Verbrenner
    investition_sonstige_euro: float = 0  # Andere Investitionen
    investition_gesamt_euro: float  # Relevante Kosten (inkl. Mehrkosten-Ansatz)
    bisherige_ertraege_euro: float  # Kumulierte Erträge seit Inbetriebnahme
    amortisations_fortschritt_prozent: float  # Wie viel % bereits amortisiert (kumuliert)
    amortisation_erreicht: bool
    amortisation_prognose_jahr: Optional[int]  # Geschätztes Jahr der Amortisation
    restlaufzeit_bis_amortisation_monate: Optional[int]

    # Monatswerte
    monatswerte: List[FinanzPrognoseMonatSchema]

    datenquellen: List[str]


# =============================================================================
# Konstanten
# =============================================================================

# DEFAULT_SYSTEM_LOSSES: zentral in services/pv_orientation.py
TEMP_COEFFICIENT = 0.004  # Leistungsabnahme pro °C über 25°C

MONATSNAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]


# =============================================================================
# Shared Helpers
# =============================================================================


async def _lade_anlage_mit_pv(
    db: AsyncSession,
    anlage_id: int,
    *,
    require_coords: bool = True,
) -> tuple["Anlage", list["Investition"], list["Investition"], float]:
    """Lädt Anlage + aktive PV-Module + BKW und berechnet Gesamtleistung.

    Returns:
        (anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp)

    Raises:
        HTTPException 404/400 bei fehlenden Daten.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    if require_coords and (not anlage.latitude or not anlage.longitude):
        raise HTTPException(
            status_code=400,
            detail="Anlage hat keine Koordinaten. Bitte Standort in Einstellungen konfigurieren."
        )

    # PV-Module + BKW in einer Query
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

    anlagenleistung_kwp = (
        sum(m.leistung_kwp or 0 for m in pv_module)
        + sum(b.leistung_kwp or 0 for b in balkonkraftwerke)
    )
    if anlagenleistung_kwp <= 0:
        anlagenleistung_kwp = anlage.leistung_kwp or 0

    return anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/kurzfristig/{anlage_id}", response_model=KurzfristPrognoseResponse)
async def get_kurzfrist_prognose(
    anlage_id: int,
    tage: int = Query(default=14, ge=1, le=16, description="Anzahl Tage (1-16)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Kurzfrist-PV-Prognose (7-16 Tage) basierend auf Wettervorhersage.

    Berechnet den erwarteten PV-Ertrag basierend auf:
    - Open-Meteo Wettervorhersage (Globalstrahlung)
    - Anlagenleistung in kWp (PV-Module + Balkonkraftwerke)
    - Systemverluste (aus PVGIS oder Standard 14%)
    - Temperaturkorrektur (Wirkungsgrad sinkt bei Hitze)
    """
    anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp = await _lade_anlage_mit_pv(db, anlage_id)

    if anlagenleistung_kwp <= 0:
        raise HTTPException(
            status_code=400,
            detail="Keine PV-Leistung konfiguriert. Bitte PV-Module in Investitionen anlegen."
        )

    # Systemverluste aus PVGIS (mit limit(1) falls mehrere aktiv)
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = result.scalar_one_or_none()
    system_losses = resolve_system_losses(pvgis)

    # Wettervorhersage abrufen (Wettermodell der Anlage berücksichtigen)
    wetter_modell = anlage.wetter_modell or "auto"
    model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
    wetter = await fetch_open_meteo_forecast(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        days=tage,
        skip_jitter=True,
        model=model_name,
    )

    if not wetter:
        raise HTTPException(
            status_code=503,
            detail="Wettervorhersage konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )

    # Tagesprognosen berechnen
    tageswerte = []
    summe_kwh = 0.0

    for tag in wetter["tage"]:
        pv_kwh = berechne_pv_ertrag_tag(
            globalstrahlung_kwh_m2=tag["globalstrahlung_kwh_m2"],
            anlagenleistung_kwp=anlagenleistung_kwp,
            temperatur_max_c=tag["temperatur_max_c"],
            system_losses=system_losses,
        )

        tageswerte.append(TagesPrognoseSchema(
            datum=tag["datum"],
            pv_prognose_kwh=pv_kwh,
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

        summe_kwh += pv_kwh

    von = tageswerte[0].datum if tageswerte else None
    bis = tageswerte[-1].datum if tageswerte else None

    return KurzfristPrognoseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        anlagenleistung_kwp=anlagenleistung_kwp,
        prognose_zeitraum={"von": von, "bis": bis},
        summe_kwh=round(summe_kwh, 1),
        durchschnitt_kwh_tag=round(summe_kwh / len(tageswerte), 2) if tageswerte else 0,
        tageswerte=tageswerte,
        datenquelle="open-meteo-forecast",
        abgerufen_am=wetter["abgerufen_am"],
        system_losses_prozent=round(system_losses * 100, 1),
    )


@router.get("/langfristig/{anlage_id}", response_model=LangfristPrognoseResponse)
async def get_langfrist_prognose(
    anlage_id: int,
    monate: int = Query(default=12, ge=1, le=24, description="Anzahl Monate (1-24)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Langfrist-PV-Prognose (Monate) basierend auf PVGIS TMY und historischen Trends.

    Kombiniert:
    - PVGIS TMY (langjährige Durchschnittswerte)
    - PV-Module + Balkonkraftwerke
    - Historische Performance-Ratio aus vorhandenen Daten
    - Konfidenzintervalle basierend auf Varianz
    """
    from datetime import date, timedelta

    anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp = await _lade_anlage_mit_pv(db, anlage_id)

    if anlagenleistung_kwp <= 0:
        raise bad_request("Keine PV-Leistung konfiguriert")

    # PVGIS-Prognose (mit limit(1) falls mehrere aktiv)
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = result.scalar_one_or_none()

    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)

    # Historische Performance-Ratio (PV-Module + BKW)
    pv_modul_ids = [m.id for m in pv_module]
    bkw_ids = [b.id for b in balkonkraftwerke]
    alle_pv_ids = pv_modul_ids + bkw_ids
    monatliche_pr = {}
    gesamt_pr = 1.0

    if alle_pv_ids:
        result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(alle_pv_ids)
            )
        )
        historische_daten = result.scalars().all()

        # Aggregiere pro Jahr/Monat über alle PV-Quellen
        monatliche_erzeugung = {}  # {(jahr, monat): kwh}
        for hd in historische_daten:
            key = (hd.jahr, hd.monat)
            ist_kwh = hd.verbrauch_daten.get("pv_erzeugung_kwh", 0) if hd.verbrauch_daten else 0
            if ist_kwh > 0:
                monatliche_erzeugung[key] = monatliche_erzeugung.get(key, 0) + ist_kwh

        for (jahr, monat), ist_kwh in monatliche_erzeugung.items():
            soll_kwh = pvgis_monatswerte.get(monat, 0)

            if soll_kwh > 0 and ist_kwh > 0:
                pr = ist_kwh / soll_kwh
                if monat not in monatliche_pr:
                    monatliche_pr[monat] = []
                monatliche_pr[monat].append(pr)

        avg_pr_monat = {m: sum(prs) / len(prs) for m, prs in monatliche_pr.items()}
        alle_prs = [pr for prs in monatliche_pr.values() for pr in prs]
        gesamt_pr = sum(alle_prs) / len(alle_prs) if alle_prs else 1.0
    else:
        avg_pr_monat = {}

    # Monatsprognosen erstellen
    heute = date.today()
    start_monat = heute.month
    start_jahr = heute.year
    monatswerte = []
    jahresprognose_kwh = 0.0

    for i in range(monate):
        monat = ((start_monat - 1 + i) % 12) + 1
        jahr = start_jahr + ((start_monat - 1 + i) // 12)

        pvgis_kwh = pvgis_monatswerte.get(monat, 0)

        if pvgis_kwh <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude)
            pvgis_kwh = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85

        monat_pr = avg_pr_monat.get(monat, gesamt_pr)
        trend_kwh = pvgis_kwh * monat_pr

        konfidenz_faktor = 0.15
        konfidenz_min = trend_kwh * (1 - konfidenz_faktor)
        konfidenz_max = trend_kwh * (1 + konfidenz_faktor)

        monatswerte.append(MonatsPrognoseSchema(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            pvgis_prognose_kwh=round(pvgis_kwh, 1),
            trend_korrigiert_kwh=round(trend_kwh, 1),
            konfidenz_min_kwh=round(konfidenz_min, 1),
            konfidenz_max_kwh=round(konfidenz_max, 1),
            historische_performance_ratio=round(monat_pr, 3) if monat in avg_pr_monat else None,
        ))

        jahresprognose_kwh += trend_kwh

    trend_richtung = "stabil"
    if gesamt_pr > 1.05:
        trend_richtung = "positiv"
    elif gesamt_pr < 0.95:
        trend_richtung = "negativ"

    return LangfristPrognoseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        anlagenleistung_kwp=anlagenleistung_kwp,
        prognose_zeitraum={
            "von": f"{start_jahr}-{start_monat:02d}",
            "bis": f"{monatswerte[-1].jahr}-{monatswerte[-1].monat:02d}" if monatswerte else None,
        },
        jahresprognose_kwh=round(jahresprognose_kwh, 0),
        monatswerte=monatswerte,
        trend_analyse=TrendAnalyseSchema(
            durchschnittliche_performance_ratio=round(gesamt_pr, 3),
            trend_richtung=trend_richtung,
            datenbasis_monate=sum(len(prs) for prs in monatliche_pr.values()),
        ),
        datenquellen=["pvgis-prognose" if pvgis else "pvgis-tmy", "historische-daten"],
    )


@router.get("/trend/{anlage_id}", response_model=TrendAnalyseResponse)
async def get_trend_analyse(
    anlage_id: int,
    jahre: int = Query(default=3, ge=1, le=10, description="Anzahl Jahre für Analyse"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trend-Analyse basierend auf historischen Daten.

    Analysiert:
    - Jahresvergleich der PV-Erträge (PV-Module + Balkonkraftwerke)
    - Saisonale Muster (beste/schlechteste Monate)
    - Degradation (Leistungsrückgang über Zeit) mit TMY-Auffüllung für unvollständige Jahre
    """
    from datetime import date

    anlage, pv_module, balkonkraftwerke, anlagenleistung_kwp = await _lade_anlage_mit_pv(
        db, anlage_id, require_coords=False
    )

    # PVGIS (mit limit(1) falls mehrere aktiv)
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = result.scalar_one_or_none()
    pvgis_jahresertrag = pvgis.jahresertrag_kwh if pvgis else 0

    # PVGIS Monatswerte für TMY-Auffüllung
    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)

    # Historische Daten (PV-Module + BKW)
    pv_modul_ids = [m.id for m in pv_module]
    bkw_ids = [b.id for b in balkonkraftwerke]
    alle_pv_ids = pv_modul_ids + bkw_ids
    jahres_ertraege = {}  # {jahr: {"kwh": X, "monate": set(), "monate_daten": {monat: kwh}}}
    monats_ertraege = {}

    if alle_pv_ids:
        result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(alle_pv_ids)
            )
        )
        historische_daten = result.scalars().all()

        for hd in historische_daten:
            jahr = hd.jahr
            monat = hd.monat
            kwh = hd.verbrauch_daten.get("pv_erzeugung_kwh", 0) if hd.verbrauch_daten else 0

            if kwh > 0:
                if jahr not in jahres_ertraege:
                    jahres_ertraege[jahr] = {"kwh": 0, "monate": set(), "monate_daten": {}}
                jahres_ertraege[jahr]["kwh"] += kwh
                jahres_ertraege[jahr]["monate"].add(monat)
                jahres_ertraege[jahr]["monate_daten"][monat] = jahres_ertraege[jahr]["monate_daten"].get(monat, 0) + kwh

                if monat not in monats_ertraege:
                    monats_ertraege[monat] = []
                monats_ertraege[monat].append(kwh)

    # Jahresvergleich mit Unterjährigkeits-Info
    heute = date.today()
    start_jahr = heute.year - jahre + 1
    jahres_vergleich = []

    for jahr in range(start_jahr, heute.year + 1):
        jahr_daten = jahres_ertraege.get(jahr, {"kwh": 0, "monate": set(), "monate_daten": {}})
        gesamt_kwh = jahr_daten["kwh"]
        anzahl_monate = len(jahr_daten["monate"])

        # Aktuelles Jahr: Max mögliche Monate = aktueller Monat
        max_monate = heute.month if jahr == heute.year else 12
        ist_vollstaendig = anzahl_monate >= max_monate

        spez_ertrag = gesamt_kwh / anlagenleistung_kwp if anlagenleistung_kwp > 0 else 0
        pr = gesamt_kwh / pvgis_jahresertrag if pvgis_jahresertrag > 0 else None

        jahres_vergleich.append(JahresVergleichSchema(
            jahr=jahr,
            gesamt_kwh=round(gesamt_kwh, 1),
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0),
            performance_ratio=round(pr, 3) if pr else None,
            anzahl_monate=anzahl_monate,
            ist_vollstaendig=ist_vollstaendig,
        ))

    # Saisonale Muster
    monats_durchschnitte = []
    for monat in range(1, 13):
        ertraege = monats_ertraege.get(monat, [])
        avg = sum(ertraege) / len(ertraege) if ertraege else 0
        monats_durchschnitte.append((monat, avg))

    sortiert = sorted(monats_durchschnitte, key=lambda x: x[1], reverse=True)
    beste_monate = [MONATSNAMEN[m[0]] for m in sortiert[:3] if m[1] > 0]
    schlechteste_monate = [MONATSNAMEN[m[0]] for m in sortiert[-3:] if m[1] > 0]

    # Degradation - Strategie:
    # 1. Primär: Nur vollständige Jahre (12 Monate) verwenden
    # 2. Fallback: Unvollständige Jahre mit TMY-Daten auffüllen (wenn Performance-Ratio verfügbar)
    degradation_prozent = None
    degradation_hinweis = "Nicht genügend Daten für Schätzung"
    degradation_methode = None

    # Nur Jahre mit 12 Monaten Daten für Degradation verwenden
    vollstaendige_jahre = [(jv.jahr, jv.gesamt_kwh) for jv in jahres_vergleich if jv.anzahl_monate == 12 and jv.gesamt_kwh > 0]

    if len(vollstaendige_jahre) >= 2:
        # Primäre Methode: Nur vollständige Jahre
        erstes = vollstaendige_jahre[0]
        letztes = vollstaendige_jahre[-1]
        if erstes[1] > 0:
            jahre_diff = letztes[0] - erstes[0]
            if jahre_diff > 0:
                aenderung = (letztes[1] - erstes[1]) / erstes[1] * 100
                degradation_prozent = round(aenderung / jahre_diff, 2)
                degradation_hinweis = f"Basierend auf {len(vollstaendige_jahre)} vollständigen Jahren ({vollstaendige_jahre[0][0]}-{vollstaendige_jahre[-1][0]})"
                degradation_methode = "vollstaendig"

    # Fallback: TMY-Auffüllung wenn nicht genug vollständige Jahre
    if degradation_prozent is None and pvgis_monatswerte:
        # Versuche unvollständige Jahre mit TMY aufzufüllen
        # Berechne Performance-Ratio pro Jahr aus vorhandenen Monaten
        aufgefuellte_jahre = []

        for jahr, daten in jahres_ertraege.items():
            monate_mit_daten = daten["monate"]
            monate_daten = daten["monate_daten"]

            if len(monate_mit_daten) >= 6:  # Mindestens 6 Monate für sinnvolle PR
                # Performance-Ratio aus vorhandenen Monaten berechnen
                ist_summe = sum(monate_daten.values())
                soll_summe = sum(pvgis_monatswerte.get(m, 0) for m in monate_mit_daten)

                if soll_summe > 0:
                    pr = ist_summe / soll_summe

                    # Fehlende Monate mit TMY * PR auffüllen
                    fehlende_monate = set(range(1, 13)) - monate_mit_daten
                    # Aktuelles Jahr: Nur bis zum aktuellen Monat auffüllen
                    if jahr == heute.year:
                        fehlende_monate = fehlende_monate & set(range(1, heute.month + 1))

                    ergaenzte_kwh = sum(pvgis_monatswerte.get(m, 0) * pr for m in fehlende_monate)
                    gesamt_aufgefuellt = ist_summe + ergaenzte_kwh

                    # Für aktuelle Jahre: Auf Jahreswert hochrechnen
                    if jahr == heute.year and heute.month < 12:
                        # Hochrechnung auf 12 Monate mit TMY-Verteilung
                        restliche_monate = set(range(heute.month + 1, 13))
                        prognose_rest = sum(pvgis_monatswerte.get(m, 0) * pr for m in restliche_monate)
                        gesamt_aufgefuellt += prognose_rest

                    aufgefuellte_jahre.append((jahr, gesamt_aufgefuellt, len(monate_mit_daten)))

        if len(aufgefuellte_jahre) >= 2:
            aufgefuellte_jahre.sort(key=lambda x: x[0])
            erstes = aufgefuellte_jahre[0]
            letztes = aufgefuellte_jahre[-1]

            if erstes[1] > 0:
                jahre_diff = letztes[0] - erstes[0]
                if jahre_diff > 0:
                    aenderung = (letztes[1] - erstes[1]) / erstes[1] * 100
                    degradation_prozent = round(aenderung / jahre_diff, 2)
                    monate_info = ", ".join([f"{j[0]}: {j[2]}/12 Mon." for j in aufgefuellte_jahre])
                    degradation_hinweis = f"TMY-ergänzt aus {len(aufgefuellte_jahre)} Jahren ({monate_info})"
                    degradation_methode = "tmy_ergaenzt"
        elif len(aufgefuellte_jahre) == 1:
            degradation_hinweis = f"Nur 1 Jahr mit ausreichend Daten ({aufgefuellte_jahre[0][2]}/12 Monate) - mindestens 2 Jahre nötig"

    if degradation_prozent is None and len(vollstaendige_jahre) == 1:
        degradation_hinweis = "Nur 1 vollständiges Jahr vorhanden - mindestens 2 Jahre für Degradations-Berechnung nötig"
    elif degradation_prozent is None:
        # Prüfe ob es unvollständige Jahre gibt
        unvollstaendige = [jv for jv in jahres_vergleich if jv.anzahl_monate < 12 and jv.gesamt_kwh > 0]
        if unvollstaendige:
            min_monate = min(j.anzahl_monate for j in unvollstaendige)
            max_monate = max(j.anzahl_monate for j in unvollstaendige)
            if min_monate < 6:
                degradation_hinweis = f"Unvollständige Jahre mit nur {min_monate}-{max_monate} Monaten - mindestens 6 Monate pro Jahr für TMY-Ergänzung nötig"
            else:
                degradation_hinweis = f"Noch kein vollständiges Jahr - aktuell nur unvollständige Jahre mit {min_monate}-{max_monate} Monaten"

    # Positive Degradation kappen (physikalisch nicht möglich, sondern Wetterschwankung)
    degradation_zuverlaessig = False
    if degradation_prozent is not None:
        anzahl_datenjahre = len(vollstaendige_jahre) if degradation_methode == "vollstaendig" else len(aufgefuellte_jahre) if 'aufgefuellte_jahre' in dir() else 0
        if degradation_prozent > 0:
            degradation_prozent = 0.0
            degradation_hinweis += " – Ertragssteigerung durch Wetterschwankungen, keine messbare Degradation"
        if anzahl_datenjahre >= 3:
            degradation_zuverlaessig = True
        else:
            degradation_hinweis += " – Wert mit Vorsicht interpretieren (min. 3 Jahre empfohlen)"

    return TrendAnalyseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        anlagenleistung_kwp=anlagenleistung_kwp,
        analyse_zeitraum={"von": start_jahr, "bis": heute.year},
        jahres_vergleich=jahres_vergleich,
        saisonale_muster=SaisonaleMusterSchema(
            beste_monate=beste_monate,
            schlechteste_monate=schlechteste_monate,
        ),
        degradation=DegradationSchema(
            geschaetzt_prozent_jahr=degradation_prozent,
            hinweis=degradation_hinweis,
            methode=degradation_methode,
            zuverlaessig=degradation_zuverlaessig,
        ),
        datenquellen=["historische-daten", "pvgis-tmy"] if degradation_methode == "tmy_ergaenzt" else ["historische-daten"],
    )


@router.get("/wetter/{anlage_id}", response_model=WetterVorhersageResponse)
async def get_wetter_vorhersage(
    anlage_id: int,
    tage: int = Query(default=7, ge=1, le=16, description="Anzahl Tage (1-16)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Reine Wettervorhersage ohne PV-Berechnung.

    Liefert Wetter-Icons, Temperaturen und Sonnenstunden für die nächsten Tage.
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    if not anlage.latitude or not anlage.longitude:
        raise bad_request("Anlage hat keine Koordinaten")

    # Wettervorhersage (Wettermodell der Anlage berücksichtigen)
    wetter_modell = anlage.wetter_modell or "auto"
    model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
    wetter = await fetch_open_meteo_forecast(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        days=tage,
        skip_jitter=True,
        model=model_name,
    )

    if not wetter:
        raise HTTPException(status_code=503, detail="Wettervorhersage nicht verfügbar")

    tage_liste = [
        WetterVorhersageTag(
            datum=tag["datum"],
            temperatur_max_c=tag["temperatur_max_c"],
            temperatur_min_c=tag["temperatur_min_c"],
            niederschlag_mm=tag["niederschlag_mm"],
            sonnenstunden=tag["sonnenstunden"],
            bewoelkung_prozent=tag["bewoelkung_prozent"],
            wetter_symbol=wetter_symbol_aus_tag(
                tag["wetter_code"],
                tag.get("bewoelkung_prozent"),
                tag.get("niederschlag_mm"),
            ),
        )
        for tag in wetter["tage"]
    ]

    return WetterVorhersageResponse(
        anlage_id=anlage_id,
        standort={
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
        },
        tage=tage_liste,
        abgerufen_am=wetter["abgerufen_am"],
    )


@router.get("/finanzen/{anlage_id}", response_model=FinanzPrognoseResponse)
async def get_finanz_prognose(
    anlage_id: int,
    monate: int = Query(default=12, ge=1, le=24, description="Anzahl Monate (1-24)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Finanzprognose für PV-Erträge inkl. aller Komponenten.

    Berücksichtigt:
    - PV-Erzeugung (aus PVGIS oder historisch)
    - Speicher (Eigenverbrauchserhöhung)
    - E-Auto mit V2H (Rückspeisung ins Haus)
    - Wärmepumpe (PV-Direktverbrauch)
    - ROI-Fortschritt und Amortisations-Prognose
    """
    from datetime import date
    from sqlalchemy import func

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    # Tarife laden (allgemein + Spezialtarife)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    wp_tarif = tarife.get("waermepumpe")

    einspeiseverguetung = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else EINSPEISEVERGUETUNG_DEFAULT_CENT
    netzbezug_preis = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else NETZBEZUG_DEFAULT_CENT
    wp_netzbezug_preis = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else netzbezug_preis

    # =====================================================================
    # ALLE INVESTITIONEN LADEN — Issue #123: Hybrid-Sicht
    # Historische Aggregation braucht ALLE (auch stillgelegte) Investitionen,
    # damit Vergangenheit vollständig bleibt. Für die Prognose-Basis
    # (anlagenleistung_kwp) wird anschließend auf aktuell aktive PV gefiltert.
    # =====================================================================
    from datetime import date as _date
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
        )
    )
    alle_investitionen = result.scalars().all()

    # Nach Typ gruppieren (alle — auch historische)
    pv_module = [i for i in alle_investitionen if i.typ == "pv-module"]
    speicher = [i for i in alle_investitionen if i.typ == "speicher"]
    e_autos = [i for i in alle_investitionen
               if i.typ == "e-auto" and not ist_dienstlich(i)]
    waermepumpen = [i for i in alle_investitionen if i.typ == "waermepumpe"]
    balkonkraftwerke = [i for i in alle_investitionen if i.typ == "balkonkraftwerk"]
    sonstiges_investitionen = [i for i in alle_investitionen if i.typ == "sonstiges"]

    # Prognose-Basis: nur aktuell aktive PV (kWp für künftige Erträge)
    _heute = _date.today()
    aktuelle_pv_module = [m for m in pv_module if m.ist_aktiv_an(_heute)]
    aktuelle_bkw = [b for b in balkonkraftwerke if b.ist_aktiv_an(_heute)]
    anlagenleistung_kwp = (
        sum(m.leistung_kwp or 0 for m in aktuelle_pv_module)
        + sum(b.leistung_kwp or 0 for b in aktuelle_bkw)
    ) or anlage.leistung_kwp or 0

    # =====================================================================
    # HISTORISCHE DATEN LADEN
    # =====================================================================
    inv_ids = [i.id for i in alle_investitionen]
    inv_by_id_hist = {i.id: i for i in alle_investitionen}
    historische_inv_daten = {}

    if inv_ids:
        result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(inv_ids)
            )
        )
        # #236: IMD vor anschaffungs- / nach stilllegungsdatum überspringen
        for imd in result.scalars().all():
            inv_hist = inv_by_id_hist.get(imd.investition_id)
            if not inv_hist or not inv_hist.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            key = (imd.investition_id, imd.jahr, imd.monat)
            historische_inv_daten[key] = imd.verbrauch_daten or {}

    # Monatsdaten für Eigenverbrauch etc.
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    monatsdaten = result.scalars().all()
    monatsdaten_dict = {(md.jahr, md.monat): md for md in monatsdaten}

    # =====================================================================
    # HISTORISCHE WERTE AGGREGIEREN
    # =====================================================================
    gesamt_pv = 0.0
    gesamt_ev = 0.0
    gesamt_speicher_entladung = 0.0
    gesamt_speicher_ladung = 0.0
    gesamt_v2h = 0.0
    gesamt_eauto_pv = 0.0
    gesamt_wp_strom = 0.0

    # #304 Teil 2: gesamt_ev + EV pro Monat werden unten aus dem SoT-Helper
    # `berechne_verbrauchs_kennzahlen` gebildet (PV+Speicher aus IMD +
    # Zählerwerte), NICHT mehr aus dem Legacy-Feld md.eigenverbrauch_kwh — das
    # bleibt bei IMD-basierten Setups leer und ließ die EV-Quote/-Ersparnis
    # kollabieren (deckungsgleich mit Cockpit/HA-Export, ADR-001).

    # PV-Erzeugung aus InvestitionMonatsdaten (gesamt + pro Monat)
    pv_pro_monat = {}  # {(jahr, monat): kwh} für EV-Quoten-Berechnung
    for pv in pv_module:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == pv.id:
                kwh = daten.get("pv_erzeugung_kwh", 0)
                gesamt_pv += kwh
                pv_pro_monat[(jahr, monat)] = pv_pro_monat.get((jahr, monat), 0) + kwh

    # BKW-Erzeugung (+ Eigenverbrauch pro Monat für die Finanz-Aggregation)
    bkw_ev_pro_monat: dict[tuple[int, int], float] = {}
    for bkw in balkonkraftwerke:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == bkw.id:
                kwh = daten.get("pv_erzeugung_kwh", 0)
                gesamt_pv += kwh
                pv_pro_monat[(jahr, monat)] = pv_pro_monat.get((jahr, monat), 0) + kwh
                bkw_ev = daten.get("eigenverbrauch_kwh", 0) or 0
                bkw_ev_pro_monat[(jahr, monat)] = (
                    bkw_ev_pro_monat.get((jahr, monat), 0) + bkw_ev
                )

    # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
    # Speicher-Daten (gesamt + pro Monat für die SoT-EV-Berechnung)
    speicher_ladung_pro_monat: dict[tuple[int, int], float] = {}
    speicher_entladung_pro_monat: dict[tuple[int, int], float] = {}
    for sp in speicher:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == sp.id and sp.ist_aktiv_im_monat(jahr, monat):
                entl = daten.get("entladung_kwh", 0) or 0
                lad = daten.get("ladung_kwh", 0) or 0
                gesamt_speicher_entladung += entl
                gesamt_speicher_ladung += lad
                speicher_entladung_pro_monat[(jahr, monat)] = (
                    speicher_entladung_pro_monat.get((jahr, monat), 0) + entl
                )
                speicher_ladung_pro_monat[(jahr, monat)] = (
                    speicher_ladung_pro_monat.get((jahr, monat), 0) + lad
                )

    # E-Auto-Daten — `gesamt_eauto_pv` und `gesamt_v2h` bleiben Aggregate
    # (für Quoten + Saisonprognose). Per-EA-Differenzierung passiert weiter
    # unten via `eauto_aggregate` (Bug-Klasse: vorher last-write-wins über
    # `vergleich_l_100km` und `benzinpreis_default`).
    eauto_pv_pro_inv: dict[int, float] = {}
    v2h_pro_monat: dict[tuple[int, int], float] = {}
    for ea in e_autos:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == ea.id and ea.ist_aktiv_im_monat(jahr, monat):
                pv_ladung = daten.get("ladung_pv_kwh", 0) or 0
                v2h = daten.get("v2h_entladung_kwh", 0) or 0
                gesamt_v2h += v2h
                gesamt_eauto_pv += pv_ladung
                eauto_pv_pro_inv[ea.id] = eauto_pv_pro_inv.get(ea.id, 0.0) + pv_ladung
                v2h_pro_monat[(jahr, monat)] = v2h_pro_monat.get((jahr, monat), 0) + v2h

    # Wärmepumpe-Daten
    for wp in waermepumpen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                gesamt_wp_strom += get_wp_strom_kwh(daten, wp.parameter)

    # #304 Teil 2: Eigenverbrauch pro Monat über den kanonischen SoT-Helper aus
    # PV(IMD) + Speicher(IMD) + Zählerwerten — plus V2H (Aussichten hat diesen
    # Term schon immer mitgezählt; der Helper kennt nur PV+Speicher). Single
    # Source: dieselbe Map speist gesamt_ev, die EV-Quoten-Historie und die
    # bisherige EV-Ersparnis — kein Punkt-Patch je Lesestelle (#304-Fix-Vorgabe).
    eigenverbrauch_pro_monat: dict[tuple[int, int], float] = {}
    for md in monatsdaten:
        key = (md.jahr, md.monat)
        kennzahlen = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=pv_pro_monat.get(key, 0),
            einspeisung_kwh=md.einspeisung_kwh or 0,
            netzbezug_kwh=md.netzbezug_kwh or 0,
            speicher_ladung_kwh=speicher_ladung_pro_monat.get(key, 0),
            speicher_entladung_kwh=speicher_entladung_pro_monat.get(key, 0),
            v2h_entladung_kwh=v2h_pro_monat.get(key, 0),
        )
        eigenverbrauch_pro_monat[key] = kennzahlen.eigenverbrauch_kwh

    gesamt_ev = sum(eigenverbrauch_pro_monat.values())

    # =====================================================================
    # QUOTEN BERECHNEN (aus historischen Daten oder Defaults)
    # =====================================================================

    anzahl_monate_hist = len(monatsdaten) if monatsdaten else 1

    # Historische EV-Quote pro Kalendermonat berechnen
    # Nutzt die echte Gesamt-EV-Quote (inkl. Speicher, V2H, WP) aus Monatsdaten
    hist_ev_quoten_lists = {}  # {kalendermonat: [quote1, quote2, ...]}
    for md in monatsdaten:
        pv_monat = pv_pro_monat.get((md.jahr, md.monat), 0)
        ev_monat = eigenverbrauch_pro_monat.get((md.jahr, md.monat), 0)
        if pv_monat > 0 and ev_monat > 0:
            quote = min(1.0, ev_monat / pv_monat)
            hist_ev_quoten_lists.setdefault(md.monat, []).append(quote)

    # Durchschnitt pro Kalendermonat (falls mehrere Jahre vorhanden)
    hist_ev_quoten = {m: sum(q) / len(q) for m, q in hist_ev_quoten_lists.items()}

    # Gesamt-Durchschnitt als Fallback für Monate ohne historische Daten
    avg_hist_ev_quote = (
        sum(hist_ev_quoten.values()) / len(hist_ev_quoten)
        if hist_ev_quoten else None
    )

    # Fallback-Komponentenmodell nur wenn KEINE historischen EV-Quoten vorhanden
    if avg_hist_ev_quote is None:
        basis_ev_quote = 0.30  # Default ohne Daten
        if gesamt_pv > 0 and gesamt_ev > 0:
            ev_ohne_speicher = max(0, gesamt_ev - gesamt_speicher_entladung - gesamt_v2h)
            basis_ev_quote = ev_ohne_speicher / gesamt_pv if gesamt_pv > 0 else 0.30
            basis_ev_quote = min(0.70, max(0.15, basis_ev_quote))
    else:
        basis_ev_quote = avg_hist_ev_quote  # Wird nur für Monate ohne hist. Daten genutzt

    # Speicher-Effizienz (Entladung/Ladung)
    speicher_effizienz = 0.90  # Default 90%
    if gesamt_speicher_ladung > 0:
        speicher_effizienz = min(0.95, gesamt_speicher_entladung / gesamt_speicher_ladung)

    # Komponentenbeiträge pro Monat (für Anzeige-Felder in der Prognose)
    speicher_ev_erhohung_monat = gesamt_speicher_entladung / anzahl_monate_hist if speicher else 0
    v2h_beitrag_monat = gesamt_v2h / anzahl_monate_hist if e_autos else 0
    eauto_pv_monat = gesamt_eauto_pv / anzahl_monate_hist if e_autos else 0
    wp_strom_monat_avg = gesamt_wp_strom / anzahl_monate_hist if waermepumpen else 0

    # =====================================================================
    # PVGIS-PROGNOSE (mit limit(1) falls mehrere aktiv)
    # =====================================================================
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = result.scalar_one_or_none()

    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)

    # =====================================================================
    # INVESTITIONEN SUMMIEREN (mit Alternativkosten-Berechnung)
    # =====================================================================
    # Für ROI werden MEHRKOSTEN gegenüber Alternativen berechnet:
    # - PV-System: volle Kosten (keine Alternative)
    # - Wärmepumpe: Mehrkosten vs. Gasheizung
    # - E-Auto: Mehrkosten vs. Verbrenner
    # - Sonstiges: volle Kosten

    PV_RELEVANTE_TYPEN = [
        "pv-module", "wechselrichter", "speicher", "wallbox", "balkonkraftwerk"
    ]

    investition_pv_system = 0.0
    investition_wp_mehrkosten = 0.0
    investition_eauto_mehrkosten = 0.0
    investition_sonstige = 0.0

    for inv in alle_investitionen:
        kosten = inv.anschaffungskosten_gesamt or 0
        if inv.typ in PV_RELEVANTE_TYPEN:
            investition_pv_system += kosten
        elif inv.typ == "waermepumpe":
            # Mehrkosten WP vs. Gasheizung (ca. 8.000-10.000€)
            # Kann über Parameter konfiguriert werden
            alternativ_kosten = 8000.0
            if inv.parameter:
                alternativ_kosten = inv.parameter.get(PARAM_WAERMEPUMPE["ALTERNATIV_KOSTEN_EURO"], 8000.0)
            investition_wp_mehrkosten += max(0, kosten - alternativ_kosten)
        elif inv.typ == "e-auto":
            # Mehrkosten E-Auto vs. Verbrenner
            # Kann über Parameter konfiguriert werden
            alternativ_kosten = 35000.0  # Default: vergleichbarer Verbrenner
            if inv.parameter:
                alternativ_kosten = inv.parameter.get(PARAM_E_AUTO["ALTERNATIV_KOSTEN_EURO"], 35000.0)
            investition_eauto_mehrkosten += max(0, kosten - alternativ_kosten)
        else:
            investition_sonstige += kosten

    # Gesamtinvestition = PV-System + Mehrkosten für WP/E-Auto + Sonstiges
    investition_gesamt = (
        investition_pv_system +
        investition_wp_mehrkosten +
        investition_eauto_mehrkosten +
        investition_sonstige
    )

    # =====================================================================
    # ALTERNATIVKOSTEN-PARAMETER LADEN
    # =====================================================================

    # Wärmepumpe: per-WP-Parameter (Alter Energieträger Gas/Öl, Preis,
    # fixe Zusatzkosten). Vorher: eine `for wp`-Schleife schrieb
    # `wp_alter_preis_cent` und `wp_alter_wirkungsgrad` last-write-wins in
    # globale Variablen — bei zwei WPs mit unterschiedlichen Energieträgern
    # (Gas + Öl) wurde der Wirkungsgrad der letzten auf beide angewendet.
    # Bug #7 (v3.25.0): Default vereinheitlicht auf zentrale 12 ct/kWh aus
    # PARAM_WAERMEPUMPE_DEFAULTS (vorher hier 10.0, andernorts 12.0).
    wp_aggregate: dict[int, dict] = {}
    for wp in waermepumpen:
        params = wp.parameter or {}
        wp_aggregate[wp.id] = {
            "alter_preis_cent": (
                params.get(
                    PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
                    PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
                ) or PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]
            ),
            "alter_wirkungsgrad": (
                WP_WIRKUNGSGRAD_OEL_DEFAULT
                if params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]) == "oel"
                else WP_WIRKUNGSGRAD_GAS_DEFAULT
            ),
            "zusatzkosten_jahr": params.get(
                PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0,
            ) or 0,
            "thermisch_kwh": 0.0,
        }
    wp_alternativ_zusatzkosten_jahr = sum(
        a["zusatzkosten_jahr"] for a in wp_aggregate.values()
    )

    # E-Auto: Benzin-Vergleich.
    # Pro E-Auto: `benzinpreis_default` (Fallback wenn `kraftstoffpreis_euro`
    # in Monatsdaten fehlt) und `vergleich_l_100km` (Verbrauch des
    # Vergleichs-Verbrenners). Vorher las eine `for ea`-Schleife diese Werte
    # in zwei globale Variablen — last-write-wins, bei zwei E-Autos mit
    # unterschiedlichen Parametern wurden die Werte des LETZTEN auf BEIDE
    # angewendet. Per-E-Auto-Aggregat (`eauto_aggregate[ea.id]`) ersetzt das.
    eauto_aggregate: dict[int, dict] = {}
    for ea in e_autos:
        params = ea.parameter or {}
        eauto_aggregate[ea.id] = {
            "bezeichnung": ea.bezeichnung,
            "benzinpreis_default": params.get(
                PARAM_E_AUTO["BENZINPREIS_EURO"],
                PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
            ) or PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
            "vergleich_l_100km": params.get(
                PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
                PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
            ) or PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
            "km": 0.0,
            "netz_kwh": 0.0,
            "pv_kwh": eauto_pv_pro_inv.get(ea.id, 0.0),
            "bisherige_ersparnis": 0.0,
        }

    # =====================================================================
    # BISHERIGE ERTRÄGE BERECHNEN (inkl. Alternativkosten!)
    # =====================================================================
    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in alle_investitionen)
    bisherige_ertraege = 0.0
    bisherige_wp_ersparnis = 0.0
    bisherige_eauto_ersparnis = 0.0

    # Anschaffungsdatum-Grenze für den anlagenweiten PV-Ertrag (Einspeise-Erlös +
    # EV-Ersparnis). WP/E-Auto/Sonstige begrenzen ihre Monate bereits über
    # `ist_aktiv_im_monat` (#236); dieser Pfad filtert auf das aktive Fenster der
    # PV-Erzeuger (PV-Module ∪ Balkonkraftwerke), analog zur `md_pv`-Logik in
    # cockpit/uebersicht.py ([[feedback_anschaffungsdatum_grenze]]). Ohne
    # registrierte PV-Quelle oder ohne gesetztes Anschaffungsdatum bleibt das
    # Verhalten unverändert (`ist_aktiv_im_monat` ist dann für alle Monate True).
    pv_erzeuger = pv_module + balkonkraftwerke

    def _pv_aktiv_im_monat(jahr: int, monat: int) -> bool:
        if not pv_erzeuger:
            return True
        return any(p.ist_aktiv_im_monat(jahr, monat) for p in pv_erzeuger)

    # #326-Vollmigration: Einspeise-Erlös §51 + EV-/BKW-Ersparnis laufen über
    # den SoT-Helper `berechne_finanz_aggregat` — per-Monat mit Monats-Flexpreis
    # UND Monats-Tarif (gueltig_ab-Stichtag), deckungsgleich mit Cockpit,
    # Jahresbericht-PDF und HA-Export ([[feedback_aggregations_drift]]). Die
    # aussichten-spezifischen Anteile (WP-/E-Auto-Alternativkosten, Prognose)
    # bleiben lokal — sie sind keine Aggregat-Semantik.
    _tarif_cache: dict[date, dict] = {}

    async def _tarif_fuer_monat(jahr: int, monat: int) -> dict:
        stichtag = date(jahr, monat, 1)
        if stichtag not in _tarif_cache:
            _tarif_cache[stichtag] = await lade_tarife_fuer_anlage(
                db, anlage_id, target_date=stichtag
            )
        return _tarif_cache[stichtag]

    finanz_zeilen: list[FinanzMonatsZeile] = []
    for md in monatsdaten:
        if not _pv_aktiv_im_monat(md.jahr, md.monat):
            continue
        m_key = (md.jahr, md.monat)
        m_tarife = await _tarif_fuer_monat(md.jahr, md.monat)
        m_allgemein = m_tarife.get("allgemein")
        m_preis_cent = m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else NETZBEZUG_DEFAULT_CENT
        m_einspeis_cent = m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
        # §51: Anwender ohne Strompreis-Mitschrift (m_neg=None) sehen die
        # ungekürzte Berechnung.
        m_neg = (
            await get_neg_preis_einspeisung_monat(db, anlage_id, md.jahr, md.monat)
            if md.einspeisung_kwh else None
        )
        finanz_zeilen.append(FinanzMonatsZeile(
            einspeisung_kwh=md.einspeisung_kwh or 0,
            netzbezug_kwh=md.netzbezug_kwh or 0,
            pv_erzeugung_kwh=pv_pro_monat.get(m_key, 0),
            speicher_ladung_kwh=speicher_ladung_pro_monat.get(m_key, 0),
            speicher_entladung_kwh=speicher_entladung_pro_monat.get(m_key, 0),
            v2h_entladung_kwh=v2h_pro_monat.get(m_key, 0),
            bkw_eigenverbrauch_kwh=bkw_ev_pro_monat.get(m_key, 0),
            netzbezug_preis_cent=resolve_netzbezug_preis_cent(md, m_preis_cent),
            einspeiseverguetung_cent=m_einspeis_cent,
            neg_preis_kwh=m_neg,
        ))

    # Wärmepumpe Alternativkosten-Ersparnis
    # Ersparnis = Gas-Kosten (was es kosten würde) + fixe Zusatzkosten - WP-Stromkosten
    gesamt_wp_thermisch = 0.0
    wp_monate_gezaehlt: set[tuple[int, int]] = set()
    for wp in waermepumpen:
        wp_agg = wp_aggregate[wp.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                heiz = daten.get("heizenergie_kwh", 0)
                ww = daten.get("warmwasser_kwh", 0)
                strom = get_wp_strom_kwh(daten, wp.parameter)
                thermisch = heiz + ww
                gesamt_wp_thermisch += thermisch
                wp_agg["thermisch_kwh"] += thermisch
                # Monatspreis: Monatsdaten.gaspreis_cent_kwh → Fallback per-WP-Default
                md = monatsdaten_dict.get((jahr, monat))
                monats_gaspreis = (
                    md.gaspreis_cent_kwh
                    if md and md.gaspreis_cent_kwh is not None
                    else wp_agg["alter_preis_cent"]
                )
                # Gas-Alternative: thermisch / Wirkungsgrad * Preis — pro WP
                gas_kosten = (thermisch / wp_agg["alter_wirkungsgrad"]) * monats_gaspreis / 100
                # WP-Stromkosten (nur Netzanteil, PV-Anteil ist bereits in EV-Ersparnis)
                # Konservative 50/50-Annahme — TODO: aus tatsächlichen Daten herleiten
                wp_netz_anteil = 1.0 - WP_PV_ANTEIL_DEFAULT
                wp_stromkosten_netz = strom * wp_netz_anteil * wp_netzbezug_preis / 100
                # Netto-Ersparnis (Gas-Alternative minus WP-Netzstrom)
                bisherige_wp_ersparnis += gas_kosten - wp_stromkosten_netz
                wp_monate_gezaehlt.add((jahr, monat))
    # Fixe Zusatzkosten pro erfassten Monat (1/12 pro Monat)
    bisherige_wp_ersparnis += wp_alternativ_zusatzkosten_jahr * len(wp_monate_gezaehlt) / 12

    # E-Auto Alternativkosten-Ersparnis
    # Ersparnis = Benzin-Kosten - Netzstrom-Kosten
    # Pro Monat + pro E-Auto, damit unterschiedliche Vergleichsverbräuche
    # und Benzinpreis-Defaults pro Fahrzeug korrekt einfließen. Vorher las
    # diese Schleife `eauto_vergleich_l_100km` aus einer last-write-wins-
    # Variable außerhalb — bei mehreren E-Autos wurden alle mit dem Wert
    # des letzten gerechnet.
    for ea in e_autos:
        agg = eauto_aggregate[ea.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != ea.id or not ea.ist_aktiv_im_monat(jahr, monat):
                continue
            km = daten.get("km_gefahren", 0) or 0
            netz = daten.get("ladung_netz_kwh", 0) or 0
            agg["km"] += km
            agg["netz_kwh"] += netz
            # Monats-Benzinpreis: Monatsdaten (EU OB) → Fallback per-Inv-Default
            md = monatsdaten_dict.get((jahr, monat))
            monats_benzinpreis = (
                md.kraftstoffpreis_euro
                if md and md.kraftstoffpreis_euro is not None
                else agg["benzinpreis_default"]
            )
            benzin_liter = km / 100 * agg["vergleich_l_100km"]
            md_preis = resolve_netzbezug_preis_cent(md, netzbezug_preis) if md else netzbezug_preis
            agg["bisherige_ersparnis"] += (
                benzin_liter * monats_benzinpreis - netz * md_preis / 100
            )
    bisherige_eauto_ersparnis = sum(a["bisherige_ersparnis"] for a in eauto_aggregate.values())
    gesamt_km = sum(a["km"] for a in eauto_aggregate.values())
    gesamt_eauto_netz = sum(a["netz_kwh"] for a in eauto_aggregate.values())

    # BKW-Ersparnis: kommt aus `berechne_finanz_aggregat` (bkw_eigenverbrauch_kwh
    # in den Finanz-Zeilen oben) — kein eigener Loop mehr.

    # Sonstige Positionen für ALLE Investitionstypen (Wallbox-Erstattungen, THG-Quote, BHKW etc.)
    bisherige_sonstige_netto = 0.0
    for inv in alle_investitionen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == inv.id and inv.ist_aktiv_im_monat(jahr, monat):
                bisherige_sonstige_netto += berechne_sonstige_netto(daten)

    # Dienstliche E-Auto/Wallbox-Ladekosten abziehen (Netzbezug + entgangene
    # Einspeisung). Netzbezug-Anteil per-Monat über den Flexpreis (gleichzeitig
    # mit cockpit/uebersicht.py umgestellt — einseitig wäre neue Asymmetrie);
    # Einspeisevergütung bleibt statisch (Vertragswert). PV/Netz-Split über den
    # SoT-Helper `get_emob_pv_netz_kwh` (#262: evcc-Import ohne ladung_netz_kwh).
    bisherige_dienstlich_ladekosten = 0.0
    for inv in alle_investitionen:
        if inv.typ in ("e-auto", "wallbox") and ist_dienstlich(inv):
            for (inv_id, jahr, monat), daten in historische_inv_daten.items():
                if inv_id == inv.id and inv.ist_aktiv_im_monat(jahr, monat):
                    pv_kwh, netz_kwh = get_emob_pv_netz_kwh(daten)
                    md = monatsdaten_dict.get((jahr, monat))
                    md_preis = resolve_netzbezug_preis_cent(md, netzbezug_preis) if md else netzbezug_preis
                    bisherige_dienstlich_ladekosten += (
                        netz_kwh * md_preis + pv_kwh * einspeiseverguetung
                    ) / 100
    bisherige_sonstige_netto -= bisherige_dienstlich_ladekosten

    # Finanz-Aggregat (Einspeise-Erlös §51 + EV- + BKW-Ersparnis + Sonstige)
    # + aussichten-spezifische Alternativkosten-Ersparnisse (WP, E-Auto).
    _finanz = berechne_finanz_aggregat(
        finanz_zeilen, sonstige_netto_euro=bisherige_sonstige_netto
    )
    bisherige_bkw_ersparnis = _finanz.bkw_ersparnis_euro
    bisherige_ertraege = (
        _finanz.netto_ertrag_euro + bisherige_wp_ersparnis + bisherige_eauto_ersparnis
    )

    # Anteilige Betriebskosten für den historischen Zeitraum abziehen
    betriebskosten_hist = betriebskosten_ges * anzahl_monate_hist / 12 if anzahl_monate_hist > 0 else 0
    bisherige_ertraege -= betriebskosten_hist

    # =====================================================================
    # MONATSPROGNOSEN ERSTELLEN
    # =====================================================================
    heute = date.today()
    start_monat = heute.month
    start_jahr = heute.year
    monatswerte = []

    jahres_erzeugung = 0.0
    jahres_eigenverbrauch = 0.0
    jahres_einspeisung = 0.0
    jahres_einspeise_erloes = 0.0
    jahres_ev_ersparnis = 0.0
    jahres_speicher_beitrag = 0.0
    jahres_v2h_beitrag = 0.0
    jahres_wp_verbrauch = 0.0
    jahres_eauto_pv = 0.0

    # Saisonale Faktoren für WP (Heizperiode)
    WP_SAISON_FAKTOREN = {
        1: 1.8, 2: 1.6, 3: 1.3, 4: 0.8, 5: 0.4, 6: 0.2,
        7: 0.2, 8: 0.2, 9: 0.4, 10: 0.8, 11: 1.3, 12: 1.7
    }

    for i in range(monate):
        monat = ((start_monat - 1 + i) % 12) + 1
        jahr = start_jahr + ((start_monat - 1 + i) // 12)

        # PV-Erzeugung aus PVGIS oder Schätzung
        pv_kwh = pvgis_monatswerte.get(monat, 0)
        if pv_kwh <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude if anlage.latitude else 48.0)
            pv_kwh = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85

        # PV-Faktor für saisonale Skalierung der Anzeige-Felder
        pv_faktor = pv_kwh / (sum(pvgis_monatswerte.values()) / 12) if pvgis_monatswerte else 1.0

        # Eigenverbrauch: Historische Quote nutzen, Fallback auf Komponentenmodell
        if monat in hist_ev_quoten:
            # Historische EV-Quote für diesen Kalendermonat vorhanden
            eigenverbrauch_kwh = pv_kwh * hist_ev_quoten[monat]
        elif avg_hist_ev_quote is not None:
            # Kein hist. Datum für diesen Monat → Durchschnitt der vorhandenen
            eigenverbrauch_kwh = pv_kwh * avg_hist_ev_quote
        else:
            # Gar keine historischen Daten → Komponentenmodell als Fallback
            basis_ev = pv_kwh * basis_ev_quote
            speicher_fallback = speicher_ev_erhohung_monat * pv_faktor if speicher else 0
            v2h_fallback = v2h_beitrag_monat if e_autos else 0
            wp_saison_fb = WP_SAISON_FAKTOREN.get(monat, 1.0)
            wp_verbrauch_fb = wp_strom_monat_avg * wp_saison_fb if waermepumpen else 0
            wp_pv_fb = wp_verbrauch_fb * 0.5 * (pv_faktor ** 0.5)
            eigenverbrauch_kwh = basis_ev + speicher_fallback + v2h_fallback + wp_pv_fb

        eigenverbrauch_kwh = min(eigenverbrauch_kwh, pv_kwh)  # Kann nicht mehr als erzeugt
        einspeisung_kwh = pv_kwh - eigenverbrauch_kwh

        # Komponentenbeiträge für Anzeige (informativ, beeinflusst EV nicht)
        speicher_beitrag = speicher_ev_erhohung_monat * pv_faktor if speicher else 0
        v2h_beitrag = v2h_beitrag_monat if e_autos else 0
        eauto_pv = eauto_pv_monat * pv_faktor if e_autos else 0
        wp_saison = WP_SAISON_FAKTOREN.get(monat, 1.0)
        wp_verbrauch = wp_strom_monat_avg * wp_saison if waermepumpen else 0

        # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None — Prognose-
        # Monate haben keine Negativpreis-Historie (der historische Pfad oben
        # bei den Monatsdaten nutzt get_neg_preis_einspeisung_monat).
        einspeise_erloes = einspeise_erloes_euro(
            einspeisung_kwh, None, einspeiseverguetung
        ).erloes_euro
        ev_ersparnis = eigenverbrauch_kwh * netzbezug_preis / 100
        netto_ertrag = einspeise_erloes + ev_ersparnis

        monatswerte.append(FinanzPrognoseMonatSchema(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            pv_erzeugung_kwh=round(pv_kwh, 1),
            eigenverbrauch_kwh=round(eigenverbrauch_kwh, 1),
            einspeisung_kwh=round(einspeisung_kwh, 1),
            einspeise_erloes_euro=round(einspeise_erloes, 2),
            ev_ersparnis_euro=round(ev_ersparnis, 2),
            netto_ertrag_euro=round(netto_ertrag, 2),
            speicher_beitrag_kwh=round(speicher_beitrag, 1),
            v2h_beitrag_kwh=round(v2h_beitrag, 1),
            wp_verbrauch_kwh=round(wp_verbrauch, 1),
        ))

        jahres_erzeugung += pv_kwh
        jahres_eigenverbrauch += eigenverbrauch_kwh
        jahres_einspeisung += einspeisung_kwh
        jahres_einspeise_erloes += einspeise_erloes
        jahres_ev_ersparnis += ev_ersparnis
        jahres_speicher_beitrag += speicher_beitrag
        jahres_v2h_beitrag += v2h_beitrag
        jahres_wp_verbrauch += wp_verbrauch
        jahres_eauto_pv += eauto_pv

    # =====================================================================
    # ALTERNATIVKOSTEN-EINSPARUNGEN PRO JAHR (für Prognose)
    # =====================================================================

    # Wärmepumpe: Ersparnis gegenüber Gas/Öl
    # Durchschnittswerte aus historischen Daten hochrechnen.
    # Aggregat-Werte für die Saisonalprognose: thermisch-gewichteter
    # Durchschnitt über die WPs. Bei genau einer WP = deren Wert (kein
    # Verhaltens-Unterschied). Bei mehreren WPs mit unterschiedlichen
    # Energieträgern (z. B. Gas + Öl) mathematisch saubere Mischung statt
    # last-write-wins.
    jahres_wp_ersparnis = 0.0
    if waermepumpen and gesamt_wp_thermisch > 0 and anzahl_monate_hist > 0:
        # Thermische Energie pro Jahr (hochgerechnet)
        wp_thermisch_jahr = gesamt_wp_thermisch / anzahl_monate_hist * 12
        # thermisch-gewichtete Aggregat-Werte
        wp_alter_preis_cent_agg = sum(
            a["thermisch_kwh"] * a["alter_preis_cent"] for a in wp_aggregate.values()
        ) / gesamt_wp_thermisch
        wp_alter_wirkungsgrad_agg = sum(
            a["thermisch_kwh"] * a["alter_wirkungsgrad"] for a in wp_aggregate.values()
        ) / gesamt_wp_thermisch
        # Prognose-Gaspreis: Ø der historischen Monatspreise, Fallback Aggregat
        hist_gaspreise = [
            md.gaspreis_cent_kwh for md in monatsdaten
            if md.gaspreis_cent_kwh is not None
        ]
        prognose_gaspreis = (
            sum(hist_gaspreise) / len(hist_gaspreise)
            if hist_gaspreise
            else wp_alter_preis_cent_agg
        )
        # Was es mit Gas kosten würde (Energiepreis + fixe Zusatzkosten)
        gas_kosten_jahr = (
            (wp_thermisch_jahr / wp_alter_wirkungsgrad_agg) * prognose_gaspreis / 100
            + wp_alternativ_zusatzkosten_jahr
        )
        # WP-Stromkosten pro Jahr (nur Netzanteil) — konservative 50/50-Annahme
        wp_netz_anteil = 1.0 - WP_PV_ANTEIL_DEFAULT
        wp_strom_jahr = jahres_wp_verbrauch
        wp_stromkosten_netz_jahr = wp_strom_jahr * wp_netz_anteil * wp_netzbezug_preis / 100
        # Netto-Ersparnis
        jahres_wp_ersparnis = gas_kosten_jahr - wp_stromkosten_netz_jahr

    # E-Auto: Ersparnis gegenüber Benzin.
    # Aggregat-Werte für die saisonal-skalierte Jahresprognose: km-gewichteter
    # Durchschnitt von `vergleich_l_100km` und `benzinpreis_default` über die
    # E-Autos. Bei einem einzigen E-Auto = dessen Wert (kein Verhaltens-
    # Unterschied). Bei mehreren = mathematisch saubere Mischung statt der
    # vorherigen last-write-wins-Variable.
    jahres_eauto_km_ersparnis = 0.0
    if e_autos and gesamt_km > 0 and anzahl_monate_hist > 0:
        # km pro Jahr (hochgerechnet)
        km_jahr = gesamt_km / anzahl_monate_hist * 12
        # km-gewichtete Aggregat-Werte über die E-Autos
        eauto_vergleich_l_100km_agg = sum(
            a["km"] * a["vergleich_l_100km"] for a in eauto_aggregate.values()
        ) / gesamt_km
        eauto_benzinpreis_default_agg = sum(
            a["km"] * a["benzinpreis_default"] for a in eauto_aggregate.values()
        ) / gesamt_km
        # Prognose-Benzinpreis: Ø der historischen Monatspreise, Fallback Aggregat
        hist_kraftstoffpreise = [
            md.kraftstoffpreis_euro for md in monatsdaten
            if md.kraftstoffpreis_euro is not None
        ]
        prognose_benzinpreis = (
            sum(hist_kraftstoffpreise) / len(hist_kraftstoffpreise)
            if hist_kraftstoffpreise
            else eauto_benzinpreis_default_agg
        )
        # Was es mit Benzin kosten würde
        benzin_liter_jahr = km_jahr / 100 * eauto_vergleich_l_100km_agg
        benzin_kosten_jahr = benzin_liter_jahr * prognose_benzinpreis
        # E-Auto Netz-Stromkosten pro Jahr (PV-Ladung ist in EV-Ersparnis)
        netz_anteil = gesamt_eauto_netz / (gesamt_eauto_pv + gesamt_eauto_netz) if (gesamt_eauto_pv + gesamt_eauto_netz) > 0 else 0.5
        eauto_netz_kwh_jahr = (jahres_eauto_pv / (1 - netz_anteil) * netz_anteil) if netz_anteil < 1 else 0
        eauto_stromkosten_netz_jahr = eauto_netz_kwh_jahr * netzbezug_preis / 100
        # Netto-Ersparnis
        jahres_eauto_km_ersparnis = benzin_kosten_jahr - eauto_stromkosten_netz_jahr
        # Per-E-Auto-Aufschlüsselung (für Komponenten-Anzeige).
        # Benzin-Kostenteil: pro E-Auto mit dessen `vergleich_l_100km` exakt.
        # Strom-Kostenteil: km-anteilig aus dem Aggregat (Vereinfachung — der
        # eigentliche Netz-Anteil wird auf Aggregat-Ebene aus PV-Quote
        # abgeleitet, eine saubere Pro-EA-Saisonprognose wäre ein eigener
        # Refactor). Die Summe der Pro-EA-Ersparnisse stimmt mit dem Aggregat
        # überein.
        for ea in e_autos:
            agg = eauto_aggregate[ea.id]
            if agg["km"] <= 0:
                agg["jahres_ersparnis"] = 0.0
                continue
            km_jahr_ea = agg["km"] / anzahl_monate_hist * 12
            benzin_kosten_jahr_ea = km_jahr_ea / 100 * agg["vergleich_l_100km"] * prognose_benzinpreis
            stromkosten_ea = eauto_stromkosten_netz_jahr * (agg["km"] / gesamt_km)
            agg["jahres_ersparnis"] = benzin_kosten_jahr_ea - stromkosten_ea

    # BKW Jahres-Ersparnis (aus historischem Durchschnitt hochgerechnet)
    jahres_bkw_ersparnis = 0.0
    if balkonkraftwerke and anzahl_monate_hist > 0 and bisherige_bkw_ersparnis > 0:
        jahres_bkw_ersparnis = bisherige_bkw_ersparnis / anzahl_monate_hist * 12

    # Sonstige Jahres-Netto (aus historischem Durchschnitt hochgerechnet, alle Investitionstypen)
    jahres_sonstige_netto = 0.0
    if anzahl_monate_hist > 0 and bisherige_sonstige_netto != 0:
        jahres_sonstige_netto = bisherige_sonstige_netto / anzahl_monate_hist * 12

    # Gesamter Jahres-Netto-Ertrag inkl. Alternativkosten, BKW, Sonstige und Betriebskosten
    jahres_netto_ertrag = jahres_einspeise_erloes + jahres_ev_ersparnis + jahres_wp_ersparnis + jahres_eauto_km_ersparnis + jahres_bkw_ersparnis + jahres_sonstige_netto - betriebskosten_ges

    # USt auf Eigenverbrauch bei Regelbesteuerung
    ust_eigenverbrauch = 0.0
    steuerliche_beh = getattr(anlage, 'steuerliche_behandlung', None) or 'keine_ust'
    if steuerliche_beh == "regelbesteuerung" and jahres_erzeugung > 0:
        _ust = getattr(anlage, 'ust_satz_prozent', None)
        ust_eigenverbrauch = berechne_ust_eigenverbrauch(
            eigenverbrauch_kwh=jahres_eigenverbrauch,
            investition_gesamt_euro=sum(i.anschaffungskosten_gesamt or 0 for i in alle_investitionen),
            betriebskosten_jahr_euro=betriebskosten_ges,
            pv_erzeugung_jahr_kwh=jahres_erzeugung,
            ust_satz_prozent=_ust if _ust is not None else 19.0,
        )
        jahres_netto_ertrag -= ust_eigenverbrauch

    # =====================================================================
    # KOMPONENTEN-BEITRÄGE ZUSAMMENSTELLEN
    # =====================================================================
    komponenten_beitraege = []

    # Etappe B (#264): Speicher-Spread-Service bekommt jetzt PV/Netz-Anteil.
    # Wir leiten den historischen Netz-Anteil an der Ladung ab und projizieren
    # ihn auf den prognostizierten Speicher-Beitrag. Ohne IST-Netzladung
    # (z. B. reiner PV-Speicher) bleibt das Verhalten exakt wie bisher.
    speicher_ladung_hist_total = 0.0
    speicher_netzladung_hist_total = 0.0
    if speicher:
        for sp in speicher:
            for (inv_id, jhr, mon), daten in historische_inv_daten.items():
                if inv_id != sp.id or not sp.ist_aktiv_im_monat(jhr, mon):
                    continue
                speicher_ladung_hist_total += float(daten.get("ladung_kwh") or 0)
                speicher_netzladung_hist_total += float(
                    daten.get("ladung_netz_kwh")
                    or daten.get("speicher_ladung_netz_kwh")
                    or 0
                )

    speicher_netz_anteil = (
        speicher_netzladung_hist_total / speicher_ladung_hist_total
        if speicher_ladung_hist_total > 0 else 0.0
    )
    speicher_wirkungsgrad_avg = (
        sum(
            (sp.parameter or {}).get(
                PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
                PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
            )
            for sp in speicher
        ) / len(speicher)
        if speicher else PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"]
    )
    # Ladepreis nur bei arbitragefähigen Speichern relevant — sonst ist die
    # Netzladung kostenneutrale Durchleitung (z. B. Backup-Ladung).
    arbitrage_speicher = [
        sp for sp in speicher
        if (sp.parameter or {}).get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"])
    ]
    speicher_lade_preis_cent = (
        sum(
            (sp.parameter or {}).get(
                PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"],
                PARAM_SPEICHER_DEFAULTS["lade_durchschnittspreis_cent"],
            )
            for sp in arbitrage_speicher
        ) / len(arbitrage_speicher)
        if arbitrage_speicher else None
    )

    # Etappe C (#264): stundengranularen effektiven Ladepreis aus TEP
    # vorziehen — Tibber/aWATTar-Setups bekommen den echten gewichteten
    # Mittelwert über die Lade-Stunden statt User-Param-Schätzung.
    if speicher and arbitrage_speicher:
        installs_c = [sp.anschaffungsdatum for sp in speicher if sp.anschaffungsdatum]
        if installs_c:
            try:
                eff_ladepreis_c = await berechne_effektiver_ladepreis(
                    db,
                    anlage_id=anlage_id,
                    von=min(installs_c),
                    bis=_date.today(),
                )
                # Etappe C1: Helper liefert immer ein Ergebnis. Nur belastbare
                # Quellen (dyn-tarif/boersenpreis) den Param-Mittelwert überstimmen
                # lassen — bei `datenbasis-zu-duenn` oder `keine-netzladung`
                # bleibt der Param-Wert aus Etappe B.
                if (
                    eff_ladepreis_c is not None
                    and eff_ladepreis_c.effektiver_ladepreis_cent is not None
                    and eff_ladepreis_c.quelle in ("dyn-tarif", "boersenpreis")
                ):
                    speicher_lade_preis_cent = eff_ladepreis_c.effektiver_ladepreis_cent
            except Exception as e:  # noqa: BLE001
                # Helper darf Aussichten-Antwort nie killen — bei Fehler
                # bleibt der Param-Mittelwert aus Etappe B.
                logger.warning(
                    "aussichten: effektiver-Ladepreis-Lookup fehlgeschlagen "
                    "(anlage=%s): %s", anlage_id, e,
                )
    # Aus Entladung auf Ladung zurückrechnen (η-Verluste), daraus den
    # projizierten Netz-Anteil-kWh der Prognoseperiode bestimmen.
    speicher_wirkungsgrad_frac = max(0.5, speicher_wirkungsgrad_avg / 100)
    prog_speicher_ladung = jahres_speicher_beitrag / speicher_wirkungsgrad_frac
    prog_speicher_netzladung = prog_speicher_ladung * speicher_netz_anteil

    # Speicher (Drift-Audit D: Spread-Modell statt Voll-Strompreis)
    if speicher:
        speicher_ersparnis = berechne_speicher_ersparnis(
            entladung_kwh=jahres_speicher_beitrag,
            bezug_preis_cent=netzbezug_preis,
            einspeise_verg_cent=einspeiseverguetung,
            ladung_netz_kwh=prog_speicher_netzladung,
            wirkungsgrad_prozent=speicher_wirkungsgrad_avg,
            lade_preis_cent=speicher_lade_preis_cent,
        ).ersparnis_euro
        for sp in speicher:
            komponenten_beitraege.append(KomponentenBeitragSchema(
                typ="speicher",
                bezeichnung=sp.bezeichnung,
                beitrag_kwh_jahr=round(jahres_speicher_beitrag, 0),
                beitrag_euro_jahr=round(speicher_ersparnis, 2),
                beschreibung="Eigenverbrauchserhöhung durch Zwischenspeicherung",
            ))

    # E-Auto / V2H (Drift-Audit D: Spread-Modell für V2H analog Speicher)
    if e_autos:
        v2h_ersparnis = berechne_v2h_ersparnis(
            v2h_entladung_kwh=jahres_v2h_beitrag,
            bezug_preis_cent=netzbezug_preis,
            einspeise_verg_cent=einspeiseverguetung,
        ).ersparnis_euro
        eauto_ersparnis = jahres_eauto_pv * netzbezug_preis / 100
        for ea in e_autos:
            # Prüfe ob V2H aktiv (Bug #1 v3.25.0: Form/Wizard schreiben v2h_faehig,
            # vorher las dieser Code nutzt_v2h → V2H-Anzeige im Aussichten-Tab war tot.)
            nutzt_v2h = ea.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"], False) if ea.parameter else False
            if nutzt_v2h and jahres_v2h_beitrag > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-v2h",
                    bezeichnung=f"{ea.bezeichnung} (V2H)",
                    beitrag_kwh_jahr=round(jahres_v2h_beitrag, 0),
                    beitrag_euro_jahr=round(v2h_ersparnis, 2),
                    beschreibung="Rückspeisung vom E-Auto ins Haus",
                ))
            # Benzin-Ersparnis als Komponenten-Beitrag — pro E-Auto getrennt
            ea_agg = eauto_aggregate.get(ea.id)
            ea_jahres_ersparnis = ea_agg["jahres_ersparnis"] if ea_agg else 0.0
            ea_vergleich_l_100km = ea_agg["vergleich_l_100km"] if ea_agg else PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]
            if ea_jahres_ersparnis > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-benzin",
                    bezeichnung=f"{ea.bezeichnung} (vs. Benzin)",
                    beitrag_kwh_jahr=0,  # Nicht in kWh messbar
                    beitrag_euro_jahr=round(ea_jahres_ersparnis, 2),
                    beschreibung=f"Ersparnis ggü. {ea_vergleich_l_100km}L/100km Benziner",
                ))
            if jahres_eauto_pv > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-ladung",
                    bezeichnung=f"{ea.bezeichnung} (PV-Ladung)",
                    beitrag_kwh_jahr=round(jahres_eauto_pv, 0),
                    beitrag_euro_jahr=round(eauto_ersparnis, 2),
                    beschreibung="PV-Direktladung statt Netzbezug",
                ))

    # Wärmepumpe
    if waermepumpen:
        wp_pv_kwh = jahres_wp_verbrauch * 0.5  # ~50% aus PV
        wp_pv_ersparnis = wp_pv_kwh * netzbezug_preis / 100
        alter_energietraeger = "Gas"
        for wp in waermepumpen:
            if wp.parameter:
                ae = wp.parameter.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"], PARAM_WAERMEPUMPE_DEFAULTS["alter_energietraeger"])
                alter_energietraeger = "Öl" if ae == "oel" else "Gas"
            # PV-Direktverbrauch
            komponenten_beitraege.append(KomponentenBeitragSchema(
                typ="waermepumpe-pv",
                bezeichnung=f"{wp.bezeichnung} (PV-Nutzung)",
                beitrag_kwh_jahr=round(wp_pv_kwh, 0),
                beitrag_euro_jahr=round(wp_pv_ersparnis, 2),
                beschreibung="PV-Direktverbrauch für Heizung/Warmwasser",
            ))
            # Alternativkosten-Ersparnis gegenüber Gas/Öl
            if jahres_wp_ersparnis > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="waermepumpe-ersparnis",
                    bezeichnung=f"{wp.bezeichnung} (vs. {alter_energietraeger})",
                    beitrag_kwh_jahr=0,  # Nicht direkt in kWh
                    beitrag_euro_jahr=round(jahres_wp_ersparnis, 2),
                    beschreibung=f"Ersparnis gegenüber {alter_energietraeger}heizung",
                ))

    # =====================================================================
    # ROI UND AMORTISATION
    # =====================================================================
    roi_fortschritt = (bisherige_ertraege / investition_gesamt * 100) if investition_gesamt > 0 else 0
    amortisation_erreicht = bisherige_ertraege >= investition_gesamt

    amortisation_prognose_jahr = None
    restlaufzeit_monate = None

    if not amortisation_erreicht and jahres_netto_ertrag > 0 and investition_gesamt > 0:
        rest_betrag = investition_gesamt - bisherige_ertraege
        monate_bis_amort = rest_betrag / (jahres_netto_ertrag / 12)
        restlaufzeit_monate = int(monate_bis_amort)
        amortisation_prognose_jahr = heute.year + int(monate_bis_amort / 12)

    # =====================================================================
    # RESPONSE
    # =====================================================================
    datenquellen = ["strompreise", "historische-daten"]
    if pvgis:
        datenquellen.insert(0, "pvgis-prognose")
    else:
        datenquellen.insert(0, "pvgis-tmy")

    # Drift-Audit D: Spread-Modell für Speicher + V2H (Bezug − Einspeise).
    # Etappe B (#264): mit PV/Netz-Anteil aus der historischen Aufteilung
    # (siehe Speicher-Netz-Anteil-Block oben — gleiche Args).
    speicher_ersparnis_euro = berechne_speicher_ersparnis(
        entladung_kwh=jahres_speicher_beitrag,
        bezug_preis_cent=netzbezug_preis,
        einspeise_verg_cent=einspeiseverguetung,
        ladung_netz_kwh=prog_speicher_netzladung,
        wirkungsgrad_prozent=speicher_wirkungsgrad_avg,
        lade_preis_cent=speicher_lade_preis_cent,
    ).ersparnis_euro
    v2h_ersparnis_euro = berechne_v2h_ersparnis(
        v2h_entladung_kwh=jahres_v2h_beitrag,
        bezug_preis_cent=netzbezug_preis,
        einspeise_verg_cent=einspeiseverguetung,
    ).ersparnis_euro
    eauto_ersparnis_euro = jahres_eauto_pv * netzbezug_preis / 100
    wp_pv_kwh_total = jahres_wp_verbrauch * WP_PV_ANTEIL_DEFAULT
    wp_pv_ersparnis_euro = wp_pv_kwh_total * netzbezug_preis / 100

    return FinanzPrognoseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        prognose_zeitraum={
            "von": f"{start_jahr}-{start_monat:02d}",
            "bis": f"{monatswerte[-1].jahr}-{monatswerte[-1].monat:02d}" if monatswerte else None,
        },
        einspeiseverguetung_cent_kwh=einspeiseverguetung,
        netzbezug_preis_cent_kwh=netzbezug_preis,
        grundpreis_euro_monat=allgemein_tarif.grundpreis_euro_monat or 0 if allgemein_tarif else 0,
        jahres_erzeugung_kwh=round(jahres_erzeugung, 0),
        jahres_eigenverbrauch_kwh=round(jahres_eigenverbrauch, 0),
        jahres_einspeisung_kwh=round(jahres_einspeisung, 0),
        eigenverbrauchsquote_prozent=round(jahres_eigenverbrauch / jahres_erzeugung * 100 if jahres_erzeugung > 0 else 0, 1),
        jahres_einspeise_erloes_euro=round(jahres_einspeise_erloes, 2),
        jahres_ev_ersparnis_euro=round(jahres_ev_ersparnis, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2) if ust_eigenverbrauch > 0 else None,
        jahres_netto_ertrag_euro=round(jahres_netto_ertrag, 2),
        komponenten_beitraege=komponenten_beitraege,
        speicher_ev_erhoehung_kwh=round(jahres_speicher_beitrag, 0),
        speicher_ev_erhoehung_euro=round(speicher_ersparnis_euro, 2),
        v2h_rueckspeisung_kwh=round(jahres_v2h_beitrag, 0),
        v2h_ersparnis_euro=round(v2h_ersparnis_euro, 2),
        eauto_ladung_pv_kwh=round(jahres_eauto_pv, 0),
        eauto_ersparnis_euro=round(eauto_ersparnis_euro, 2),
        wp_stromverbrauch_kwh=round(jahres_wp_verbrauch, 0),
        wp_pv_anteil_kwh=round(wp_pv_kwh_total, 0),
        wp_pv_ersparnis_euro=round(wp_pv_ersparnis_euro, 2),
        wp_alternativ_ersparnis_euro=round(jahres_wp_ersparnis, 2),
        eauto_alternativ_ersparnis_euro=round(jahres_eauto_km_ersparnis, 2),
        investition_pv_system_euro=round(investition_pv_system, 2),
        investition_wp_mehrkosten_euro=round(investition_wp_mehrkosten, 2),
        investition_eauto_mehrkosten_euro=round(investition_eauto_mehrkosten, 2),
        investition_sonstige_euro=round(investition_sonstige, 2),
        investition_gesamt_euro=round(investition_gesamt, 2),  # PV + Mehrkosten + Sonstige
        bisherige_ertraege_euro=round(bisherige_ertraege, 2),
        amortisations_fortschritt_prozent=round(roi_fortschritt, 1),
        amortisation_erreicht=amortisation_erreicht,
        amortisation_prognose_jahr=amortisation_prognose_jahr,
        restlaufzeit_bis_amortisation_monate=restlaufzeit_monate,
        monatswerte=monatswerte,
        datenquellen=datenquellen,
    )

