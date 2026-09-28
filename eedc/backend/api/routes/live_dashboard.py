"""
Live Dashboard API - Echtzeit-Leistungsdaten.

GET /api/live/{anlage_id} — Aktuelle Leistungswerte für eine Anlage.
GET /api/live/{anlage_id}/tagesverlauf — Stündlicher Leistungsverlauf.
"""

import logging
import random
from datetime import date, datetime
from typing import Literal, Optional

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

class LiveFahrzeug(BaseModel):
    """Ein E-Auto in der Wallbox-Kachel (#341/#348, Plan 1.4a).

    Auch Autos OHNE eigenen Knoten stehen hier — die nur einen Ladestand melden
    und die, deren Leistungssensor mit der Wallbox geteilt ist. Jeder Wert ist
    einzeln optional: fehlt er, steht dort nichts statt einer 0 (ADR-002/P4).
    """
    investition_id: int
    label: str
    soc: Optional[float] = None
    #: Momentanleistung des Autos in kW, **vorzeichenbehaftet**: positiv lädt
    #: es, negativ gibt es ab (V2H). `None`, wenn sie nicht getrennt gemessen ist.
    kw: Optional[float] = None
    v2h: bool = False


class LiveKomponente(BaseModel):
    """Eine Zeile in der Energiebilanz-Tabelle."""
    key: str
    label: str
    icon: str
    erzeugung_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    parent_key: Optional[str] = None
    leistung_kwp: Optional[float] = None  # PV-Strings: installierte Leistung für Auslastungs-Anzeige
    # #398: der aktuelle Betriebsmodus einer Wärmepumpe/Klimaanlage. `None`
    # heißt „keine Zuordnung, kein HA, kein verwertbarer Zustand" — NICHT „aus"
    # (ADR-002/P4). Der Klartext kommt aus dem Kanon mit, damit der Client keine
    # zweite Übersetzungstabelle führt.
    betriebsmodus: Optional[str] = None
    betriebsmodus_label: Optional[str] = None
    # ── #341/#348: Merkmale für die Gruppierung im Energiefluss ─────────────
    # Reine Anreicherung (keine Summe, kein Residual liest sie); alle optional,
    # damit ein neuer Client mit einem alten Backend definiert auf die letzte
    # Kaskadenstufe fällt. ⛔ Jedes Feld, das der Builder setzt und der Client
    # lesen soll, MUSS hier stehen — FastAPI verwirft Undeklariertes still.
    # (`abgabe` bleibt bewusst draußen: der Buchungszweig kommt aus `kategorie`.)
    #: Investitionstyp — an jedem Investitions-Knoten, nie an netz/haushalt/pv_gesamt.
    typ: Optional[str] = None
    #: Nur `typ == "sonstiges"`: die gepflegte Kategorie (erzeuger · abgabe ·
    #: speicher · verbraucher · zaehler …), roh; `None` ohne Pflege.
    kategorie: Optional[str] = None
    #: Nur `pv_*`, nur bei gepflegter Ausrichtung (`pv_orientation.ausrichtung_label`,
    #: ohne Süd-Default); „Ost-West" ist EIN Label.
    ausrichtung_label: Optional[str] = None
    #: Nur `pv_*`: ID des Trägers (Wechselrichter oder Balkonkraftwerk); der
    #: Rest-Knoten eines abtretenden Balkonkraftwerks trägt seine eigene ID.
    traeger_id: Optional[int] = None
    #: Nur `pv_*`, genau dann gesetzt, wenn `traeger_id` es ist: die Bezeichnung
    #: des Trägers (bzw. des BKW-Rests selbst) — die Gruppe heißt im Client
    #: „<traeger_label> (n)" (#341/#348 A1b).
    traeger_label: Optional[str] = None
    #: Nur `batterie_*`: nutzbare Kapazität (SoT `get_speicher_nutzbare_kapazitaet_kwh`).
    kapazitaet_kwh: Optional[float] = None
    #: Nur `wallbox_*`: die zugeordneten Autos (dieselbe Zuordnung wie `parent_key`).
    fahrzeuge: Optional[list[LiveFahrzeug]] = None
    #: Nur `wallbox_*`: „eindeutig" bei genau einer live liefernden Wallbox, sonst „geschaetzt".
    fahrzeuge_zuordnung: Optional[Literal["eindeutig", "geschaetzt"]] = None


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
#
# EINE Demo-Anlage für Energiefluss, Tagesverlauf und Heute-Kacheln — sonst
# widerspricht sich die Demo-Box beim Durchklicken. Der Bestand ist so gewählt,
# dass die Gruppierung des Energieflusses (#341/#348) sichtbar wird: sechs
# PV-Strings an zwei Wechselrichtern in drei Ausrichtungen, zwei Wallboxen,
# zwei E-Autos (eines meldet nur seinen Ladestand und hat deshalb keinen
# eigenen Knoten), zwei Sonstige Verbraucher. Die Merkmale je Knoten (`typ`,
# `kategorie`, `ausrichtung_label`, `traeger_id`, `traeger_label`,
# `kapazitaet_kwh`, `fahrzeuge`) stehen hier so, wie der Live-Builder sie für
# diesen Bestand liefern würde.

