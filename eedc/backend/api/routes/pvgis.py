"""
PVGIS API Routes

Integration mit der PVGIS API der EU für PV-Ertragsprognosen.
https://re.jrc.ec.europa.eu/pvg_tools/en/

PVGIS liefert:
- Monatliche PV-Ertragserwartungen basierend auf Standort und Anlagenparametern
- Historische Strahlungsdaten
- Optimale Neigung/Ausrichtung

Struktur:
- PV-Module werden als Investitionen vom Typ "pv-module" erfasst
- Jedes Modul hat eigene Ausrichtung, Neigung und Leistung
- PVGIS Prognose kann pro Modul oder für die gesamte Anlage abgerufen werden
- Die Gesamt-Prognose ist die Summe aller PV-Module
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import httpx

from backend.core.config import settings
from backend.core.exceptions import not_found
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.berechnungen.wr_kappung import zuordne_grenzen
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel, PVGISMonatsprognose
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.pvgis_aktualitaet import pruefe_prognose
from backend.services.pv_orientation import get_pv_neigung
from backend.services.wetter.pvgis_kappung import (
    KappungsModul,
    monats_kappungsfaktoren,
)

# =============================================================================
# PVGIS API Constants
# =============================================================================

# Eine Quelle für die API-Version (`core/config.py::pvgis_api_url`) — sie
# entscheidet über den Strahlungsdatensatz und damit über jede SOLL-Zahl.
PVGIS_BASE_URL = settings.pvgis_api_url

# Standard-Werte für Deutschland
DEFAULT_LOSSES = 14  # Systemverluste in % (Kabel, Wechselrichter, etc.)
DEFAULT_AZIMUTH = 0  # 0 = Süd, -90 = Ost, 90 = West
DEFAULT_TILT = 35    # Typische Dachneigung in Deutschland

# Erzeuger, für die PVGIS ein SOLL rechnen kann (#367). Ein Balkonkraftwerk
# trägt kWp, Neigung und Ausrichtung genau wie ein PV-String — der frühere
# Filter auf `pv-module` war eine Typ-Grenze ohne fachlichen Grund und ließ
# reine BKW-Anlagen mit einem 400er stehen.
PVGIS_ERZEUGER_TYPEN = (
    InvestitionTyp.PV_MODULE.value,
    InvestitionTyp.BALKONKRAFTWERK.value,
)


# =============================================================================
# Pydantic Schemas
# =============================================================================

class PVGISMonthlyData(BaseModel):
    """Monatliche Ertragsdaten von PVGIS."""
    monat: int = Field(..., ge=1, le=12)
    e_m: float = Field(..., description="Monatlicher Ertrag in kWh")
    h_m: float = Field(..., description="Globale Einstrahlung auf Modulebene kWh/m²")
    sd_m: float = Field(..., description="Standardabweichung kWh")


class PVModulPrognose(BaseModel):
    """PVGIS Prognose für ein einzelnes PV-Modul."""
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: str
    ausrichtung_grad: float
    neigung_grad: float
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    monatsdaten: list[PVGISMonthlyData]


class PVGISPrognose(BaseModel):
    """Vollständige PVGIS Prognose für eine Anlage (Summe aller PV-Module)."""
    anlage_id: int
    anlage_name: str

    # Standortdaten (von Anlage)
    latitude: float
    longitude: float

    # Gesamt-Ergebnisse
    gesamt_leistung_kwp: float
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float = Field(..., description="kWh pro kWp")

    # Monatliche Summen
    monatsdaten: list[PVGISMonthlyData]

    # Detail pro PV-Modul
    module: list[PVModulPrognose]

    # Systemparameter
    system_losses: float = Field(..., description="Systemverluste in %")

    # Metadata
    abgerufen_am: datetime
    # Aus der konfigurierten URL abgeleitet statt hart geschrieben: bis v4.0.11
    # stand hier "5.2" als Literal — es war die vierte Stelle, an der die
    # Version dupliziert war, und wäre beim Wechsel auf v5_3 still falsch
    # geworden (gelesen wird das Feld von niemandem, deklariert schon).
    pvgis_version: str = Field(
        default_factory=lambda: settings.pvgis_api_url.rstrip("/").rsplit("/", 1)[-1]
    )
    # Strahlungsdatensatz laut PVGIS-Antwort (z. B. "PVGIS-SARAH3"), None wenn
    # kein Modul abgefragt wurde. Entscheidet über den Neuabruf (#363).
    raddatabase: Optional[str] = None


class GespeichertePrognoseResponse(BaseModel):
    """Response für gespeicherte Prognose."""
    id: int
    anlage_id: int
    abgerufen_am: datetime
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    neigung_grad: float
    ausrichtung_grad: float
    ist_aktiv: bool
    horizont_verwendet: Optional[bool] = False

    class Config:
        from_attributes = True


class HorizontStatusResponse(BaseModel):
    """Status des Horizont-Profils einer Anlage."""
    hat_horizont: bool
    anzahl_punkte: int = 0
    azimut_schrittweite: float = 0
    min_elevation: float = 0
    max_elevation: float = 0
    daten: Optional[list[float]] = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


AUSRICHTUNG_AZIMUT: dict[str, float] = {
    "süd": 0, "sued": 0, "s": 0, "south": 0,
    "südost": -45, "suedost": -45, "so": -45, "southeast": -45,
    "ost": -90, "o": -90, "east": -90,
    "nordost": -135, "no": -135, "northeast": -135,
    "nord": 180, "n": 180, "north": 180,
    "nordwest": 135, "nw": 135, "northwest": 135,
    "west": 90, "w": 90,
    "südwest": 45, "suedwest": 45, "sw": 45, "southwest": 45,
    # Ost-West wird in den PVGIS-Berechnungen separat behandelt (zwei Abfragen,
    # Ost + West). Dieser Wert dient nur als Anzeige-Fallback.
    "ost-west": 0, "ow": 0, "o-w": 0, "east-west": 0,
}


def ausrichtung_zu_azimut(ausrichtung: Optional[str]) -> float:
    """
    Konvertiert Ausrichtungstext zu PVGIS Azimut.

    PVGIS Azimut: 0 = Süd, -90 = Ost, 90 = West, 180/-180 = Nord

    ⚠ Bis v4.0.11 lief hier ein **Substring**-Match über ein Dict in
    Einfüge-Reihenfolge (`if key in ausrichtung_lower`). Der Ein-Buchstaben-
    Schlüssel „s" (Süd) traf damit in „o**s**t" und „we**s**t", „o" (Ost) in
    „n**o**rd" — **11 von 16 Himmelsrichtungen** kamen falsch heraus: Ost, West
    und alle vier Zwischenrichtungen wurden zu **Süd (0°)**, Nord zu Ost.
    Wirksam wurde das überall dort, wo kein exakter `parameter.ausrichtung_grad`
    gepflegt ist (Altbestand, JSON-Import) — die betroffene Anlage bekam eine
    deutlich zu hohe SOLL-Prognose. Kein Test griff die Funktion je (#363).

    Deshalb jetzt ein **exakter** Vergleich auf dem normalisierten Text. Ein
    unbekannter Wert fällt bewusst auf Süd zurück wie bisher: eine Prognose ist
    besser als keine, und der Daten-Checker sieht die Abweichung im PR.
    """
    if not ausrichtung:
        return DEFAULT_AZIMUTH

    # Normalisieren, nicht raten: Groß/Klein, Rand-Leerzeichen und die im
    # Bestand vorkommenden Trenner („Süd-Ost", „Süd Ost") auf eine Form.
    schluessel = ausrichtung.strip().lower().replace(" ", "").replace("_", "-")
    if schluessel in AUSRICHTUNG_AZIMUT:
        return AUSRICHTUNG_AZIMUT[schluessel]

    # „süd-ost" → „südost"; die zusammengesetzten Richtungen stehen ohne
    # Bindestrich in der Tabelle, „ost-west" dagegen MIT — deshalb erst der
    # ungekürzte Versuch oben, dann dieser.
    ohne_trenner = schluessel.replace("-", "")
    return AUSRICHTUNG_AZIMUT.get(ohne_trenner, DEFAULT_AZIMUTH)


def _azimut_zu_richtung(azimut: float) -> str:
    """Konvertiert Azimut-Grad zu Himmelsrichtung."""
    if -22.5 <= azimut < 22.5:
        return "Süd"
    elif 22.5 <= azimut < 67.5:
        return "Südwest"
    elif 67.5 <= azimut < 112.5:
        return "West"
    elif 112.5 <= azimut < 157.5:
        return "Nordwest"
    elif azimut >= 157.5 or azimut < -157.5:
        return "Nord"
    elif -157.5 <= azimut < -112.5:
        return "Nordost"
    elif -112.5 <= azimut < -67.5:
        return "Ost"
    elif -67.5 <= azimut < -22.5:
        return "Südost"
    return "Süd"


async def fetch_pvgis_data(
    latitude: float,
    longitude: float,
    peak_power: float,
    tilt: float,
    azimuth: float,
    losses: float = DEFAULT_LOSSES,
    user_horizon: Optional[list[float]] = None,
) -> dict:
    """
    Ruft Daten von der PVGIS API ab.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        peak_power: Installierte Leistung in kWp
        tilt: Modulneigung in Grad
        azimuth: Azimut (0=Süd)
        losses: Systemverluste in %
        user_horizon: Benutzerdefiniertes Horizontprofil (Elevationswerte ab Nord)

    Returns:
        dict: PVGIS Antwort

    Raises:
        HTTPException: Bei API-Fehlern
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "peakpower": peak_power,
        "angle": tilt,
        "aspect": azimuth,
        "loss": losses,
        "outputformat": "json",
        "pvtechchoice": "crystSi",  # Kristallines Silizium (Standard)
        "mountingplace": "building",  # Dachanlage
        "usehorizon": 1,  # PVGIS DEM-Geländehorizont verwenden
    }

    if user_horizon:
        params["userhorizon"] = ",".join(f"{v:.1f}" for v in user_horizon)

    url = f"{PVGIS_BASE_URL}/PVcalc"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="PVGIS API Timeout - bitte erneut versuchen"
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PVGIS API Fehler: {e.response.status_code}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"PVGIS Anfrage fehlgeschlagen: {str(e)}"
            )


