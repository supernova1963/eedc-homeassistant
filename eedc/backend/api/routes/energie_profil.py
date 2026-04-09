"""
Energie-Profil API - Tägliche und stündliche Energiedaten.

GET /api/energie-profil/{anlage_id}/tage      — Tageszusammenfassungen
GET /api/energie-profil/{anlage_id}/stunden   — Stundenwerte für einen Tag
GET /api/energie-profil/{anlage_id}/wochenmuster — Ø-Tagesprofil je Wochentag
GET /api/energie-profil/{anlage_id}/debug-rohdaten — Rohdaten TagesEnergieProfil (7 Tage)
DELETE /api/energie-profil/{anlage_id}/rohdaten — Löscht TagesEnergieProfil-Daten
"""

import logging
import re
from collections import defaultdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
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
    Löscht alle TagesEnergieProfil-Daten einer Anlage.

    Der Scheduler schreibt ab dem nächsten Lauf (alle 15 Min) neue, korrekte Daten.
    Nur aufrufen wenn die Daten nachweislich falsch sind (z.B. falsch gemappte Sensoren).
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    del_result = await db.execute(
        delete(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage_id)
    )
    await db.commit()

    return {
        "geloescht": del_result.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten.",
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
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }
