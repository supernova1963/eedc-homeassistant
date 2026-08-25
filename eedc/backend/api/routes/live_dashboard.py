"""
Live Dashboard API - Echtzeit-Leistungsdaten.

GET /api/live/{anlage_id} — Aktuelle Leistungswerte für eine Anlage.
GET /api/live/{anlage_id}/tagesverlauf — Stündlicher Leistungsverlauf.
"""

import logging
import random
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil
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
    leistung_kwp: Optional[float] = None  # PV-Strings: installierte Leistung für Auslastungs-Anzeige


class LiveGauge(BaseModel):
    """Ein Gauge-Chart (SoC, Netz-Richtung, Autarkie)."""
    key: str
    label: str
    wert: float
    min_wert: float = 0
    max_wert: float = 100
    einheit: str = "%"


class LiveInnengeraet(BaseModel):
    """Ein Innengerät einer Split-Klimaanlage im Live-Bild (#263).

    Alle drei Werte sind optional und einzeln — ein Innengerät kann einen
    Temperatur-Sensor haben und keinen Leistungs-Sensor. Fehlt einer, steht
    dort nichts statt einer 0 (ADR-002/P4).
    """
    investition_id: int
    innengeraet_id: int
    bezeichnung: str
    leistung_w: Optional[float] = None
    soll_temperatur_c: Optional[float] = None
    ist_temperatur_c: Optional[float] = None


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

    #: #263 — Live-Werte je Innengerät einer Split-Klimaanlage. **Reine
    #: Anzeige**: sie gehen in keine Summe und keine Bilanz — die Leistung
    #: eines Innengeräts ist eine Teilmenge der Geräteleistung, die als
    #: Komponente schon zählt. `None`, solange kein einziger Wert ankommt.
    innengeraete: Optional[list[LiveInnengeraet]] = None


class TagesverlaufSerie(BaseModel):
    """Beschreibung einer Kurve im Tagesverlauf-Chart."""
    key: str              # z.B. "pv_3", "batterie_5", "wallbox_6", "netz", "haushalt"
    label: str            # z.B. "PV Süd", "BYD HVS 10.2"
    kategorie: str        # "pv", "batterie", "wallbox", "waermepumpe", "sonstige", "netz", "haushalt"
    farbe: str            # Hex-Farbe, z.B. "#f59e0b" (Kanon, s. lib/colors.ts)
    seite: str            # "quelle" (positiv) oder "senke" (negativ), oder "overlay" (sekundäre Y-Achse)
    bidirektional: bool = False  # Speicher/Netz: wechselt dynamisch die Seite
    einheit: Optional[str] = None  # Nur für Overlay-Serien, z.B. "ct/kWh"
    max_w: Optional[float] = None  # Optional: Plausibilitäts-Obergrenze für Leistungswerte


class TagesverlaufPunkt(BaseModel):
    """Ein Stunden-Datenpunkt im Tagesverlauf."""
    zeit: str  # "14:00"
    werte: dict[str, float] = {}  # {serie_key: kW-Wert mit Vorzeichen}


class TagesverlaufResponse(BaseModel):
    anlage_id: int
    datum: str  # "2026-03-14"
    serien: list[TagesverlaufSerie] = []
    punkte: list[TagesverlaufPunkt] = []


class BoersenpreisStunde(BaseModel):
    """Eine bewertete Stunde der Day-Ahead-Kurve."""
    stunde: int              # 0–23, lokale Stunde der Gebotszone
    preis_cent: float        # ct/kWh, netto (ohne Steuern/Netzentgelte) — kann negativ sein
    rang: int                # 1–5 = eine der günstigsten des Fensters, 99 = Rest
    unter_schwelle: bool     # UNGEKAPPT — anders als der Rang nicht auf 5 begrenzt
    # ct/kWh unter (negativ) bzw. über dem optimierten Ø DIESES Tages (N-173).
    # Gegen einen festen Preisaufschlag invariant, anders als jede Prozentzahl.
    abstand_cent: Optional[float] = None


class BoersenpreisTag(BaseModel):
    datum: str                                        # "2026-08-06"
    stunden: list[BoersenpreisStunde] = []
    schwelle_cent: Optional[float] = None             # Günstig-Schwelle DIESES Tages
    optimierter_durchschnitt_cent: Optional[float] = None  # Ø ohne die 3 Peaks
    tages_durchschnitt_cent: Optional[float] = None   # schlichter Ø ALLER Stunden (rapahl-PN 23.08.)