def _ist_ost_west(ausrichtung: Optional[str]) -> bool:
    """Prüft ob eine Ausrichtungsangabe eine Ost-West-Anlage beschreibt."""
    if not ausrichtung:
        return False
    al = ausrichtung.lower().strip()
    return al in ("ost-west", "east-west", "ow", "o-w") or "ost-west" in al or "east-west" in al


def _kappungs_abrufe(
    leistung_kwp: float, tilt: float, ausrichtung: Optional[str], azimuth: float,
) -> list[tuple[float, float, float]]:
    """PVGIS-Abrufe eines Moduls für das Stundenprofil der AC-Kappung.

    Bewusst dieselbe Fallunterscheidung wie `_berechne_pvgis_modul`: eine
    Ost-West-Anlage rechnet PVGIS als zwei halbe Anlagen (Ost -90°, West +90°).
    Wer das Stundenprofil stattdessen aus einer Süd-Abfrage bildete, kappte ein
    Profil, das die Anlage nie hatte — die Mittagsspitze einer Ost-West-Anlage
    ist deutlich flacher.
    """
    if _ist_ost_west(ausrichtung):
        haelfte = leistung_kwp / 2
        return [(haelfte, tilt, -90.0), (haelfte, tilt, 90.0)]
    return [(leistung_kwp, tilt, azimuth)]