#: Die zwei Demo-Wechselrichter: Träger-ID → Bezeichnung (`traeger_label`).
_DEMO_WECHSELRICHTER: dict[int, str] = {20: "WR Hausdach", 21: "WR Garage"}

#: (Investitions-ID, Bezeichnung, Ausrichtung, Träger-ID (Wechselrichter),
#:  kWp, kW jetzt, Spitzenstunde, kWh heute)
_DEMO_PV_STRINGS: tuple[tuple, ...] = (
    (1, "PV Süd (String A)", "Süd", 20, 4.0, 2.8, 13.0, 12.1),
    (2, "PV Ost (String B)", "Ost", 20, 2.0, 1.4, 10.5, 6.2),
    (7, "PV Süd (String C)", "Süd", 20, 2.5, 1.9, 13.0, 7.4),
    (8, "PV Ost (String D)", "Ost", 21, 2.0, 1.0, 10.5, 5.1),
    (9, "PV West (String E)", "West", 21, 2.0, 1.3, 15.5, 5.6),
    (10, "PV West (String F)", "West", 21, 1.5, 0.9, 15.5, 4.3),
)
_DEMO_KWP_GESAMT = sum(s[4] for s in _DEMO_PV_STRINGS)

#: Zwei Sonstige Verbraucher: (Investitions-ID, Bezeichnung).
_DEMO_POOL = (13, "Poolpumpe")
_DEMO_SAUNA = (14, "Sauna")


