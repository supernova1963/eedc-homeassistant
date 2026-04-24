"""
Energie-Profil API - Tägliche und stündliche Energiedaten.

GET /api/energie-profil/{anlage_id}/tage      — Tageszusammenfassungen
GET /api/energie-profil/{anlage_id}/stunden   — Stundenwerte für einen Tag
GET /api/energie-profil/{anlage_id}/wochenmuster — Ø-Tagesprofil je Wochentag
GET /api/energie-profil/{anlage_id}/monat     — Monatsauswertung (Heatmap + KPIs + Peaks)
GET /api/energie-profil/{anlage_id}/tagesprognose — Verbrauch+PV+Batterie-Prognose für einen Tag
GET /api/energie-profil/{anlage_id}/debug-rohdaten — Rohdaten TagesEnergieProfil (7 Tage)
DELETE /api/energie-profil/{anlage_id}/rohdaten — Löscht TagesEnergieProfil-Daten
"""

import calendar
import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

# seite je Investitionstyp
_TYP_SEITE: dict[str, str] = {
    "pv-module":       "quelle",
    "balkonkraftwerk": "quelle",
    "wechselrichter":  "quelle",
    "speicher":        "bidirektional",
    "e-auto":          "bidirektional",
    "wallbox":         "senke",
    "waermepumpe":     "senke",
}

# Virtuelle Serien (kein Investment dahinter)
_VIRTUAL_SERIEN: dict[str, dict] = {
    "haushalt":   {"label": "Haushalt",    "typ": "virtual", "kategorie": "haushalt",  "seite": "senke"},
    "netz":       {"label": "Stromnetz",   "typ": "virtual", "kategorie": "netz",      "seite": "bidirektional"},
    "pv_gesamt":  {"label": "PV Gesamt",   "typ": "virtual", "kategorie": "pv",        "seite": "quelle"},
}

# Optionale Suffixe bei WP-Serien (waermepumpe_{id}_heizen)
_SUFFIX_LABELS = {"heizen": " Heizen", "warmwasser": " Warmwasser"}

# Kategorien die bereits in dedizierten Spalten landen (kein Extra-Tracking nötig)
_DEDIZIERTE_KATEGORIEN = {"pv", "batterie", "netz", "haushalt", "waermepumpe", "wallbox", "eauto"}


def _key_to_serie_info(
    key: str, inv_map: dict[int, "Investition"]
) -> Optional[dict]:
    """Löst einen Komponenten-Key zu Label + Typ auf."""
    if key in _VIRTUAL_SERIEN:
        return {"key": key, **_VIRTUAL_SERIEN[key]}

    m = re.match(r'^([a-z]+)_(\d+)(?:_([a-z]+))?$', key)
    if not m:
        return None

    inv_id = int(m.group(2))
    suffix = m.group(3)
    inv = inv_map.get(inv_id)
    if not inv:
        return None

    label = inv.bezeichnung
    if suffix and suffix in _SUFFIX_LABELS:
        label += _SUFFIX_LABELS[suffix]

    # seite bestimmen
    seite = _TYP_SEITE.get(inv.typ, "senke")
    if inv.typ == "sonstiges" and isinstance(inv.parameter, dict):
        kat = inv.parameter.get("kategorie", "verbraucher")
        if kat == "erzeuger":
            seite = "quelle"
        elif kat == "speicher":
            seite = "bidirektional"

    return {
        "key": key,
        "label": label,
        "typ": inv.typ,
        "kategorie": m.group(1),
        "seite": seite,
    }

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response Models ──────────────────────────────────────────────────────────

class SerieInfo(BaseModel):
    """Metadaten einer Komponenten-Serie (für Label-Auflösung im Frontend)."""
    key: str
    label: str
    typ: str        # z.B. "sonstiges", "pv-module", "virtual"
    kategorie: str  # z.B. "sonstige", "pv", "netz"
    seite: str      # "quelle" | "senke" | "bidirektional"


