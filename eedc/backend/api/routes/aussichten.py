"""
Aussichten API Routes

Prognosen und Vorhersagen für PV-Erträge:
- Kurzfristig (7-16 Tage): Basierend auf Wettervorhersagen
- Langfristig (Monate): Basierend auf PVGIS TMY und Trends
- Trend-Analyse: Historische Entwicklung
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import (
    ERTRAGSFELD_TYPEN,
    Investition,
    InvestitionMonatsdaten,
)
from backend.utils.investition_filter import aktiv_jetzt, aktiv_im_zeitraum
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.models.strompreis import Strompreis
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    annahme_dauer_text,
    berechne_amortisations_fortschritt,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    kapitaleinsatz_euro,
    relevante_kosten_aus_investitionen,
    alter_wirkungsgrad,
    ersetzt_keine_heizung,
    berechne_wp_alternativkosten_ersparnis,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    gas_kosten_altanlage,
    spezifischer_ertrag_kwh_kwp,
    verteile_nach_gewichten,
)
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.core.berechnungen.phev_anteil import teile_fahrleistung
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.field_definitions import get_emob_pv_netz_kwh, get_wp_strom_kwh
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    build_emob_pool_ctx,
    eigener_verbrauch_l_100km,
    emob_month_share,
)
from backend.services.emob_ladeanteil import reichere_monatszeilen_an
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_PV_ANTEIL_DEFAULT,
)
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
)
from backend.services.speicher_wirtschaftlichkeit import (
    berechne_effektiver_ladepreis,
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
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.utils import wetter_symbol_aus_tag
from backend.services.wetter.pvgis import get_pvgis_tmy_defaults
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp
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


class ErtragJeInvestitionSchema(BaseModel):
    """Der kumulierte, GEMESSENE Netto-Ertrag einer ROI-Zeile (Bauschritt 5).

    ``investition_id`` ist die **Zeilen**-ID der ROI-Sicht: beim PV-System der
    Wechselrichter, sonst die Investition selbst. Der Betrag darf negativ sein
    — eine Komponente, deren Betriebskosten ihre Erträge übersteigen, soll das
    sagen dürfen, statt auf 0 geschönt zu werden.
    """

    investition_id: int
    bisherige_ertraege_euro: float


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
    # F-19: der tatsächliche Nenner des Amortisations-Fortschritts — relevante
    # Kosten plus die kumulierten sonstigen AUSGABEN. Er steht in der Response,
    # damit die Zahl nachvollziehbar bleibt UND der Symmetrie-Wächter sie
    # direkt vergleichen kann, statt sie aus Prozentwerten zurückzurechnen.
    kapitaleinsatz_euro: float = 0.0
    bisherige_ertraege_euro: float  # Kumulierte Erträge seit Inbetriebnahme
    amortisations_fortschritt_prozent: float  # Wie viel % bereits amortisiert (kumuliert)
    amortisation_erreicht: bool
    amortisation_prognose_jahr: Optional[int]  # Geschätztes Jahr der Amortisation
    restlaufzeit_bis_amortisation_monate: Optional[int]
    #: Konzept §5/§8-6 — die Annahme hinter **diesen beiden** Feldern.
    #: ⚠ Der Fortschritt selbst (`amortisations_fortschritt_prozent`) ist eine
    #: Messung und unterstellt nichts (§4). Restlaufzeit und Prognosejahr sind
    #: es nicht: sie rechnen den offenen Rest mit `jahres_netto_ertrag_euro`
    #: hoch und sind damit **Dauer-Aussagen** — also fällt genau dieses Paar
    #: unter §5 und trägt denselben Satz wie das ROI-Dashboard.
    amortisation_annahme: Optional[str] = None
    # Bauschritt 5 (§8): derselbe Zähler, auf die ROI-Zeilen zerlegt. Der
    # NENNER kommt je Zeile aus dem ROI-Dashboard (`kapitaleinsatz`) — genau
    # wie bei der anlagenweiten Kachel, die schon heute ihren Zähler von hier
    # und ihren Nenner von dort bezieht.
    ertraege_je_investition: List[ErtragJeInvestitionSchema] = []
    #: Was zu keiner Zeile gehören KANN — anlagenweite Monatspositionen (sie
    #: haben keine Investition, §8/4) und die dienstlichen Ladekosten. Steht
    #: ausdrücklich in der Response: ein wachsender Rest ist ein Befund, kein
    #: Rundungsfehler.
    ertraege_nicht_zurechenbar_euro: float = 0.0

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

    # N36/P3: kWp über den SoT-Dispatcher (Spalte → `parameter.kwp`), nicht über
    # die Spalte allein. Ein Modul mit kWp nur im `parameter`-JSON zählte sonst
    # als 0 — die Aussichten rechneten mit einer Teilsumme, und der
    # `or anlage.leistung_kwp`-Fallback darunter greift nur bei Summe 0, nicht
    # bei gemischter Pflege.
    # A24-2: `get_erzeuger_kwp` statt `get_pv_kwp` — Letzterer kennt den
    # BKW-Zweig `leistung_wp × anzahl` nicht, ein so gepflegtes
    # Balkonkraftwerk fiel hier still auf 0 (Befund §4.1, Variante 7).
    # N-266: `erzeuger_traeger` lässt ein Balkonkraftwerk mit Modul-Kindern
    # heraus — es hat seine kWp abgetreten, und die Aussichten multiplizieren
    # diese Summe mit dem SOLL-Ertrag. Doppelt gezählt wäre die ganze
    # Jahresprognose doppelt.
    anlagenleistung_kwp = sum(
        get_erzeuger_kwp(i) for i in erzeuger_traeger([*pv_module, *balkonkraftwerke])
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

    # Systemverluste aus der aktiven PVGIS-Prognose (Auswahl-SoT, P5)
    pvgis = await lade_aktive_prognose(db, anlage_id)
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

    # Aktive PVGIS-Prognose (Auswahl-SoT, P5)
    pvgis = await lade_aktive_prognose(db, anlage_id)

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
        # Historisches IST aus den Monats-Fakten (ADR-002/**P10**). Bis
        # 2026-07-31 summierte diese Stelle roh
        # `verbrauch_daten["pv_erzeugung_kwh"]` über die PV-/BKW-IMD-Zeilen —
        # dieselbe Klasse wie F-5, hier nachträglich erhoben (Register N-1).
        # Ohne Pro-Modul-IMD blieb `monatliche_erzeugung` leer, `gesamt_pr`
        # fiel auf den Default **1,0** zurück, und die Langfrist-Prognose
        # rechnete damit ungebremst mit dem PVGIS-SOLL statt mit der
        # gemessenen Anlagen-Güte.
        fakten = await lade_monats_fakten(db, anlage_id)

        # {(jahr, monat): kwh} — `pv_kwh` ist Module **und** BKW, deckungsgleich
        # mit dem früheren `alle_pv_ids`-Filter.
        monatliche_erzeugung = {
            f.schluessel: f.erzeugung.pv_kwh
            for f in fakten
            if f.erzeugung.pv_kwh > 0
        }

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

    # Aktive PVGIS-Prognose (Auswahl-SoT, P5)
    pvgis = await lade_aktive_prognose(db, anlage_id)
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
        # Historisches IST aus den Monats-Fakten (ADR-002/**P10**) — dieselbe
        # Begründung wie in der Langfrist-Prognose oben (Register N-1): die
        # rohe IMD-Summe verlor die PV komplett, sobald die Erzeugung nur als
        # Anlagen-Aggregat gepflegt war, und der Degradations-/Jahresvergleich
        # zeigte dann leere Jahre statt der gemessenen Erträge.
        fakten = await lade_monats_fakten(db, anlage_id)

        for fakt in fakten:
            jahr = fakt.jahr
            monat = fakt.monat
            kwh = fakt.erzeugung.pv_kwh

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

        spez_ertrag = spezifischer_ertrag_kwh_kwp(gesamt_kwh, anlagenleistung_kwp) or 0
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

    # #392: bewusst der HEUTIGE Stammwert — diese Variable speist die
    # Hochrechnung nach vorn, und künftige Monate haben keinen Monatswert.
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
    # N36/P3: kWp über den SoT-Dispatcher — wie in `_lade_anlage_mit_pv`.
    # N-266: Selektor NACH dem `ist_aktiv_an`-Filter darüber — vor der
    # Anschaffung der Module trägt das BKW seine kWp noch selbst.
    anlagenleistung_kwp = sum(
        get_erzeuger_kwp(i)
        for i in erzeuger_traeger([*aktuelle_pv_module, *aktuelle_bkw])
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

    # F-16: der abgeleitete PV-Anteil der Heimladung gilt auch hier. Diese Route
    # liest die IMD direkt (P10-Restschuld) und speist daraus BEIDE Achsen — die
    # historische Ersparnis (`gesamt_eauto_pv`/`agg["netz_kwh"]`) und über
    # `netz_anteil` auch die **Prognose** (N-188). Ohne die Anreicherung stünde
    # der abgeleitete Anteil im Cockpit und 0 % in den Aussichten, und die
    # Prognose schriebe die ungeteilte Historie fort. Angereichert wird an genau
    # DIESER Stelle, weil sechs Lesestellen weiter unten aus derselben Map
    # schöpfen — eine je Lesestelle wäre die Kopie, die N-181 beschreibt.
    _emob_keys = [
        key
        for key in historische_inv_daten
        if (_inv := inv_by_id_hist.get(key[0])) is not None
        and _inv.typ in ("e-auto", "wallbox")
        and not ist_dienstlich(_inv)
    ]
    if _emob_keys:
        _emob_daten = await reichere_monatszeilen_an(
            db,
            anlage_id,
            [
                (
                    (jahr, monat),
                    inv_by_id_hist[inv_id].typ == "wallbox",
                    historische_inv_daten[(inv_id, jahr, monat)],
                )
                for (inv_id, jahr, monat) in _emob_keys
            ],
        )
        for key, daten in zip(_emob_keys, _emob_daten):
            historische_inv_daten[key] = daten

    # F-17: Wallbox-Pool-Attribution — die Lücke, die diese Route als EINZIGE
    # der fünf E-Mob-Sichten hatte. Bei einem evcc-Setup liegt die Heimladung
    # auf der *Wallbox*; die Schleifen unten filtern aber auf `inv_id == ea.id`
    # und sahen deshalb null Ladung. Folge auf beiden Achsen: die historische
    # Ersparnis zog **gar keine** Netz-Stromkosten ab, und `netz_anteil` fiel
    # in der Prognose auf den 0,5-Default, weil PV und Netz beide 0 waren.
    # An Gernots Anlage (Mär–Jul 2026, ausschließlich Sensordaten gemessen):
    # 0 statt 126,23 kWh Netz und 0 statt 619,77 kWh PV.
    emob_pool_ctx = build_emob_pool_ctx(
        historische_inv_daten,
        {i.id for i in inv_by_id_hist.values() if i.typ == "e-auto" and not ist_dienstlich(i)},
        {i.id for i in inv_by_id_hist.values() if i.typ == "wallbox" and not ist_dienstlich(i)},
    )

    # Monatsdaten für Eigenverbrauch etc.
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    monatsdaten = result.scalars().all()
    monatsdaten_dict = {(md.jahr, md.monat): md for md in monatsdaten}

    # =====================================================================
    # HISTORISCHE WERTE AGGREGIEREN — aus den Monats-Fakten (ADR-002/P10)
    # =====================================================================
    # Bis 2026-07-31 faltete dieser Block die IMD-Zeilen selbst zu Monatswerten,
    # und dabei fiel die PV-Auflösung aus P7 weg: die rohe Summe über
    # `verbrauch_daten["pv_erzeugung_kwh"]` liefert 0, wenn die Erzeugung nur
    # als Anlagen-Aggregat (`Monatsdaten.pv_erzeugung_kwh`) gepflegt ist — der
    # Normalfall bei manueller Pflege und beim Import mit einem Gesamt-PV-Sensor.
    # Folge (Befund F-5 der Drift-Inventur): 32,00 € statt 212,00 € Netto-Ertrag,
    # und damit ein um 85 % zu niedriger ROI-Fortschritt.
    # `lade_monats_fakten` löst genau einmal auf — inklusive Zeitfilter (#236),
    # Dienstwagen-Filter und Monatstarif ([[feedback_aggregations_drift]]).
    fakten = await lade_monats_fakten(db, anlage_id)

    gesamt_eauto_pv = 0.0
    gesamt_wp_strom = 0.0

    # `pv_kwh` = Module + BKW (P9: der daraus abgeleitete Eigenverbrauch enthält
    # den BKW-Anteil bereits; ein zusätzlicher Rest-Term nur bei fehlender
    # BKW-Erzeugung, entschieden von `bkw_finanz_beitrag` in der Schicht).
    pv_pro_monat = {f.schluessel: f.erzeugung.pv_kwh for f in fakten}
    bkw_rest_ev_pro_monat = {
        f.schluessel: f.bkw.rest_eigenverbrauch_kwh for f in fakten
    }
    speicher_ladung_pro_monat = {f.schluessel: f.speicher.ladung_kwh for f in fakten}
    speicher_entladung_pro_monat = {
        f.schluessel: f.speicher.entladung_kwh for f in fakten
    }
    v2h_pro_monat = {f.schluessel: f.emob.v2h_entladung_kwh for f in fakten}

    gesamt_pv = sum(pv_pro_monat.values())
    gesamt_speicher_ladung = sum(speicher_ladung_pro_monat.values())
    gesamt_speicher_entladung = sum(speicher_entladung_pro_monat.values())
    gesamt_v2h = sum(v2h_pro_monat.values())

    # #304 Teil 2: Eigenverbrauch pro Monat kanonisch (PV + Speicher + V2H +
    # Erzeuger hinter dem Zähler), NICHT aus dem Legacy-Feld
    # `md.eigenverbrauch_kwh` — das bleibt bei IMD-basierten Setups leer und
    # ließ die EV-Quote/-Ersparnis kollabieren. Nur Monate MIT Zählerzeile: ohne
    # gemessene Einspeisung wäre die ganze Erzeugung als Eigenverbrauch
    # ausgewiesen — eine Aussage, die niemand belegen kann (P4).
    eigenverbrauch_pro_monat = {
        f.schluessel: f.kennzahlen.eigenverbrauch_kwh
        for f in fakten
        if f.meta.hat_zaehlerzeile
    }
    gesamt_ev = sum(eigenverbrauch_pro_monat.values())

    # E-Auto-PV-Ladung + WP-Strom bleiben per-Investition aggregiert: beide
    # Größen werden unten je Fahrzeug/Wärmepumpe mit DESSEN Parametern bewertet
    # (Vergleichsverbrauch, JAZ) — dafür reicht die Monatssumme nicht.
    eauto_pv_pro_inv: dict[int, float] = {}
    for ea in e_autos:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == ea.id and ea.ist_aktiv_im_monat(jahr, monat):
                # N-199: über den SoT-Helper statt roh — der evcc-Portal-Import
                # schreibt `ladung_kwh` + `ladung_pv_kwh` und **kein**
                # `ladung_netz_kwh`; der Rohzugriff sah dort eine 0, wo der
                # Helfer `Total − PV` ableitet.
                pv_ladung, _ = get_emob_pv_netz_kwh(daten)
                # F-17: liegt die Ladung kanonisch auf der Wallbox, kommt der
                # km-anteilige Pool-Anteil statt der eigenen (leeren) Zeile.
                share = emob_month_share(
                    emob_pool_ctx, "e-auto",
                    daten.get("km_gefahren", 0) or 0, jahr, monat,
                )
                if share is not None:
                    pv_ladung = share.pv_kwh
                gesamt_eauto_pv += pv_ladung
                eauto_pv_pro_inv[ea.id] = eauto_pv_pro_inv.get(ea.id, 0.0) + pv_ladung

    # N-279: zusätzlich je Gerät gemerkt — die Anzeige-Felder (`wp_verbrauch_kwh`,
    # PV-Nutzung) meinen ALLE Wärmepumpen, der Alternativkosten-Vergleich unten
    # aber nur die, die überhaupt etwas ersetzt haben. Ohne die Aufteilung wurde
    # der Strom einer Neubau-WP von der Ersparnis der ersetzenden abgezogen.
    # Muster wie `eauto_pv_pro_inv` darüber; `wp_mit_ersatz` steht erst weiter
    # unten, deshalb hier je Investition statt in zwei Summen.
    wp_strom_pro_inv: dict[int, float] = {}
    for wp in waermepumpen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                strom = get_wp_strom_kwh(daten, wp.parameter)
                gesamt_wp_strom += strom
                wp_strom_pro_inv[wp.id] = wp_strom_pro_inv.get(wp.id, 0.0) + strom

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
    # PVGIS-PROGNOSE — die aktive (Auswahl-SoT, P5)
    # =====================================================================
    pvgis = await lade_aktive_prognose(db, anlage_id)

    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)

    # =====================================================================
    # INVESTITIONEN SUMMIEREN (mit Alternativkosten-Berechnung)
    # =====================================================================
    # Relevante Kosten = MEHRKOSTEN gegenüber der Alternative, je Position
    # geklemmt — über den Layer-SoT (ADR-001), dieselbe Zahl wie USt-Bemessung
    # (N-129/N-130) und ROI-Sicht.
    #
    # N-137/N-134: Hier stand bis 04.08. eine **Hybrid-Summe** — PV-System voll
    # + WP-/eAuto-Mehrkosten + Sonstiges voll —, und ihre Mehrkosten kamen aus
    # `inv.parameter["alternativ_kosten_euro"]`. Dieser Schlüssel hat baumweit
    # KEINEN Schreiber (gemessen): kein Formular, kein Wizard, kein Import setzt
    # ihn. Gepflegt wird die Spalte `anschaffungskosten_alternativ`, die der
    # Daten-Checker mit WARNING einfordert („werden für ROI-Berechnung
    # benötigt") — die Summe fiel also immer auf die Festannahmen 8.000/35.000 €
    # zurück und ignorierte genau das Feld, nach dem eedc fragt. Dieselbe
    # Hybrid-Summe stand ein zweites Mal in `cockpit/uebersicht.py`.
    #
    # Sichtbare Folge: keine. Die Summe erreichte über diesen Endpoint keine
    # Oberfläche (kein `.tsx` las `investition_gesamt_euro`) — sie war der
    # Nenner des Amortisations-Fortschritts, den es am Bildschirm nicht gab.
    # Mit der neuen Fortschritts-Kachel in Auswertungen → ROI wird sie sichtbar,
    # deshalb wird sie jetzt richtig.
    investition_gesamt = relevante_kosten_aus_investitionen(alle_investitionen)

    # Aufschlüsselung für die Response — dieselbe Klemmung je Position, nur nach
    # Typ gruppiert. `investition_pv_system` und `investition_sonstige` sind
    # dort, wo keine Alternative gepflegt ist, weiterhin die Vollkosten; das ist
    # keine Sonderregel, sondern `max(0, gesamt − 0)`.
    PV_RELEVANTE_TYPEN = [
        "pv-module", "wechselrichter", "speicher", "wallbox", "balkonkraftwerk"
    ]
    investition_pv_system = 0.0
    investition_wp_mehrkosten = 0.0
    investition_eauto_mehrkosten = 0.0
    investition_sonstige = 0.0
    for inv in alle_investitionen:
        relevant = relevante_kosten_aus_investitionen([inv])
        if inv.typ in PV_RELEVANTE_TYPEN:
            investition_pv_system += relevant
        elif inv.typ == "waermepumpe":
            investition_wp_mehrkosten += relevant
        elif inv.typ == "e-auto":
            investition_eauto_mehrkosten += relevant
        else:
            investition_sonstige += relevant

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
    #
    # N-88/F2b: Wer nichts ersetzt hat, gehoert in keine dieser Groessen — weder
    # mit Wirkungsgrad noch mit Zusatzkosten noch mit seiner Waerme. Deshalb EINE
    # gefilterte Liste statt drei `continue`: Die Schleife darunter greift mit
    # `wp_aggregate[wp.id]` zu und wuerde bei einem uebersprungenen Geraet mit
    # KeyError abstuerzen.
    wp_mit_ersatz = [
        wp for wp in waermepumpen
        if not ersetzt_keine_heizung(
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        )
    ]
    wp_aggregate: dict[int, dict] = {}
    for wp in wp_mit_ersatz:
        params = wp.parameter or {}
        wp_aggregate[wp.id] = {
            "alter_preis_cent": (
                params.get(
                    PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
                    PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
                ) or PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]
            ),
            "alter_wirkungsgrad": alter_wirkungsgrad(
                params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
            ),
            "zusatzkosten_jahr": params.get(
                PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0,
            ) or 0,
            "thermisch_kwh": 0.0,
        }
    wp_alternativ_zusatzkosten_jahr = sum(
        a["zusatzkosten_jahr"] for a in wp_aggregate.values()
    )
    # N-279: derselbe Monats-Ø wie `wp_strom_monat_avg`, aber nur über die
    # Geräte, die etwas ersetzt haben. Er speist AUSSCHLIESSLICH den
    # Alternativkosten-Vergleich; die Anzeige-Felder bleiben beim Gesamt-Ø,
    # denn `wp_verbrauch_kwh` meint den Verbrauch der Anlage, nicht den des
    # Vergleichs. Ohne die Trennung stand die Stromkostenseite auf einer
    # größeren Menge als die Gaskostenseite — der Strom einer Neubau-WP
    # schmälerte die Ersparnis der ersetzenden.
    gesamt_wp_strom_mit_ersatz = sum(
        wp_strom_pro_inv.get(wp.id, 0.0) for wp in wp_mit_ersatz
    )
    wp_strom_mit_ersatz_monat_avg = (
        gesamt_wp_strom_mit_ersatz / anzahl_monate_hist if wp_mit_ersatz else 0
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
            # #331: der REAL getankte Verbrauch eines Plug-in-Hybrids — `None`
            # bei einem BEV, dann bleibt hier jede Zahl wie vorher. Diese Route
            # rechnet die E-Auto-Ersparnis als VIERTE Read-Site selbst (Cockpit,
            # E-Auto-Dashboard und HA-Export gehen über
            # `eauto_wirtschaftlichkeit`); ohne diesen Wert zeigte
            # Auswertungen → Finanzen für einen Hybrid mehr Ersparnis als jede
            # andere Sicht. [[feedback_aggregations_drift]]
            "eigener_l_100km": eigener_verbrauch_l_100km(params),
            "fahranteil_prozent": params.get(
                PARAM_E_AUTO["ELEKTRISCHER_FAHRANTEIL_PROZENT"]
            ),
            "verbrauch_kwh_100km": params.get(
                PARAM_E_AUTO["VERBRAUCH_KWH_100KM"],
                PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"],
            ) or PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"],
            "km": 0.0,
            "netz_kwh": 0.0,
            "fahrverbrauch_kwh": 0.0,
            "pv_kwh": eauto_pv_pro_inv.get(ea.id, 0.0),
            "bisherige_ersparnis": 0.0,
            # Invariante: immer gesetzt — der Jahres-Block unten (Zeile ~1589)
            # läuft nur bei gesamt_km > 0. Ohne diese Init crasht die
            # Komponenten-Schleife (Zeile ~1757) bei einem E-Auto OHNE
            # historische km (frisch angelegt, noch keine Daten) → 500 auf der
            # gesamten Aussichten-Finanzseite.
            "jahres_ersparnis": 0.0,
        }

    # =====================================================================
    # BISHERIGE ERTRÄGE BERECHNEN (inkl. Alternativkosten!)
    # =====================================================================
    # N-228: nur **heute aktive** Komponenten — dieser Wert geht ausschließlich
    # in ZUKUNFTS-Größen (Jahres-Netto-Ertrag, Amortisationsdauer, USt-
    # Bemessung). Eine 2023 stillgelegte Wärmepumpe verursacht keine
    # Versicherung mehr; sie verlängerte die Amortisation trotzdem dauerhaft.
    # Der RÜCKBLICK ist davon unberührt — er rechnet weiter unten mit
    # `betriebskosten_hist_je_inv` über die tatsächliche Laufzeit.
    # `ha_export.py` filtert an derselben Stelle seit jeher (`aktiv_jetzt()`),
    # die vier Sichten waren darüber uneins.
    _heute_bk = date.today()
    betriebskosten_ges = sum(
        i.betriebskosten_jahr or 0
        for i in alle_investitionen
        if i.ist_aktiv_im_monat(_heute_bk.year, _heute_bk.month)
    )
    # §8/2 des Wirtschaftlichkeits-Konzepts: das Gegenstück zu den
    # Betriebskosten auf der Ertragsseite. Ein Jahresbetrag an der Investition
    # ist per FORM wiederkehrend (§2/1) und wirkt deshalb auch in der Prognose;
    # bis 2026-08-10 kannte diese Sicht das Feld nicht (0 Treffer).
    #
    # ⚠ Zwei Einschränkungen gegenüber `betriebskosten_ges`, beide bewusst:
    # (a) nur die Typen, an denen das Feld überhaupt pflegbar und gelesen wird
    #     (`ERTRAGSFELD_TYPEN`) — sonst stünde ein Wert an einer PV-Zeile hier
    #     im Zähler, während *Auswertungen → ROI* ihn ignoriert;
    # (b) nur **heute aktive** Investitionen — eine stillgelegte Komponente
    #     bringt keinen künftigen Ertrag. Der Rückblick oben ist davon
    #     unberührt, er rechnet aus gemessenen Monatswerten.
    ertrag_jahr_ges = sum(
        i.einsparung_prognose_jahr or 0
        for i in alle_investitionen
        if i.typ in ERTRAGSFELD_TYPEN and i.ist_aktiv_an(_heute)
    )
    bisherige_ertraege = 0.0
    bisherige_eauto_ersparnis = 0.0

    # #326-Vollmigration: Einspeise-Erlös §51 + EV-/BKW-Ersparnis laufen über
    # den SoT-Helper `berechne_finanz_aggregat` — per-Monat mit Monats-Flexpreis
    # UND Monats-Tarif (gueltig_ab-Stichtag), deckungsgleich mit Cockpit,
    # Jahresbericht-PDF und HA-Export ([[feedback_aggregations_drift]]). Die
    # aussichten-spezifischen Anteile (WP-/E-Auto-Alternativkosten, Prognose)
    # bleiben lokal — sie sind keine Aggregat-Semantik.
    #
    # ADR-002/P10: die Eingabe der Zeile entsteht aus dem `MonatsFakt`
    # (`finanz_zeile_eingabe`), nicht mehr aus site-eigenen Maps. Damit trägt
    # sie die P7-Auflösung, den §51-Negativpreis und den Monats-Flexpreis, ohne
    # dass diese Sicht eine der drei Regeln selbst kennt.
    #
    # `meta.erzeuger_aktiv` ist die Anschaffungsdatum-Grenze für den
    # anlagenweiten PV-Ertrag (Einspeise-Erlös + EV-Ersparnis): WP/E-Auto/
    # Sonstige begrenzen ihre Monate bereits über `ist_aktiv_im_monat` (#236),
    # dieser Pfad zusätzlich auf das aktive Fenster der Erzeuger hinter dem
    # Zähler ([[feedback_anschaffungsdatum_grenze]]). Ohne registrierten
    # Erzeuger bleibt das Verhalten unverändert.
    _tarif_cache: dict[date, dict] = {}
    finanz_zeilen: list[FinanzMonatsZeile] = []
    # Dieselben Zeilen je Kalenderjahr — die USt rechnet je Jahr (N-130), und
    # `eigenverbrauch_kwh` des Aggregats ist die Summe der Monatswerte, das
    # Zerlegen ist also exakt.
    finanz_zeilen_je_jahr: dict[int, list[FinanzMonatsZeile]] = defaultdict(list)
    for f in fakten:
        if not f.meta.hat_zaehlerzeile or not f.meta.erzeuger_aktiv:
            continue
        _zeile = await baue_finanz_zeile(
            db, anlage_id, finanz_zeile_eingabe(f), tarif_cache=_tarif_cache
        )
        finanz_zeilen.append(_zeile)
        finanz_zeilen_je_jahr[f.jahr].append(_zeile)

    # #392: die Monatszeilen für den Vergütungs-Override in `_monats_tarif` —
    # ein Lookup je Periode, dieselben Zeilen wie oben geladen.
    _md_by_periode = {(md.jahr, md.monat): md for md in monatsdaten}

    async def _tarife_fuer_stichtag(jahr: int, monat: int) -> dict:
        """Kompletter Tarifsatz des Monats (allgemein + WP/Wallbox).

        Teilt sich `_tarif_cache` mit `baue_finanz_zeile` → keine Extra-Queries.
        """
        stichtag = date(jahr, monat, 1)
        if stichtag not in _tarif_cache:
            _tarif_cache[stichtag] = await lade_tarife_fuer_anlage(
                db, anlage_id, target_date=stichtag
            )
        return _tarif_cache[stichtag]

    async def _monats_tarif(jahr: int, monat: int) -> tuple[float, float]:
        """(Arbeitspreis, Einspeisevergütung) des Monats in ct/kWh.

        Für die RÜCKBLICKENDEN Schleifen unten. Die Modul-Variablen
        `netzbezug_preis`/`einspeiseverguetung` tragen den HEUTE gültigen Tarif
        — richtig für die Hochrechnung nach vorn, falsch für einen Altmonat:
        eine Preiserhöhung hätte die gesamte E-Auto-Historie rückwirkend
        umgerechnet, während die Finanz-Zeilen daneben korrekt je Monat rechnen
        (dieselbe Klasse wie der Jahresbericht-Drift, Forum simon42 #89667/60).
        Teilt sich `_tarif_cache` mit `baue_finanz_zeile` → keine Extra-Queries.
        """
        m_allgemein = (await _tarife_fuer_stichtag(jahr, monat)).get("allgemein")
        return (
            m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else NETZBEZUG_DEFAULT_CENT,
            # #392: der gepflegte Monatssatz der variablen Vergütung schlägt
            # den Stammwert des Monats-Tarifs (rückblickend; die Hochrechnung
            # nach vorn nimmt weiter den heutigen Stammwert).
            resolve_einspeise_preis_cent(
                _md_by_periode.get((jahr, monat)),
                m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT,
            ),
        )

    # Wärmepumpe Alternativkosten-Ersparnis (vs. Gas/Öl) — die „bisherige"-
    # Ersparnis-FORMEL liegt jetzt im SoT-Helper `berechne_wp_alternativkosten_
    # ersparnis` (core/berechnungen/alternativkosten.py), identisch zum HA-Export
    # ([[feedback_aggregations_drift]]). `historische_inv_daten` ist bereits
    # per-Investition auf das aktive Fenster gefiltert (Z. ~948–953), erfüllt
    # also den Helper-Kontrakt; der Monats-Gaspreis (Monatsdaten → per-WP-Default-
    # Fallback im Helper) wird als Perioden-Map durchgereicht.
    gaspreis_by_periode = {
        (md.jahr, md.monat): md.gaspreis_cent_kwh for md in monatsdaten
    }
    # WP-Arbeitspreis je Monat (ADR-002/P8) — deckungsgleich mit dem HA-Export.
    wp_preis_by_periode: dict[tuple[int, int], float] = {}
    for (_inv_id, _p_jahr, _p_monat) in historische_inv_daten:
        _periode = (_p_jahr, _p_monat)
        if _periode not in wp_preis_by_periode:
            _p_tarife = await _tarife_fuer_stichtag(_p_jahr, _p_monat)
            wp_preis_by_periode[_periode] = resolve_strompreis_for_komponente(
                _p_tarife, "waermepumpe", fallback=netzbezug_preis
            )
    bisherige_wp_ersparnis = berechne_wp_alternativkosten_ersparnis(
        waermepumpen,
        historische_inv_daten,
        gaspreis_by_periode,
        wp_preis_by_periode,
        wp_netzbezug_preis,
    )

    # Thermische Wärmemengen pro WP/gesamt — getrennte Concern: nur die
    # WP-PROGNOSE (Z. ~1520) braucht sie (thermisch-gewichtete alter_preis/
    # Wirkungsgrad-Mischung). Bewusst NICHT im Ersparnis-Helper, der reine
    # Aggregat-Σ liefert.
    gesamt_wp_thermisch = 0.0
    for wp in wp_mit_ersatz:
        wp_agg = wp_aggregate[wp.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                thermisch = (daten.get("heizenergie_kwh", 0) or 0) + (
                    daten.get("warmwasser_kwh", 0) or 0
                )
                gesamt_wp_thermisch += thermisch
                wp_agg["thermisch_kwh"] += thermisch

    # E-Auto Alternativkosten-Ersparnis
    # Ersparnis = Benzin-Kosten - Netzstrom-Kosten
    # Pro Monat + pro E-Auto, damit unterschiedliche Vergleichsverbräuche
    # und Benzinpreis-Defaults pro Fahrzeug korrekt einfließen. Vorher las
    # diese Schleife `eauto_vergleich_l_100km` aus einer last-write-wins-
    # Variable außerhalb — bei mehreren E-Autos wurden alle mit dem Wert
    # des letzten gerechnet.
    #
    # N-181/F-18: die **Rechnung** liegt seit 2026-08-08 im Layer-SoT; diese
    # Schleife sammelt nur noch. Sie war die vierte von vier Formen der
    # Preisauflösung — als einzige monatsgenau, dafür über den **allgemeinen**
    # Tarif statt des Wallbox-Tarifs, den Cockpit und Hub nehmen. Beide Achsen
    # der Abweichung fallen mit dem Umhängen weg.
    _benzin_lookup_aus = {
        k: (md.kraftstoffpreis_euro if md.kraftstoffpreis_euro is not None else None)
        for k, md in monatsdaten_dict.items()
    }
    _strompreis_lookup_aus: dict[tuple[int, int], float] = {}
    for ea in e_autos:
        agg = eauto_aggregate[ea.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != ea.id or not ea.ist_aktiv_im_monat(jahr, monat):
                continue
            km = daten.get("km_gefahren", 0) or 0
            # N-199: SoT-Helper statt Rohkey (leitet `Total − PV` ab).
            _, netz = get_emob_pv_netz_kwh(daten)
            # F-17: kanonische Quelle ist die Wallbox, wenn sie Ladung trägt.
            share = emob_month_share(emob_pool_ctx, "e-auto", km, jahr, monat)
            if share is not None:
                netz = share.netz_kwh
            agg["km"] += km
            agg["netz_kwh"] += netz
            agg["fahrverbrauch_kwh"] += daten.get("verbrauch_kwh", 0) or 0
            if km > 0:
                agg.setdefault("km_monate", []).append((jahr, monat, km))
            if netz > 0:
                agg.setdefault("netz_monate", []).append((jahr, monat, netz))
            # ADR-002/P8: Tarif DES MONATS inkl. Flex-Ø, jetzt über den
            # Wallbox-Tarif (`resolve_strompreis_for_komponente`), damit die
            # Sicht dieselbe Größe bewertet wie Cockpit und Komponenten-Hub.
            if (jahr, monat) not in _strompreis_lookup_aus:
                _m_tarife = await _tarife_fuer_stichtag(jahr, monat)
                _m_allgemein = _m_tarife.get("allgemein")
                _m_wallbox = resolve_strompreis_for_komponente(
                    _m_tarife, "wallbox",
                    fallback=(
                        _m_allgemein.netzbezug_arbeitspreis_cent_kwh
                        if _m_allgemein else NETZBEZUG_DEFAULT_CENT
                    ),
                )
                _strompreis_lookup_aus[(jahr, monat)] = resolve_netzbezug_preis_cent(
                    monatsdaten_dict.get((jahr, monat)), _m_wallbox
                )

    for ea in e_autos:
        agg = eauto_aggregate[ea.id]
        if not agg.get("km_monate"):
            continue
        _erg = berechne_eauto_ersparnis_periode(
            km_pro_monat=agg["km_monate"],
            ladung_netz_kwh_gesamt=agg["netz_kwh"],
            # Externe Ladekosten sind in dieser Sicht noch nie eingegangen —
            # beim Umhängen nicht stillschweigend dazunehmen.
            ladung_extern_euro_gesamt=0.0,
            wallbox_strompreis_cent=netzbezug_preis,
            eauto_parameter=inv_by_id_hist.get(ea.id).parameter if inv_by_id_hist.get(ea.id) else ea.parameter,
            monats_benzinpreis_lookup=_benzin_lookup_aus,
            fahrverbrauch_kwh_gesamt=agg["fahrverbrauch_kwh"] or None,
            monats_strompreis_lookup=_strompreis_lookup_aus,
            netz_pro_monat=agg.get("netz_monate") or None,
        )
        agg["bisherige_ersparnis"] = _erg.ersparnis_euro
        agg["km_verbrenner"] = _erg.km_verbrenner
    bisherige_eauto_ersparnis = sum(a["bisherige_ersparnis"] for a in eauto_aggregate.values())
    gesamt_km = sum(a["km"] for a in eauto_aggregate.values())
    gesamt_eauto_netz = sum(a["netz_kwh"] for a in eauto_aggregate.values())

    # BKW-Ersparnis: kommt aus `berechne_finanz_aggregat` (bkw_eigenverbrauch_kwh
    # in den Finanz-Zeilen oben) — kein eigener Loop mehr.

    # Sonstige Positionen — **aus den Monats-Fakten** (Bauschritt 4 des
    # Wirtschaftlichkeits-Konzepts §8, zugleich eine P10-Bereinigung).
    #
    # ⚑ Bis 2026-08-10 lief hier eine eigene Schleife über
    # `historische_inv_daten` — also ausschließlich über
    # `InvestitionMonatsdaten`. Damit fehlte genau der Erfassungsort, den das
    # Handbuch für „mehrere Komponenten" vorsieht: die Positionen auf der
    # **Monatsdaten-Zeile** (G19-1). Gemessen am 10.08.: eine anlagenweite
    # Ausgabe von 3.000 € bewegte den Kapitaleinsatz dieser Route um **0 €**,
    # während der HA-Sensor sie voll trug (18.000 gegen 15.000) — und eine
    # anlagenweite Förderung war im Fortschritt schlicht unsichtbar.
    #
    # `f.sonstiges` fasst beide Orte zusammen (IMD **typ-unabhängig**, #310,
    # plus die Basis-Positionen der Monatsdaten-Zeile) und bringt den
    # Laufzeit-Filter (#236) bereits mit — die Schleife hatte ihn von Hand
    # nachgebaut.
    #
    # F-19 + Bauschritt 7: beide Seiten daneben getrennt — sie gehen in den
    # Kapitaleinsatz (Ausgaben erhöhend, Erträge mindernd). Die dienstlichen
    # Ladekosten unten sind laufender Aufwand und gehören ausdrücklich nicht in
    # den Nenner (SoT `berechnungen/kapitalrechnung.py`).
    bisherige_sonstige_netto = sum(f.sonstiges.netto_euro for f in fakten)
    # Konzept §9 Weg 2: gepflegte Erlöse von Erzeugern mit eigenem
    # Einspeisetarif. Eigener Summand — er bewertet nicht den Anlagenzähler.
    bisherige_erzeuger_erloes = sum(f.sonstiges.einspeise_erloes_euro for f in fakten)
    bisherige_sonstige_ausgaben = sum(f.sonstiges.ausgaben_euro for f in fakten)
    bisherige_sonstige_ertraege = sum(f.sonstiges.ertraege_euro for f in fakten)

    # Dienstliche E-Auto/Wallbox-Ladekosten abziehen — Mengen aus den
    # Monats-Fakten (P10: Dienstwagen-Filter, Laufzeit-Fenster und PV/Netz-Split
    # löst die Schicht auf), Bewertung über den Layer-SoT (ADR-001).
    # Bis 2026-07-31 hat dieser Block beides selbst getan und dabei ZWEI Preise
    # anders gewählt als das Cockpit: den Netzanteil zum **allgemeinen**
    # Arbeitspreis statt zum Wallbox-Tarif (N-12) und den PV-Anteil zur
    # Einspeisevergütung statt zum Netzbezugspreis (N-18). Das Cockpit ist der
    # Kanon (Gernot 2026-07-31), hier läuft jetzt dieselbe Formel.
    bisherige_dienstlich_ladekosten = berechne_dienstliche_ladekosten(
        DienstlicheLadungZeile(
            ladung_pv_kwh=f.emob.dienstlich_ladung_pv_kwh,
            ladung_netz_kwh=f.emob.dienstlich_ladung_netz_kwh,
            netzbezug_preis_cent=f.tarif.netzbezug_preis_cent,
            wallbox_preis_cent=f.tarif.wallbox_preis_effektiv_cent,
        )
        for f in fakten
    ).gesamt_euro
    bisherige_sonstige_netto -= bisherige_dienstlich_ladekosten

    # Finanz-Aggregat (Einspeise-Erlös §51 + EV- + BKW-Ersparnis + Sonstige)
    # + aussichten-spezifische Alternativkosten-Ersparnisse (WP, E-Auto).
    _finanz = berechne_finanz_aggregat(
        finanz_zeilen, sonstige_netto_euro=bisherige_sonstige_netto,
        erzeuger_erloes_euro=bisherige_erzeuger_erloes
    )
    bisherige_bkw_ersparnis = _finanz.bkw_ersparnis_euro
    bisherige_ertraege = (
        _finanz.netto_ertrag_euro + bisherige_wp_ersparnis + bisherige_eauto_ersparnis
    )

    # Anteilige Betriebskosten für den historischen Zeitraum abziehen — je
    # Komponente über IHRE Laufzeit (N-228).
    #
    # ⚑ Bis 2026-08-10 stand hier `betriebskosten_ges × Monate / 12`: die
    # anlagenweite Jahressumme über den GANZEN Beobachtungszeitraum, also auch
    # über Monate, in denen eine Komponente noch nicht angeschafft oder bereits
    # stillgelegt war. Eine 2024 gekaufte Wärmepumpe zahlte damit Versicherung
    # ab 2023. **Am Dev-Bestand gemessen: 1.291,67 € statt 725,00 € — 566,67 €
    # zu viel**, allein aus zwei Komponenten mit gepflegten Betriebskosten.
    #
    # Die Größe wird **einmal** gebildet und zweimal benutzt: hier als Summe und
    # unten in der Zerlegung je Zeile (Bauschritt 5). Genau deshalb ließ sich
    # N-228 nicht abtrennen — mit dem alten Abzug trug der Rest der Zerlegung
    # die Differenz systematisch, und ein Rest, der eine bekannte Ursache hat,
    # ist keine Restgröße mehr, sondern ein verstecktes Vorzeichen.
    _monate_beobachtet = {(f.jahr, f.monat) for f in fakten}
    betriebskosten_hist_je_inv: dict[int, float] = {}
    for _inv in alle_investitionen:
        _bk = _inv.betriebskosten_jahr or 0
        if not _bk:
            continue
        _aktive = sum(
            1 for (_j, _m) in _monate_beobachtet if _inv.ist_aktiv_im_monat(_j, _m)
        )
        if _aktive:
            betriebskosten_hist_je_inv[_inv.id] = _bk * _aktive / 12
    betriebskosten_hist = sum(betriebskosten_hist_je_inv.values())
    bisherige_ertraege -= betriebskosten_hist

    # USt auf Eigenverbrauch bei Regelbesteuerung — auch RÜCKBLICKEND. Sie stand
    # bisher nur in der Jahres-Prognose (`jahres_netto_ertrag`, weiter unten);
    # die bisherigen Erträge trugen sie nicht, obwohl der Cockpit-Netto-Ertrag
    # sie abzieht. Bei Regelbesteuerung lagen ROI-Fortschritt und Amortisation
    # damit um den USt-Betrag zu günstig (#326-Inventur, Dimension 2).
    #
    # N-130: Der Rückblick geht IMMER über den gesamten bisherigen Zeitraum —
    # er war damit von der Zeitraum-Kollaps-Klasse durchgehend betroffen, nicht
    # nur bei gesetztem Filter. `sum(pv_pro_monat.values())` stand als
    # „Jahres-Erzeugung" gegen eine Ein-Jahres-AfA. N-129: Bemessungsgrundlage
    # über den Layer-SoT (Mehrkosten) statt der Vollkosten.
    _pv_je_jahr: dict[int, float] = defaultdict(float)
    for (_j, _m), _pv in pv_pro_monat.items():
        _pv_je_jahr[_j] += _pv
    # Bauschritt 5: als eigene Größe, weil die Zerlegung sie braucht — die USt
    # hängt am Eigenverbrauch und damit an der ERZEUGUNGS-Seite, sie muss also
    # denselben Weg gehen wie Einspeise-Erlös und EV-Ersparnis. Vorher stand
    # hier ein direktes `-=`; der Betrag war danach nicht mehr greifbar.
    bisherige_ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[
            UstJahresanteil(
                jahr=_j,
                eigenverbrauch_kwh=berechne_finanz_aggregat(
                    finanz_zeilen_je_jahr[_j]
                ).eigenverbrauch_kwh,
                pv_kwh=_pv_je_jahr.get(_j, 0.0),
                monate=len(finanz_zeilen_je_jahr[_j]),
            )
            for _j in sorted(finanz_zeilen_je_jahr)
        ],
        bemessungsgrundlage_euro=bemessungsgrundlage_aus_investitionen(alle_investitionen),
        betriebskosten_jahr_euro=betriebskosten_ges,
    )
    bisherige_ertraege -= bisherige_ust_eigenverbrauch

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
    #: N-279: dieselbe saisonale Hochrechnung, nur über `wp_mit_ersatz`.
    #: Bewusst parallel mitgeführt statt aus `jahres_wp_verbrauch` skaliert —
    #: eine abgeleitete Zahl wäre eine zweite Bildungsvorschrift für dieselbe
    #: Größe (P4) und würde bei einer künftigen Änderung der Saisonfaktoren
    #: stillschweigend auseinanderlaufen.
    jahres_wp_verbrauch_mit_ersatz = 0.0
    jahres_eauto_pv = 0.0

    # Saisonale Faktoren für WP (Heizperiode)
    WP_SAISON_FAKTOREN = {
        1: 1.8, 2: 1.6, 3: 1.3, 4: 0.8, 5: 0.4, 6: 0.2,
        7: 0.2, 8: 0.2, 9: 0.4, 10: 0.8, 11: 1.3, 12: 1.7
    }

    def _pv_kwh_im_kalendermonat(monat: int) -> float:
        """PVGIS-Wert des Monats, sonst TMY-Schätzung — EINE Vorschrift.

        N-277: Die Monatsschleife unten brauchte diese Zahl schon immer; seit
        der Normierung braucht sie auch der Vorlauf. Als Funktion statt zweimal
        ausgeschrieben, sonst laufen die beiden bei der nächsten Änderung
        auseinander (P4).
        """
        pv = pvgis_monatswerte.get(monat, 0)
        if pv <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude if anlage.latitude else 48.0)
            pv = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85
        return pv

    def _pv_faktor(monat: int) -> float:
        """Saisonale Skalierung: Monatsertrag gegen den Monats-Ø des Jahres."""
        if not pvgis_monatswerte:
            return 1.0
        return _pv_kwh_im_kalendermonat(monat) / (sum(pvgis_monatswerte.values()) / 12)

    # ── N-277: der gepflegte PV-Anteil der Wärmepumpe(n) ────────────────────
    #
    # Hier stand bis 2026-08-30 eine feste `0.5`, und das Feld „PV-Anteil (%) —
    # Anteil des WP-Stroms aus PV" wurde nirgends gelesen.
    #
    # ⚠ DIE ZAHL WIRD NICHT EINFACH ERSETZT, und das ist der Kern: Die `0.5` war
    # **kein Jahresanteil**, sondern ein Basiswert VOR der Dämpfung
    # `* (pv_faktor ** 0.5)`. Effektiv lieferte sie rund 38 % im Jahresmittel —
    # die Winterdämpfung, die eine Wärmepumpe braucht, war also bereits da
    # (Januar ~27 %, Juli ~65 %). Wer `0.5` stumpf durch den gepflegten Wert
    # ersetzt, bekommt bei gepflegten 30 % effektiv 23 %: der Anwender pflegt
    # 30 und sieht 23.
    #
    # ⇒ Die saisonale FORM bleibt, die JAHRESSUMME wird auf den gepflegten Wert
    # normiert. Damit bedeutet das Formularfeld, was draufsteht.
    #
    # ⚠ Was das Modell weiterhin nicht kann: Es bildet das PV-ANGEBOT ab, nicht
    # die GLEICHZEITIGKEIT (die WP läuft nachts und morgens, die PV mittags).
    # Der reale Deckungsgrad liegt darunter. Ein Gleichzeitigkeitsmodell
    # bräuchte ein Lastprofil — das es in genau diesem Fallback-Fall (keine
    # historische EV-Quote) per Definition nicht gibt.
    if waermepumpen:
        # Mehrere Wärmepumpen: Mittelwert. `wp_strom_monat_avg` ist ohnehin
        # anlagenweit, eine Gewichtung je Gerät hätte hier keinen Nenner.
        _anteile = [
            (wp.parameter or {}).get(
                PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"],
                PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"],
            )
            for wp in waermepumpen
        ]
        _anteile = [float(a) for a in _anteile if a is not None]
        wp_pv_anteil = (sum(_anteile) / len(_anteile) / 100.0) if _anteile else 0.0
    else:
        wp_pv_anteil = 0.0

    # Normierung über die ZWÖLF KALENDERMONATE, nicht über den Prognosehorizont
    # — sonst hinge der Jahresanteil an der Länge der Anfrage.
    _saison_summe = sum(WP_SAISON_FAKTOREN.values())
    _gewicht_summe = sum(
        WP_SAISON_FAKTOREN[m] * (_pv_faktor(m) ** 0.5) for m in range(1, 13)
    )
    wp_pv_norm = (_saison_summe / _gewicht_summe) if _gewicht_summe > 0 else 1.0

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
            # N-277: gepflegter Anteil × Saisonform × Normierung (s. Vorlauf oben)
            wp_pv_fb = wp_verbrauch_fb * wp_pv_anteil * (pv_faktor ** 0.5) * wp_pv_norm
            eigenverbrauch_kwh = basis_ev + speicher_fallback + v2h_fallback + wp_pv_fb

        eigenverbrauch_kwh = min(eigenverbrauch_kwh, pv_kwh)  # Kann nicht mehr als erzeugt
        einspeisung_kwh = pv_kwh - eigenverbrauch_kwh

        # Komponentenbeiträge für Anzeige (informativ, beeinflusst EV nicht)
        speicher_beitrag = speicher_ev_erhohung_monat * pv_faktor if speicher else 0
        v2h_beitrag = v2h_beitrag_monat if e_autos else 0
        eauto_pv = eauto_pv_monat * pv_faktor if e_autos else 0
        wp_saison = WP_SAISON_FAKTOREN.get(monat, 1.0)
        wp_verbrauch = wp_strom_monat_avg * wp_saison if waermepumpen else 0
        wp_verbrauch_mit_ersatz = (
            wp_strom_mit_ersatz_monat_avg * wp_saison if wp_mit_ersatz else 0
        )

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
        jahres_wp_verbrauch_mit_ersatz += wp_verbrauch_mit_ersatz
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
    if wp_mit_ersatz and gesamt_wp_thermisch > 0 and anzahl_monate_hist > 0:
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
            gas_kosten_altanlage(
                wp_thermisch_jahr, wp_alter_wirkungsgrad_agg, prognose_gaspreis
            )
            + wp_alternativ_zusatzkosten_jahr
        )
        # WP-Stromkosten pro Jahr (nur Netzanteil) — konservative 50/50-Annahme
        wp_netz_anteil = 1.0 - WP_PV_ANTEIL_DEFAULT
        # N-279: dieselbe Grundmenge wie `gas_kosten_jahr` darüber — also NUR die
        # Geräte mit Ersatz. `jahres_wp_verbrauch` (alle WPs) stand hier bis
        # 2026-08-29 und machte die Differenz unsymmetrisch: der Zähler zählte
        # die Wärme der ersetzenden Geräte, der Abzug den Strom ALLER. Eine
        # Wärmepumpe im Neubau senkte damit die ausgewiesene Ersparnis der
        # zweiten, die tatsächlich eine Gasheizung ersetzt hat.
        wp_strom_jahr = jahres_wp_verbrauch_mit_ersatz
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
        # #331: die fortgeschriebene Tankrechnung der Plug-in-Hybride. Der
        # Verbrenner-Anteil je Fahrzeug steht aus der Historie oben fest und
        # wird mit derselben Quote hochgerechnet wie die Kilometer.
        fossile_kosten_jahr = 0.0
        for _agg in eauto_aggregate.values():
            if _agg["eigener_l_100km"] is None or _agg["km"] <= 0:
                continue
            _km_v_jahr = _agg.get("km_verbrenner", 0.0) / anzahl_monate_hist * 12
            _agg["fossile_kosten_jahr"] = (
                _km_v_jahr / 100 * _agg["eigener_l_100km"] * prognose_benzinpreis
            )
            fossile_kosten_jahr += _agg["fossile_kosten_jahr"]
        # Netto-Ersparnis
        jahres_eauto_km_ersparnis = (
            benzin_kosten_jahr - eauto_stromkosten_netz_jahr - fossile_kosten_jahr
        )
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
            # #331: derselbe Posten wie im Aggregat oben — sonst wäre die Summe
            # der Pro-Fahrzeug-Zeilen nicht mehr das Aggregat.
            agg["jahres_ersparnis"] = (
                benzin_kosten_jahr_ea - stromkosten_ea
                - agg.get("fossile_kosten_jahr", 0.0)
            )

    # BKW Jahres-Ersparnis (aus historischem Durchschnitt hochgerechnet).
    # P9-konform 0, sobald das BKW seine Erzeugung mitschreibt: dann steckt es
    # in `gesamt_pv` und damit in `jahres_ev_ersparnis` — der Posten trägt nur
    # noch die Anlagen, deren BKW ausschließlich Eigenverbrauch führt.
    jahres_bkw_ersparnis = 0.0
    if balkonkraftwerke and anzahl_monate_hist > 0 and bisherige_bkw_ersparnis > 0:
        jahres_bkw_ersparnis = bisherige_bkw_ersparnis / anzahl_monate_hist * 12

    # F-19: die sonstigen AUSGABEN werden nicht mehr in die Zukunft
    # hochgerechnet. Das war die unangenehmste der vier Rechenstellen — eine
    # einmalige Reparatur belastete hier **jedes künftige Prognosejahr**, und
    # zwar dauerhaft: der historische Schnitt trug sie für immer weiter. Sie
    # gehört einmalig in den Kapitaleinsatz, nicht jährlich in den Ertrag.
    #
    # §8/3 (2026-08-10): jetzt gilt dasselbe für die sonstigen **Erträge**.
    # Eine Position im Monatsabschluss ist per FORM einmal geflossen (§2/2) —
    # sie in die Zukunft zu verlängern unterstellt eine Wiederholung, die
    # niemand behauptet hat. Der Ort für einen *wiederkehrenden* Ertrag ist
    # seit §8/1 das Feld „Ertrag/Jahr" an der Investition (`ertrag_jahr_ges`
    # oben); vor diesem Schritt gab es ihn nicht, und deshalb musste er in
    # dieser Reihenfolge gefahren werden.
    #
    # ⚠ Was hier bleibt: **nur** die dienstlichen Ladekosten. Sie stecken als
    # Abzug in `bisherige_sonstige_netto`, sind aber keine gepflegte Position,
    # sondern laufender Aufwand, den der Code selbst rechnet — er fällt jeden
    # Monat wieder an. Ein Nullsetzen der ganzen Zeile hätte ihn still aus der
    # Prognose entfernt.
    #
    # ⚑ Der **Fortschritt** (Messung, §4) trägt die Erträge unverändert weiter:
    # er rechnet aus `bisherige_ertraege`, nicht aus dieser Projektion.
    jahres_sonstige_netto = 0.0
    _sonstige_laufend = -bisherige_dienstlich_ladekosten
    if anzahl_monate_hist > 0 and _sonstige_laufend != 0:
        jahres_sonstige_netto = _sonstige_laufend / anzahl_monate_hist * 12

    # Gesamter Jahres-Netto-Ertrag inkl. Alternativkosten, BKW, Sonstige,
    # Betriebskosten und dem Jahres-Ertrag an der Investition (§8/2).
    jahres_netto_ertrag = jahres_einspeise_erloes + jahres_ev_ersparnis + jahres_wp_ersparnis + jahres_eauto_km_ersparnis + jahres_bkw_ersparnis + jahres_sonstige_netto + ertrag_jahr_ges - betriebskosten_ges

    # USt auf Eigenverbrauch bei Regelbesteuerung.
    # N-130 greift hier NICHT: `jahres_*` sind auf zwölf Monate hochgerechnete
    # Jahresmengen, kein Zeitraum-Aggregat ⇒ genau EIN Anteil mit `monate=12`.
    # Geändert hat sich nur die Bemessungsgrundlage (N-129).
    ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[UstJahresanteil(
            jahr=heute.year,
            eigenverbrauch_kwh=jahres_eigenverbrauch,
            pv_kwh=jahres_erzeugung,
            monate=12,
        )],
        bemessungsgrundlage_euro=bemessungsgrundlage_aus_investitionen(alle_investitionen),
        betriebskosten_jahr_euro=betriebskosten_ges,
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
    # Layer-SoT (ADR-001) statt vier Zeilen Arithmetik an dieser Stelle — dieselbe
    # Formel speist seit N-137 die Kachel „Amortisations-Fortschritt" in
    # Auswertungen → ROI. Der Fortschritt ist reine MESSUNG (kumulierte Erträge
    # ÷ relevante Kosten); `jahres_netto_ertrag` geht nur in die Restlaufzeit ein.
    # F-19: Nenner ist der Kapitaleinsatz — relevante Kosten plus die
    # kumulierten sonstigen Netto-Kosten. Damit rechnet der Fortschritt gegen
    # dieselbe Größe wie ROI-Dashboard und HA-Sensoren; `investition_gesamt`
    # selbst bleibt die Mehrkosten-Größe (N-137, zugleich USt-Grundlage).
    kapitaleinsatz = kapitaleinsatz_euro(
        relevante_kosten_euro=investition_gesamt,
        sonstige_ausgaben_euro=bisherige_sonstige_ausgaben,
        sonstige_ertraege_euro=bisherige_sonstige_ertraege,
    )
    # ⚠ Und der Zähler **ohne beide Seiten** der sonstigen Positionen — sonst
    # stünde dieselbe Reparatur (bzw. dieselbe Förderung) zweimal in derselben
    # Formel. Die Ausgaben werden wieder aufgeschlagen, weil sie im Netto
    # abgezogen waren; die Erträge werden abgezogen, weil sie darin enthalten
    # sind (Bauschritt 7).
    #
    # Das ausgewiesene Feld `bisherige_ertraege_euro` bleibt davon
    # **unberührt**: es ist die Zeitraum-Bilanz und deckungsgleich mit dem
    # Cockpit-Netto-Ertrag (`test_aussichten_finanz_aggregat_symmetrie.py`).
    # Ein erster Bau zog den Betrag dort ab und brach genau diese Zusicherung —
    # die Trennlinie verläuft zwischen ANGEZEIGTER Bilanz und Kapitalrechnung,
    # nicht zwischen zwei Rechenwegen.
    ertraege_fuer_kapitalrechnung = (
        bisherige_ertraege + bisherige_sonstige_ausgaben - bisherige_sonstige_ertraege
    )
    _amort = berechne_amortisations_fortschritt(
        relevante_kosten_euro=kapitaleinsatz,
        bisherige_ertraege_euro=ertraege_fuer_kapitalrechnung,
        jahres_netto_ertrag_euro=jahres_netto_ertrag,
        aktuelles_jahr=heute.year,
    )
    roi_fortschritt = _amort.fortschritt_prozent
    amortisation_erreicht = _amort.erreicht
    amortisation_prognose_jahr = _amort.prognose_jahr
    restlaufzeit_monate = _amort.rest_monate

    # =====================================================================
    # FORTSCHRITT JE INVESTITION — Bauschritt 5 des Konzepts (§8)
    # =====================================================================
    # ⚑ **Zerlegung, keine zweite Rechnung.** Der Zähler oben wird auf die
    # ROI-Zeilen VERTEILT; niemand rechnet eine Komponenten-Ersparnis ein
    # zweites Mal. Damit gilt `Σ Zeilen + Rest == gesamt` per Konstruktion —
    # die Zusicherung kann nicht auseinanderlaufen, und was sich nicht
    # zurechnen lässt, steht als Rest da statt still auf den Zeilen zu landen
    # (die N-220-Lehre: eine Zusicherung, die nur an einer Fixture hängt,
    # trägt nicht).
    #
    # Der Schlüssel der Erzeugungsseite ist die **gemessene Erzeugung** je
    # Zeile (Entscheid Maintainer 2026-08-10), nicht die Nennleistung: kWp
    # sagt, was ein Modul könnte, kWh sagt, was es beigetragen hat.
    from backend.api.routes.investitionen.crud import _gruppiere_investitionen
    from backend.core.berechnungen.ertrag_zerlegung import zerlege_kumulierten_ertrag

    _pv_systeme, _, _orphan_module = _gruppiere_investitionen(alle_investitionen)
    # Modul -> ROI-Zeile. Ein Modul mit gültigem Parent zählt auf den
    # Wechselrichter (dort steht die Zeile), ein Orphan-Modul auf sich selbst.
    _modul_zu_zeile: dict[int, int] = {
        m.id: wr_id for wr_id, sys in _pv_systeme.items() for m in sys["pv_module"]
    }

    _erz_gewichte: dict[int, float] = {}
    _bkw_gewichte: dict[int, float] = {}
    for _f in fakten:
        for _mod_id, _wert in (_f.erzeugung.pv_je_modul or {}).items():
            _zeile = _modul_zu_zeile.get(_mod_id, _mod_id)
            _erz_gewichte[_zeile] = (
                _erz_gewichte.get(_zeile, 0.0) + _wert.pv_erzeugung_kwh
            )
        for _bkw_id, _kwh in (_f.bkw.erzeugung_je_investition or {}).items():
            _bkw_gewichte[_bkw_id] = _bkw_gewichte.get(_bkw_id, 0.0) + (_kwh or 0.0)
    # Das BKW erzeugt hinter demselben Zähler und trägt deshalb auch die
    # Erlösseite mit — es hat aber zusätzlich seinen eigenen Ersparnis-Posten
    # (P9), der unten direkt zugeordnet wird.
    for _bkw_id, _kwh in _bkw_gewichte.items():
        _erz_gewichte[_bkw_id] = _erz_gewichte.get(_bkw_id, 0.0) + _kwh

    # Was am Zähler entsteht: Einspeise-Erlös + EV-Ersparnis, abzüglich der USt
    # auf den Eigenverbrauch — sie hängt an derselben Menge und geht deshalb
    # denselben Weg.
    _erzeugungs_erloes = (
        _finanz.einspeise_erloes_euro
        + _finanz.ev_ersparnis_euro
        - bisherige_ust_eigenverbrauch
    )

    _direkt: dict[int, float] = {}
    _abzug: dict[int, float] = {}

    # Wärmepumpe je Gerät — derselbe Layer-SoT, nur je WP gerufen.
    # ⚠ Bei MEHREREN WPs mit unterschiedlicher Monatsabdeckung ist die Summe
    # der Einzelaufrufe nicht bitgleich zum Gesamtaufruf: der anteilige
    # Zusatzkosten-Term rechnet dort mit der VEREINIGUNG der Monate. Die
    # Differenz landet sichtbar im Rest, statt eine Zeile zu verfälschen.
    for _wp in waermepumpen:
        _direkt[_wp.id] = _direkt.get(_wp.id, 0.0) + berechne_wp_alternativkosten_ersparnis(
            [_wp],
            historische_inv_daten,
            gaspreis_by_periode,
            wp_preis_by_periode,
            wp_netzbezug_preis,
        )

    # E-Auto je Fahrzeug — liegt bereits je Investition vor.
    for _ea_id, _agg in eauto_aggregate.items():
        _direkt[_ea_id] = _direkt.get(_ea_id, 0.0) + (_agg.get("bisherige_ersparnis") or 0.0)

    # BKW-Ersparnis (P9) auf die Balkonkraftwerke, nach ihrer Erzeugung.
    for _bkw_id, _betrag in verteile_nach_gewichten(
        _finanz.bkw_ersparnis_euro, _bkw_gewichte
    ).items():
        _direkt[_bkw_id] = _direkt.get(_bkw_id, 0.0) + _betrag

    # Erzeuger-Erlös je Gerät (§9 Weg 2, Bauschritt 9) — er liegt
    # komponentenscharf vor und wird deshalb **direkt zugeordnet**, nicht
    # verteilt. Bis zu dieser Stelle landete er im nicht zurechenbaren Rest,
    # obwohl seine Zeile bekannt ist: die Bauschritt-5-Regel lautet „alles
    # komponentenscharf Vorliegende direkt".
    for _f in fakten:
        for _inv_id, _g in (_f.sonstiges.je_geraet or {}).items():
            if _g.einspeise_erloes_euro:
                _direkt[_inv_id] = _direkt.get(_inv_id, 0.0) + _g.einspeise_erloes_euro

    # ⚑ **Gepflegte Monatspositionen tauchen hier seit Bauschritt 7 auf KEINER
    # Seite mehr auf** — weder als Zuschlag (Ertrag) noch als Abzug (Ausgabe).
    # Beide stehen im NENNER der Zeile (`kapitaleinsatz` im ROI-Dashboard, das
    # den Nenner je Zeile liefert). Sie zusätzlich in den Zähler zu verteilen
    # hieße, dieselbe Position zweimal zu verrechnen — bis 2026-08-10 tat der
    # Block hier genau das mit der Ertragsseite, weil sie damals noch im Zähler
    # stand.

    # Betriebskosten je Komponente — **dieselbe** Größe, die oben in Summe vom
    # Zähler abgezogen wurde (N-228). Sie hier ein zweites Mal zu bilden wäre
    # genau die Drift, die diese Zerlegung vermeiden soll.
    for _inv_id, _betrag in betriebskosten_hist_je_inv.items():
        _zeile = _modul_zu_zeile.get(_inv_id, _inv_id)
        _abzug[_zeile] = _abzug.get(_zeile, 0.0) + _betrag

    _zerlegung = zerlege_kumulierten_ertrag(
        gesamt_euro=ertraege_fuer_kapitalrechnung,
        erzeugungs_erloes_euro=_erzeugungs_erloes,
        erzeugungs_gewichte=_erz_gewichte,
        direkt_je_investition=_direkt,
        abzug_je_investition=_abzug,
    )
    fortschritt_je_investition = [
        ErtragJeInvestitionSchema(
            investition_id=_inv_id,
            bisherige_ertraege_euro=round(_betrag, 2),
        )
        for _inv_id, _betrag in sorted(_zerlegung.je_investition.items())
    ]

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
        eigenverbrauchsquote_prozent=round(
            eigenverbrauchsquote_prozent(jahres_eigenverbrauch, jahres_erzeugung), 1
        ),
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
        kapitaleinsatz_euro=round(kapitaleinsatz, 2),
        bisherige_ertraege_euro=round(bisherige_ertraege, 2),
        amortisations_fortschritt_prozent=round(roi_fortschritt, 1),
        amortisation_erreicht=amortisation_erreicht,
        amortisation_prognose_jahr=amortisation_prognose_jahr,
        restlaufzeit_bis_amortisation_monate=restlaufzeit_monate,
        # `betriebskosten_ges` ist genau der Betrag, der oben in
        # `jahres_netto_ertrag` abgezogen wurde — die Restlaufzeit rechnet mit
        # dieser Zahl, also beschreibt der Satz ihre eigene Grundlage.
        amortisation_annahme=annahme_dauer_text(
            betriebskosten_jahr_euro=betriebskosten_ges,
        ),
        ertraege_je_investition=fortschritt_je_investition,
        ertraege_nicht_zurechenbar_euro=_zerlegung.nicht_zurechenbar_euro,
        monatswerte=monatswerte,
        datenquellen=datenquellen,
    )

