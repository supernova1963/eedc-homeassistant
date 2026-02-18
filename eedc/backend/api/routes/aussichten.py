"""
Aussichten API Routes

Prognosen und Vorhersagen für PV-Erträge:
- Kurzfristig (7-16 Tage): Basierend auf Wettervorhersagen
- Langfristig (Monate): Basierend auf PVGIS TMY und Trends
- Trend-Analyse: Historische Entwicklung
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.strompreis import Strompreis
from backend.models.monatsdaten import Monatsdaten
from backend.services.wetter_service import (
    fetch_open_meteo_forecast,
    wetter_code_zu_symbol,
    get_pvgis_tmy_defaults,
)


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

    # Jahresprognose
    jahres_erzeugung_kwh: float
    jahres_eigenverbrauch_kwh: float
    jahres_einspeisung_kwh: float
    eigenverbrauchsquote_prozent: float

    # Finanzen
    jahres_einspeise_erloes_euro: float
    jahres_ev_ersparnis_euro: float
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

DEFAULT_SYSTEM_LOSSES = 0.14  # 14% Systemverluste
TEMP_COEFFICIENT = 0.004  # Leistungsabnahme pro °C über 25°C

MONATSNAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]


# =============================================================================
# Helper Functions
# =============================================================================

def berechne_pv_ertrag_tag(
    globalstrahlung_kwh_m2: Optional[float],
    anlagenleistung_kwp: float,
    temperatur_max_c: Optional[float] = None,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
) -> float:
    """Berechnet erwarteten PV-Ertrag für einen Tag."""
    if globalstrahlung_kwh_m2 is None or globalstrahlung_kwh_m2 <= 0:
        return 0.0

    ertrag = globalstrahlung_kwh_m2 * anlagenleistung_kwp * (1 - system_losses)

    if temperatur_max_c is not None and temperatur_max_c > 25:
        temp_verlust = (temperatur_max_c - 25) * TEMP_COEFFICIENT
        ertrag *= (1 - temp_verlust)

    return round(max(0, ertrag), 2)


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
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=400,
            detail="Anlage hat keine Koordinaten. Bitte Standort in Einstellungen konfigurieren."
        )

    # Anlagenleistung aus PV-Modulen
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            Investition.aktiv == True
        )
    )
    pv_module = result.scalars().all()

    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module)

    # Balkonkraftwerke hinzufügen
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "balkonkraftwerk",
            Investition.aktiv == True
        )
    )
    balkonkraftwerke = result.scalars().all()
    bkw_leistung_kwp = sum(b.leistung_kwp or 0 for b in balkonkraftwerke)
    anlagenleistung_kwp += bkw_leistung_kwp

    if anlagenleistung_kwp <= 0:
        anlagenleistung_kwp = anlage.leistung_kwp or 0

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
    system_losses = pvgis.system_losses / 100 if pvgis and pvgis.system_losses else DEFAULT_SYSTEM_LOSSES

    # Wettervorhersage abrufen
    wetter = await fetch_open_meteo_forecast(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        days=tage
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
            wetter_symbol=wetter_code_zu_symbol(tag["wetter_code"]),
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

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten")

    # Anlagenleistung aus PV-Modulen
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            Investition.aktiv == True
        )
    )
    pv_module = result.scalars().all()
    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module)

    # Balkonkraftwerke hinzufügen
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "balkonkraftwerk",
            Investition.aktiv == True
        )
    )
    balkonkraftwerke = result.scalars().all()
    bkw_leistung_kwp = sum(b.leistung_kwp or 0 for b in balkonkraftwerke)
    anlagenleistung_kwp += bkw_leistung_kwp

    if anlagenleistung_kwp <= 0:
        anlagenleistung_kwp = anlage.leistung_kwp or 0

    if anlagenleistung_kwp <= 0:
        raise HTTPException(status_code=400, detail="Keine PV-Leistung konfiguriert")

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

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # PV-Module
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            Investition.aktiv == True
        )
    )
    pv_module = result.scalars().all()
    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module)

    # Balkonkraftwerke
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "balkonkraftwerk",
            Investition.aktiv == True
        )
    )
    balkonkraftwerke = result.scalars().all()
    bkw_leistung_kwp = sum(b.leistung_kwp or 0 for b in balkonkraftwerke)
    anlagenleistung_kwp += bkw_leistung_kwp

    if anlagenleistung_kwp <= 0:
        anlagenleistung_kwp = anlage.leistung_kwp or 0

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
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten")

    # Wettervorhersage
    wetter = await fetch_open_meteo_forecast(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        days=tage
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
            wetter_symbol=wetter_code_zu_symbol(tag["wetter_code"]),
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
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Aktuellen Strompreis laden
    result = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage_id)
        .where(Strompreis.gueltig_bis == None)
        .order_by(Strompreis.gueltig_ab.desc())
    )
    strompreis = result.scalar_one_or_none()

    einspeiseverguetung = strompreis.einspeiseverguetung_cent_kwh if strompreis else 8.2
    netzbezug_preis = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0

    # =====================================================================
    # ALLE INVESTITIONEN LADEN
    # =====================================================================
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.aktiv == True
        )
    )
    alle_investitionen = result.scalars().all()

    # Nach Typ gruppieren
    pv_module = [i for i in alle_investitionen if i.typ == "pv-module"]
    speicher = [i for i in alle_investitionen if i.typ == "speicher"]
    e_autos = [i for i in alle_investitionen if i.typ == "e-auto"]
    waermepumpen = [i for i in alle_investitionen if i.typ == "waermepumpe"]
    balkonkraftwerke = [i for i in alle_investitionen if i.typ == "balkonkraftwerk"]

    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module) or anlage.leistung_kwp or 0

    # =====================================================================
    # HISTORISCHE DATEN LADEN
    # =====================================================================
    inv_ids = [i.id for i in alle_investitionen]
    historische_inv_daten = {}

    if inv_ids:
        result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(inv_ids)
            )
        )
        for imd in result.scalars().all():
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

    for md in monatsdaten:
        if md.eigenverbrauch_kwh and md.eigenverbrauch_kwh > 0:
            gesamt_ev += md.eigenverbrauch_kwh

    # PV-Erzeugung aus InvestitionMonatsdaten
    for pv in pv_module:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == pv.id:
                gesamt_pv += daten.get("pv_erzeugung_kwh", 0)

    # BKW-Erzeugung
    for bkw in balkonkraftwerke:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == bkw.id:
                gesamt_pv += daten.get("pv_erzeugung_kwh", 0)

    # Speicher-Daten
    for sp in speicher:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == sp.id:
                gesamt_speicher_entladung += daten.get("entladung_kwh", 0)
                gesamt_speicher_ladung += daten.get("ladung_kwh", 0)

    # E-Auto-Daten
    for ea in e_autos:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == ea.id:
                gesamt_v2h += daten.get("v2h_entladung_kwh", 0)
                gesamt_eauto_pv += daten.get("ladung_pv_kwh", 0)

    # Wärmepumpe-Daten
    for wp in waermepumpen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id:
                gesamt_wp_strom += daten.get("stromverbrauch_kwh", 0)

    # =====================================================================
    # QUOTEN BERECHNEN (aus historischen Daten oder Defaults)
    # =====================================================================

    # Basis-EV-Quote (ohne Speicher-Effekt)
    basis_ev_quote = 0.30  # Default
    if gesamt_pv > 0 and gesamt_ev > 0:
        # Speicher-Beitrag abziehen für Basis-Quote
        ev_ohne_speicher = max(0, gesamt_ev - gesamt_speicher_entladung - gesamt_v2h)
        basis_ev_quote = ev_ohne_speicher / gesamt_pv if gesamt_pv > 0 else 0.30
        basis_ev_quote = min(0.70, max(0.15, basis_ev_quote))  # Begrenzen auf realistische Werte

    # Speicher-Effizienz (Entladung/Ladung)
    speicher_effizienz = 0.90  # Default 90%
    if gesamt_speicher_ladung > 0:
        speicher_effizienz = min(0.95, gesamt_speicher_entladung / gesamt_speicher_ladung)

    # Speicher-EV-Erhöhung pro Monat (durchschnittlich)
    anzahl_monate_hist = len(monatsdaten) if monatsdaten else 1
    speicher_ev_erhohung_monat = gesamt_speicher_entladung / anzahl_monate_hist if speicher else 0

    # V2H-Beitrag pro Monat
    v2h_beitrag_monat = gesamt_v2h / anzahl_monate_hist if e_autos else 0

    # E-Auto PV-Ladung pro Monat
    eauto_pv_monat = gesamt_eauto_pv / anzahl_monate_hist if e_autos else 0

    # WP-Stromverbrauch pro Monat (saisonal gewichtet später)
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
                alternativ_kosten = inv.parameter.get("alternativ_kosten_euro", 8000.0)
            investition_wp_mehrkosten += max(0, kosten - alternativ_kosten)
        elif inv.typ == "e-auto":
            # Mehrkosten E-Auto vs. Verbrenner
            # Kann über Parameter konfiguriert werden
            alternativ_kosten = 35000.0  # Default: vergleichbarer Verbrenner
            if inv.parameter:
                alternativ_kosten = inv.parameter.get("alternativ_kosten_euro", 35000.0)
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

    # Wärmepumpe: Alter Energieträger (Gas/Öl) Preis
    wp_alter_preis_cent = 10.0  # Default: 10 ct/kWh Gas
    wp_alter_wirkungsgrad = 0.90  # Gasheizung ~90% Wirkungsgrad
    for wp in waermepumpen:
        if wp.parameter:
            wp_alter_preis_cent = wp.parameter.get("alter_preis_cent_kwh", 10.0)
            if wp.parameter.get("alter_energietraeger") == "oel":
                wp_alter_wirkungsgrad = 0.85  # Öl etwas schlechter

    # E-Auto: Benzin-Vergleich
    eauto_benzinpreis = 1.65  # €/L Default
    eauto_vergleich_l_100km = 7.5  # L/100km Default
    for ea in e_autos:
        if ea.parameter:
            eauto_benzinpreis = ea.parameter.get("benzinpreis_euro", 1.65)
            eauto_vergleich_l_100km = ea.parameter.get("vergleich_verbrauch_l_100km", 7.5)

    # =====================================================================
    # BISHERIGE ERTRÄGE BERECHNEN (inkl. Alternativkosten!)
    # =====================================================================
    bisherige_ertraege = 0.0
    bisherige_wp_ersparnis = 0.0
    bisherige_eauto_ersparnis = 0.0

    for md in monatsdaten:
        # Einspeise-Erlös
        if md.einspeisung_kwh:
            bisherige_ertraege += md.einspeisung_kwh * einspeiseverguetung / 100
        # EV-Ersparnis (beinhaltet bereits Speicher + V2H)
        if md.eigenverbrauch_kwh:
            bisherige_ertraege += md.eigenverbrauch_kwh * netzbezug_preis / 100

    # Wärmepumpe Alternativkosten-Ersparnis
    # Ersparnis = Gas-Kosten (was es kosten würde) - WP-Stromkosten
    gesamt_wp_thermisch = 0.0
    for wp in waermepumpen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id:
                heiz = daten.get("heizenergie_kwh", 0)
                ww = daten.get("warmwasser_kwh", 0)
                strom = daten.get("stromverbrauch_kwh", 0)
                thermisch = heiz + ww
                gesamt_wp_thermisch += thermisch
                # Gas-Alternative: thermisch / Wirkungsgrad * Preis
                gas_kosten = (thermisch / wp_alter_wirkungsgrad) * wp_alter_preis_cent / 100
                # WP-Stromkosten (nur Netzanteil, PV-Anteil ist bereits in EV-Ersparnis)
                # Annahme: ca. 50% aus PV (konservativ)
                wp_netz_anteil = 0.5
                wp_stromkosten_netz = strom * wp_netz_anteil * netzbezug_preis / 100
                # Netto-Ersparnis (Gas-Alternative minus WP-Netzstrom)
                bisherige_wp_ersparnis += gas_kosten - wp_stromkosten_netz

    # E-Auto Alternativkosten-Ersparnis
    # Ersparnis = Benzin-Kosten - Netzstrom-Kosten
    gesamt_km = 0.0
    gesamt_eauto_netz = 0.0
    for ea in e_autos:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == ea.id:
                km = daten.get("km_gefahren", 0)
                netz = daten.get("ladung_netz_kwh", 0)
                gesamt_km += km
                gesamt_eauto_netz += netz

    if gesamt_km > 0:
        # Benzin-Kosten für dieselbe Strecke
        benzin_liter = gesamt_km / 100 * eauto_vergleich_l_100km
        benzin_kosten = benzin_liter * eauto_benzinpreis
        # Netzstrom-Kosten für E-Auto
        eauto_netzstrom_kosten = gesamt_eauto_netz * netzbezug_preis / 100
        # Ersparnis = was Benzin gekostet hätte - was Netzstrom kostet
        bisherige_eauto_ersparnis = benzin_kosten - eauto_netzstrom_kosten

    # Alternativkosten zu bisherigen Erträgen addieren
    bisherige_ertraege += bisherige_wp_ersparnis + bisherige_eauto_ersparnis

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

        # Basis-Eigenverbrauch
        basis_ev = pv_kwh * basis_ev_quote

        # Speicher-Beitrag (verhältnismäßig zur PV-Erzeugung im Monat)
        # Speicher erhöht EV besonders in ertragreichen Monaten
        pv_faktor = pv_kwh / (sum(pvgis_monatswerte.values()) / 12) if pvgis_monatswerte else 1.0
        speicher_beitrag = speicher_ev_erhohung_monat * pv_faktor if speicher else 0

        # V2H-Beitrag (eher konstant über Jahr)
        v2h_beitrag = v2h_beitrag_monat if e_autos else 0

        # E-Auto PV-Ladung (verhältnismäßig zur PV-Erzeugung)
        eauto_pv = eauto_pv_monat * pv_faktor if e_autos else 0

        # WP-Verbrauch (saisonal)
        wp_saison = WP_SAISON_FAKTOREN.get(monat, 1.0)
        wp_verbrauch = wp_strom_monat_avg * wp_saison if waermepumpen else 0

        # WP erhöht Eigenverbrauch (PV-Direktverbrauch)
        # Annahme: 40-60% des WP-Stroms kann aus PV kommen (abhängig von Tageszeit)
        wp_pv_anteil = wp_verbrauch * 0.5 * (pv_faktor ** 0.5)  # Mehr im Sommer

        # Gesamt-Eigenverbrauch
        eigenverbrauch_kwh = basis_ev + speicher_beitrag + v2h_beitrag + wp_pv_anteil
        eigenverbrauch_kwh = min(eigenverbrauch_kwh, pv_kwh)  # Kann nicht mehr als erzeugt

        einspeisung_kwh = pv_kwh - eigenverbrauch_kwh

        einspeise_erloes = einspeisung_kwh * einspeiseverguetung / 100
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
    # Durchschnittswerte aus historischen Daten hochrechnen
    jahres_wp_ersparnis = 0.0
    if waermepumpen and gesamt_wp_thermisch > 0 and anzahl_monate_hist > 0:
        # Thermische Energie pro Jahr (hochgerechnet)
        wp_thermisch_jahr = gesamt_wp_thermisch / anzahl_monate_hist * 12
        # Was es mit Gas kosten würde
        gas_kosten_jahr = (wp_thermisch_jahr / wp_alter_wirkungsgrad) * wp_alter_preis_cent / 100
        # WP-Stromkosten pro Jahr (nur Netzanteil, ca. 50%)
        wp_netz_anteil = 0.5
        wp_strom_jahr = jahres_wp_verbrauch
        wp_stromkosten_netz_jahr = wp_strom_jahr * wp_netz_anteil * netzbezug_preis / 100
        # Netto-Ersparnis
        jahres_wp_ersparnis = gas_kosten_jahr - wp_stromkosten_netz_jahr

    # E-Auto: Ersparnis gegenüber Benzin
    jahres_eauto_km_ersparnis = 0.0
    if e_autos and gesamt_km > 0 and anzahl_monate_hist > 0:
        # km pro Jahr (hochgerechnet)
        km_jahr = gesamt_km / anzahl_monate_hist * 12
        # Was es mit Benzin kosten würde
        benzin_liter_jahr = km_jahr / 100 * eauto_vergleich_l_100km
        benzin_kosten_jahr = benzin_liter_jahr * eauto_benzinpreis
        # E-Auto Netz-Stromkosten pro Jahr (PV-Ladung ist in EV-Ersparnis)
        netz_anteil = gesamt_eauto_netz / (gesamt_eauto_pv + gesamt_eauto_netz) if (gesamt_eauto_pv + gesamt_eauto_netz) > 0 else 0.5
        eauto_netz_kwh_jahr = (jahres_eauto_pv / (1 - netz_anteil) * netz_anteil) if netz_anteil < 1 else 0
        eauto_stromkosten_netz_jahr = eauto_netz_kwh_jahr * netzbezug_preis / 100
        # Netto-Ersparnis
        jahres_eauto_km_ersparnis = benzin_kosten_jahr - eauto_stromkosten_netz_jahr

    # Gesamter Jahres-Netto-Ertrag inkl. Alternativkosten
    jahres_netto_ertrag = jahres_einspeise_erloes + jahres_ev_ersparnis + jahres_wp_ersparnis + jahres_eauto_km_ersparnis

    # =====================================================================
    # KOMPONENTEN-BEITRÄGE ZUSAMMENSTELLEN
    # =====================================================================
    komponenten_beitraege = []

    # Speicher
    if speicher:
        speicher_ersparnis = jahres_speicher_beitrag * netzbezug_preis / 100
        for sp in speicher:
            komponenten_beitraege.append(KomponentenBeitragSchema(
                typ="speicher",
                bezeichnung=sp.bezeichnung,
                beitrag_kwh_jahr=round(jahres_speicher_beitrag, 0),
                beitrag_euro_jahr=round(speicher_ersparnis, 2),
                beschreibung="Eigenverbrauchserhöhung durch Zwischenspeicherung",
            ))

    # E-Auto / V2H
    if e_autos:
        v2h_ersparnis = jahres_v2h_beitrag * netzbezug_preis / 100
        eauto_ersparnis = jahres_eauto_pv * netzbezug_preis / 100
        for ea in e_autos:
            # Prüfe ob V2H aktiv
            nutzt_v2h = ea.parameter.get("nutzt_v2h", False) if ea.parameter else False
            if nutzt_v2h and jahres_v2h_beitrag > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-v2h",
                    bezeichnung=f"{ea.bezeichnung} (V2H)",
                    beitrag_kwh_jahr=round(jahres_v2h_beitrag, 0),
                    beitrag_euro_jahr=round(v2h_ersparnis, 2),
                    beschreibung="Rückspeisung vom E-Auto ins Haus",
                ))
            # Benzin-Ersparnis als Komponenten-Beitrag
            if jahres_eauto_km_ersparnis > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-benzin",
                    bezeichnung=f"{ea.bezeichnung} (vs. Benzin)",
                    beitrag_kwh_jahr=0,  # Nicht in kWh messbar
                    beitrag_euro_jahr=round(jahres_eauto_km_ersparnis, 2),
                    beschreibung=f"Ersparnis ggü. {eauto_vergleich_l_100km}L/100km Benziner",
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
                ae = wp.parameter.get("alter_energietraeger", "gas")
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

    speicher_ersparnis_euro = jahres_speicher_beitrag * netzbezug_preis / 100
    v2h_ersparnis_euro = jahres_v2h_beitrag * netzbezug_preis / 100
    eauto_ersparnis_euro = jahres_eauto_pv * netzbezug_preis / 100
    wp_pv_kwh_total = jahres_wp_verbrauch * 0.5
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
        jahres_erzeugung_kwh=round(jahres_erzeugung, 0),
        jahres_eigenverbrauch_kwh=round(jahres_eigenverbrauch, 0),
        jahres_einspeisung_kwh=round(jahres_einspeisung, 0),
        eigenverbrauchsquote_prozent=round(jahres_eigenverbrauch / jahres_erzeugung * 100 if jahres_erzeugung > 0 else 0, 1),
        jahres_einspeise_erloes_euro=round(jahres_einspeise_erloes, 2),
        jahres_ev_ersparnis_euro=round(jahres_ev_ersparnis, 2),
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