class BoersenpreisResponse(BaseModel):
    """Day-Ahead-Börsenpreise für heute und (ab ~13 Uhr) morgen.

    ``tage`` enthält **nur** Tage mit Preisen. Fehlt morgen, sagt ``hinweis``
    warum — ein stilles Weglassen wäre eine unvollständige Antwort, die sich als
    vollständige ausgibt (ADR-002/P4).
    """
    anlage_id: int
    markt: str                                   # "DE" | "AT"
    tage: list[BoersenpreisTag] = []
    #: Ø Börsenpreis des laufenden Kalendermonats aus der eigenen stündlichen
    #: Mitschrift (Zusage an Rainer). `None`, solange nichts vorliegt — dann
    #: fehlt die Kachel, statt ein halber Tag als „Monatsmittel" zu gelten.
    monats_durchschnitt_cent: Optional[float] = None
    aktuelle_stunde: Optional[int] = None        # lokale Stunde in der Gebotszone
    heute: Optional[str] = None                  # Datum von „heute" in derselben Zone
    hinweis: Optional[str] = None                # gesetzt, wenn ein Tag fehlt
    #: Endpreis der laufenden Stunde in ct/kWh — das, was der Anwender
    #: tatsächlich zahlt (Börsenanteil **plus** Netzentgelte, Steuern, Abgaben).
    #: Quelle ist ausschließlich der zugeordnete Strompreis-Sensor
    #: (``TagesEnergieProfil.strompreis_cent``, Tibber/aWATTar/EPEX-Endpreis).
    #:
    #: ⚠ **Bewusst KEIN Rückfall auf den Tarif-Arbeitspreis** (N-173/R2, rapahl):
    #: Wer einen dynamischen Tarif fährt, hat dort einen gemittelten oder
    #: geschätzten Wert stehen — ihn als „Endpreis der laufenden Stunde"
    #: auszugeben wäre eine erfundene Genauigkeit. Ohne Sensor bleibt das Feld
    #: ``None`` und die Kachel fehlt, wie bei allen anderen Kennzahlen dieses
    #: Blocks auch.
    endpreis_jetzt_cent: Optional[float] = None


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

    # Batterie heute: Ladung + Entladung getrennt (wie der echte Pfad in
    # live_history_service: `batterie_<id>_ladung`/`_entladung` + Summe `batterie_<id>`).
    # Ohne die getrennten Keys rendert LiveHeuteKacheln keine Batterie-Kachel → Lücke.
    batt_ladung_kwh = round(6.0 + random.uniform(-0.5, 0.5), 1)
    batt_entladung_kwh = round(4.5 + random.uniform(-0.5, 0.5), 1)

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
            "batterie_3_ladung": batt_ladung_kwh,
            "batterie_3_entladung": batt_entladung_kwh,
            "batterie_3": round(batt_ladung_kwh + batt_entladung_kwh, 1),
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
        raise not_found("Anlage")

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
         "farbe": "#f59e0b", "seite": "quelle", "bidirektional": False},
        {"key": "pv_2", "label": "PV Ost (String B)", "kategorie": "pv",
         "farbe": "#b45309", "seite": "quelle", "bidirektional": False},
        {"key": "batterie_3", "label": "BYD HVS 10.2", "kategorie": "batterie",
         "farbe": "#3b82f6", "seite": "quelle", "bidirektional": True},
        {"key": "wallbox_6", "label": "go-eCharger", "kategorie": "wallbox",
         "farbe": "#06b6d4", "seite": "senke", "bidirektional": False},
        {"key": "waermepumpe_5", "label": "Viessmann Vitocal", "kategorie": "waermepumpe",
         "farbe": "#ef4444", "seite": "senke", "bidirektional": False},
        {"key": "netz", "label": "Stromnetz", "kategorie": "netz",
         "farbe": "#b91c1c", "seite": "quelle", "bidirektional": True},
        {"key": "haushalt", "label": "Haushalt", "kategorie": "haushalt",
         "farbe": "#64748b", "seite": "senke", "bidirektional": False},
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
        raise not_found("Anlage")

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


# ── Börsenpreis-Endpoint (#335) ──────────────────────────────────────────────