def _radiation_db(pvgis_data: dict) -> Optional[str]:
    """Liest den Strahlungsdatensatz aus einer PVGIS-Antwort (`PVGIS-SARAH3`, …).

    Bewusst aus der ANTWORT und nicht aus der konfigurierten API-Version
    abgeleitet: die Version bestimmt den Datensatz zwar, aber eine Konstante
    daneben würde ihn behaupten statt belegen — und PVGIS kann eine Version
    intern weiterdrehen, ohne dass sich die URL ändert. Der Wert entscheidet in
    `services/pvgis_aktualitaet.py`, ob eine gespeicherte Prognose noch auf
    derselben Grundlage steht wie ein frischer Abruf (#363).
    """
    return (pvgis_data.get("inputs", {}).get("meteo_data", {}) or {}).get("radiation_db")


async def _berechne_pvgis_modul(
    latitude: float,
    longitude: float,
    leistung_kwp: float,
    ausrichtung: Optional[str],
    neigung_grad: float,
    system_losses: float,
    user_horizon: Optional[list[float]] = None,
    ausrichtung_grad: Optional[float] = None,
) -> tuple[list[PVGISMonthlyData], float, Optional[str]]:
    """
    Berechnet PVGIS-Prognose für ein PV-Modul.

    Für Ost-West-Anlagen werden zwei separate Abfragen durchgeführt (Ost 50% + West 50%)
    und die Ergebnisse summiert. Das gibt realistische Ertragswerte statt der (zu hohen)
    Süd-Ausrichtung als Fallback.

    Returns:
        (monatsdaten, jahresertrag_kwh, raddatabase)
    """
    if _ist_ost_west(ausrichtung):
        half_kwp = leistung_kwp / 2
        pvgis_ost = await fetch_pvgis_data(latitude, longitude, half_kwp, neigung_grad, -90.0, system_losses, user_horizon)
        pvgis_west = await fetch_pvgis_data(latitude, longitude, half_kwp, neigung_grad, 90.0, system_losses, user_horizon)

        monthly_ost = {m["month"]: m for m in pvgis_ost.get("outputs", {}).get("monthly", {}).get("fixed", [])}
        monthly_west = {m["month"]: m for m in pvgis_west.get("outputs", {}).get("monthly", {}).get("fixed", [])}

        monatsdaten = []
        for month_num in range(1, 13):
            m_o = monthly_ost.get(month_num, {})
            m_w = monthly_west.get(month_num, {})
            e_m = round(m_o.get("E_m", 0) + m_w.get("E_m", 0), 2)
            h_m = round((m_o.get("H(i)_m", 0) + m_w.get("H(i)_m", 0)) / 2, 2)
            sd_m = round(m_o.get("SD_m", 0) + m_w.get("SD_m", 0), 2)
            monatsdaten.append(PVGISMonthlyData(monat=month_num, e_m=e_m, h_m=h_m, sd_m=sd_m))

        jahresertrag_ost = pvgis_ost.get("outputs", {}).get("totals", {}).get("fixed", {}).get("E_y", 0)
        jahresertrag_west = pvgis_west.get("outputs", {}).get("totals", {}).get("fixed", {}).get("E_y", 0)
        # Beide Hälften stammen aus derselben API-Version; die Ost-Antwort steht
        # stellvertretend für beide.
        return monatsdaten, jahresertrag_ost + jahresertrag_west, _radiation_db(pvgis_ost)
    else:
        azimuth = ausrichtung_grad if ausrichtung_grad is not None else ausrichtung_zu_azimut(ausrichtung)
        pvgis_data = await fetch_pvgis_data(latitude, longitude, leistung_kwp, neigung_grad, azimuth, system_losses, user_horizon)

        outputs = pvgis_data.get("outputs", {})
        monthly = outputs.get("monthly", {}).get("fixed", [])
        totals = outputs.get("totals", {}).get("fixed", {})

        monatsdaten = [
            PVGISMonthlyData(
                monat=m["month"],
                e_m=round(m["E_m"], 2),
                h_m=round(m["H(i)_m"], 2),
                sd_m=round(m["SD_m"], 2),
            )
            for m in monthly
        ]
        return monatsdaten, totals.get("E_y", 0), _radiation_db(pvgis_data)


