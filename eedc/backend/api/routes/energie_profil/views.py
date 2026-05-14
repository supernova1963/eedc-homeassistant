"""
Energie-Profil API — Read-Endpoints.

GET /api/energie-profil/{anlage_id}/tage      — Tageszusammenfassungen
GET /api/energie-profil/{anlage_id}/stunden   — Stundenwerte für einen Tag
GET /api/energie-profil/{anlage_id}/wochenmuster — Ø-Tagesprofil je Wochentag
GET /api/energie-profil/{anlage_id}/monat     — Monatsauswertung (Heatmap + KPIs + Peaks)
GET /api/energie-profil/{anlage_id}/debug-rohdaten — Rohdaten TagesEnergieProfil (7 Tage)
GET /api/energie-profil/{anlage_id}/verfuegbare-monate — Jahr/Monat-Kombis mit Daten
GET /api/energie-profil/{anlage_id}/stats     — Datenbestand für Settings
GET /api/energie-profil/{anlage_id}/reaggregate-tag/preview — Diff-Vorschau Reaggregate
GET /api/energie-profil/{anlage_id}/kraftstoffpreis-status — Anzahl offener Zeilen
GET /api/energie-profil/{anlage_id}/tagesprognose — Kombinierte Tagesprognose
"""

import calendar
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

from ._shared import (
    HeatmapZelle,
    KategorieSumme,
    KomponentenEintrag,
    MonatsAuswertungResponse,
    PeakStunde,
    ReaggregatePreviewBoundary,
    ReaggregatePreviewCounterTagesdelta,
    ReaggregatePreviewResponse,
    ReaggregatePreviewSlot,
    SerieInfo,
    StundenAntwort,
    StundenPrognose,
    StundenWertResponse,
    TagesPrognoseResponse,
    TagesZusammenfassungResponse,
    TagesprofilStunde,
    WochenmusterPunkt,
    _key_to_serie_info,
    logger,
)

router = APIRouter()


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
            komponenten_starts=t.komponenten_starts,
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
            wp_starts_anzahl=r.wp_starts_anzahl,
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


# ── Debug + Diagnose-Endpoints ───────────────────────────────────────────────

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


@router.get("/{anlage_id}/reaggregate-tag/preview", response_model=ReaggregatePreviewResponse)
async def reaggregate_tag_preview(
    anlage_id: int,
    datum: date = Query(..., description="Tag, fuer den die Vorschau erzeugt werden soll"),
    db: AsyncSession = Depends(get_db),
):
    """
    Liefert eine alt/neu-Vergleichstabelle der Snapshot-Werte und Slot-Deltas,
    die ein Reload des Tages produzieren WÜRDE — ohne irgendetwas zu schreiben.

    Damit der Nutzer vor der Übernahme sieht, welche Werte aus HA kommen und
    wie sich die Tagesbilanz ändert. Erst nach manueller Bestätigung
    (`POST /reaggregate-tag`) werden die Werte tatsächlich übernommen.

    Range: Vortag 23:00 .. Folgetag 00:00 (25 Boundaries pro Counter, 24 Slots).
    Slot 0 = snap(Tag 00:00) − snap(Vortag 23:00). Damit ist die Slot-0-
    Boundary in der Tabelle sichtbar — der ehemalige Hauptverdächtige für
    persistente Counter-Spikes (Befund Rainer 1.5.2026).
    """
    from backend.services.sensor_snapshot_service import get_reaggregate_preview

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

    try:
        preview = await get_reaggregate_preview(db, anlage, invs_by_id, datum)
    except Exception as e:
        logger.error(
            f"Reaggregate-Preview Anlage {anlage_id} {datum}: {type(e).__name__}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    return ReaggregatePreviewResponse(
        datum=datum.isoformat(),
        boundaries=[
            ReaggregatePreviewBoundary(
                sensor_key=b["sensor_key"],
                kategorie=b["kategorie"],
                zeitpunkt=b["zeitpunkt"].isoformat(),
                alt_kwh=b["alt_kwh"],
                neu_kwh=b["neu_kwh"],
            )
            for b in preview["boundaries"]
        ],
        slot_deltas=[
            ReaggregatePreviewSlot(
                stunde=s["stunde"],
                kategorie=s["kategorie"],
                alt_kwh=s["alt_kwh"],
                neu_kwh=s["neu_kwh"],
            )
            for s in preview["slot_deltas"]
        ],
        tagesumme_alt=preview["tagesumme_alt"],
        tagesumme_neu=preview["tagesumme_neu"],
        ha_verfuegbar=preview["ha_verfuegbar"],
        counter_tagesdelta=[
            ReaggregatePreviewCounterTagesdelta(
                feld=c["feld"],
                alt=c["alt"],
                neu=c["neu"],
            )
            for c in preview.get("counter_tagesdelta", [])
        ],
    )


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


# ── Tagesprognose (Etappe 3b) ──────────────────────────────────────────────


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

    # Versuche Solcast zuerst (wenn als Quelle gewählt)
    from backend.services.prognose_router import resolve_prognose_quelle
    pq = resolve_prognose_quelle(anlage)

    if pq.ist_solcast:
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
                # Einheitlich kWp + Neigung + Azimut aus Top-Level-Spalten ODER
                # parameter-JSON lesen — je nachdem, wo das Formular die Werte
                # gespeichert hat. Ohne den Helper fallen Prognose-Pfade stumm
                # auf Neigung=35°/Azimut=0° zurück, wenn die Werte nur in den
                # Top-Level-Spalten (Investition.neigung_grad, .ausrichtung)
                # liegen statt im parameter-JSON.
                from backend.services.pv_orientation import (
                    get_pv_kwp, get_pv_neigung, get_pv_azimut,
                )
                from backend.services.solar_forecast_service import DEFAULT_SYSTEM_LOSSES
                from backend.models.pvgis_prognose import PVGISPrognose
                total_kwp = sum(get_pv_kwp(inv) for inv in aktive_invs)

                # system_losses aus aktuellem PVGIS-Eintrag (gleicher Pfad wie
                # solar_prognose.py und prefetch_service.py). Es gibt KEIN
                # system_losses-Attribut auf Anlage — der frühere Zugriff
                # `anlage.system_losses` warf einen AttributeError, der im
                # try/except geschluckt wurde und pv_stunden auf [0] * 24 ließ.
                pvgis_result = await db.execute(
                    select(PVGISPrognose).where(
                        PVGISPrognose.anlage_id == anlage_id,
                        PVGISPrognose.ist_aktiv == True,
                    ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
                )
                pvgis = pvgis_result.scalar_one_or_none()
                system_losses = (
                    pvgis.system_losses / 100 if pvgis and pvgis.system_losses
                    else DEFAULT_SYSTEM_LOSSES
                )

                # Tage bis zum Zieldatum berechnen
                tage_bis_ziel = (datum - date.today()).days
                forecast_days = max(tage_bis_ziel + 1, 2)

                prognose = await get_solar_prognose(
                    latitude=anlage.latitude,
                    longitude=anlage.longitude,
                    kwp=total_kwp,
                    neigung=get_pv_neigung(aktive_invs[0]),
                    ausrichtung=get_pv_azimut(aktive_invs[0]),
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