# Die Veröffentlichungsstunde der Day-Ahead-Auktion steht im SoT der Preis-Schicht
# (`services/preis_tag.py`) — der HA-Export braucht sie seit N-104 ebenso, und eine
# Konstante in zwei Modulen ist genau die Drift, gegen die diese Schicht gebaut ist.
from backend.services.preis_tag import (  # noqa: E402
    DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE,
)


@router.get("/{anlage_id}/boersenpreise", response_model=BoersenpreisResponse)
async def get_boersenpreise(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Bewertete Day-Ahead-Börsenpreise für heute und — sobald veröffentlicht — morgen.

    Bewertet wird über ``services/preis_tag.py``, also über **dieselbe** Schicht,
    aus der auch die HA-Preis-Sensoren ihre Zahlen ziehen. Der Chart zeigt damit
    genau die Stunden als günstig, die ``eedc_preis_rang`` meldet.

    **Je Tag eine eigene Schwelle:** Day-Ahead ist ein Tagesprodukt, und der
    optimierte Ø (ohne die 3 Peaks) wird je Kalendertag gebildet. Ein gemeinsamer
    Ø über 48 Stunden würde an einem teuren Tag keine einzige günstige Stunde
    ausweisen und am billigen fast alle — und stünde damit im Widerspruch zu den
    Sensoren derselben Anlage.

    **Kein Demo-Zweig:** Börsenpreise sind öffentliche Marktdaten, keine
    Anlagendaten. Der Endpunkt liefert im Demo-Modus dieselbe echte Kurve —
    simuliert würde hier nichts glaubwürdiger, nur falsch.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    from datetime import timedelta

    from backend.services.preis_tag import (
        jetzt_im_markt, lade_preistag, markt_der_anlage,
    )

    markt = markt_der_anlage(anlage)
    now = jetzt_im_markt(markt)
    heute = now.date()
    morgen = heute + timedelta(days=1)

    tage: list[dict] = []
    for datum in (heute, morgen):
        try:
            tag = await lade_preistag(db, anlage, datum, now.hour)
        except Exception as e:
            # Ein Tag, der nicht geladen werden kann, darf den anderen nicht
            # mitreißen — und er wird unten als fehlend ausgewiesen, nicht
            # stillschweigend als „gibt es nicht" behandelt.
            logger.warning(
                "Börsenpreise %s (Anlage %s): %s: %s",
                datum, anlage_id, type(e).__name__, e,
            )
            continue
        if tag is None or not tag.stunden:
            continue
        tage.append({
            "datum": tag.datum.isoformat(),
            "stunden": [
                {
                    "stunde": s.stunde,
                    "preis_cent": s.preis_cent,
                    "rang": s.rang,
                    "unter_schwelle": s.unter_schwelle,
                    "abstand_cent": s.abstand_cent,
                }
                for s in tag.stunden
            ],
            "schwelle_cent": tag.schwelle_cent,
            "optimierter_durchschnitt_cent": tag.optimierter_durchschnitt_cent,
            "tages_durchschnitt_cent": tag.tages_durchschnitt_cent,
        })

    geladene = {t["datum"] for t in tage}
    hinweis: Optional[str] = None
    if heute.isoformat() not in geladene and morgen.isoformat() not in geladene:
        hinweis = (
            "Börsenpreise sind derzeit nicht abrufbar. Ohne Koordinaten der Anlage "
            "lassen sich Tag- und Nachtfenster nicht bestimmen; ansonsten antwortet "
            "die Marktdaten-Quelle gerade nicht."
        )
    elif morgen.isoformat() not in geladene:
        hinweis = (
            f"Für morgen liegen noch keine Börsenpreise vor — die Day-Ahead-Auktion "
            f"veröffentlicht sie gegen {DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE}:00 Uhr."
            if now.hour < DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE
            else "Für morgen liegen noch keine Börsenpreise vor."
        )
    elif heute.isoformat() not in geladene:
        hinweis = "Für heute liegen keine Börsenpreise vor, nur für morgen."

    return {
        "anlage_id": anlage.id,
        "markt": markt,
        "tage": tage,
        "monats_durchschnitt_cent": await _monats_durchschnitt_cent(
            db, anlage_id, heute,
        ),
        "aktuelle_stunde": now.hour,
        "heute": heute.isoformat(),
        "hinweis": hinweis,
        "endpreis_jetzt_cent": await _endpreis_jetzt_cent(
            db, anlage_id, heute, now.hour,
        ),
    }


async def _endpreis_jetzt_cent(
    db, anlage_id: int, heute: date, stunde: int,
) -> Optional[float]:
    """Endpreis der laufenden Stunde — was der Anwender wirklich zahlt.

    **Wunsch von rapahl** (N-173/R2): Der Block zeigte bisher ausschließlich den
    **Börsenpreis**. Der ist die Steuergröße für „wann laden", aber er ist nicht
    der Preis auf der Rechnung — dazwischen liegen Netzentgelte, Steuern und
    Abgaben. Wer prüfen will, was eine Stunde kostet, brauchte bisher einen
    zweiten Blick in Home Assistant.

    Quelle ist ``TagesEnergieProfil.strompreis_cent``, also der **zugeordnete
    Strompreis-Sensor** (Tibber/aWATTar/EPEX). Damit ist es kein zweiter
    Preis-Kanal, sondern dieselbe stündliche Mitschrift, aus der auch die
    Monats- und Tagesauswertungen lesen — Muster wie
    {@link _monats_durchschnitt_cent}.

    ⚠ **Kein Rückfall auf ``Strompreis.netzbezug_arbeitspreis_cent_kwh``.** Das
    Tarif-Feld ist ein **Endpreis inklusive Börsenanteil** und bei dynamischem
    Tarif ein Mittel- oder Schätzwert; ihn als „Preis dieser Stunde" auszugeben
    wäre erfundene Genauigkeit — dieselbe Vokabular-Drift, die schon bei N-173
    gegen dieses Feld entschieden hat. Ohne Sensor bleibt es ``None``, und die
    Kachel fehlt (ADR-002/P4: lieber keine Zahl als eine, die etwas anderes
    behauptet).

    ⚠ **Stundenkonvention:** ``strompreis_cent`` wird je Stunde als Mittel über
    ``[h:00, h+1:00)`` geschrieben (HA-LTS-Hourly bzw. History-Fallback), also
    **forward** — dieselbe Richtung wie der Börsenpreis, der aus dem
    ``start_timestamp`` der Marktdaten kommt. ``stunde`` ist damit direkt die
    laufende Stunde und braucht keinen Versatz. Das ist **nicht** die
    Backward-Konvention der Energiewerte (#144, Slot N = ``[N-1, N)``) — in
    dieser Tabelle stehen beide nebeneinander, jede in ihrer sachlich richtigen
    Richtung.
    """
    res = await db.execute(
        select(TagesEnergieProfil.strompreis_cent).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == heute,
            TagesEnergieProfil.stunde == stunde,
            TagesEnergieProfil.strompreis_cent.isnot(None),
        )
    )
    wert = res.scalar_one_or_none()
    return round(wert, 2) if wert is not None else None