@router.get("/prognose/{anlage_id}", response_model=PVGISPrognose)
async def get_pvgis_prognose(
    anlage_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt PVGIS Ertragsprognose für eine Anlage.

    Summiert die Prognosen aller PV-Module (Investitionen vom Typ "pv-module").
    Verwendet die Koordinaten der Anlage und die Ausrichtung/Neigung jedes Moduls.

    Args:
        anlage_id: ID der Anlage
        system_losses: Systemverluste in % (Standard: 14)

    Returns:
        PVGISPrognose: Monatliche Ertragsprognose für alle Module
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage", anlage_id)

    # Koordinaten prüfen
    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten. Bitte latitude/longitude in den Stammdaten ergänzen."
        )

    # Erzeuger laden — PV-Module UND Balkonkraftwerke (#367). Ein BKW trägt
    # alles, was PVGIS braucht (kWp über `get_erzeuger_kwp`, Neigung und
    # Ausrichtung als eigene Formularfelder); es hier auszuschließen war eine
    # Typ-Grenze, keine fachliche. Zwei andere Prognose-Routen behandeln es seit
    # v4.0.4 gleichberechtigt als String (`prognosen.py`, `solar_prognose.py`).
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ.in_(PVGIS_ERZEUGER_TYPEN))
        .where(aktiv_jetzt())
    )
    # N-266: `alle_erzeuger` ist die UNGEFILTERTE Menge und geht so in
    # `zuordne_grenzen` — nur dort findet ein Modul-Kind die AC-Grenze seines
    # Balkonkraftwerks. `pv_module` ist die gefilterte: ein BKW mit Kindern hat
    # kWp und Ausrichtung abgetreten und bekommt keine eigene PVGIS-Abfrage
    # mehr, sonst stünde sein Ertrag zweimal im Anlagen-SOLL.
    alle_erzeuger = list(result.scalars().all())
    pv_module = erzeuger_traeger(alle_erzeuger)

    if not pv_module:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Keine PV-Module oder Balkonkraftwerke für diese Anlage gefunden. "
                "Bitte zuerst einen Erzeuger als Investition anlegen."
            )
        )

    wechselrichter = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WECHSELRICHTER.value)
    )).scalars().all()
    # F-11: ein DC-gekoppelter Speicher am Träger der Grenze nimmt den Überschuss
    # auf, der sonst weggekappt würde — dann darf gar nicht gekappt werden.
    speicher = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )).scalars().all()
    grenzen = zuordne_grenzen(alle_erzeuger, wechselrichter, speicher)

    # Prognose für jedes Modul abrufen
    module_prognosen: list[PVModulPrognose] = []
    gesamt_monatsdaten: dict[int, dict] = {m: {"e_m": 0.0, "h_m": 0.0, "sd_m": 0.0} for m in range(1, 13)}
    gesamt_jahresertrag = 0.0
    gesamt_leistung = 0.0
    kappungs_module: list[KappungsModul] = []
    roh_prognosen: list[tuple] = []
    raddatabase: Optional[str] = None

    for modul in pv_module:
        # kWp über den SoT-Helper (ADR-002/P3-a): wer die Nennleistung nur im
        # Detail-Feld (`parameter`) gepflegt hat — Import-/Altbestand, #229 —
        # hat in der Spalte NULL stehen. Der frühere Spalten-Direktzugriff ließ
        # das Modul hier komplett aus der Anlagen-Prognose fallen.
        # `get_erzeuger_kwp` dispatcht zusätzlich auf das BKW (Leistung × Anzahl).
        modul_kwp = get_erzeuger_kwp(modul)
        if modul_kwp <= 0:
            continue  # Modul ohne Leistung überspringen

        tilt = get_pv_neigung(modul, default=int(DEFAULT_TILT))

        # Exakten Azimut aus Parameter-JSON bevorzugen (falls vorhanden)
        modul_params = modul.parameter or {}
        exact_azimuth = modul_params.get("ausrichtung_grad")  # float oder None

        # PVGIS abrufen – Ost-West-Anlagen: 2 separate Abfragen (Ost 50% + West 50%)
        modul_monatsdaten, jahresertrag, modul_raddatabase = await _berechne_pvgis_modul(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            leistung_kwp=modul_kwp,
            ausrichtung=modul.ausrichtung,
            neigung_grad=tilt,
            system_losses=system_losses,
            user_horizon=anlage.horizont_daten,
            ausrichtung_grad=exact_azimuth,
        )
        # Alle Module derselben Anlage fragen dieselbe API-Version; der erste
        # gelieferte Wert steht für die ganze Prognose.
        raddatabase = raddatabase or modul_raddatabase

        azimuth = exact_azimuth if exact_azimuth is not None else ausrichtung_zu_azimut(modul.ausrichtung)
        grenze_kw, grenz_id = grenzen.get(modul.id, (None, None))
        roh_prognosen.append((modul, modul_kwp, tilt, azimuth, modul_monatsdaten, jahresertrag))
        kappungs_module.append(KappungsModul(
            id=modul.id,
            kwp=modul_kwp,
            grenze_kw=grenze_kw,
            grenz_id=grenz_id,
            abrufe=_kappungs_abrufe(modul_kwp, tilt, modul.ausrichtung, azimuth),
        ))

    # #354/#367: Die AC-Grenze des Wechselrichters wirkt stündlich, die
    # PVGIS-Monatssumme kennt keine Stunden. Der Faktor kommt deshalb aus einem
    # eigenen `seriescalc`-Profil derselben Anlage — nur wenn überhaupt eine
    # Grenze gepflegt ist, sonst wird PVGIS gar nicht zusätzlich gefragt.
    faktoren = await monats_kappungsfaktoren(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        module=kappungs_module,
        losses=system_losses,
        user_horizon=anlage.horizont_daten,
    )

    for modul, modul_kwp, tilt, azimuth, modul_monatsdaten, jahresertrag in roh_prognosen:
        modul_faktoren = faktoren.get(modul.id)
        if modul_faktoren:
            modul_monatsdaten = [
                PVGISMonthlyData(
                    monat=md.monat,
                    e_m=round(md.e_m * modul_faktoren[md.monat - 1], 2),
                    h_m=md.h_m,   # Einstrahlung ist ungekappt — der Wechselrichter
                    sd_m=md.sd_m,  # begrenzt die Abgabe, nicht die Sonne
                )
                for md in modul_monatsdaten
            ]
            jahresertrag = sum(md.e_m for md in modul_monatsdaten)

        # Zu Gesamt addieren
        for md in modul_monatsdaten:
            gesamt_monatsdaten[md.monat]["e_m"] += md.e_m
            gesamt_monatsdaten[md.monat]["h_m"] = md.h_m  # Einstrahlung gleich für alle Module am Standort
            gesamt_monatsdaten[md.monat]["sd_m"] += md.sd_m

        spezifischer_ertrag = jahresertrag / modul_kwp if modul_kwp > 0 else 0

        module_prognosen.append(PVModulPrognose(
            investition_id=modul.id,
            bezeichnung=modul.bezeichnung,
            leistung_kwp=modul_kwp,
            ausrichtung=modul.ausrichtung or _azimut_zu_richtung(azimuth),
            ausrichtung_grad=azimuth,
            neigung_grad=tilt,
            jahresertrag_kwh=round(jahresertrag, 2),
            spezifischer_ertrag_kwh_kwp=round(spezifischer_ertrag, 2),
            monatsdaten=modul_monatsdaten
        ))

        gesamt_jahresertrag += jahresertrag
        gesamt_leistung += modul_kwp

    # Gesamt-Monatsdaten zusammenstellen
    gesamt_monatsdaten_list = [
        PVGISMonthlyData(
            monat=m,
            e_m=round(gesamt_monatsdaten[m]["e_m"], 2),
            h_m=round(gesamt_monatsdaten[m]["h_m"], 2),
            sd_m=round(gesamt_monatsdaten[m]["sd_m"], 2)
        )
        for m in range(1, 13)
    ]

    spezifischer_ertrag_gesamt = gesamt_jahresertrag / gesamt_leistung if gesamt_leistung > 0 else 0

    return PVGISPrognose(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        gesamt_leistung_kwp=round(gesamt_leistung, 2),
        jahresertrag_kwh=round(gesamt_jahresertrag, 2),
        spezifischer_ertrag_kwh_kwp=round(spezifischer_ertrag_gesamt, 2),
        monatsdaten=gesamt_monatsdaten_list,
        module=module_prognosen,
        system_losses=system_losses,
        abgerufen_am=datetime.now(),
        raddatabase=raddatabase,
    )


