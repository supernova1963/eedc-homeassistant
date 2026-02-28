"""
Prognose-Service für PV-Ertragsprognosen.

Bietet:
- Kurzfristige Prognosen (7-16 Tage) basierend auf Wettervorhersagen
- Langfristige Prognosen (Monate) basierend auf PVGIS TMY + historischen Trends
- Trend-Analysen basierend auf historischen Daten
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.wetter_service import (
    fetch_open_meteo_forecast,
    wetter_code_zu_symbol,
    fetch_pvgis_tmy_monat,
    get_pvgis_tmy_defaults,
)

logger = logging.getLogger(__name__)

# Konstanten für PV-Berechnung
DEFAULT_SYSTEM_EFFICIENCY = 0.85  # Systemwirkungsgrad (Wechselrichter, Kabel, etc.)
DEFAULT_SYSTEM_LOSSES = 0.14  # 14% Systemverluste (PVGIS Standard)
TEMP_COEFFICIENT = 0.004  # Leistungsabnahme pro °C über 25°C


@dataclass
class TagesPrognose:
    """Prognose für einen einzelnen Tag."""
    datum: str
    pv_prognose_kwh: float
    globalstrahlung_kwh_m2: float
    sonnenstunden: float
    temperatur_max_c: float
    temperatur_min_c: Optional[float]
    niederschlag_mm: Optional[float]
    bewoelkung_prozent: Optional[int]
    wetter_symbol: str


@dataclass
class MonatsPrognose:
    """Prognose für einen Monat."""
    jahr: int
    monat: int
    monat_name: str
    pvgis_prognose_kwh: float
    trend_korrigiert_kwh: float
    konfidenz_min_kwh: float
    konfidenz_max_kwh: float
    historische_performance_ratio: Optional[float]


def berechne_pv_ertrag_tag(
    globalstrahlung_kwh_m2: float,
    anlagenleistung_kwp: float,
    temperatur_max_c: Optional[float] = None,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
) -> float:
    """
    Berechnet den erwarteten PV-Ertrag für einen Tag.

    Formel:
    PV_kwh = Globalstrahlung × kWp × (1 - Systemverluste) × Temperaturkorrektur

    Args:
        globalstrahlung_kwh_m2: Globalstrahlung in kWh/m²
        anlagenleistung_kwp: Anlagenleistung in kWp
        temperatur_max_c: Maximaltemperatur in °C (für Temperaturkorrektur)
        system_losses: Systemverluste (0.14 = 14%)

    Returns:
        Erwarteter Ertrag in kWh
    """
    if globalstrahlung_kwh_m2 is None or globalstrahlung_kwh_m2 <= 0:
        return 0.0

    # Basisberechnung
    ertrag = globalstrahlung_kwh_m2 * anlagenleistung_kwp * (1 - system_losses)

    # Temperaturkorrektur (Module werden bei Hitze ineffizienter)
    if temperatur_max_c is not None and temperatur_max_c > 25:
        temp_verlust = (temperatur_max_c - 25) * TEMP_COEFFICIENT
        ertrag *= (1 - temp_verlust)

    return round(max(0, ertrag), 2)


async def get_kurzfrist_prognose(
    db: Session,
    anlage_id: int,
    tage: int = 14
) -> Optional[dict]:
    """
    Erstellt eine Kurzfrist-PV-Prognose (7-16 Tage) basierend auf Wettervorhersage.

    Args:
        db: Datenbankverbindung
        anlage_id: ID der Anlage
        tage: Anzahl Tage (max 16)

    Returns:
        dict mit Prognose oder None bei Fehler
    """
    # Anlage laden
    anlage = db.query(Anlage).filter(Anlage.id == anlage_id).first()
    if not anlage:
        logger.error(f"Anlage {anlage_id} nicht gefunden")
        return None

    if not anlage.latitude or not anlage.longitude:
        logger.error(f"Anlage {anlage_id} hat keine Koordinaten")
        return None

    # Anlagenleistung aus PV-Modulen berechnen
    pv_module = db.query(Investition).filter(
        Investition.anlage_id == anlage_id,
        Investition.typ == "pv_module",
        Investition.aktiv == True
    ).all()

    anlagenleistung_kwp = sum(
        m.leistung_kwp or 0 for m in pv_module
    ) or anlage.leistung_kwp or 0

    if anlagenleistung_kwp <= 0:
        logger.error(f"Anlage {anlage_id} hat keine Leistung konfiguriert")
        return None

    # Systemverluste aus PVGIS-Prognose oder Default
    pvgis = db.query(PVGISPrognose).filter(
        PVGISPrognose.anlage_id == anlage_id,
        PVGISPrognose.ist_aktiv == True
    ).first()
    system_losses = pvgis.system_losses / 100 if pvgis and pvgis.system_losses else DEFAULT_SYSTEM_LOSSES

    # Wettervorhersage abrufen
    wetter = await fetch_open_meteo_forecast(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        days=min(tage, 16)
    )

    if not wetter:
        logger.error(f"Keine Wettervorhersage für Anlage {anlage_id}")
        return None

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

        tageswerte.append({
            "datum": tag["datum"],
            "pv_prognose_kwh": pv_kwh,
            "globalstrahlung_kwh_m2": tag["globalstrahlung_kwh_m2"],
            "sonnenstunden": tag["sonnenstunden"],
            "temperatur_max_c": tag["temperatur_max_c"],
            "temperatur_min_c": tag["temperatur_min_c"],
            "niederschlag_mm": tag["niederschlag_mm"],
            "bewoelkung_prozent": tag["bewoelkung_prozent"],
            "wetter_symbol": wetter_code_zu_symbol(tag["wetter_code"]),
        })

        summe_kwh += pv_kwh

    # Erste und letzte Datum ermitteln
    von = tageswerte[0]["datum"] if tageswerte else None
    bis = tageswerte[-1]["datum"] if tageswerte else None

    return {
        "anlage_id": anlage_id,
        "anlagenname": anlage.anlagenname,
        "anlagenleistung_kwp": anlagenleistung_kwp,
        "prognose_zeitraum": {
            "von": von,
            "bis": bis,
        },
        "summe_kwh": round(summe_kwh, 1),
        "durchschnitt_kwh_tag": round(summe_kwh / len(tageswerte), 2) if tageswerte else 0,
        "tageswerte": tageswerte,
        "datenquelle": "open-meteo-forecast",
        "abgerufen_am": wetter["abgerufen_am"],
        "system_losses_prozent": round(system_losses * 100, 1),
    }


async def get_langfrist_prognose(
    db: Session,
    anlage_id: int,
    monate: int = 12
) -> Optional[dict]:
    """
    Erstellt eine Langfrist-PV-Prognose (Monate) basierend auf PVGIS TMY und Trends.

    Args:
        db: Datenbankverbindung
        anlage_id: ID der Anlage
        monate: Anzahl Monate in die Zukunft

    Returns:
        dict mit Monatsprognosen oder None bei Fehler
    """
    # Anlage laden
    anlage = db.query(Anlage).filter(Anlage.id == anlage_id).first()
    if not anlage:
        return None

    if not anlage.latitude or not anlage.longitude:
        return None

    # Anlagenleistung
    pv_module = db.query(Investition).filter(
        Investition.anlage_id == anlage_id,
        Investition.typ == "pv_module",
        Investition.aktiv == True
    ).all()

    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module) or anlage.leistung_kwp or 0

    if anlagenleistung_kwp <= 0:
        return None

    # PVGIS-Prognose laden (für Monatswerte)
    pvgis = db.query(PVGISPrognose).filter(
        PVGISPrognose.anlage_id == anlage_id,
        PVGISPrognose.ist_aktiv == True
    ).first()

    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)

    # Historische Performance-Ratio berechnen (letzte 12 Monate)
    heute = date.today()
    ein_jahr_zurueck = heute - timedelta(days=365)

    # PV-Erträge aus InvestitionMonatsdaten
    pv_modul_ids = [m.id for m in pv_module]
    historische_daten = db.query(InvestitionMonatsdaten).filter(
        InvestitionMonatsdaten.investition_id.in_(pv_modul_ids)
    ).all()

    # Performance-Ratio pro Monat berechnen
    monatliche_pr = {}
    for hd in historische_daten:
        monat = hd.monat
        ist_kwh = hd.verbrauch_daten.get("pv_erzeugung_kwh", 0) if hd.verbrauch_daten else 0
        soll_kwh = pvgis_monatswerte.get(monat, 0)

        if soll_kwh > 0 and ist_kwh > 0:
            pr = ist_kwh / soll_kwh
            if monat not in monatliche_pr:
                monatliche_pr[monat] = []
            monatliche_pr[monat].append(pr)

    # Durchschnittliche PR pro Monat
    avg_pr_monat = {}
    for monat, prs in monatliche_pr.items():
        avg_pr_monat[monat] = sum(prs) / len(prs)

    # Gesamt-PR
    alle_prs = [pr for prs in monatliche_pr.values() for pr in prs]
    gesamt_pr = sum(alle_prs) / len(alle_prs) if alle_prs else 1.0

    # Monatsprognosen erstellen
    monatswerte = []
    start_monat = heute.month
    start_jahr = heute.year
    jahresprognose_kwh = 0.0

    monatsnamen = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    for i in range(monate):
        monat = ((start_monat - 1 + i) % 12) + 1
        jahr = start_jahr + ((start_monat - 1 + i) // 12)

        # PVGIS-Prognose für diesen Monat (skaliert auf aktuelle kWp)
        pvgis_kwh = pvgis_monatswerte.get(monat, 0)

        # Wenn keine PVGIS-Daten, TMY-Defaults verwenden
        if pvgis_kwh <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude)
            # Grobe Schätzung: kWh/m² × kWp × 0.85
            pvgis_kwh = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85

        # Trend-Korrektur anwenden
        monat_pr = avg_pr_monat.get(monat, gesamt_pr)
        trend_kwh = pvgis_kwh * monat_pr

        # Konfidenzintervall (±15% oder basierend auf historischer Varianz)
        konfidenz_faktor = 0.15
        konfidenz_min = trend_kwh * (1 - konfidenz_faktor)
        konfidenz_max = trend_kwh * (1 + konfidenz_faktor)

        monatswerte.append({
            "jahr": jahr,
            "monat": monat,
            "monat_name": monatsnamen[monat],
            "pvgis_prognose_kwh": round(pvgis_kwh, 1),
            "trend_korrigiert_kwh": round(trend_kwh, 1),
            "konfidenz_min_kwh": round(konfidenz_min, 1),
            "konfidenz_max_kwh": round(konfidenz_max, 1),
            "historische_performance_ratio": round(monat_pr, 3) if monat in avg_pr_monat else None,
        })

        jahresprognose_kwh += trend_kwh

    # Trend-Richtung bestimmen
    trend_richtung = "stabil"
    if gesamt_pr > 1.05:
        trend_richtung = "positiv"
    elif gesamt_pr < 0.95:
        trend_richtung = "negativ"

    return {
        "anlage_id": anlage_id,
        "anlagenname": anlage.anlagenname,
        "anlagenleistung_kwp": anlagenleistung_kwp,
        "prognose_zeitraum": {
            "von": f"{start_jahr}-{start_monat:02d}",
            "bis": f"{monatswerte[-1]['jahr']}-{monatswerte[-1]['monat']:02d}" if monatswerte else None,
        },
        "jahresprognose_kwh": round(jahresprognose_kwh, 0),
        "monatswerte": monatswerte,
        "trend_analyse": {
            "durchschnittliche_performance_ratio": round(gesamt_pr, 3),
            "trend_richtung": trend_richtung,
            "datenbasis_monate": len(alle_prs),
        },
        "datenquellen": ["pvgis-tmy" if not pvgis else "pvgis-prognose", "historische-daten"],
    }


async def get_trend_analyse(
    db: Session,
    anlage_id: int,
    jahre: int = 3
) -> Optional[dict]:
    """
    Erstellt eine Trend-Analyse basierend auf historischen Daten.

    Args:
        db: Datenbankverbindung
        anlage_id: ID der Anlage
        jahre: Anzahl Jahre für Analyse

    Returns:
        dict mit Trend-Analyse oder None bei Fehler
    """
    # Anlage laden
    anlage = db.query(Anlage).filter(Anlage.id == anlage_id).first()
    if not anlage:
        return None

    # PV-Module laden
    pv_module = db.query(Investition).filter(
        Investition.anlage_id == anlage_id,
        Investition.typ == "pv_module",
        Investition.aktiv == True
    ).all()

    anlagenleistung_kwp = sum(m.leistung_kwp or 0 for m in pv_module) or anlage.leistung_kwp or 0

    # PVGIS-Prognose
    pvgis = db.query(PVGISPrognose).filter(
        PVGISPrognose.anlage_id == anlage_id,
        PVGISPrognose.ist_aktiv == True
    ).first()

    pvgis_jahresertrag = pvgis.jahresertrag_kwh if pvgis else 0

    # Historische Daten laden
    pv_modul_ids = [m.id for m in pv_module]
    historische_daten = db.query(InvestitionMonatsdaten).filter(
        InvestitionMonatsdaten.investition_id.in_(pv_modul_ids)
    ).all()

    # Nach Jahren gruppieren
    jahres_ertraege = {}
    monats_ertraege = {}

    for hd in historische_daten:
        jahr = hd.jahr
        monat = hd.monat
        kwh = hd.verbrauch_daten.get("pv_erzeugung_kwh", 0) if hd.verbrauch_daten else 0

        if kwh > 0:
            if jahr not in jahres_ertraege:
                jahres_ertraege[jahr] = 0
            jahres_ertraege[jahr] += kwh

            if monat not in monats_ertraege:
                monats_ertraege[monat] = []
            monats_ertraege[monat].append(kwh)

    # Jahresvergleich erstellen
    heute = date.today()
    start_jahr = heute.year - jahre + 1
    jahres_vergleich = []

    for jahr in range(start_jahr, heute.year + 1):
        gesamt_kwh = jahres_ertraege.get(jahr, 0)
        spez_ertrag = gesamt_kwh / anlagenleistung_kwp if anlagenleistung_kwp > 0 else 0
        pr = gesamt_kwh / pvgis_jahresertrag if pvgis_jahresertrag > 0 else None

        jahres_vergleich.append({
            "jahr": jahr,
            "gesamt_kwh": round(gesamt_kwh, 1),
            "spezifischer_ertrag_kwh_kwp": round(spez_ertrag, 0),
            "performance_ratio": round(pr, 3) if pr else None,
        })

    # Saisonale Muster
    monatsnamen = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    monats_durchschnitte = []
    for monat in range(1, 13):
        ertraege = monats_ertraege.get(monat, [])
        avg = sum(ertraege) / len(ertraege) if ertraege else 0
        monats_durchschnitte.append((monat, avg))

    # Sortieren nach Ertrag
    sortiert = sorted(monats_durchschnitte, key=lambda x: x[1], reverse=True)
    beste_monate = [monatsnamen[m[0]] for m in sortiert[:3] if m[1] > 0]
    schlechteste_monate = [monatsnamen[m[0]] for m in sortiert[-3:] if m[1] > 0]

    # Degradation schätzen (lineare Regression über Jahre)
    degradation_prozent = None
    if len(jahres_vergleich) >= 2:
        ertraege = [(jv["jahr"], jv["gesamt_kwh"]) for jv in jahres_vergleich if jv["gesamt_kwh"] > 0]
        if len(ertraege) >= 2:
            # Einfache Schätzung: Änderung von erstem zu letztem Jahr
            erstes = ertraege[0]
            letztes = ertraege[-1]
            if erstes[1] > 0:
                jahre_diff = letztes[0] - erstes[0]
                if jahre_diff > 0:
                    aenderung = (letztes[1] - erstes[1]) / erstes[1] * 100
                    degradation_prozent = round(aenderung / jahre_diff, 2)

    return {
        "anlage_id": anlage_id,
        "anlagenname": anlage.anlagenname,
        "anlagenleistung_kwp": anlagenleistung_kwp,
        "analyse_zeitraum": {
            "von": start_jahr,
            "bis": heute.year,
        },
        "jahres_vergleich": jahres_vergleich,
        "saisonale_muster": {
            "beste_monate": beste_monate,
            "schlechteste_monate": schlechteste_monate,
        },
        "degradation": {
            "geschaetzt_prozent_jahr": degradation_prozent,
            "hinweis": "Positive Werte = Leistungssteigerung, negative Werte = Degradation" if degradation_prozent else "Nicht genügend Daten für Schätzung",
        },
        "datenquellen": ["historische-daten"],
    }