async def _monats_durchschnitt_cent(db, anlage_id: int, heute: date) -> Optional[float]:
    """Ø Börsenpreis des laufenden Kalendermonats — aus der eigenen Mitschrift.

    **Zusage an Rainer** (PN 2026-08-20): Der Börsenpreis-Block sagte, wie teuer
    diese Stunde gegen *heute* ist, aber nicht, wie teuer heute gegen den Monat
    ist — und genau das entscheidet, ob sich Warten lohnt.

    Quelle ist ``TagesEnergieProfil.boersenpreis_cent``, dieselbe stündliche
    Mitschrift, aus der auch der Fallback in ``preis_tag.persistierte_preise``
    liest. Damit ist es **kein zweiter Preis-Kanal**: es steht dort, was eedc
    an dieser Anlage tatsächlich gesehen hat.

    ⚠ **Der Monat, soweit er da ist.** Am Zweiten des Monats sind es zwei Tage;
    Stunden ohne Mitschrift fehlen im Nenner wie im Zähler. ``None``, wenn
    nichts vorliegt — dann fehlt die Kachel, statt eine Zahl aus einem halben
    Tag als „Monatsmittel" auszugeben (ADR-002/P4).
    """
    from sqlalchemy import func

    monatsbeginn = heute.replace(day=1)
    res = await db.execute(
        select(func.avg(TagesEnergieProfil.boersenpreis_cent)).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= monatsbeginn,
            TagesEnergieProfil.datum <= heute,
            TagesEnergieProfil.boersenpreis_cent.isnot(None),
        )
    )
    wert = res.scalar()
    return round(float(wert), 2) if wert is not None else None