@router.get("/modul/{investition_id}")
async def get_pvgis_modul_prognose(
    investition_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt PVGIS Ertragsprognose für ein einzelnes PV-Modul.

    Args:
        investition_id: ID der PV-Modul-Investition
        system_losses: Systemverluste in %

    Returns:
        dict: Prognose für das Modul
    """
    # Investition laden
    result = await db.execute(
        select(Investition).where(Investition.id == investition_id)
    )
    modul = result.scalar_one_or_none()

    if not modul:
        raise not_found("Investition", investition_id)

    if modul.typ not in PVGIS_ERZEUGER_TYPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Investition ist kein PV-Erzeuger (Typ: {modul.typ})"
        )

    # kWp über den SoT-Helper (ADR-002/P3-a): mit dem Spalten-Direktzugriff
    # bekam ein nur im `parameter` gepflegtes Modul (#229) hier einen harten
    # 400er — für eine Nennleistung, die gepflegt ist. `get_erzeuger_kwp`
    # dispatcht zusätzlich auf das BKW (Leistung × Anzahl, #367).
    modul_kwp = get_erzeuger_kwp(modul)
    if modul_kwp <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erzeuger hat keine Leistung (kWp) definiert"
        )

    # Anlage für Koordinaten laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == modul.anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage or not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten"
        )

    tilt = get_pv_neigung(modul, default=int(DEFAULT_TILT))

    # Exakten Azimut aus Parameter-JSON bevorzugen (falls vorhanden)
    modul_params = modul.parameter or {}
    exact_azimuth = modul_params.get("ausrichtung_grad")  # float oder None

    # PVGIS abrufen – Ost-West-Anlagen: 2 separate Abfragen (Ost 50% + West 50%)
    monatsdaten_list, jahresertrag, _raddb = await _berechne_pvgis_modul(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        leistung_kwp=modul_kwp,
        ausrichtung=modul.ausrichtung,
        neigung_grad=tilt,
        system_losses=system_losses,
        user_horizon=anlage.horizont_daten,
        ausrichtung_grad=exact_azimuth,
    )

    azimuth = exact_azimuth if exact_azimuth is not None else ausrichtung_zu_azimut(modul.ausrichtung)

    # #354/#367: dieselbe AC-Kappung wie in der Anlagen-Prognose. Der Einzel-
    # Endpunkt sieht nur EIN Modul — teilen sich mehrere Strings einen
    # Wechselrichter, kann er ihre gemeinsame Grenze nicht auflösen. Er kappt
    # deshalb nur, wenn dieses Modul der einzige Erzeuger an seiner Grenze ist;
    # sonst bliebe die Zahl hier eine andere als in der Anlagen-Sicht.
    wechselrichter = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == modul.anlage_id)
        .where(Investition.typ == InvestitionTyp.WECHSELRICHTER.value)
    )).scalars().all()
    geschwister = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == modul.anlage_id)
        .where(Investition.typ.in_(PVGIS_ERZEUGER_TYPEN))
        .where(aktiv_jetzt())
    )).scalars().all()
    speicher = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == modul.anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )).scalars().all()
    grenzen = zuordne_grenzen(geschwister, wechselrichter, speicher)
    grenze_kw, grenz_id = grenzen.get(modul.id, (None, None))
    teilt_sich_die_grenze = sum(
        1 for g in geschwister if grenzen.get(g.id, (None, None))[1] == grenz_id
    ) > 1 if grenz_id else False

    if grenze_kw and not teilt_sich_die_grenze:
        faktoren = await monats_kappungsfaktoren(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            module=[KappungsModul(
                id=modul.id,
                kwp=modul_kwp,
                grenze_kw=grenze_kw,
                grenz_id=grenz_id,
                abrufe=_kappungs_abrufe(modul_kwp, tilt, modul.ausrichtung, azimuth),
            )],
            losses=system_losses,
            user_horizon=anlage.horizont_daten,
        )
        modul_faktoren = faktoren.get(modul.id)
        if modul_faktoren:
            monatsdaten_list = [
                PVGISMonthlyData(
                    monat=md.monat,
                    e_m=round(md.e_m * modul_faktoren[md.monat - 1], 2),
                    h_m=md.h_m,
                    sd_m=md.sd_m,
                )
                for md in monatsdaten_list
            ]
            jahresertrag = sum(md.e_m for md in monatsdaten_list)

    spezifischer_ertrag = jahresertrag / modul_kwp if modul_kwp > 0 else 0

    return {
        "investition_id": modul.id,
        "bezeichnung": modul.bezeichnung,
        "leistung_kwp": modul_kwp,
        "ausrichtung": modul.ausrichtung or _azimut_zu_richtung(azimuth),
        "ausrichtung_grad": azimuth,
        "neigung_grad": tilt,
        "jahresertrag_kwh": round(jahresertrag, 2),
        "spezifischer_ertrag_kwh_kwp": round(spezifischer_ertrag, 2),
        "monatsdaten": [
            {"monat": m.monat, "e_m": m.e_m, "h_m": m.h_m, "sd_m": m.sd_m}
            for m in monatsdaten_list
        ],
        "system_losses": system_losses,
        "standort": {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude
        },
        "abgerufen_am": datetime.now().isoformat()
    }


@router.get("/optimum/{anlage_id}")
async def get_pvgis_optimum(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Ermittelt die optimale Neigung und Ausrichtung für den Standort.

    Args:
        anlage_id: ID der Anlage (für Koordinaten)

    Returns:
        dict: Optimale Parameter für maximalen Jahresertrag
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage", anlage_id)

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten."
        )

    # PVGIS mit optimalem Winkel (1 kWp Referenz)
    params = {
        "lat": anlage.latitude,
        "lon": anlage.longitude,
        "peakpower": 1.0,  # Referenz 1 kWp
        "loss": DEFAULT_LOSSES,
        "outputformat": "json",
        "pvtechchoice": "crystSi",
        "mountingplace": "building",
        "optimalangles": 1,  # Optimale Winkel berechnen
        "usehorizon": 1,  # PVGIS DEM-Geländehorizont verwenden
    }

    if anlage.horizont_daten:
        params["userhorizon"] = ",".join(f"{v:.1f}" for v in anlage.horizont_daten)

    url = f"{PVGIS_BASE_URL}/PVcalc"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PVGIS API Fehler: {str(e)}"
            )

    inputs = data.get("inputs", {}).get("mounting_system", {}).get("fixed", {})
    outputs = data.get("outputs", {}).get("totals", {}).get("fixed", {})

    optimal_tilt = inputs.get("slope", {}).get("value", DEFAULT_TILT)
    optimal_azimuth = inputs.get("azimuth", {}).get("value", DEFAULT_AZIMUTH)
    optimal_ertrag_pro_kwp = outputs.get("E_y", 0)

    return {
        "anlage_id": anlage.id,
        "anlage_name": anlage.anlagenname,
        "standort": {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude
        },
        "optimal": {
            "neigung_grad": round(optimal_tilt, 1),
            "azimut_grad": round(optimal_azimuth, 1),
            "azimut_richtung": _azimut_zu_richtung(optimal_azimuth),
            "spezifischer_ertrag_kwh_kwp": round(optimal_ertrag_pro_kwp, 2)
        },
        "hinweis": "Die optimale Ausrichtung bezieht sich auf eine nach Süden ausgerichtete, freistehende Anlage. Dachneigung und -ausrichtung sind oft vorgegeben."
    }


# =============================================================================
# Speichern und Laden von Prognosen
# =============================================================================

@router.post("/prognose/{anlage_id}/speichern", response_model=GespeichertePrognoseResponse)
async def speichere_pvgis_prognose(
    anlage_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft PVGIS Prognose ab und speichert sie in der Datenbank.

    Deaktiviert vorherige aktive Prognosen für diese Anlage.

    Args:
        anlage_id: ID der Anlage
        system_losses: Systemverluste in %

    Returns:
        GespeichertePrognoseResponse: Die gespeicherte Prognose
    """
    # Prognose abrufen
    prognose = await get_pvgis_prognose(
        anlage_id=anlage_id,
        system_losses=system_losses,
        db=db
    )

    # Vorherige aktive Prognosen deaktivieren
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
    )
    for alte_prognose in result.scalars().all():
        alte_prognose.ist_aktiv = False

    # Die Deaktivierung muss VOR dem Insert der neuen aktiven Prognose in der DB
    # stehen: seit A17 trägt `pvgis_prognosen` einen partiellen Unique-Index auf
    # (anlage_id) WHERE ist_aktiv = 1. Ohne dieses Flush ordnet die Unit of Work
    # den INSERT vor die UPDATEs und der Index schlägt zu — ein DB-Fehler bei einer
    # völlig korrekten Operation. Das Flush macht die Reihenfolge explizit statt
    # sie der SQLAlchemy-Sortierung zu überlassen.
    await db.flush()

    # Monatswerte als JSON vorbereiten (Gesamt-Summe aller Module)
    monatswerte = [
        {"monat": m.monat, "e_m": m.e_m, "h_m": m.h_m, "sd_m": m.sd_m}
        for m in prognose.monatsdaten
    ]

    # Per-Modul-Daten für genaue SOLL-Berechnung im String-Vergleich (v2.3.2)
    # Ohne diese Daten wird im Cockpit proportional nach kWp verteilt (ungenau bei
    # unterschiedlichen Ausrichtungen wie Ost-West vs. Süd).
    module_monatswerte_data = {
        str(m.investition_id): [
            {"monat": md.monat, "e_m": md.e_m, "h_m": md.h_m, "sd_m": md.sd_m}
            for md in m.monatsdaten
        ]
        for m in prognose.module
    }

    # Gewichtete Durchschnittswerte für Speicherung berechnen
    gesamt_neigung = 0.0
    gesamt_azimut = 0.0
    # `prog_modul` läuft über PVModulPrognose-Pydantic-Objekte, NICHT über
    # Investitionen — dieselbe Datei benutzt `modul` sonst durchgehend für
    # Investitionen. Der eigene Name hält die beiden Bedeutungen auseinander
    # (A24-2): `.leistung_kwp` ist hier ein Response-Feld, kein DB-Kennwert,
    # und darf deshalb nicht über die SoT-Helper laufen.
    for prog_modul in prognose.module:
        gewicht = prog_modul.leistung_kwp / prognose.gesamt_leistung_kwp if prognose.gesamt_leistung_kwp > 0 else 0
        gesamt_neigung += prog_modul.neigung_grad * gewicht
        gesamt_azimut += prog_modul.ausrichtung_grad * gewicht

    # Horizont-Status prüfen
    result_anlage = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result_anlage.scalar_one_or_none()
    hat_horizont = bool(anlage and anlage.horizont_daten)

    # Neue Prognose erstellen
    neue_prognose = PVGISPrognoseModel(
        anlage_id=anlage_id,
        latitude=prognose.latitude,
        longitude=prognose.longitude,
        neigung_grad=round(gesamt_neigung, 1),
        ausrichtung_grad=round(gesamt_azimut, 1),
        system_losses=prognose.system_losses,
        jahresertrag_kwh=prognose.jahresertrag_kwh,
        spezifischer_ertrag_kwh_kwp=prognose.spezifischer_ertrag_kwh_kwp,
        gesamt_leistung_kwp=round(prognose.gesamt_leistung_kwp, 3),
        monatswerte=monatswerte,
        module_monatswerte=module_monatswerte_data,
        horizont_verwendet=hat_horizont,
        raddatabase=prognose.raddatabase,
        ist_aktiv=True
    )

    db.add(neue_prognose)
    await db.flush()

    # Normalisierte Monatsprognosen erstellen
    for m in prognose.monatsdaten:
        monats_prognose = PVGISMonatsprognose(
            prognose_id=neue_prognose.id,
            monat=m.monat,
            ertrag_kwh=m.e_m,
            einstrahlung_kwh_m2=m.h_m,
            standardabweichung_kwh=m.sd_m
        )
        db.add(monats_prognose)

    await db.flush()
    await db.refresh(neue_prognose)

    return neue_prognose


