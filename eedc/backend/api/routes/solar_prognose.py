"""
Solar-Prognose API Routes

Direkte PV-Ertragsprognose basierend auf Open-Meteo Solar API.
Nutzt GTI (Global Tilted Irradiance) für geneigte PV-Module.

Angezeigt wird der **eedc-korrigierte** Tageswert (``eedc_kwh``, Prognose-Kanon)
mit Fallback auf den OpenMeteo-Rohwert (``pv_ertrag_kwh``). Der Rohwert bleibt
in der Response — er ist die Basis der Korrektur und die „OpenMeteo"-Spalte im
Prognosen-Vergleich; ergänzt, nicht ersetzt. ``anzeige_quelle`` sagt, welche
Werte die Anzeige tatsächlich zeigt (Beschriftung muss zur Zahl passen).
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.solar_forecast_service import (
    get_solar_prognose,
    get_multi_string_prognose,
    PVStringConfig,
)
from backend.services.prognose_kanon import kanon_days, kanon_tagesprognose
from backend.services.pv_orientation import resolve_system_losses

logger = logging.getLogger(__name__)

router = APIRouter()

# Werte-Quelle der Tages-Anzeige (Balken, Tabelle, KPI). Kein Wettermodell —
# das steht je Tag in `datenquelle`.
ANZEIGE_QUELLE_EEDC = "eedc"
ANZEIGE_QUELLE_OPENMETEO = "openmeteo"
ANZEIGE_QUELLE_GEMISCHT = "gemischt"


# =============================================================================
# Helpers
# =============================================================================

def _aggregate_string_tageswerte(
    string_prognosen: list[dict],
) -> list["SolarPrognoseTagSchema"]:
    """Aggregiert Tageswerte aus mehreren Strings zu einer Gesamtliste.

    GTI (N34): **kWp-gewichtetes** Mittel über die Strings = die effektive
    Einstrahlung auf die Modulfläche der Anlage. Vorher stand hier das
    ungewichtete arithmetische Mittel (``Σ gti / Anzahl Strings``), während der
    Ertrag daneben summiert wurde — bei gemischten Orientierungen zählte damit
    ein 0,8-kWp-Balkonmodul genauso viel wie ein 12-kWp-Süddach, und die Spalte
    passte zu keiner Größe der Zeile. Gewichtet ist sie konsistent zur
    Ertragssumme (``Ertrag ≈ GTI × kWp × (1 − Verluste)``, linear in kWp).
    Ohne kWp-Angaben bleibt es beim ungewichteten Mittel; liegt gar kein GTI
    vor, steht 0 → die Anzeige zeigt „—".
    """
    if not string_prognosen:
        return []

    tageswerte = []
    first_string = string_prognosen[0]["tageswerte"]
    for i, day in enumerate(first_string):
        total_ertrag = sum(
            sp["tageswerte"][i]["pv_ertrag_kwh"]
            for sp in string_prognosen
            if i < len(sp["tageswerte"])
        )
        beitraege = [
            (sp["tageswerte"][i]["gti_kwh_m2"], sp.get("kwp") or 0.0)
            for sp in string_prognosen
            if i < len(sp["tageswerte"])
        ]
        kwp_summe = sum(kwp for _, kwp in beitraege)
        if kwp_summe > 0:
            total_gti = sum(gti * kwp for gti, kwp in beitraege) / kwp_summe
        elif beitraege:
            total_gti = sum(gti for gti, _ in beitraege) / len(beitraege)
        else:
            total_gti = 0.0

        total_morgens = sum(
            sp["tageswerte"][i].get("pv_ertrag_morgens_kwh") or 0
            for sp in string_prognosen
            if i < len(sp["tageswerte"])
        )
        total_nachmittags = sum(
            sp["tageswerte"][i].get("pv_ertrag_nachmittags_kwh") or 0
            for sp in string_prognosen
            if i < len(sp["tageswerte"])
        )
        # Wetter-Daten vom ersten String übernehmen (identischer Standort)
        tageswerte.append(SolarPrognoseTagSchema(
            datum=day["datum"],
            pv_ertrag_kwh=round(total_ertrag, 2),
            gti_kwh_m2=round(total_gti, 2),
            ghi_kwh_m2=0,
            sonnenstunden=day.get("sonnenstunden", 0),
            temperatur_max_c=day.get("temperatur_max_c"),
            temperatur_min_c=day.get("temperatur_min_c"),
            bewoelkung_prozent=day.get("bewoelkung_prozent"),
            niederschlag_mm=day.get("niederschlag_mm"),
            schnee_cm=day.get("schnee_cm"),
            wetter_symbol=day.get("wetter_symbol", "unknown"),
            pv_ertrag_morgens_kwh=round(total_morgens, 2) if total_morgens > 0 else None,
            pv_ertrag_nachmittags_kwh=round(total_nachmittags, 2) if total_nachmittags > 0 else None,
            datenquelle=day.get("datenquelle", "best_match"),
        ))
    return tageswerte


async def _mit_eedc_werten(
    db, anlage, tageswerte: list["SolarPrognoseTagSchema"], tage: int,
) -> tuple[Optional[float], Optional[float], str]:
    """Hängt die eedc-korrigierten Tageswerte an ``tageswerte`` (in-place).

    Rückgabe: ``(summe, durchschnitt, anzeige_quelle)`` über die tatsächlich
    angezeigten Werte (``eedc_kwh ?? pv_ertrag_kwh``).

    Warum hier und nicht im Frontend: Balken und 14-Tage-Tabelle iterieren über
    ``tageswerte`` — käme der korrigierte Wert aus einer zweiten Antwort, müsste
    er über das Datum gejoint werden, und genau solche Joins sind in diesem
    Projekt wiederholt zur Drift-Quelle geworden ([[feedback_aggregations_drift]]).

    Kosten: KEIN zusätzlicher OpenMeteo-Abruf — der Kanon fragt dieselben
    GTI-Cache-Keys ab wie der Fan-out oben (Key =
    ``lat:lon:neigung:ausrichtung:days:model``, ohne kWp). Seit E15/A29 ist
    ``days`` darin der Modell-Snapshot statt des angefragten Horizonts, der
    Treffer also unabhängig davon, ob hier 2, 7 oder 14 Tage angefragt sind.
    Ausnahme: bei gewähltem Wettermodell ≠ „auto" nutzt der Kanon (noch) das
    Standardmodell → eigener Key-Satz. Das ist bewusst offen (Wettermodell in
    den Kanon durchreichen ändert auch die HA-Sensor-Werte → eigenes Päckchen).
    """
    kanon = None
    try:
        kanon = await kanon_tagesprognose(
            db, anlage, days=kanon_days(tage),
            # Interaktiver User-Request → kein Random-Jitter (R18-13).
            skip_jitter=True,
        )
    except Exception as e:  # pragma: no cover — Soft-fail, Anzeige bleibt OM
        logger.warning("Kanon-Prognose für /solar-prognose fehlgeschlagen: %s", e)

    kanon_by_datum = {
        t.datum: t for t in (kanon.tage if kanon else []) if t is not None
    }
    mit_eedc = 0
    for tw in tageswerte:
        kt = kanon_by_datum.get(tw.datum)
        if kt is None or kt.eedc_kwh is None:
            continue
        tw.eedc_kwh = kt.eedc_kwh
        mit_eedc += 1
        # VM/NM nur gemeinsam ersetzen — sonst summierten korrigierter Tageswert
        # und rohe Hälften nicht mehr auf (der Schätzpfad des Kanons liefert
        # einen Tageswert ohne Stundenprofil und damit ohne VM/NM).
        if kt.vm_kwh is not None and kt.nm_kwh is not None:
            tw.eedc_morgens_kwh = kt.vm_kwh
            tw.eedc_nachmittags_kwh = kt.nm_kwh

    if not tageswerte:
        return None, None, ANZEIGE_QUELLE_OPENMETEO
    quelle = (
        ANZEIGE_QUELLE_EEDC if mit_eedc == len(tageswerte)
        else ANZEIGE_QUELLE_OPENMETEO if mit_eedc == 0
        else ANZEIGE_QUELLE_GEMISCHT
    )
    if mit_eedc == 0:
        return None, None, quelle
    summe = sum(
        (tw.eedc_kwh if tw.eedc_kwh is not None else tw.pv_ertrag_kwh)
        for tw in tageswerte
    )
    return round(summe, 1), round(summe / len(tageswerte), 2), quelle


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SolarPrognoseTagSchema(BaseModel):
    """Prognose für einen Tag."""
    datum: str
    pv_ertrag_kwh: float
    gti_kwh_m2: float = Field(
        description=(
            "Global Tilted Irradiance auf der Modulfläche. Bei mehreren "
            "Ausrichtungen kWp-gewichtetes Mittel über die Strings (N34)"
        )
    )
    ghi_kwh_m2: float = Field(description="Global Horizontal Irradiance (Vergleich)")
    sonnenstunden: float
    temperatur_max_c: float | None
    temperatur_min_c: float | None
    bewoelkung_prozent: int | None
    niederschlag_mm: float | None
    schnee_cm: float | None
    wetter_symbol: str = "unknown"
    pv_ertrag_morgens_kwh: float | None = None
    pv_ertrag_nachmittags_kwh: float | None = None
    datenquelle: str = "best_match"
    # eedc-korrigierte Werte (Prognose-Kanon). `None` = für diesen Tag lag keine
    # Korrektur vor → die Anzeige fällt auf `pv_ertrag_kwh` (OpenMeteo roh)
    # zurück. Die Rohwerte oben bleiben unverändert erhalten.
    eedc_kwh: float | None = Field(
        None, description="eedc-korrigierter Tagesertrag (Kanon) — Anzeige-Wert"
    )
    eedc_morgens_kwh: float | None = None
    eedc_nachmittags_kwh: float | None = None


class StringPrognoseSchema(BaseModel):
    """Prognose für einen einzelnen String."""
    name: str
    kwp: float
    neigung: int
    ausrichtung: int
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[dict]


class SolarPrognoseResponse(BaseModel):
    """Response für Solar-Prognose."""
    anlage_id: int
    anlagenname: str
    kwp_gesamt: float
    neigung: int = Field(description="Durchschnittliche/Haupt-Neigung in Grad")
    ausrichtung: int = Field(description="Durchschnittliche/Haupt-Ausrichtung (0=Süd)")
    system_losses_prozent: float
    prognose_zeitraum: dict
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[SolarPrognoseTagSchema]
    string_prognosen: List[StringPrognoseSchema] | None = Field(
        None, description="Prognosen pro String (falls mehrere Ausrichtungen)"
    )
    datenquelle: str
    abgerufen_am: str
    hinweise: List[str] = []
    # Aggregate über die ANGEZEIGTEN Tageswerte (`eedc_kwh ?? pv_ertrag_kwh`) —
    # damit Summenzeile/Ø je Konstruktion zu den Balken passen und die Seite
    # sich nicht an anderer Stelle selbst widerspricht.
    eedc_summe_kwh: float | None = None
    eedc_durchschnitt_kwh_tag: float | None = None
    anzeige_quelle: str = Field(
        ANZEIGE_QUELLE_OPENMETEO,
        description="'eedc' | 'openmeteo' | 'gemischt' — Quelle der Tages-Anzeigewerte",
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{anlage_id}", response_model=SolarPrognoseResponse)
async def get_solar_prognose_endpoint(
    anlage_id: int,
    tage: int = Query(default=7, ge=1, le=16, description="Anzahl Tage (1-16)"),
    pro_string: bool = Query(
        default=False,
        description="Separate Prognose pro PV-String (bei unterschiedlichen Ausrichtungen)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    PV-Ertragsprognose basierend auf Open-Meteo Solar API mit GTI.

    Verwendet:
    - GTI (Global Tilted Irradiance) für geneigte Module
    - Neigung und Ausrichtung aus PV-Modul-Konfiguration
    - Systemverluste aus PVGIS-Einstellungen

    Args:
        anlage_id: ID der Anlage
        tage: Anzahl Vorhersagetage (1-16)
        pro_string: Separate Prognose pro String bei unterschiedlichen Ausrichtungen

    Returns:
        SolarPrognoseResponse: Detaillierte PV-Ertragsprognose
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=400,
            detail="Anlage hat keine Koordinaten. Bitte Standort konfigurieren."
        )

    # PV-Module laden
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            aktiv_jetzt()
        )
    )
    pv_module = result.scalars().all()

    # Balkonkraftwerke laden
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "balkonkraftwerk",
            aktiv_jetzt()
        )
    )
    balkonkraftwerke = result.scalars().all()

    alle_pv = list(pv_module) + list(balkonkraftwerke)

    if not alle_pv:
        raise HTTPException(
            status_code=400,
            detail="Keine PV-Module oder Balkonkraftwerke konfiguriert."
        )

    # System-Verluste aus der aktiven PVGIS-Prognose (Auswahl-SoT, P5)
    pvgis = await lade_aktive_prognose(db, anlage_id)
    system_losses = resolve_system_losses(pvgis)

    # String-Konfigurationen erstellen
    strings: List[PVStringConfig] = []
    hinweise: List[str] = []

    from backend.services.pv_orientation import (
        get_pv_kwp, get_pv_neigung, get_pv_azimut,
    )
    for pv in alle_pv:
        kwp = get_pv_kwp(pv)
        if kwp <= 0:
            continue

        strings.append(PVStringConfig(
            name=pv.bezeichnung or f"String {pv.id}",
            kwp=kwp,
            neigung=get_pv_neigung(pv),
            ausrichtung=get_pv_azimut(pv),
        ))

    if not strings:
        raise HTTPException(
            status_code=400,
            detail="Keine PV-Module mit gültiger Leistung gefunden."
        )

    # Prüfe ob unterschiedliche Ausrichtungen
    unique_orientations = set((s.neigung, s.ausrichtung) for s in strings)
    has_multiple_orientations = len(unique_orientations) > 1

    # Bei mehreren Ausrichtungen IMMER per-String berechnen (korrekte VM/NM)
    wetter_modell = getattr(anlage, 'wetter_modell', None) or "auto"

    if has_multiple_orientations:
        multi_result = await get_multi_string_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            strings=strings,
            days=tage,
            system_losses=system_losses,
            wetter_modell=wetter_modell,
            # Interaktiver User-Request: der 1-30s-Random-Jitter ist nur für
            # Hintergrund-Abrufe gedacht (Prefetch jittert selbst einmal pro
            # Durchlauf). Bei Multi-String zahlte der User sonst das MAXIMUM
            # mehrerer paralleler Jitter-Würfe (~25 s bei 4 Strings, R18-13).
            skip_jitter=True,
        )

        if not multi_result:
            raise HTTPException(
                status_code=503,
                detail="Solar-Prognose konnte nicht abgerufen werden."
            )

        # Aggregierte Tageswerte aus allen Strings erstellen
        string_prognosen = multi_result["string_prognosen"]
        tageswerte = _aggregate_string_tageswerte(string_prognosen)

        # P4 (N77): hat eine Orientierungsgruppe keinen Forecast geliefert
        # (transienter OpenMeteo-Aussetzer, z. B. HTTP 429 auf einem der
        # parallelen /forecast-Calls), enthalten `summe_kwh`, `durchschnitt_kwh_tag`
        # und alle Tagesbalken nur die ÜBERLEBENDEN Gruppen. Der Service markiert
        # das seit #306 als `vollstaendig: False` und loggt es — die HTTP-Antwort
        # sagte es nicht, `hinweise` blieb leer. Eine Teilsumme ohne Kennzeichnung
        # ist eine falsche Aussage: bei 4 Gruppen und einem Aussetzer fehlt grob
        # ein Viertel, und 3,0 kWp statt 20,8 kWp sieht wie ein schlechter Tag aus.
        # Der Wert bleibt stehen (kein Ersatz durch Schätzung, keine Kappung), er
        # wird nur ehrlich beschriftet. Vorhandenes Signal, kein zweites.
        if not multi_result.get("vollstaendig", True):
            geliefert, erwartet = len(string_prognosen), len(strings)
            hinweise.append(
                f"Der Wetterabruf war unvollständig: nur {geliefert} von {erwartet} "
                "PV-Teilanlagen haben eine Prognose geliefert. Summe, Ø/Tag und die "
                "Tagesbalken sind deshalb eine Teilsumme und zu niedrig — bitte "
                "später erneut laden."
            )
        eedc_summe, eedc_schnitt, anzeige_quelle = await _mit_eedc_werten(
            db, anlage, tageswerte, tage
        )

        return SolarPrognoseResponse(
            anlage_id=anlage_id,
            anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
            kwp_gesamt=multi_result["kwp_gesamt"],
            neigung=multi_result["neigung_durchschnitt"],
            ausrichtung=multi_result["ausrichtung_durchschnitt"],
            system_losses_prozent=round(system_losses * 100, 1),
            prognose_zeitraum={
                "von": tageswerte[0].datum if tageswerte else None,
                "bis": tageswerte[-1].datum if tageswerte else None,
            },
            summe_kwh=multi_result["summe_kwh"],
            durchschnitt_kwh_tag=multi_result["durchschnitt_kwh_tag"],
            tageswerte=tageswerte,
            string_prognosen=[
                StringPrognoseSchema(**sp) for sp in string_prognosen
            ] if pro_string else None,
            datenquelle=multi_result["datenquelle"],
            abgerufen_am=multi_result["abgerufen_am"],
            hinweise=hinweise,
            eedc_summe_kwh=eedc_summe,
            eedc_durchschnitt_kwh_tag=eedc_schnitt,
            anzeige_quelle=anzeige_quelle,
        )

    else:
        # Einzelne Ausrichtung — ein API-Call reicht
        total_kwp = sum(s.kwp for s in strings)

        prognose = await get_solar_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            kwp=total_kwp,
            neigung=strings[0].neigung,
            ausrichtung=strings[0].ausrichtung,
            days=tage,
            system_losses=system_losses,
            wetter_modell=wetter_modell,
            # Interaktiver User-Request → kein Random-Jitter (siehe oben).
            skip_jitter=True,
        )

        if not prognose:
            raise HTTPException(
                status_code=503,
                detail="Solar-Prognose konnte nicht abgerufen werden."
            )

        tageswerte = [
            SolarPrognoseTagSchema(
                datum=t.datum,
                pv_ertrag_kwh=t.pv_ertrag_kwh,
                gti_kwh_m2=t.gti_kwh_m2,
                ghi_kwh_m2=t.ghi_kwh_m2,
                sonnenstunden=t.sonnenstunden,
                temperatur_max_c=t.temperatur_max_c,
                temperatur_min_c=t.temperatur_min_c,
                bewoelkung_prozent=t.bewoelkung_prozent,
                niederschlag_mm=t.niederschlag_mm,
                schnee_cm=t.schnee_cm,
                wetter_symbol=t.wetter_symbol,
                pv_ertrag_morgens_kwh=t.pv_ertrag_morgens_kwh,
                pv_ertrag_nachmittags_kwh=t.pv_ertrag_nachmittags_kwh,
                datenquelle=t.datenquelle,
            )
            for t in prognose.tageswerte
        ]
        eedc_summe, eedc_schnitt, anzeige_quelle = await _mit_eedc_werten(
            db, anlage, tageswerte, tage
        )

        return SolarPrognoseResponse(
            anlage_id=anlage_id,
            anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
            kwp_gesamt=prognose.kwp_gesamt,
            neigung=prognose.neigung,
            ausrichtung=prognose.ausrichtung,
            system_losses_prozent=prognose.system_losses_prozent,
            prognose_zeitraum=prognose.prognose_zeitraum,
            summe_kwh=prognose.summe_kwh,
            durchschnitt_kwh_tag=prognose.durchschnitt_kwh_tag,
            tageswerte=tageswerte,
            string_prognosen=None,
            datenquelle=prognose.datenquelle,
            abgerufen_am=prognose.abgerufen_am,
            hinweise=hinweise,
            eedc_summe_kwh=eedc_summe,
            eedc_durchschnitt_kwh_tag=eedc_schnitt,
            anzeige_quelle=anzeige_quelle,
        )