class StundenWertResponse(BaseModel):
    """Stündlicher Energiewert eines Tages."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    waermepumpe_kw: Optional[float] = None
    wallbox_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None
    defizit_kw: Optional[float] = None
    temperatur_c: Optional[float] = None
    globalstrahlung_wm2: Optional[float] = None
    soc_prozent: Optional[float] = None
    komponenten: Optional[dict] = None  # Rohwerte aller Serien (key → kW)


class StundenAntwort(BaseModel):
    """Tagesdetail-Antwort: Stundenwerte + aufgelöste Serie-Labels."""
    stunden: list[StundenWertResponse]
    serien: list[SerieInfo]  # alle in komponenten vorkommenden Serien mit Label


class WochenmusterPunkt(BaseModel):
    """Durchschnittlicher Stundenwert pro Wochentag."""
    wochentag: int      # 0=Mo, 1=Di, …, 6=So
    stunde: int         # 0–23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    batterie_kw: Optional[float] = None
    anzahl_tage: int = 0


class HeatmapZelle(BaseModel):
    """Eine Zelle der Monats-Heatmap (Tag × Stunde)."""
    tag: int          # 1..31
    stunde: int       # 0..23
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None
    netzbezug_kw: Optional[float] = None
    einspeisung_kw: Optional[float] = None
    ueberschuss_kw: Optional[float] = None  # pv − verbrauch


class PeakStunde(BaseModel):
    """Eine einzelne Peak-Stunde im Monat."""
    datum: date
    stunde: int
    wert_kw: float


class TagesprofilStunde(BaseModel):
    """Ein Stundenpunkt im typischen Tagesprofil (Ø über Monat)."""
    stunde: int
    pv_kw: Optional[float] = None
    verbrauch_kw: Optional[float] = None


class KomponentenEintrag(BaseModel):
    """Ein einzelnes Gerät mit Monatssumme."""
    key: str
    label: str
    kategorie: str       # "pv", "waermepumpe", "wallbox", "eauto", "sonstiges", …
    typ: str             # z.B. "pv-module", "balkonkraftwerk", "waermepumpe", "sonstiges"
    seite: str           # "quelle" | "senke" | "bidirektional"
    kwh: float           # positiv = Erzeugung, negativ = Verbrauch
    anteil_prozent: Optional[float] = None  # vom Gesamt-PV bzw. Gesamt-Verbrauch


class KategorieSumme(BaseModel):
    """Monatssumme pro Kategorie (für KPI-Strip)."""
    kategorie: str       # "pv_module", "bkw", "sonstige_erzeuger", "waermepumpe", "wallbox_eauto", "sonstige_verbraucher", "haushalt"
    kwh: float
    anteil_prozent: Optional[float] = None


class MonatsAuswertungResponse(BaseModel):
    """Monatsauswertung aus TagesEnergieProfil + TagesZusammenfassung."""
    jahr: int
    monat: int
    tage_im_monat: int
    tage_mit_daten: int

    # Energie-Summen (kWh)
    pv_kwh: float
    verbrauch_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    ueberschuss_kwh: float
    defizit_kwh: float

    # Kennzahlen
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_prozent: Optional[float] = None
    performance_ratio_avg: Optional[float] = None
    batterie_vollzyklen_summe: Optional[float] = None

    # Erweiterte Analyse-KPIs
    grundbedarf_kw: Optional[float] = None          # Ø Verbrauch Nachtstunden 0–5 Uhr
    batterie_ladung_kwh: Optional[float] = None      # Σ Energie in die Batterie
    batterie_entladung_kwh: Optional[float] = None   # Σ Energie aus der Batterie
    batterie_wirkungsgrad: Optional[float] = None    # Entladung / Ladung
    direkt_eigenverbrauch_kwh: Optional[float] = None  # Σ min(pv, verbrauch) je Stunde
    pv_tag_best_kwh: Optional[float] = None
    pv_tag_schnitt_kwh: Optional[float] = None
    pv_tag_schlecht_kwh: Optional[float] = None

    # Typisches Tagesprofil (24 Punkte, Ø über Monat)
    typisches_tagesprofil: list[TagesprofilStunde] = []

    # Per-Komponente Aggregation
    kategorien: list[KategorieSumme] = []
    komponenten: list[KomponentenEintrag] = []

    # Peaks (Top-N Stunden)
    peak_netzbezug: list[PeakStunde] = []
    peak_einspeisung: list[PeakStunde] = []
    peak_pv: Optional[PeakStunde] = None

    # Heatmap-Matrix
    heatmap: list[HeatmapZelle] = []

    # Börsenpreis / Negativpreis (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None

    # Datenqualität (Issue #135): Anteil der Stunden ohne gemappten Zähler
    # Ermöglicht dem Frontend, Warnhinweise zu Datenlücken anzuzeigen.
    stunden_fehlend_pv: int = 0
    stunden_fehlend_verbrauch: int = 0


class TagesZusammenfassungResponse(BaseModel):
    """Tageszusammenfassung mit Per-Komponenten-kWh."""
    datum: date
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    performance_ratio: Optional[float] = None
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    komponenten_kwh: Optional[dict] = None
    # Börsenpreis-Aggregation (§51 EEG)
    boersenpreis_avg_cent: Optional[float] = None
    boersenpreis_min_cent: Optional[float] = None
    negative_preis_stunden: Optional[int] = None
    einspeisung_neg_preis_kwh: Optional[float] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{anlage_id}/tage", response_model=list[TagesZusammenfassungResponse])
async def get_tages_zusammenfassungen(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Tageszusammenfassungen für einen Zeitraum zurück.

    Enthält Per-Komponenten-kWh (z.B. pv_3, waermepumpe_5, wallbox_7)
    sowie Gesamtkennzahlen (Überschuss, Defizit, Peaks, Performance Ratio).
    """
    # Anlage prüfen
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Maximal 366 Tage (ein Jahr)
    if (bis - von).days > 366:
        raise HTTPException(status_code=400, detail="Zeitraum darf maximal 366 Tage umfassen")

    # Tageszusammenfassungen laden
    result = await db.execute(
        select(TagesZusammenfassung)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
        .order_by(TagesZusammenfassung.datum)
    )
    tage = result.scalars().all()

    return [
        TagesZusammenfassungResponse(
            datum=t.datum,
            ueberschuss_kwh=t.ueberschuss_kwh,
            defizit_kwh=t.defizit_kwh,
            peak_pv_kw=t.peak_pv_kw,
            peak_netzbezug_kw=t.peak_netzbezug_kw,
            peak_einspeisung_kw=t.peak_einspeisung_kw,
            batterie_vollzyklen=t.batterie_vollzyklen,
            temperatur_min_c=t.temperatur_min_c,
            temperatur_max_c=t.temperatur_max_c,
            strahlung_summe_wh_m2=t.strahlung_summe_wh_m2,
            performance_ratio=t.performance_ratio,
            stunden_verfuegbar=t.stunden_verfuegbar,
            datenquelle=t.datenquelle,
            komponenten_kwh=t.komponenten_kwh,
            boersenpreis_avg_cent=t.boersenpreis_avg_cent,
            boersenpreis_min_cent=t.boersenpreis_min_cent,
            negative_preis_stunden=t.negative_preis_stunden,
            einspeisung_neg_preis_kwh=t.einspeisung_neg_preis_kwh,
        )
        for t in tage
    ]


@router.get("/{anlage_id}/stunden", response_model=StundenAntwort)
async def get_stundenwerte(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt die 24 Stundenwerte eines Tages aus TagesEnergieProfil zurück.

    Enthält zusätzlich `serien` mit aufgelösten Labels für alle in `komponenten`
    vorkommenden Einträge — damit Sonstiges-Investments (Poolpumpe, Sauna …)
    namentlich im Frontend angezeigt werden können.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
        )
        .order_by(TagesEnergieProfil.stunde)
    )
    rows = result.scalars().all()

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    # Alle vorkommenden Komponenten-Keys sammeln (über alle Stunden)
    alle_keys: set[str] = set()
    for r in rows:
        if r.komponenten:
            alle_keys.update(r.komponenten.keys())

    # Keys zu SerieInfo auflösen (nur einmal pro Key, geordnet)
    serien: list[SerieInfo] = []
    seen: set[str] = set()
    for key in sorted(alle_keys):
        if key in seen:
            continue
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
            seen.add(key)

    stunden = [
        StundenWertResponse(
            stunde=r.stunde,
            pv_kw=r.pv_kw,
            verbrauch_kw=r.verbrauch_kw,
            einspeisung_kw=r.einspeisung_kw,
            netzbezug_kw=r.netzbezug_kw,
            batterie_kw=r.batterie_kw,
            waermepumpe_kw=r.waermepumpe_kw,
            wallbox_kw=r.wallbox_kw,
            ueberschuss_kw=r.ueberschuss_kw,
            defizit_kw=r.defizit_kw,
            temperatur_c=r.temperatur_c,
            globalstrahlung_wm2=r.globalstrahlung_wm2,
            soc_prozent=r.soc_prozent,
            komponenten=r.komponenten,
        )
        for r in rows
    ]

    return StundenAntwort(stunden=stunden, serien=serien)