@router.get("/prognose/{anlage_id}/gespeichert", response_model=list[GespeichertePrognoseResponse])
async def liste_gespeicherte_prognosen(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Listet alle gespeicherten Prognosen für eine Anlage auf.
    """
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .order_by(PVGISPrognoseModel.abgerufen_am.desc())
    )
    return result.scalars().all()


@router.get("/prognose/{anlage_id}/aktiv")
async def get_aktive_prognose(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt die aktive Prognose für eine Anlage zurück.
    """
    prognose = await lade_aktive_prognose(db, anlage_id)

    if not prognose:
        return None

    # Per-Modul-Infos aufbauen (für Multi-String-Anzeige im Frontend)
    module_info: list[dict] = []
    if prognose.module_monatswerte:
        inv_ids = [int(k) for k in prognose.module_monatswerte.keys()]
        result_inv = await db.execute(
            select(Investition).where(Investition.id.in_(inv_ids))
        )
        inv_by_id = {inv.id: inv for inv in result_inv.scalars().all()}

        for inv_id_str, monatsdaten in prognose.module_monatswerte.items():
            inv_id = int(inv_id_str)
            inv = inv_by_id.get(inv_id)
            # kWp über den Typ-DISPATCHER (ADR-002/P3-a): sonst zeigt die
            # gespeicherte Prognose für ein nur im `parameter` gepflegtes
            # Modul (#229) „0,0 kWp" — und für ein Balkonkraftwerk aus dem
            # Einrichtungsassistenten ebenso (F-32). `get_pv_kwp` allein kennt
            # die BKW-Form (Anzahl × Wp) nicht; der Kommentar behauptete bis
            # F-32 „den SoT-Helper" und nannte den engeren.
            leistung_kwp = get_erzeuger_kwp(inv) if inv else 0.0
            neigung = float(inv.neigung_grad) if inv and inv.neigung_grad is not None else 0.0
            ausrichtung_str = (inv.ausrichtung if inv and inv.ausrichtung else "Süd")
            jahres_kwh = sum(float(m.get("e_m", 0) or 0) for m in monatsdaten)
            module_info.append({
                "investition_id": inv_id,
                "bezeichnung": (inv.bezeichnung if inv else f"Modul {inv_id}"),
                "leistung_kwp": leistung_kwp,
                "neigung_grad": neigung,
                "ausrichtung_richtung": ausrichtung_str,
                "jahresertrag_kwh": round(jahres_kwh, 1),
                "monatsdaten": monatsdaten,
            })
        # Stabile Reihenfolge: größte Module zuerst
        module_info.sort(key=lambda m: m["leistung_kwp"], reverse=True)

    # Passt die Prognose noch zur Anlage? Aus demselben SoT wie der nächtliche
    # Neuabruf (#363) — die Einstellungs-Kachel meldete früher stattdessen das
    # ALTER („Letzter Abruf vor N Tagen"). Das war eine Warnung ohne Gegenstand:
    # PVGIS rechnet auf einem festen Klimamittel, eine sieben Tage alte Prognose
    # ist so gut wie eine von heute. Falsch wird sie erst durch eine Änderung.
    abweichung = await pruefe_prognose(db, anlage_id)

    return {
        "id": prognose.id,
        "anlage_id": prognose.anlage_id,
        "abgerufen_am": prognose.abgerufen_am,
        "passt_zur_anlage": abweichung is None,
        "abweichung_text": abweichung.text if abweichung else None,
        "latitude": prognose.latitude,
        "longitude": prognose.longitude,
        "neigung_grad": prognose.neigung_grad,
        "ausrichtung_grad": prognose.ausrichtung_grad,
        "ausrichtung_richtung": _azimut_zu_richtung(prognose.ausrichtung_grad),
        "system_losses": prognose.system_losses,
        "jahresertrag_kwh": prognose.jahresertrag_kwh,
        "spezifischer_ertrag_kwh_kwp": prognose.spezifischer_ertrag_kwh_kwp,
        "monatswerte": prognose.monatswerte,
        "module": module_info,
        "horizont_verwendet": prognose.horizont_verwendet or False,
    }


@router.put("/prognose/{prognose_id}/aktivieren")
async def aktiviere_prognose(
    prognose_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktiviert eine gespeicherte Prognose.
    """
    result = await db.execute(
        select(PVGISPrognoseModel).where(PVGISPrognoseModel.id == prognose_id)
    )
    prognose = result.scalar_one_or_none()

    if not prognose:
        raise not_found("Prognose", prognose_id)

    # Andere Prognosen der Anlage deaktivieren
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == prognose.anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
    )
    for alte_prognose in result.scalars().all():
        alte_prognose.ist_aktiv = False

    # Erst deaktivieren, dann aktivieren — in zwei Flushes. Der partielle
    # Unique-Index (A17) verbietet zwei aktive Prognosen je Anlage; in EINEM Flush
    # sortiert die Unit of Work die UPDATEs nach Primärschlüssel, und genau der
    # Kernfall dieses Endpoints (eine ÄLTERE Prognose aktivieren, also eine mit
    # kleinerer id) würde das Aktivieren vor das Deaktivieren stellen und mit
    # einem IntegrityError enden.
    await db.flush()

    prognose.ist_aktiv = True
    await db.flush()

    return {"message": "Prognose aktiviert", "id": prognose_id}


@router.delete("/prognose/{prognose_id}")
async def loesche_prognose(
    prognose_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Löscht eine gespeicherte Prognose.
    """
    result = await db.execute(
        select(PVGISPrognoseModel).where(PVGISPrognoseModel.id == prognose_id)
    )
    prognose = result.scalar_one_or_none()

    if not prognose:
        raise not_found("Prognose", prognose_id)

    await db.delete(prognose)
    return {"message": "Prognose gelöscht", "id": prognose_id}


# =============================================================================
# Horizont-Profil Endpoints
# =============================================================================

def _parse_horizont_datei(content: str) -> list[float]:
    """
    Parst eine PVGIS Horizont-Textdatei.

    Format: Zeilen mit azimuth(°) und elevation(°), Whitespace-getrennt.
    Kommentarzeilen (#) und Leerzeilen werden ignoriert.
    """
    punkte: list[tuple[float, float]] = []

    for line in content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            azimuth = float(parts[0])
            elevation = float(parts[1])
        except ValueError:
            continue

        if not (0 <= azimuth < 360):
            continue
        elevation = max(0.0, min(90.0, elevation))
        punkte.append((azimuth, elevation))

    if len(punkte) < 4:
        raise ValueError(f"Zu wenige Datenpunkte ({len(punkte)}). Mindestens 4 erwartet.")

    # Nach Azimut sortieren und nur Elevationswerte als Flat-Liste zurückgeben
    punkte.sort(key=lambda p: p[0])
    return [round(p[1], 2) for p in punkte]


def _horizont_status(daten: Optional[list]) -> HorizontStatusResponse:
    """Erzeugt HorizontStatusResponse aus gespeicherten Daten."""
    if not daten:
        return HorizontStatusResponse(hat_horizont=False)

    anzahl = len(daten)
    return HorizontStatusResponse(
        hat_horizont=True,
        anzahl_punkte=anzahl,
        azimut_schrittweite=round(360 / anzahl, 1) if anzahl > 0 else 0,
        min_elevation=round(min(daten), 1),
        max_elevation=round(max(daten), 1),
        daten=daten,
    )


@router.get("/horizont/{anlage_id}", response_model=HorizontStatusResponse)
async def get_horizont(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gibt den Horizont-Status einer Anlage zurück."""
    anlage = await db.get(Anlage, anlage_id)
    if not anlage:
        raise not_found("Anlage")
    return _horizont_status(anlage.horizont_daten)


@router.post("/horizont/{anlage_id}/upload", response_model=HorizontStatusResponse)
async def upload_horizont_datei(
    anlage_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Lädt eine PVGIS Horizont-Datei hoch und speichert das Profil.

    Akzeptiert das PVGIS-Textformat mit azimuth/elevation Spalten.
    """
    anlage = await db.get(Anlage, anlage_id)
    if not anlage:
        raise not_found("Anlage")

    try:
        content = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Datei muss eine UTF-8 Textdatei sein")

    try:
        daten = _parse_horizont_datei(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    anlage.horizont_daten = daten
    await db.commit()

    return _horizont_status(daten)


@router.post("/horizont/{anlage_id}/abrufen", response_model=HorizontStatusResponse)
async def abrufe_horizont_von_pvgis(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Ruft das Horizontprofil vom PVGIS-Server ab (DEM-Geländedaten).

    Nutzt die Koordinaten der Anlage, um das Geländeprofil automatisch zu laden.
    """
    anlage = await db.get(Anlage, anlage_id)
    if not anlage:
        raise not_found("Anlage")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Geokoordinaten")

    url = f"{PVGIS_BASE_URL}/printhorizon"
    params = {
        "lat": anlage.latitude,
        "lon": anlage.longitude,
        "outputformat": "json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="PVGIS API Timeout")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"PVGIS API Fehler: {str(e)}")

    # PVGIS liefert: outputs.horizon_profile = [{A: azimuth, H_hor: elevation}, ...]
    # (Ältere PVGIS-Versionen nutzten "horizon" statt "horizon_profile")
    outputs = data.get("outputs", {})
    horizon_data = outputs.get("horizon_profile", []) or outputs.get("horizon", [])
    if not horizon_data:
        raise HTTPException(status_code=502, detail="PVGIS lieferte keine Horizontdaten")

    daten = [round(float(p.get("H_hor", 0)), 2) for p in horizon_data]

    anlage.horizont_daten = daten
    await db.commit()

    return _horizont_status(daten)


@router.delete("/horizont/{anlage_id}")
async def loesche_horizont(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Löscht das benutzerdefinierte Horizont-Profil einer Anlage."""
    anlage = await db.get(Anlage, anlage_id)
    if not anlage:
        raise not_found("Anlage")

    anlage.horizont_daten = None
    await db.commit()

    return {"message": "Horizontprofil gelöscht"}