def _generate_demo_data(anlage_id: int, anlage_name: str) -> dict:
    """Simulierte Live-Daten der Demo-Anlage (Bestand s. `_DEMO_PV_STRINGS`).

    Die Netzleistung ist der Rest der Bilanz — Σ Quellen = Σ Senken, wie im
    echten Builder; Autarkie und Eigenverbrauchsquote rechnen nach derselben
    Formel. Die Auto-Zuordnung folgt `_fahrzeug_zuordnung` (Wallboxen 6, 11 ·
    Autos 4, 12 nach ID reihum ⇒ ID.4 → go-eCharger, Zoe → Carport), und bei
    zwei Wallboxen heißt sie „geschaetzt".
    """
    def jitter(base: float, pct: float = 0.1) -> float:
        return round(base * (1 + random.uniform(-pct, pct)), 2)

    pv_kw_je = {sid: jitter(kw) for sid, _l, _a, _t, _kwp, kw, _p, _e in _DEMO_PV_STRINGS}
    pv_kw = round(sum(pv_kw_je.values()), 2)

    batt_kw = jitter(0.5)
    ist_ladung = random.random() > 0.4
    batt_ladung = batt_kw if ist_ladung else 0.0
    batt_entladung = 0.0 if ist_ladung else batt_kw
    wallbox_kw = jitter(7.4) if random.random() > 0.25 else 0
    eauto_kw = round(wallbox_kw * random.uniform(0.85, 0.95), 2) if wallbox_kw > 0 else 0
    wallbox2_kw = jitter(3.7) if random.random() > 0.7 else 0
    wp_kw = jitter(1.8)
    pool_kw = jitter(0.8)
    sauna_kw = jitter(6.0) if random.random() > 0.8 else 0
    haushalt_kw = jitter(0.6)
    batt_soc = min(100, max(0, 72 + random.randint(-5, 5)))
    eauto_soc = min(100, max(0, 45 + random.randint(-3, 3)))
    zoe_soc = min(100, max(0, 68 + random.randint(-3, 3)))

    # Energiebilanz: das Netz schließt sie (das E-Auto hinter der Wallbox ist
    # ein Kind und zählt nicht ein zweites Mal).
    senken_ohne_netz = (haushalt_kw + wallbox_kw + wallbox2_kw + wp_kw
                        + pool_kw + sauna_kw + batt_ladung)
    netto = pv_kw + batt_entladung - senken_ohne_netz
    einsp_kw = round(max(0.0, netto), 2)
    bezug_kw = round(max(0.0, -netto), 2)
    summe_erz = pv_kw + bezug_kw + batt_entladung
    summe_vrb = einsp_kw + senken_ohne_netz

    # Autarkie/EV wie `live_komponenten_builder` (Netzpunkt-Bilanz).
    direkt = max(0.0, pv_kw - einsp_kw - batt_ladung)
    eigenverbrauch = direkt + batt_entladung
    gesamt_verbrauch = eigenverbrauch + bezug_kw
    autarkie = round(eigenverbrauch / gesamt_verbrauch * 100, 0) if gesamt_verbrauch > 0 else 0
    ev_quote = round(eigenverbrauch / pv_kw * 100, 0) if pv_kw > 0 else 0

    netto_w = round((bezug_kw - einsp_kw) * 1000, 0)
    max_netz = max(einsp_kw * 1000, bezug_kw * 1000, 1)

    # Batterie heute: Ladung + Entladung getrennt (wie der echte Pfad in
    # live_history_service: `batterie_<id>_ladung`/`_entladung` + Summe `batterie_<id>`).
    # Ohne die getrennten Keys rendert LiveHeuteKacheln keine Batterie-Kachel → Lücke.
    batt_ladung_kwh = round(6.0 + random.uniform(-0.5, 0.5), 1)
    batt_entladung_kwh = round(4.5 + random.uniform(-0.5, 0.5), 1)
    pv_kwh_je = {sid: round(kwh * (1 + random.uniform(-0.05, 0.05)), 1)
                 for sid, _l, _a, _t, _kwp, _kw, _p, kwh in _DEMO_PV_STRINGS}
    pv_kwh = round(sum(pv_kwh_je.values()), 1)
    bezug_kwh = round(3.1 + random.uniform(-0.3, 0.3), 1)
    wallbox_kwh = round(14.7 + random.uniform(-1, 1), 1)
    wallbox2_kwh = round(4.2 + random.uniform(-0.4, 0.4), 1)
    wp_kwh = round(5.2 + random.uniform(-0.3, 0.3), 1)
    pool_kwh = round(3.1 + random.uniform(-0.2, 0.2), 1)
    sauna_kwh = round(2.0 + random.uniform(-0.2, 0.2), 1)
    haushalt_kwh = round(6.8 + random.uniform(-0.5, 0.5), 1)
    # Tagesbilanz wie im Moment: die Einspeisung ist der Rest.
    einsp_kwh = round(max(0.0, pv_kwh + bezug_kwh + batt_entladung_kwh - (
        batt_ladung_kwh + wallbox_kwh + wallbox2_kwh + wp_kwh
        + pool_kwh + sauna_kwh + haushalt_kwh)), 1)

    komponenten: list[dict] = [
        {"key": f"pv_{sid}", "label": label, "icon": "sun",
         "erzeugung_kw": pv_kw_je[sid], "verbrauch_kw": None,
         "leistung_kwp": kwp, "typ": "pv-module",
         "ausrichtung_label": ausr, "traeger_id": traeger,
         "traeger_label": _DEMO_WECHSELRICHTER[traeger]}
        for sid, label, ausr, traeger, kwp, _kw, _p, _e in _DEMO_PV_STRINGS
    ]
    komponenten += [
        {"key": "netz", "label": "Stromnetz", "icon": "zap",
         "erzeugung_kw": bezug_kw if bezug_kw > 0 else None,
         "verbrauch_kw": einsp_kw if einsp_kw > 0 else None},
        {"key": "batterie_3", "label": "BYD HVS 10.2", "icon": "battery",
         "erzeugung_kw": batt_kw if not ist_ladung else None,
         "verbrauch_kw": batt_kw if ist_ladung else None,
         "typ": "speicher", "kapazitaet_kwh": 10.2},
        {"key": "wallbox_6", "label": "go-eCharger", "icon": "plug",
         "erzeugung_kw": None, "verbrauch_kw": wallbox_kw, "typ": "wallbox",
         "fahrzeuge": [{"investition_id": 4, "label": "VW ID.4", "soc": eauto_soc,
                        "kw": eauto_kw, "v2h": False}],
         "fahrzeuge_zuordnung": "geschaetzt"},
        {"key": "eauto_4", "label": "VW ID.4", "icon": "car",
         "erzeugung_kw": None, "verbrauch_kw": eauto_kw,
         "parent_key": "wallbox_6", "typ": "e-auto"},
        # Die Zoe meldet nur ihren Ladestand: kein eigener Knoten (wie im
        # Builder), sie steht allein in `fahrzeuge` der Carport-Wallbox.
        {"key": "wallbox_11", "label": "Wallbox Carport", "icon": "plug",
         "erzeugung_kw": None, "verbrauch_kw": wallbox2_kw, "typ": "wallbox",
         "fahrzeuge": [{"investition_id": 12, "label": "Renault Zoe", "soc": zoe_soc,
                        "kw": None, "v2h": False}],
         "fahrzeuge_zuordnung": "geschaetzt"},
        {"key": "waermepumpe_5", "label": "Viessmann Vitocal", "icon": "flame",
         "erzeugung_kw": None, "verbrauch_kw": wp_kw, "typ": "waermepumpe"},
        {"key": f"sonstige_{_DEMO_POOL[0]}", "label": _DEMO_POOL[1], "icon": "wrench",
         "erzeugung_kw": None, "verbrauch_kw": pool_kw,
         "typ": "sonstiges", "kategorie": "verbraucher"},
        {"key": f"sonstige_{_DEMO_SAUNA[0]}", "label": _DEMO_SAUNA[1], "icon": "wrench",
         "erzeugung_kw": None, "verbrauch_kw": sauna_kw,
         "typ": "sonstiges", "kategorie": "verbraucher"},
        {"key": "haushalt", "label": "Haushalt", "icon": "home",
         "erzeugung_kw": None, "verbrauch_kw": haushalt_kw},
    ]

    heute_pro_komp: dict[str, float] = {f"pv_{sid}": kwh for sid, kwh in pv_kwh_je.items()}
    heute_pro_komp.update({
        "netz_bezug": bezug_kwh,
        "netz_einspeisung": einsp_kwh,
        "batterie_3_ladung": batt_ladung_kwh,
        "batterie_3_entladung": batt_entladung_kwh,
        "batterie_3": round(batt_ladung_kwh + batt_entladung_kwh, 1),
        "wallbox_6": wallbox_kwh,
        "eauto_4": round(8.3 + random.uniform(-0.5, 0.5), 1),
        "wallbox_11": wallbox2_kwh,
        "waermepumpe_5": wp_kwh,
        f"sonstige_{_DEMO_POOL[0]}": pool_kwh,
        f"sonstige_{_DEMO_SAUNA[0]}": sauna_kwh,
        "haushalt": haushalt_kwh,
    })

    return {
        "anlage_id": anlage_id,
        "anlage_name": anlage_name,
        "zeitpunkt": datetime.now().isoformat(),
        "verfuegbar": True,
        "komponenten": komponenten,
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
            {"key": "soc_12", "label": "Renault Zoe", "wert": zoe_soc,
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "autarkie", "label": "Autarkie", "wert": min(autarkie, 100),
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "eigenverbrauch", "label": "Eigenverbr.", "wert": min(ev_quote, 100),
             "min_wert": 0, "max_wert": 100, "einheit": "%"},
            {"key": "pv_leistung", "label": "PV-Leistung",
             "wert": min(round(pv_kw / _DEMO_KWP_GESAMT * 100, 0), 120),
             "min_wert": 0, "max_wert": 120, "einheit": "% kWp"},
        ],
        "heute_pv_kwh": pv_kwh,
        "heute_einspeisung_kwh": einsp_kwh,
        "heute_netzbezug_kwh": bezug_kwh,
        "heute_eigenverbrauch_kwh": round(pv_kwh - einsp_kwh, 1),
        "gestern_pv_kwh": round(44.5 + random.uniform(-2, 2), 1),
        "gestern_einspeisung_kwh": round(12.1 + random.uniform(-1, 1), 1),
        "gestern_netzbezug_kwh": round(4.2 + random.uniform(-0.5, 0.5), 1),
        "gestern_eigenverbrauch_kwh": round(32.4 + random.uniform(-1, 1), 1),
        "heute_kwh_pro_komponente": heute_pro_komp,
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
    """Simulierter Tagesverlauf für Demo-Modus (Butterfly-Chart).

    Dieselbe Demo-Anlage wie `_generate_demo_data` — dieselben Schlüssel, damit
    Energiefluss, Tagesverlauf und Heute-Kacheln einander nicht widersprechen.
    Wie im echten Pfad keine E-Auto-Serie: existiert eine Wallbox-Serie, entfällt
    jede E-Auto-Serie (KONZEPT-WALLBOX-EAUTO §Gebaut).
    """
    import math

    now = datetime.now()

    # Farben = Kanon (`lib/colors.ts`, Wächter test_live_tagesverlauf_farben_kanon).
    serien = [
        {"key": f"pv_{sid}", "label": label, "kategorie": "pv",
         "farbe": "#f59e0b", "seite": "quelle", "bidirektional": False}
        for sid, label, *_rest in _DEMO_PV_STRINGS
    ]
    serien += [
        {"key": "batterie_3", "label": "BYD HVS 10.2", "kategorie": "batterie",
         "farbe": "#3b82f6", "seite": "quelle", "bidirektional": True},
        {"key": "wallbox_6", "label": "go-eCharger", "kategorie": "wallbox",
         "farbe": "#06b6d4", "seite": "senke", "bidirektional": False},
        {"key": "wallbox_11", "label": "Wallbox Carport", "kategorie": "wallbox",
         "farbe": "#06b6d4", "seite": "senke", "bidirektional": False},
        {"key": "waermepumpe_5", "label": "Viessmann Vitocal", "kategorie": "waermepumpe",
         "farbe": "#ef4444", "seite": "senke", "bidirektional": False},
        {"key": f"sonstige_{_DEMO_POOL[0]}", "label": _DEMO_POOL[1], "kategorie": "sonstige",
         "farbe": "#6b7280", "seite": "senke", "bidirektional": False},
        {"key": f"sonstige_{_DEMO_SAUNA[0]}", "label": _DEMO_SAUNA[1], "kategorie": "sonstige",
         "farbe": "#6b7280", "seite": "senke", "bidirektional": False},
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

        # PV: je String eine Glockenkurve um die Spitzenstunde seiner
        # Ausrichtung (Ost früh, Süd mittags, West nachmittags), Höhe nach kWp.
        pv_total = 0.0
        for sid, _label, _ausr, _tr, kwp, _kw, spitze, _kwh in _DEMO_PV_STRINGS:
            basis = max(0, 0.8 * kwp * math.exp(-((h_float - spitze) ** 2) / 14))
            wert = round(basis * (0.85 + random.uniform(0, 0.3)), 2) if basis > 0.05 else 0
            if wert > 0:
                werte[f"pv_{sid}"] = wert  # Quelle → positiv
                pv_total += wert

        # Haushalt (BDEW H0)
        haushalt = round(lastprofil.get(h_int, 0.3) * (0.8 + random.uniform(0, 0.4)), 2)

        # Wallboxen: go-eCharger nachmittags, Carport morgens
        wallbox = round(random.uniform(3, 7), 2) if (15 <= h_float <= 17 and random.random() > 0.4) else 0
        wallbox2 = round(random.uniform(3, 3.7), 2) if (7 <= h_float <= 8.5 and random.random() > 0.5) else 0

        # WP: Morgens und abends stärker
        wp = round(random.uniform(1.2, 2.5), 2) if h_int in (6, 7, 8, 17, 18, 19) else round(0.3 * random.uniform(0.5, 1.5), 2)

        # Poolpumpe tagsüber, Sauna am frühen Abend
        pool = round(random.uniform(0.7, 0.9), 2) if 10 <= h_float <= 16 else 0
        sauna = round(random.uniform(5.5, 6.5), 2) if (18 <= h_float <= 19.5 and random.random() > 0.3) else 0

        verbrauch_gesamt = haushalt + wallbox + wallbox2 + wp + pool + sauna

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
        if wallbox2 > 0.01:
            werte["wallbox_11"] = round(-wallbox2, 2)
        if wp > 0.05:
            werte["waermepumpe_5"] = round(-wp, 2)
        if pool > 0.01:
            werte[f"sonstige_{_DEMO_POOL[0]}"] = round(-pool, 2)
        if sauna > 0.01:
            werte[f"sonstige_{_DEMO_SAUNA[0]}"] = round(-sauna, 2)
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