@router.get("/{anlage_id}/wochenmuster", response_model=list[WochenmusterPunkt])
async def get_wochenmuster(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt durchschnittliche Stundenprofile je Wochentag zurück.

    Aggregiert TagesEnergieProfil-Werte über den Zeitraum und berechnet
    pro Wochentag (0=Mo … 6=So) × Stunde den Mittelwert.
    Basis für den Wochenvergleich-Chart im Energieprofil-Tab.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    if (bis - von).days > 366:
        raise HTTPException(status_code=400, detail="Zeitraum darf maximal 366 Tage umfassen")

    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = result.scalars().all()

    # Aggregation in Python: {(wochentag, stunde) → {field: [values]}}
    # date.weekday(): 0=Mo, 1=Di, …, 6=So
    acc: dict[tuple[int, int], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    tage_set: dict[tuple[int, int], set] = defaultdict(set)

    for r in rows:
        wt = r.datum.weekday()
        key = (wt, r.stunde)
        tage_set[key].add(r.datum)
        for field in ("pv_kw", "verbrauch_kw", "netzbezug_kw", "einspeisung_kw", "batterie_kw"):
            val = getattr(r, field)
            if val is not None:
                acc[key][field].append(val)

    punkte: list[WochenmusterPunkt] = []
    for (wt, stunde) in sorted(acc.keys()):
        felder = acc[(wt, stunde)]
        punkte.append(WochenmusterPunkt(
            wochentag=wt,
            stunde=stunde,
            pv_kw=round(sum(felder["pv_kw"]) / len(felder["pv_kw"]), 3) if felder.get("pv_kw") else None,
            verbrauch_kw=round(sum(felder["verbrauch_kw"]) / len(felder["verbrauch_kw"]), 3) if felder.get("verbrauch_kw") else None,
            netzbezug_kw=round(sum(felder["netzbezug_kw"]) / len(felder["netzbezug_kw"]), 3) if felder.get("netzbezug_kw") else None,
            einspeisung_kw=round(sum(felder["einspeisung_kw"]) / len(felder["einspeisung_kw"]), 3) if felder.get("einspeisung_kw") else None,
            batterie_kw=round(sum(felder["batterie_kw"]) / len(felder["batterie_kw"]), 3) if felder.get("batterie_kw") else None,
            anzahl_tage=len(tage_set[(wt, stunde)]),
        ))

    return punkte


@router.get("/{anlage_id}/monat", response_model=MonatsAuswertungResponse)
async def get_monatsauswertung(
    anlage_id: int,
    jahr: int = Query(..., ge=2000, le=2100),
    monat: int = Query(..., ge=1, le=12),
    top_n: int = Query(10, ge=1, le=50, description="Anzahl Peak-Stunden (Netzbezug/Einspeisung)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Monatsauswertung aus TagesEnergieProfil + TagesZusammenfassung.

    Liefert Heatmap-Matrix (Tag × Stunde), KPIs, Peak-Stunden,
    Batterie-Vollzyklen-Summe und Ø Performance Ratio für einen Kalendermonat.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    tage_im_monat = calendar.monthrange(jahr, monat)[1]
    von = date(jahr, monat, 1)
    bis = date(jahr, monat, tage_im_monat)

    # Stundenwerte des Monats laden
    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    stunden_rows = result.scalars().all()

    # Tageszusammenfassungen (für Batterie-Zyklen + PR)
    result = await db.execute(
        select(TagesZusammenfassung)
        .where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        )
    )
    tag_rows = result.scalars().all()

    # ── Heatmap + Summen aggregieren ──
    heatmap: list[HeatmapZelle] = []
    pv_sum = 0.0
    verbrauch_sum = 0.0
    einspeisung_sum = 0.0
    netzbezug_sum = 0.0
    ueberschuss_sum = 0.0
    defizit_sum = 0.0
    batt_lade_sum = 0.0
    batt_entlade_sum = 0.0
    direkt_sum = 0.0

    tage_mit_daten: set[date] = set()
    pv_pro_tag: dict[date, float] = defaultdict(float)

    # Für typisches Tagesprofil: Ø pro Stunde
    profil_pv: dict[int, list[float]] = defaultdict(list)
    profil_verbrauch: dict[int, list[float]] = defaultdict(list)
    # Für Grundbedarf: Nachtstunden 0–5 Uhr
    nacht_verbrauch: list[float] = []

    # Datenqualität (Issue #135): Zähle Stunden mit NULL-Werten
    # als Signal an UI, dass kumulativer Zähler fehlt/lückenhaft ist.
    stunden_fehlend_pv = 0
    stunden_fehlend_verbrauch = 0

    # Peaks sammeln — alle Einträge, später sortieren
    netzbezug_kandidaten: list[PeakStunde] = []
    einspeisung_kandidaten: list[PeakStunde] = []
    peak_pv: Optional[PeakStunde] = None

    for r in stunden_rows:
        tage_mit_daten.add(r.datum)

        # NULL-Handling: Stunde ohne gemapptem Zähler → nicht als 0 zählen
        pv = r.pv_kw
        verbrauch = r.verbrauch_kw
        einspeisung = r.einspeisung_kw
        netzbezug = r.netzbezug_kw
        batt = r.batterie_kw

        if pv is None:
            stunden_fehlend_pv += 1
        if verbrauch is None:
            stunden_fehlend_verbrauch += 1

        # Summen: NULL überspringt stillschweigend (statt als 0 zu zählen)
        if pv is not None:
            pv_sum += pv
            pv_pro_tag[r.datum] += pv
        if verbrauch is not None:
            verbrauch_sum += verbrauch
        if einspeisung is not None:
            einspeisung_sum += einspeisung
        if netzbezug is not None:
            netzbezug_sum += netzbezug

        # Überschuss/Defizit + Direkt-Eigenverbrauch nur wenn beide Werte da
        ueberschuss: Optional[float] = None
        if pv is not None and verbrauch is not None:
            ueberschuss = pv - verbrauch
            if ueberschuss > 0:
                ueberschuss_sum += ueberschuss
            else:
                defizit_sum += -ueberschuss
            direkt_sum += min(pv, verbrauch)

        # Batterie getrennt nach Richtung (nur wenn Wert vorhanden)
        if batt is not None:
            if batt < 0:
                batt_lade_sum += -batt
            elif batt > 0:
                batt_entlade_sum += batt

        # Profilsammlung
        if pv is not None:
            profil_pv[r.stunde].append(pv)
        if verbrauch is not None:
            profil_verbrauch[r.stunde].append(verbrauch)
            if 0 <= r.stunde < 5:
                nacht_verbrauch.append(verbrauch)

        heatmap.append(HeatmapZelle(
            tag=r.datum.day,
            stunde=r.stunde,
            pv_kw=round(pv, 3) if pv is not None else None,
            verbrauch_kw=round(verbrauch, 3) if verbrauch is not None else None,
            netzbezug_kw=round(netzbezug, 3) if netzbezug is not None else None,
            einspeisung_kw=round(einspeisung, 3) if einspeisung is not None else None,
            ueberschuss_kw=round(ueberschuss, 3) if ueberschuss is not None else None,
        ))

        if r.netzbezug_kw is not None and r.netzbezug_kw > 0:
            netzbezug_kandidaten.append(PeakStunde(
                datum=r.datum, stunde=r.stunde, wert_kw=round(r.netzbezug_kw, 3),
            ))
        if r.einspeisung_kw is not None and r.einspeisung_kw > 0:
            einspeisung_kandidaten.append(PeakStunde(
                datum=r.datum, stunde=r.stunde, wert_kw=round(r.einspeisung_kw, 3),
            ))
        if r.pv_kw is not None and r.pv_kw > 0:
            if peak_pv is None or r.pv_kw > peak_pv.wert_kw:
                peak_pv = PeakStunde(
                    datum=r.datum, stunde=r.stunde, wert_kw=round(r.pv_kw, 3),
                )

    netzbezug_kandidaten.sort(key=lambda p: p.wert_kw, reverse=True)
    einspeisung_kandidaten.sort(key=lambda p: p.wert_kw, reverse=True)

    # ── KPIs ──
    eigenverbrauch_pv = pv_sum - einspeisung_sum
    autarkie = (
        round((verbrauch_sum - netzbezug_sum) / verbrauch_sum * 100, 1)
        if verbrauch_sum > 0 else None
    )
    eigenverbrauch = (
        round(eigenverbrauch_pv / pv_sum * 100, 1)
        if pv_sum > 0 else None
    )

    grundbedarf = (
        round(sum(nacht_verbrauch) / len(nacht_verbrauch), 3)
        if nacht_verbrauch else None
    )
    batt_wirkungsgrad = (
        round(batt_entlade_sum / batt_lade_sum, 3)
        if batt_lade_sum > 0.1 else None
    )

    # Tagesverteilung PV
    pv_tage = [v for v in pv_pro_tag.values() if v > 0]
    pv_best = round(max(pv_tage), 2) if pv_tage else None
    pv_schlecht = round(min(pv_tage), 2) if pv_tage else None
    pv_schnitt = round(sum(pv_tage) / len(pv_tage), 2) if pv_tage else None

    # Typisches Tagesprofil (Ø pro Stunde)
    tagesprofil: list[TagesprofilStunde] = []
    for s in range(24):
        pv_werte = profil_pv.get(s, [])
        vb_werte = profil_verbrauch.get(s, [])
        tagesprofil.append(TagesprofilStunde(
            stunde=s,
            pv_kw=round(sum(pv_werte) / len(pv_werte), 3) if pv_werte else None,
            verbrauch_kw=round(sum(vb_werte) / len(vb_werte), 3) if vb_werte else None,
        ))

    # ── Batterie-Vollzyklen + PR + Börsenpreis aus TagesZusammenfassung ──
    zyklen_werte = [t.batterie_vollzyklen for t in tag_rows if t.batterie_vollzyklen is not None]
    zyklen_summe = round(sum(zyklen_werte), 2) if zyklen_werte else None

    pr_werte = [t.performance_ratio for t in tag_rows if t.performance_ratio is not None]
    pr_avg = round(sum(pr_werte) / len(pr_werte), 3) if pr_werte else None

    # Börsenpreis / Negativpreis (§51 EEG)
    boersen_werte = [t.boersenpreis_avg_cent for t in tag_rows if t.boersenpreis_avg_cent is not None]
    boersenpreis_avg = round(sum(boersen_werte) / len(boersen_werte), 2) if boersen_werte else None
    neg_stunden_werte = [t.negative_preis_stunden for t in tag_rows if t.negative_preis_stunden is not None]
    neg_stunden_summe = sum(neg_stunden_werte) if neg_stunden_werte else None
    neg_einsp_werte = [t.einspeisung_neg_preis_kwh for t in tag_rows if t.einspeisung_neg_preis_kwh is not None]
    neg_einsp_summe = round(sum(neg_einsp_werte), 2) if neg_einsp_werte else None

    # ── Per-Komponente Aggregation aus komponenten_kwh ──
    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    komponenten_sum: dict[str, float] = defaultdict(float)
    for t in tag_rows:
        if not t.komponenten_kwh:
            continue
        for k, v in t.komponenten_kwh.items():
            if v is not None:
                komponenten_sum[k] += v

    # Einträge auflösen + Anteile berechnen
    komponenten_liste: list[KomponentenEintrag] = []
    # Kategorie-Mapping: detaillierte Kategorie aus Invest-Typ
    def detail_kategorie(info: dict, inv: Optional[Investition]) -> str:
        kat = info.get("kategorie", "sonstige")
        typ = info.get("typ", "")
        key = info.get("key", "")
        if key == "netz":
            return "netz"
        if typ == "pv-module":
            return "pv_module"
        if typ == "balkonkraftwerk":
            return "bkw"
        if typ == "speicher":
            return "speicher"
        if typ == "waermepumpe":
            return "waermepumpe"
        if typ in ("wallbox", "e-auto"):
            return "wallbox_eauto"
        if kat == "haushalt":
            return "haushalt"
        if typ == "sonstiges" and inv and isinstance(inv.parameter, dict):
            unterkat = inv.parameter.get("kategorie", "verbraucher")
            if unterkat == "erzeuger":
                return "sonstige_erzeuger"
            if unterkat == "speicher":
                return "speicher"
            return "sonstige_verbraucher"
        if kat == "pv":
            return "pv_module"
        return "sonstige_verbraucher"

    kategorie_sum: dict[str, float] = defaultdict(float)

    for key, kwh in komponenten_sum.items():
        info = _key_to_serie_info(key, inv_map)
        if not info:
            continue
        inv = None
        m = re.match(r'^[a-z]+_(\d+)(?:_[a-z]+)?$', key)
        if m:
            inv = inv_map.get(int(m.group(1)))
        det_kat = detail_kategorie(info, inv)
        kategorie_sum[det_kat] += kwh
        komponenten_liste.append(KomponentenEintrag(
            key=key,
            label=info["label"],
            kategorie=det_kat,
            typ=info["typ"],
            seite=info["seite"],
            kwh=round(kwh, 2),
            anteil_prozent=None,  # später setzen
        ))

    # Anteile: Erzeuger → vom Gesamt-PV, Senken → vom Gesamt-Verbrauch
    for e in komponenten_liste:
        if e.seite == "quelle" and pv_sum > 0:
            e.anteil_prozent = round(abs(e.kwh) / pv_sum * 100, 1)
        elif e.seite == "senke" and verbrauch_sum > 0:
            e.anteil_prozent = round(abs(e.kwh) / verbrauch_sum * 100, 1)

    # Sortieren: Erzeuger zuerst (absteigend), dann Verbraucher (absteigend nach Betrag)
    komponenten_liste.sort(key=lambda e: (
        0 if e.seite == "quelle" else (1 if e.seite == "senke" else 2),
        -abs(e.kwh),
    ))

    kategorien_liste: list[KategorieSumme] = []
    ERZEUGER_KAT = {"pv_module", "bkw", "sonstige_erzeuger"}
    VERBRAUCHER_KAT = {"waermepumpe", "wallbox_eauto", "haushalt", "sonstige_verbraucher"}
    # Bidirektionale Kategorien (speicher, netz) werden nicht als Erzeuger/Verbraucher-KPI ausgewiesen,
    # tauchen aber in der Geräteliste weiter unten auf.
    BIDI_KAT = {"speicher", "netz"}
    for kat, kwh in sorted(kategorie_sum.items(), key=lambda kv: -abs(kv[1])):
        if kat in BIDI_KAT:
            continue
        anteil = None
        if kat in ERZEUGER_KAT and pv_sum > 0:
            anteil = round(abs(kwh) / pv_sum * 100, 1)
        elif kat in VERBRAUCHER_KAT and verbrauch_sum > 0:
            anteil = round(abs(kwh) / verbrauch_sum * 100, 1)
        kategorien_liste.append(KategorieSumme(
            kategorie=kat,
            kwh=round(kwh, 2),
            anteil_prozent=anteil,
        ))

    return MonatsAuswertungResponse(
        jahr=jahr,
        monat=monat,
        tage_im_monat=tage_im_monat,
        tage_mit_daten=len(tage_mit_daten),
        pv_kwh=round(pv_sum, 2),
        verbrauch_kwh=round(verbrauch_sum, 2),
        einspeisung_kwh=round(einspeisung_sum, 2),
        netzbezug_kwh=round(netzbezug_sum, 2),
        ueberschuss_kwh=round(ueberschuss_sum, 2),
        defizit_kwh=round(defizit_sum, 2),
        autarkie_prozent=autarkie,
        eigenverbrauch_prozent=eigenverbrauch,
        performance_ratio_avg=pr_avg,
        batterie_vollzyklen_summe=zyklen_summe,
        grundbedarf_kw=grundbedarf,
        batterie_ladung_kwh=round(batt_lade_sum, 2) if batt_lade_sum > 0 else None,
        batterie_entladung_kwh=round(batt_entlade_sum, 2) if batt_entlade_sum > 0 else None,
        batterie_wirkungsgrad=batt_wirkungsgrad,
        direkt_eigenverbrauch_kwh=round(direkt_sum, 2) if direkt_sum > 0 else None,
        pv_tag_best_kwh=pv_best,
        pv_tag_schnitt_kwh=pv_schnitt,
        pv_tag_schlecht_kwh=pv_schlecht,
        typisches_tagesprofil=tagesprofil,
        kategorien=kategorien_liste,
        komponenten=komponenten_liste,
        peak_netzbezug=netzbezug_kandidaten[:top_n],
        peak_einspeisung=einspeisung_kandidaten[:top_n],
        peak_pv=peak_pv,
        heatmap=heatmap,
        boersenpreis_avg_cent=boersenpreis_avg,
        negative_preis_stunden=neg_stunden_summe,
        einspeisung_neg_preis_kwh=neg_einsp_summe,
        stunden_fehlend_pv=stunden_fehlend_pv,
        stunden_fehlend_verbrauch=stunden_fehlend_verbrauch,
    )


# ── Debug + Wartungs-Endpoints ───────────────────────────────────────────────

@router.get("/{anlage_id}/debug-rohdaten")
async def get_debug_rohdaten(
    anlage_id: int,
    tage: int = Query(7, ge=1, le=30, description="Anzahl Tage zurück"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt TagesEnergieProfil-Rohdaten zurück (für Diagnose falsch gespeicherter Werte).

    Zeigt pv_kw, verbrauch_kw, netzbezug_kw, einspeisung_kw pro Stunde + Datum.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    from datetime import timedelta
    start = date.today() - timedelta(days=tage)

    rows_result = await db.execute(
        select(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= start,
        ).order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = rows_result.scalars().all()

    alle_verbrauch = [r.verbrauch_kw for r in rows if r.verbrauch_kw is not None]
    median_verbrauch = None
    if alle_verbrauch:
        sv = sorted(alle_verbrauch)
        median_verbrauch = sv[len(sv) // 2]

    return {
        "anlage_id": anlage_id,
        "anzahl_zeilen": len(rows),
        "median_verbrauch_kw": median_verbrauch,
        "plausibel": median_verbrauch is None or median_verbrauch <= 100,
        "zeilen": [
            {
                "datum": r.datum.isoformat(),
                "stunde": r.stunde,
                "pv_kw": r.pv_kw,
                "verbrauch_kw": r.verbrauch_kw,
                "netzbezug_kw": r.netzbezug_kw,
                "einspeisung_kw": r.einspeisung_kw,
                "batterie_kw": r.batterie_kw,
                "waermepumpe_kw": r.waermepumpe_kw,
            }
            for r in rows
        ],
    }


@router.delete("/{anlage_id}/rohdaten")
async def delete_rohdaten(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten einer Anlage.

    Der Scheduler schreibt ab dem nächsten Lauf (alle 15 Min) neue, korrekte Daten.
    Monatsdaten bleiben erhalten.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    del_stunden = await db.execute(
        delete(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage_id)
    )
    del_tage = await db.execute(
        delete(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage_id)
    )
    # Flag zurücksetzen, damit der nächste Monatsabschluss den Auto-Vollbackfill
    # aus HA Statistics erneut anstößt
    anlage.vollbackfill_durchgefuehrt = False
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }


@router.get("/{anlage_id}/verfuegbare-monate")
async def verfuegbare_monate(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert alle Jahr/Monat-Kombinationen mit TagesZusammenfassung-Einträgen.

    Für Jahr-/Monats-Selektoren, die nur Werte mit Daten anbieten sollen.
    Sortierung: neueste zuerst.
    """
    from sqlalchemy import func

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    jahr = func.extract("year", TagesZusammenfassung.datum)
    monat = func.extract("month", TagesZusammenfassung.datum)
    rows = (await db.execute(
        select(jahr.label("jahr"), monat.label("monat"), func.count().label("tage"))
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .group_by(jahr, monat)
        .order_by(jahr.desc(), monat.desc())
    )).all()

    return [
        {"jahr": int(r.jahr), "monat": int(r.monat), "tage": int(r.tage)}
        for r in rows
    ]


@router.get("/{anlage_id}/stats")
async def get_anlage_stats(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Anlage-spezifische Profildaten-Statistik für die Energieprofil-Seite.

    Zählt Stundenwerte, Tageszusammenfassungen und Monatsdaten nur für diese
    Anlage und liefert den Abdeckungs-Zeitraum aus TagesZusammenfassung.
    """
    from sqlalchemy import func
    from backend.models.monatsdaten import Monatsdaten

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    stundenwerte = await db.scalar(
        select(func.count(TagesEnergieProfil.id)).where(TagesEnergieProfil.anlage_id == anlage_id)
    ) or 0
    tageszusammenfassungen = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(TagesZusammenfassung.anlage_id == anlage_id)
    ) or 0
    monatswerte = await db.scalar(
        select(func.count(Monatsdaten.id)).where(Monatsdaten.anlage_id == anlage_id)
    ) or 0

    zeitraum = None
    if tageszusammenfassungen > 0:
        row = (await db.execute(
            select(
                func.min(TagesZusammenfassung.datum),
                func.max(TagesZusammenfassung.datum),
                func.count(func.distinct(TagesZusammenfassung.datum)),
            ).where(TagesZusammenfassung.anlage_id == anlage_id)
        )).one()
        von_datum, bis_datum, tage_mit_daten = row
        if von_datum:
            tage_gesamt = (bis_datum - von_datum).days + 1
            zeitraum = {
                "von": von_datum.isoformat(),
                "bis": bis_datum.isoformat(),
                "tage_mit_daten": tage_mit_daten,
                "tage_gesamt": tage_gesamt,
                "abdeckung_prozent": round(tage_mit_daten / tage_gesamt * 100, 1) if tage_gesamt > 0 else 0,
            }

    return {
        "stundenwerte": int(stundenwerte),
        "tageszusammenfassungen": int(tageszusammenfassungen),
        "monatswerte": int(monatswerte),
        "zeitraum": zeitraum,
        "wachstum_pro_monat": 750,  # 24h + 1 Tagessumme × 30 Tage
    }


@router.post("/reaggregate-heute")
async def reaggregate_heute():
    """Triggert sofortige Neu-Aggregation des heutigen Tages für alle Anlagen."""
    from backend.services.energie_profil_service import aggregate_today_all
    results = await aggregate_today_all()
    return {"status": "ok", "anlagen": results}


@router.post("/{anlage_id}/vollbackfill")
async def vollbackfill(
    anlage_id: int,
    von: Optional[date] = Query(None, description="Startdatum (Standard: frühestes Datum in HA Statistics)"),
    bis: Optional[date] = Query(None, description="Enddatum (Standard: gestern)"),
    overwrite: bool = Query(False, description="Bestehende Tage überschreiben statt überspringen"),
    db: AsyncSession = Depends(get_db),
):
    """
    Berechnet Energieprofile rückwirkend aus HA Long-Term Statistics.

    Füllt TagesEnergieProfil + TagesZusammenfassung für den gesamten Zeitraum
    (unabhängig von der ~10-Tage-Grenze der HA-Sensor-History).
    Überspringt bereits vorhandene Tage (außer bei overwrite=True).

    Returns:
        verarbeitet: Anzahl Tage im Zeitraum
        geschrieben: Davon neu geschriebene Tage
    """
    from backend.services.energie_profil_service import resolve_and_backfill_from_statistics

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    try:
        backfill = await resolve_and_backfill_from_statistics(anlage, db, von=von, bis=bis, overwrite=overwrite)
    except Exception as e:
        import traceback
        logger.error(f"Vollbackfill Anlage {anlage_id} FEHLER: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    if backfill.missing_eids:
        logger.warning(
            f"Anlage {anlage_id}: {len(backfill.missing_eids)} Sensor(en) nicht in HA "
            f"statistics_meta gefunden, werden ignoriert: {backfill.missing_eids}"
        )

    if backfill.status == "ha_unavailable":
        raise HTTPException(status_code=503, detail=backfill.detail)
    if backfill.status in ("no_sensors", "no_valid_sensors", "earliest_unknown", "empty_range"):
        raise HTTPException(status_code=400, detail=backfill.detail)

    # Flag setzen, damit der Auto-Vollbackfill im _post_save_hintergrund nicht erneut läuft
    anlage.vollbackfill_durchgefuehrt = True
    await db.commit()

    logger.info(
        f"Vollbackfill Anlage {anlage_id}: {backfill.geschrieben}/{backfill.verarbeitet} Tage "
        f"von {backfill.von} bis {backfill.bis}"
    )
    return {
        "verarbeitet": backfill.verarbeitet,
        "geschrieben": backfill.geschrieben,
        "von": backfill.von.isoformat(),
        "bis": backfill.bis.isoformat(),
    }


@router.get("/{anlage_id}/kraftstoffpreis-status")
async def kraftstoffpreis_status(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert die Anzahl offener Zeilen ohne Kraftstoffpreis für die UI-Sichtbarkeit.
    """
    from sqlalchemy import func
    from backend.models.monatsdaten import Monatsdaten

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    tages_offen = await db.scalar(
        select(func.count(TagesZusammenfassung.id)).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.kraftstoffpreis_euro.is_(None),
        )
    )
    monats_offen = await db.scalar(
        select(func.count(Monatsdaten.id)).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.kraftstoffpreis_euro.is_(None),
        )
    )
    return {
        "tages_offen": int(tages_offen or 0),
        "monats_offen": int(monats_offen or 0),
        "land": anlage.standort_land or "DE",
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill/tages")
async def kraftstoffpreis_backfill_tages(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt TagesZusammenfassung.kraftstoffpreis_euro aus EU Oil Bulletin
    (Euro-Super 95, inkl. Steuern) für alle Tage ohne Preis.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import backfill_kraftstoffpreise
    land = anlage.standort_land or "DE"
    info = await backfill_kraftstoffpreise(anlage_id, land, db)
    return {
        "aktualisiert": info.get("aktualisiert", 0),
        "land": info.get("land", land),
        "hinweis": info.get("hinweis"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill/monats")
async def kraftstoffpreis_backfill_monats(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt Monatsdaten.kraftstoffpreis_euro aus EU Oil Bulletin
    (Monatsdurchschnitt aus Wochenpreisen) für alle Monate ohne Preis.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import backfill_monatsdaten_kraftstoffpreise
    land = anlage.standort_land or "DE"
    info = await backfill_monatsdaten_kraftstoffpreise(anlage_id, land, db)
    return {
        "aktualisiert": info.get("aktualisiert", 0),
        "land": info.get("land", land),
        "hinweis": info.get("hinweis"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill")
async def kraftstoffpreis_backfill(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Alt-Endpoint (Rückwärtskompatibilität): befüllt Tages- und Monats-Kraftstoffpreise
    in einem Aufruf. Neue UIs sollten die split-Endpoints ``/tages`` und ``/monats`` nutzen.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import (
        backfill_kraftstoffpreise, backfill_monatsdaten_kraftstoffpreise
    )
    land = anlage.standort_land or "DE"
    tages_info = await backfill_kraftstoffpreise(anlage_id, land, db)
    monats_info = await backfill_monatsdaten_kraftstoffpreise(anlage_id, land, db)
    return {
        "tages_aktualisiert": tages_info.get("aktualisiert", 0),
        "monats_aktualisiert": monats_info.get("aktualisiert", 0),
        "land": tages_info.get("land", land),
    }


@router.delete("/rohdaten")
async def delete_alle_rohdaten(
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten aller Anlagen.

    Wird verwendet wenn Energieprofil-Daten durch falsch gemappte Sensoren
    korrumpiert wurden. Monatsdaten bleiben erhalten.
    Der Scheduler berechnet alles neu (max. 15 Min).
    """
    del_stunden = await db.execute(delete(TagesEnergieProfil))
    del_tage = await db.execute(delete(TagesZusammenfassung))
    # Flag bei ALLEN Anlagen zurücksetzen, damit der nächste Monatsabschluss
    # den Auto-Vollbackfill aus HA Statistics erneut anstößt
    await db.execute(update(Anlage).values(vollbackfill_durchgefuehrt=False))
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }


# ── Tagesprognose (Etappe 3b) ──────────────────────────────────────────────


class StundenPrognose(BaseModel):
    """Prognose für eine Stunde: PV, Verbrauch, Netto-Bilanz, Batterie-SoC."""
    stunde: int
    pv_kw: float
    verbrauch_kw: float
    netto_kw: float           # pv - verbrauch (positiv=Überschuss)
    netzbezug_kw: float       # max(0, Bedarf nach Batterie-Entladung)
    einspeisung_kw: float     # max(0, Überschuss nach Batterie-Ladung)
    soc_prozent: Optional[float] = None  # Simulierter Batterie-SoC


class TagesPrognoseResponse(BaseModel):
    """Kombinierte Verbrauchs- + PV- + Batterie-Prognose für einen Tag."""
    datum: str
    stunden: list[StundenPrognose]
    # Zusammenfassung
    pv_summe_kwh: float
    verbrauch_summe_kwh: float
    netzbezug_summe_kwh: float
    einspeisung_summe_kwh: float
    eigenverbrauch_kwh: float
    autarkie_prozent: float
    # Speicher (optional)
    speicher_kapazitaet_kwh: Optional[float] = None
    speicher_voll_um: Optional[str] = None
    speicher_leer_um: Optional[str] = None
    # Meta
    verbrauch_basis: str        # "gleicher_wochentag", "tagestyp", "alle"
    pv_quelle: str              # "openmeteo" oder "solcast"
    daten_tage: int


@router.get("/{anlage_id}/tagesprognose", response_model=TagesPrognoseResponse)
async def get_tagesprognose(
    anlage_id: int,
    datum: Optional[date] = Query(
        default=None,
        description="Ziel-Datum (Default: morgen)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Kombinierte Tagesprognose: Verbrauch + PV + Batterie-Simulation.

    Berechnet für einen Tag (Standard: morgen):
    - Verbrauchsprofil aus historischen Stundenmitteln (Wochenmuster-Basis)
    - PV-Stundenprofil aus Solar Forecast (OpenMeteo GTI oder Solcast)
    - Netto-Bilanz und optionale Batterie-SoC-Simulation
    """
    if datum is None:
        datum = date.today() + timedelta(days=1)

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten konfiguriert")

    # ── 1. Verbrauchsprognose ──
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    vp = await get_verbrauch_prognose(anlage_id, datum, db)
    if not vp:
        raise HTTPException(
            status_code=422,
            detail="Zu wenig historische Energieprofil-Daten für Verbrauchsprognose. "
                   "Mindestens 3 vollständige Tage benötigt."
        )

    verbrauch_stunden = vp["stunden_kw"]

    # ── 2. PV-Stundenprofil ──
    pv_stunden = [0.0] * 24
    pv_quelle = "openmeteo"

    # Versuche Solcast zuerst (wenn konfiguriert)
    prognose_basis = getattr(anlage, "prognose_basis", None) or "openmeteo"
    solcast_config = (anlage.sensor_mapping or {}).get("solcast_config")

    if solcast_config and prognose_basis == "solcast":
        try:
            from backend.services.solcast_service import get_solcast_forecast
            solcast = await get_solcast_forecast(anlage)
            if solcast and solcast.hourly_kw and len(solcast.hourly_kw) == 24:
                # Solcast hourly_kw enthält Werte für heute
                # Für morgen: tage_voraus nutzen (falls verfügbar mit Stundenwerten)
                # Sonst: hourly als Approximation
                pv_stunden = list(solcast.hourly_kw)
                pv_quelle = "solcast"
        except Exception as e:
            logger.warning("Solcast für Tagesprognose fehlgeschlagen: %s", e)

    # Fallback: OpenMeteo GTI
    if pv_quelle == "openmeteo":
        try:
            from backend.services.solar_forecast_service import get_solar_prognose

            # Strings für Multi-Ausrichtung laden
            inv_result = await db.execute(
                select(Investition).where(
                    Investition.anlage_id == anlage_id,
                    Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
                    Investition.aktiv.is_(True),
                )
            )
            invs = inv_result.scalars().all()
            # Nur aktive (nicht stillgelegte) Investitionen
            aktive_invs = [
                inv for inv in invs
                if not inv.stilllegungsdatum or inv.stilllegungsdatum >= datum
            ]

            if aktive_invs:
                total_kwp = sum((inv.parameter or {}).get("kwp", 0) or 0 for inv in aktive_invs)
                system_losses = (anlage.system_losses or 14) / 100

                # Tage bis zum Zieldatum berechnen
                tage_bis_ziel = (datum - date.today()).days
                forecast_days = max(tage_bis_ziel + 1, 2)

                # Neigung + Azimut aus den PV-Parametern extrahieren. Reihenfolge
                # der Felder wie in solar_prognose.py (erst *_grad als Zahl, dann
                # String-Mapping als Fallback), damit Tagesprognose und Kurzfrist
                # dieselben Eingabewerte sehen.
                ausrichtung_map = {
                    "sued": 0, "süd": 0, "s": 0,
                    "ost": -90, "o": -90, "e": -90,
                    "west": 90, "w": 90,
                    "nord": 180, "n": 180,
                    "suedost": -45, "südost": -45, "so": -45, "se": -45,
                    "suedwest": 45, "südwest": 45, "sw": 45,
                    "nordost": -135, "no": -135, "ne": -135,
                    "nordwest": 135, "nw": 135,
                }
                p0 = aktive_invs[0].parameter or {}
                neigung_raw = p0.get("neigung_grad", p0.get("neigung", 35))
                ausrichtung_raw = p0.get("ausrichtung_grad", p0.get("ausrichtung", 0))
                if isinstance(ausrichtung_raw, str):
                    ausrichtung_raw = ausrichtung_map.get(ausrichtung_raw.lower(), 0)

                prognose = await get_solar_prognose(
                    latitude=anlage.latitude,
                    longitude=anlage.longitude,
                    kwp=total_kwp,
                    neigung=int(neigung_raw),
                    ausrichtung=int(ausrichtung_raw),
                    days=forecast_days,
                    system_losses=system_losses,
                )
                if prognose:
                    ziel_str = datum.isoformat()
                    for tag in prognose.tageswerte:
                        if tag.datum == ziel_str and tag.stunden_kw:
                            pv_stunden = tag.stunden_kw
                            break

                    # Lernfaktor anwenden (MOS-Kaskade)
                    from backend.api.routes.live_wetter import _get_lernfaktor
                    lernfaktor = await _get_lernfaktor(anlage_id, db)
                    if lernfaktor is not None:
                        pv_stunden = [round(v * lernfaktor, 3) for v in pv_stunden]

        except Exception as e:
            logger.warning("PV-Prognose für Tagesprognose fehlgeschlagen: %s", e)

    # ── 3. Batterie-Info laden ──
    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == InvestitionTyp.SPEICHER.value,
            Investition.aktiv.is_(True),
        )
    )
    speicher_invs = [
        inv for inv in inv_result.scalars().all()
        if not inv.stilllegungsdatum or inv.stilllegungsdatum >= datum
    ]

    speicher_kap = sum(
        (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0
        for inv in speicher_invs
    )

    # Start-SoC: Ø SoC um Mitternacht der letzten 7 Tage
    start_soc = 50.0  # Default
    if speicher_kap > 0:
        soc_result = await db.execute(
            select(TagesEnergieProfil.soc_prozent)
            .where(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum >= datum - timedelta(days=7),
                TagesEnergieProfil.datum < datum,
                TagesEnergieProfil.stunde == 0,
                TagesEnergieProfil.soc_prozent.isnot(None),
            )
            .order_by(TagesEnergieProfil.datum.desc())
        )
        soc_werte = [r for r in soc_result.scalars().all()]
        if soc_werte:
            start_soc = sum(soc_werte) / len(soc_werte)

    # ── 4. Stündliche Bilanz + Batterie-Simulation ──
    stunden: list[StundenPrognose] = []
    soc = start_soc
    speicher_voll_um = None
    speicher_leer_um = None

    sum_pv = 0.0
    sum_verbrauch = 0.0
    sum_netzbezug = 0.0
    sum_einspeisung = 0.0

    for h in range(24):
        pv = pv_stunden[h] if h < len(pv_stunden) else 0.0
        vb = verbrauch_stunden[h] if h < len(verbrauch_stunden) else 0.0
        netto = pv - vb  # positiv = Überschuss

        netzbezug = 0.0
        einspeisung = 0.0
        soc_h: Optional[float] = None

        if speicher_kap > 0:
            if netto > 0:
                # Überschuss → Batterie laden
                lade_kapazitaet = (100.0 - soc) / 100.0 * speicher_kap
                ladung = min(netto, lade_kapazitaet)  # kWh (1h Intervall)
                soc += (ladung / speicher_kap) * 100.0
                soc = min(soc, 100.0)
                rest_ueberschuss = netto - ladung
                einspeisung = rest_ueberschuss
            else:
                # Defizit → Batterie entladen
                defizit = abs(netto)
                entlade_kapazitaet = soc / 100.0 * speicher_kap
                entladung = min(defizit, entlade_kapazitaet)
                soc -= (entladung / speicher_kap) * 100.0
                soc = max(soc, 0.0)
                rest_defizit = defizit - entladung
                netzbezug = rest_defizit

            soc_h = round(soc, 1)

            if soc >= 98.0 and speicher_voll_um is None:
                speicher_voll_um = f"{h:02d}:00"
            if soc <= 2.0 and speicher_leer_um is None and h >= 12:
                speicher_leer_um = f"{h:02d}:00"
        else:
            # Ohne Batterie: direkte Bilanz
            if netto > 0:
                einspeisung = netto
            else:
                netzbezug = abs(netto)

        sum_pv += pv
        sum_verbrauch += vb
        sum_netzbezug += netzbezug
        sum_einspeisung += einspeisung

        stunden.append(StundenPrognose(
            stunde=h,
            pv_kw=round(pv, 3),
            verbrauch_kw=round(vb, 3),
            netto_kw=round(netto, 3),
            netzbezug_kw=round(netzbezug, 3),
            einspeisung_kw=round(einspeisung, 3),
            soc_prozent=soc_h,
        ))

    eigenverbrauch = sum_pv - sum_einspeisung
    autarkie = (eigenverbrauch / sum_verbrauch * 100) if sum_verbrauch > 0 else 0.0

    return TagesPrognoseResponse(
        datum=datum.isoformat(),
        stunden=stunden,
        pv_summe_kwh=round(sum_pv, 2),
        verbrauch_summe_kwh=round(sum_verbrauch, 2),
        netzbezug_summe_kwh=round(sum_netzbezug, 2),
        einspeisung_summe_kwh=round(sum_einspeisung, 2),
        eigenverbrauch_kwh=round(eigenverbrauch, 2),
        autarkie_prozent=round(autarkie, 1),
        speicher_kapazitaet_kwh=round(speicher_kap, 1) if speicher_kap > 0 else None,
        speicher_voll_um=speicher_voll_um,
        speicher_leer_um=speicher_leer_um,
        verbrauch_basis=vp["basis"],
        pv_quelle=pv_quelle,
        daten_tage=vp["daten_tage"],
    )
