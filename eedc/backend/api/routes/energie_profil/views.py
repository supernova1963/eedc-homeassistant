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

import asyncio
import calendar
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    geraete_spalte_kw,
)
from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
)
from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.core.exceptions import bad_request, not_found
from backend.core.investition_kennwerte import aggregiere_speicher_basis
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.einspeise_erloes_service import neg_preis_einspeisung_tageswert

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
    TagDetailResponse,
    TagStatusResponse,
    TagesZusammenfassungResponse,
    TagWerteResponse,
    TagesprofilStunde,
    WochenmusterPunkt,
    _key_to_serie_info,
    detail_kategorie,
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
        raise not_found("Anlage", anlage_id)

    # Maximal 366 Tage (ein Jahr)
    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

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
            # §51-Menge nur bei Anlagen mit gesetztem Schalter; die Stundenzahl
            # daneben bleibt ungegatet — sie ist reine Marktinfo, kein Abzug.
            einspeisung_neg_preis_kwh=neg_preis_einspeisung_tageswert(
                anlage, t.einspeisung_neg_preis_kwh
            ),
        )
        for t in tage
    ]


@router.get("/{anlage_id}/tage-werte", response_model=list[TagWerteResponse])
async def get_tage_werte(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """Tages-Werte-Zeilen (Energie-Bilanz + Finanzen + tag-native Metriken)
    für die Werte/Tabelle-Embed-Sicht in Tagesgranularität (IA v4 E3).

    Eine Zeile pro Tag, additiv zur Monatsbilanz (Σ stündl. TEP-Rows über den
    SoT-Helper `bilanz_aus_stundenrows`). Finanzen über den `baue_finanz_zeile`-
    SoT (je-Monat-Tarif).
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    # Lazy-Import: Service importiert das Routes-Schema (`_shared`) → Top-Level-
    # Import hier ergäbe einen Zyklus (routes-Package ↔ Service).
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    return await baue_tage_werte(db, anlage, von, bis)


@router.get("/{anlage_id}/tag-detail", response_model=TagDetailResponse)
async def get_tag_detail(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Snapshot-teure Tages-Detailwerte für Cockpit/Tag (D1 „maximal erheben",
    SPEC-COCKPIT-TAG-JAHR Abschnitt F/I): WP-Strom-Split + WP-Wärme (Heizung/
    Warmwasser, nur mit Wärmemengenzähler), Speicher-Netzladung + effektiver
    Ladepreis, E-Mob PV-/Netz-Anteil der Ladung, PV-Tages-SOLL (OM × eedc-
    Lernfaktor) und Tagestarif (für Wirkungsverluste €/Tarif-Zeile). Alles
    tagesgenau aus Snapshots/TEP/Prognose. Bewusst EIN Aufruf pro gewähltem Tag
    (nicht über die 90-Tage-Werte-Spanne), da Snapshot-Boundary-Diffs teuer sind.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    inv_result = await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))
    investitionen_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

    from backend.services.snapshot.aggregator import get_tagesdetail_kwh
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
    from backend.services.finanz_zeilen import FinanzZeileEingabe, baue_finanz_zeile
    from backend.api.routes.live_wetter import _get_lernfaktor

    detail = await get_tagesdetail_kwh(db, anlage, investitionen_by_id, datum)
    eff = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=datum, bis=datum)

    # PV Tages-SOLL = OM-Tagesprognose × eedc-Lernfaktor (wie Genauigkeits-Tracking).
    tz_prog = await db.execute(
        select(TagesZusammenfassung.pv_prognose_kwh).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )
    pv_prognose = tz_prog.scalar_one_or_none()
    lernfaktor = await _get_lernfaktor(anlage_id, db, quelle="openmeteo")
    soll_pv = round(pv_prognose * lernfaktor, 1) if (pv_prognose and lernfaktor) else pv_prognose

    # Tagestarif (Monatstarif je Tag) — Preise hängen nicht von Mengen ab.
    # Die Monatsdaten-Zeile muss mit: bei dynamischem Tarif trägt sie den
    # abgerechneten Monats-Ø, der den Stammdaten-Arbeitspreis schlägt. Ohne sie
    # nennt die Tarif-Zeile hier einen anderen Preis als Cockpit/Monat.
    md_tag = (await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == datum.year,
            Monatsdaten.monat == datum.month,
        )
    )).scalar_one_or_none()
    tarif = await baue_finanz_zeile(
        db,
        anlage_id,
        FinanzZeileEingabe(jahr=datum.year, monat=datum.month, monatsdaten=md_tag),
        tarif_cache={},
    )

    # #263/T2 — die Aufteilung Heizen/Kühlen des Tages, anlagenweite Σ.
    #
    # Die Rechnung ist ohnehin tagesweise (`falte_modus_split_tag`); die
    # Monatssicht summiert sie nur hinterher auf. Hier bleibt sie eine Ebene
    # früher stehen — derselbe Ladepfad, dieselbe Faltung.
    #
    # ⚠ **Die Teilmengen-Invariante gilt hier genauso** (`teilmengen_passen`):
    # passt ein Gerät nicht, wird es **ganz** ausgelassen statt gekappt — eine
    # stille Kappung machte aus einem Widerspruch eine plausible Zahl.
    from backend.core.berechnungen import teilmengen_passen
    from backend.core.betriebsmodus import HEIZEN, KUEHLEN
    from backend.services.energie_profil import lade_modus_split_tag

    heizen_tag = kuehlen_tag = rest_tag = abdeckung_tag = 0.0
    hat_split = False
    for inv_id_str, split in (await lade_modus_split_tag(db, anlage_id, datum)).items():
        inv = investitionen_by_id.get(inv_id_str)
        if inv is None or not inv.ist_aktiv_an(datum):
            continue
        if not teilmengen_passen(split, split.bezug_kwh):
            continue
        hat_split = True
        heizen_tag += split.teilmenge_kwh(HEIZEN)
        kuehlen_tag += split.teilmenge_kwh(KUEHLEN)
        rest_tag += max(
            0.0,
            float(split.bezug_kwh or 0.0)
            - split.teilmenge_kwh(HEIZEN) - split.teilmenge_kwh(KUEHLEN),
        )
        abdeckung_tag += split.abdeckung_h

    return TagDetailResponse(
        datum=datum,
        wp_modus_strom_heizen_kwh=round(heizen_tag, 2) if hat_split else None,
        wp_modus_strom_kuehlen_kwh=round(kuehlen_tag, 2) if hat_split else None,
        wp_modus_nicht_aufgeteilt_kwh=round(rest_tag, 2) if hat_split else None,
        wp_modus_abdeckung_h=round(abdeckung_tag, 1) if hat_split else None,
        wp_strom_heizen_kwh=detail.get("wp_strom_heizen_kwh"),
        wp_strom_warmwasser_kwh=detail.get("wp_strom_warmwasser_kwh"),
        wp_heizung_kwh=detail.get("wp_heizung_kwh"),
        wp_warmwasser_kwh=detail.get("wp_warmwasser_kwh"),
        speicher_ladung_netz_kwh=detail.get("speicher_ladung_netz_kwh"),
        speicher_effektiver_ladepreis_cent=(
            round(eff.effektiver_ladepreis_cent, 2)
            if eff.effektiver_ladepreis_cent is not None else None
        ),
        speicher_effektiver_ladepreis_quelle=eff.quelle,
        emob_ladung_pv_kwh=detail.get("emob_ladung_pv_kwh"),
        emob_ladung_netz_kwh=detail.get("emob_ladung_netz_kwh"),
        soll_pv_kwh=soll_pv,
        einspeise_preis_cent=tarif.einspeiseverguetung_cent,
        netzbezug_preis_cent=tarif.netzbezug_preis_cent,
    )


@router.get("/{anlage_id}/tag-status", response_model=TagStatusResponse)
async def get_tag_status(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Warum liegen für diesen Tag keine Werte vor — und was hilft? (F-2)

    Aufruf **nur** aus der leeren Tagessicht heraus, nicht bei jedem
    Tageswechsel: die letzte Prüfung ist ein HA-LTS-Read für den Tag, und nur
    er unterscheidet „Lücke, nachholbar" von „HA hat für den Tag selbst nichts".

    Bewusst getrennt vom Daten-Checker: der beschreibt die **Anlage** (letzte
    Tageszeile, 90-Tage-Lücken, ~2,5 s je Lauf) und beantwortet die Frage nach
    **diesem** Tag nicht.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    from backend.services.energie_profil.tag_status import baue_tag_status

    status = await baue_tag_status(db, anlage, datum)
    return TagStatusResponse(
        datum=datum,
        lage=status.lage,
        meldung=status.meldung,
        details=status.details,
        link=status.link,
        aktion_kind=status.aktion_kind,
        aktion_label=status.aktion_label,
    )


@router.get("/{anlage_id}/komponenten-serien", response_model=list[SerieInfo])
async def get_komponenten_serien(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Löst alle im Zeitraum vorkommenden `komponenten_kwh`-Keys zu SerieInfo
    (Label/Kategorie/Seite) auf.

    Dient der Tagestabelle, die pro Komponente eine eigene Diagnose-Spalte
    mit echtem Investitions-Label statt Roh-Key anbietet.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    result = await db.execute(
        select(TagesZusammenfassung.komponenten_kwh)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
    )
    alle_keys: set[str] = set()
    for (komponenten_kwh,) in result.all():
        if komponenten_kwh:
            alle_keys.update(komponenten_kwh.keys())

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    serien: list[SerieInfo] = []
    for key in sorted(alle_keys):
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
    return serien


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
        raise not_found("Anlage", anlage_id)

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

    # #263/T1 — die Geräte-Sammelspalten kennen BEIDE Pfade.
    #
    # `waermepumpe_kw`/`wallbox_kw` kommen aus dem Zähler-Snapshot und bleiben
    # leer, wenn nur ein Leistungssensor zugeordnet ist — während derselbe Wert
    # in `komponenten` steht, die gerätebenannte Spalte daneben ihn zeigt und
    # der Monats-Modus-Split aus ihm rechnet. Die Auflösung („Zähler schlägt
    # Leistung, kein Key heißt None") liegt im Layer, nicht hier.
    #
    # ⚠ **Bewusst nur die Geräte-Spalten.** `pv_kw` und `verbrauch_kw` sind
    # Bilanzgrößen — an ihnen hängen Performance-Ratio sowie Überschuss/Defizit
    # (`aggregator.py`). Ein Fallback dort änderte die Bilanz, nicht eine
    # Anzeige; das wäre ein eigener Vorgang mit eigener Messung.
    stunden = [
        StundenWertResponse(
            stunde=r.stunde,
            pv_kw=r.pv_kw,
            verbrauch_kw=r.verbrauch_kw,
            einspeisung_kw=r.einspeisung_kw,
            netzbezug_kw=r.netzbezug_kw,
            batterie_kw=r.batterie_kw,
            waermepumpe_kw=geraete_spalte_kw(
                r.waermepumpe_kw, r.komponenten, WAERMEPUMPE_KOMPONENTEN_PREFIXE,
            ),
            wallbox_kw=geraete_spalte_kw(
                r.wallbox_kw, r.komponenten, WALLBOX_KOMPONENTEN_PREFIXE,
            ),
            ueberschuss_kw=r.ueberschuss_kw,
            defizit_kw=r.defizit_kw,
            temperatur_c=r.temperatur_c,
            globalstrahlung_wm2=r.globalstrahlung_wm2,
            soc_prozent=r.soc_prozent,
            komponenten=r.komponenten,
            wp_starts_anzahl=r.wp_starts_anzahl,
            wp_betriebsstunden=r.wp_betriebsstunden,
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
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

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
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

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
    # Abdeckung je Achse + Paar-Abdeckung der beiden Differenzen (N-92) —
    # dieselbe Rechnung wie in `core/berechnungen/tagesbilanz.py`, weil dieser
    # Endpunkt laut Modul-Docstring dessen NULL-Semantik 1:1 trägt.
    pv_n = verbrauch_n = einspeisung_n = netzbezug_n = 0
    pv_ein_n = verb_netz_n = 0
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
            pv_n += 1
        if verbrauch is not None:
            verbrauch_sum += verbrauch
            verbrauch_n += 1
        if einspeisung is not None:
            einspeisung_sum += einspeisung
            einspeisung_n += 1
        if netzbezug is not None:
            netzbezug_sum += netzbezug
            netzbezug_n += 1
        if pv is not None and einspeisung is not None:
            pv_ein_n += 1
        if verbrauch is not None and netzbezug is not None:
            verb_netz_n += 1

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
    # Beide Quoten über den Layer-SoT (ADR-001) statt inline: die Formeln standen
    # hier ausgeschrieben und stimmten, aber dieselbe Kennzahl inline zu rechnen
    # ist genau der Weg, auf dem N129 entstanden ist — an der dritten Stelle
    # (Tagesvorschau) wich der Zähler ab, und kein Test sah es.
    #
    # ⚑ **N-92 (2026-08-22): beide Quoten stehen auf einer DIFFERENZ**, und eine
    # Differenz erbt die Unvollständigkeit jedes Summanden
    # (`KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 Regel 1). Die Summen darüber
    # überspringen NULL-Stunden korrekt — die Differenz erbte das nicht: fehlten
    # der Einspeisung Stunden und der PV keine, war der Eigenverbrauch um genau
    # die ungemessene Einspeisung zu hoch, und war der Netzbezug **gar nicht**
    # erfasst, meldete die Autarkie **100 %**. Der Zwilling im Tages-Layer trägt
    # die Begründung ausführlich; hier steht dieselbe Regel, damit die beiden
    # Sichten nicht auseinanderlaufen (die N-129-Klasse).
    eigenverbrauch_pv = pv_sum - einspeisung_sum
    ev_abdeckung_gleich = pv_n > 0 and pv_n == einspeisung_n == pv_ein_n
    autarkie_abdeckung_gleich = (
        netzbezug_n > 0 and verbrauch_n == netzbezug_n == verb_netz_n
    )
    autarkie = (
        round(autarkie_prozent(verbrauch_sum - netzbezug_sum, verbrauch_sum), 1)
        if verbrauch_sum > 0 and autarkie_abdeckung_gleich else None
    )
    eigenverbrauch = (
        round(eigenverbrauchsquote_prozent(eigenverbrauch_pv, pv_sum), 1)
        if pv_sum > 0 and ev_abdeckung_gleich else None
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
    # §51-Menge nur bei Anlagen mit gesetztem Schalter (Gate im Erlös-Service);
    # `negative_preis_stunden` oben bleibt ungegatet — Marktinfo, kein Abzug.
    neg_einsp_werte = [
        w for w in (
            neg_preis_einspeisung_tageswert(anlage, t.einspeisung_neg_preis_kwh)
            for t in tag_rows
        ) if w is not None
    ]
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

    # Einträge auflösen + Anteile berechnen. Detail-Kategorie-Mapping liegt im
    # Shared-Helper `detail_kategorie` (ADR-001 testbar, #316).
    komponenten_liste: list[KomponentenEintrag] = []
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
        raise not_found("Anlage")

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
        raise not_found("Anlage", anlage_id)

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
        raise not_found("Anlage", anlage_id)

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
        raise not_found("Anlage", anlage_id)

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
        raise not_found("Anlage", anlage_id)

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


async def _pv_stunden_aus_kanon(db, anlage, datum: date) -> Optional[list[float]]:
    """Korrigierte 24 kWh-Slots des Zieltages aus dem Prognose-Kanon.

    ``None`` = der Kanon hat für diesen Tag kein Stundenprofil (kein Abruf,
    kein Treffer, Schätzpfad ohne Hourly) → der Aufrufer nutzt seinen Fallback.

    Warum überhaupt: der frühere Eigenweg holte OpenMeteo mit **einem** Abruf
    für die Gesamt-kWp und der Orientierung der zufällig ersten Investition
    (kein ``ORDER BY``) und multiplizierte den flachen Legacy-Skalar darauf.
    Beides weicht vom Kanon ab (Multi-String-Fan-out + Kaskade pro Energie-Slot)
    — dieselbe Anlage bekam so je nach Pfad verschiedene Tagessummen.

    ``days`` kommt aus ``kanon_days`` (Horizont-Formel-SoT, geteilt mit
    ``/solar-prognose``): mindestens 4, für spätere Zieltage aus dem Datum
    abgeleitet — der Picker erlaubt +14 Tage, also ``days`` ≤ 15 (OpenMeteo-
    Maximum 16). Dass dabei derselbe OpenMeteo-Snapshot gezogen wird wie im
    Prognosen-Vergleich und im HA-/MQTT-Export, hängt seit E15/A29 nicht mehr
    an diesem Horizont: der Cache-Key trägt den Modell-Snapshot, nicht die
    Anfrage (``services/wetter/cache.snapshot_days``).
    """
    tage_bis_ziel = (datum - date.today()).days
    if tage_bis_ziel < 0:
        return None

    from backend.services.prognose_kanon import kanon_days, kanon_tagesprognose

    try:
        kanon = await kanon_tagesprognose(
            db, anlage,
            days=kanon_days(tage_bis_ziel + 1),
            # Interaktiver User-Request: der 1-30s-Random-Jitter gilt nur für
            # Hintergrund-Abrufe (R18-13, KONZEPT-LADEZEIT-CACHE-SWR).
            skip_jitter=True,
        )
    except Exception as e:
        logger.warning("Kanon-Tagesprognose fehlgeschlagen: %s", e)
        return None
    if not kanon:
        return None

    ziel_iso = datum.isoformat()
    for tag in kanon.tage:
        if tag is not None and tag.datum == ziel_iso and tag.profil is not None:
            # Export-Slots (2 NK) — exakt die Werte, die auch als MQTT-Attribut
            # `stundenprofil_kwh` rausgehen. Damit gilt die Kanon-Invariante
            # `Tageswert == Σ Export-Slots` auch für die Summenzeile hier.
            return list(tag.profil.stundenprofil_export_kwh)
    return None


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

    **Ohne Verbrauchshistorie** (< 3 vollständige Tage Energieprofil, also jede
    frische Installation) liefert die Route trotzdem die PV-Hälfte — sie hängt
    nur an Wetterdienst und kWp. Die verbrauchsabhängigen Felder sind dann
    ``None`` (nicht 0, das sähe aus wie ein Messwert) und ``hinweise`` sagt es.
    Bis A28 (N122) stand hier ein HTTP 422 für den GANZEN Endpoint.
    """
    if datum is None:
        datum = date.today() + timedelta(days=1)

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten konfiguriert")

    # `hinweise` begleitet die Antwort: jede Abweichung von „das ist die volle
    # Prognose für DIESEN Tag" wird hier vermerkt und geht in die Response (P4).
    hinweise: list[str] = []

    # ── 1. Verbrauchsprognose ──
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    vp = await get_verbrauch_prognose(anlage_id, datum, db)
    verbrauch_stunden = vp["stunden_kw"] if vp else None
    if vp is None:
        # A28 (N122): hier stand ein HTTP 422 für den ganzen Endpoint — die
        # PV-Stundenwerte fielen mit, obwohl sie keine Historie brauchen. Jede
        # frische Installation sah in den ersten Tagen deshalb nur eine
        # Fehlermeldung statt der PV-Vorschau. Der fehlende Teil wird jetzt
        # benannt (P4), statt die ganze Antwort zu verweigern.
        hinweise.append(
            "Für die Verbrauchsprognose fehlt noch die Historie — dafür braucht "
            "eedc mindestens 3 vollständige Tage Energieprofil. Gezeigt wird "
            "deshalb nur die PV-Vorschau; Verbrauch, Netzbezug, Einspeisung, "
            "Eigenverbrauch, Autarkie und die Speicher-Vorschau bleiben leer, "
            "bis genug Tage aufgezeichnet sind."
        )

    # ── 2. PV-Stundenprofil ──
    pv_stunden = [0.0] * 24
    pv_quelle = "openmeteo"
    pv_profil_vorhanden = False

    # Versuche Solcast zuerst (wenn als Quelle gewählt)
    from backend.services.prognose_router import resolve_prognose_quelle
    pq = resolve_prognose_quelle(anlage)

    if pq.ist_solcast:
        try:
            from backend.services.solcast_service import get_solcast_forecast
            solcast = await get_solcast_forecast(anlage)
            # Seit #357 trägt Solcast ein eigenes Stundenprofil je Prognosetag
            # (HA-Integration: `detailedForecast` am Tages-Sensor; API: 168 h).
            # Wo es eins gibt, ist der Zieltag echt beantwortet — die Näherung
            # samt Kennzeichnung bleibt nur für Tage ohne eigenes Profil.
            tages_profil = solcast.profil_fuer(datum) if solcast else None
            if tages_profil is not None:
                pv_stunden = list(tages_profil.p50)
                pv_quelle = "solcast"
                pv_profil_vorhanden = True
            elif solcast and solcast.hourly_kw and len(solcast.hourly_kw) == 24:
                # `solcast.hourly_kw` ist das Stundenprofil von HEUTE. Für einen
                # anderen Zieltag ist es eine Näherung — bisher stand das nur als
                # Code-Kommentar, während die Antwort `pv_quelle = "solcast"`
                # meldete wie bei einem echten Profil dieses Tages (N79). Der Wert
                # bleibt (er ist die beste verfügbare Information), aber die
                # Antwort sagt jetzt, worauf man sieht.
                pv_stunden = list(solcast.hourly_kw)
                pv_quelle = "solcast"
                pv_profil_vorhanden = True
                if datum != date.today():
                    hinweise.append(
                        "Solcast liefert für diesen Tag nur die Tagesmenge, kein "
                        "eigenes Stundenprofil. Der Tagesverlauf ist deshalb das "
                        "heutige Profil als Näherung für den "
                        f"{datum.strftime('%d.%m.%Y')} — die Tagessumme kann "
                        "abweichen."
                    )
        except Exception as e:
            logger.warning("Solcast für Tagesprognose fehlgeschlagen: %s", e)
            hinweise.append(
                "Die Solcast-Prognose war nicht abrufbar; für den PV-Tagesverlauf "
                "liegt keine Solcast-Quelle vor."
            )

    # Fallback: OpenMeteo GTI — kanonischer Weg zuerst (Multi-String-Fan-out +
    # Korrektur pro Energie-Slot), damit Chart/Tabelle denselben Tag zeigen wie
    # Prognosen-Vergleich und HA-/MQTT-Export.
    kanon_stunden = (
        await _pv_stunden_aus_kanon(db, anlage, datum)
        if pv_quelle == "openmeteo" else None
    )
    if kanon_stunden is not None:
        pv_stunden = kanon_stunden
        pv_profil_vorhanden = True
    elif pv_quelle == "openmeteo":
        # Fallback (Kanon ohne Ergebnis: kein OpenMeteo, keine kWp, Zieltag
        # jenseits des Abrufs): eigener Abruf-Pfad, damit die Prognose nicht
        # ganz ausfällt. Seit `49954860` (P1/N51) fächert er wie der Kanon je
        # Orientierungsgruppe auf; was bleibt, ist der flache Legacy-Skalar
        # (`_get_lernfaktor`) statt der Kaskade pro Energie-Slot — deshalb
        # kann seine Tagessumme weiter leicht vom Kanon abweichen.
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
                    orientierungs_gruppen, resolve_system_losses,
                )
                from backend.services.prognose_auswahl import lade_aktive_prognose

                # P1 (N51): EIN Abruf je Orientierungsgruppe statt eines Abrufs
                # über die Gesamt-kWp mit der Orientierung der zufällig ersten
                # Investition (`aktive_invs[0]`, Query ohne `ORDER BY`). Eine
                # Ost/West-Anlage bekam so den Tagesgang EINER Himmelsrichtung
                # auf die volle Leistung gerechnet — bei ausgeglichener
                # Verteilung ein Fehler in der Summenzeile, der sich NICHT
                # herausmittelt. Der Kanon-Pfad darüber fächert längst auf; hier
                # lief der Fallback als einzige Sicht daneben.
                # Bei genau EINER Gruppe ist der eine Abruf die korrekte Form —
                # dann ist bewiesen, dass alle Module dieselbe Orientierung
                # haben (dieselbe Guard-Form wie prefetch_service/solar_prognose).
                gruppen = orientierungs_gruppen(aktive_invs)

                # system_losses aus aktuellem PVGIS-Eintrag (gleicher Pfad wie
                # solar_prognose.py und prefetch_service.py). Es gibt KEIN
                # system_losses-Attribut auf Anlage — der frühere Zugriff
                # `anlage.system_losses` warf einen AttributeError, der im
                # try/except geschluckt wurde und pv_stunden auf [0] * 24 ließ.
                pvgis = await lade_aktive_prognose(db, anlage_id)
                system_losses = resolve_system_losses(pvgis)

                # Tage bis zum Zieldatum berechnen
                tage_bis_ziel = (datum - date.today()).days
                forecast_days = max(tage_bis_ziel + 1, 2)

                ergebnisse = await asyncio.gather(*[
                    get_solar_prognose(
                        latitude=anlage.latitude,
                        longitude=anlage.longitude,
                        kwp=g.kwp,
                        neigung=g.neigung,
                        ausrichtung=g.ausrichtung,
                        days=forecast_days,
                        system_losses=system_losses,
                        # Interaktiver User-Request (Stunden-/Tagesprognose der
                        # Aussicht): der 1-30s-Random-Jitter gilt nur für
                        # Hintergrund-Abrufe (R18-13, KONZEPT-LADEZEIT-CACHE-SWR).
                        skip_jitter=True,
                    )
                    for g in gruppen
                ])

                ziel_str = datum.isoformat()
                summe = [0.0] * 24
                geliefert = 0
                for prognose in ergebnisse:
                    if not prognose:
                        continue
                    for tag in prognose.tageswerte:
                        if tag.datum == ziel_str and tag.stunden_kw:
                            for i, v in enumerate(tag.stunden_kw[:24]):
                                summe[i] += v or 0.0
                            geliefert += 1
                            break

                if geliefert:
                    pv_stunden = [round(v, 3) for v in summe]
                    pv_profil_vorhanden = True

                    # P4: eine Teilsumme sagt es selbst. Fällt eine
                    # Orientierungsgruppe aus, fehlt ihr kWp-Anteil im
                    # Tagesverlauf — der Wert bleibt (beste verfügbare
                    # Information), aber nicht ungekennzeichnet.
                    if geliefert < len(gruppen):
                        hinweise.append(
                            f"Nur {geliefert} von {len(gruppen)} Dachflächen "
                            "(Orientierungsgruppen) haben eine Prognose geliefert. "
                            "Der PV-Tagesverlauf ist deshalb eine Teilsumme und zu "
                            "niedrig — bitte später erneut laden."
                        )

                    # Lernfaktor anwenden (MOS-Kaskade)
                    from backend.api.routes.live_wetter import _get_lernfaktor
                    lernfaktor = await _get_lernfaktor(anlage_id, db)
                    if lernfaktor is not None:
                        pv_stunden = [round(v * lernfaktor, 3) for v in pv_stunden]

        except Exception as e:
            logger.warning("PV-Prognose für Tagesprognose fehlgeschlagen: %s", e)

    # P4 (N78): Bis hierher konnte die Antwort mit der Vorbelegung `[0.0] * 24`
    # herauskommen — als PV-Prognose „0 kWh", nicht als „keine Prognose". Die
    # Speicher-Simulation unten rechnet mit diesen Nullen weiter und meldet dann
    # „Speicher lädt nicht". Die Zahlen bleiben (kein geschätzter Ersatz), aber
    # die Antwort sagt jetzt, dass sie keine Prognose sind.
    if not pv_profil_vorhanden:
        hinweise.append(
            "Für diesen Tag liegt keine PV-Prognose vor — der Wetterabruf ist "
            "ausgefallen oder der Tag liegt außerhalb des Prognose-Horizonts. Die "
            "PV-Werte im Verlauf sind deshalb 0 und bedeuten NICHT, dass die "
            "Anlage nichts erzeugt; auch die Speicher-Vorschau darunter ist damit "
            "ohne Aussage."
        )

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

    # A31-2/E-1: NETTO-Kapazität. Die Simulation unten fährt den Speicher von
    # 0 auf 100 % der übergebenen Zahl; mit der Brutto-Kapazität ist er
    # rechnerisch später voll als real. Stiller Brutto-Fallback (E17) — bei
    # ungepflegtem Netto-Feld bleibt alles wie bisher, deshalb hier bewusst
    # KEIN `hinweise`-Eintrag.
    # N-238: Kapazität UND Wirkungsgrad über den geteilten Helper — der
    # HA-Sensor `eedc_speicher_voll_um` liest dieselbe Regel, und zwei
    # gleichlautende Faltungen wären genau die Drift-Klasse dieses Projekts.
    speicher_kap, speicher_eta = aggregiere_speicher_basis(speicher_invs)
    speicher_kap = speicher_kap or 0.0

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
    # SoC-State-Machine + Bilanz-Rest liegen im Berechnungs-Layer (ADR-001).
    # Diese deskriptive Ganztags-Vorschau simuliert ab Mitternacht (start_soc =
    # 7-Tage-Mittel, start_stunde=0) — bewusst anders parametrisiert als der
    # HA-Export (ab aktuellem SoC), daher kein Symmetrie-Paar.
    stunden: list[StundenPrognose] = []
    sum_pv = 0.0
    sum_verbrauch: Optional[float] = None
    sum_netzbezug: Optional[float] = None
    sum_einspeisung: Optional[float] = None
    eigenverbrauch: Optional[float] = None
    autarkie: Optional[float] = None
    speicher_voll_um: Optional[str] = None
    speicher_leer_um: Optional[str] = None

    if verbrauch_stunden is None:
        # A28: ohne Verbrauchsprofil ist jede Bilanzgröße unbestimmt — die
        # Simulation liefe zwar durch (sie liest fehlende Slots als 0), würde
        # dann aber „Netzbezug 0, Autarkie 100 %" behaupten. Also gar nicht
        # rechnen und die Felder leer lassen (P4); das PV-Profil bleibt.
        sum_pv = sum(pv_stunden[:24])
        stunden = [
            StundenPrognose(
                stunde=h,
                pv_kw=round(pv_stunden[h] if h < len(pv_stunden) else 0.0, 3),
            )
            for h in range(24)
        ]
    else:
        sim = simuliere_speicher_tag(
            pv_stunden=pv_stunden,
            verbrauch_stunden=verbrauch_stunden,
            speicher_kap_kwh=speicher_kap,
            start_soc_prozent=start_soc,
            start_stunde=0,
            wirkungsgrad_prozent=speicher_eta,
        )
        speicher_voll_um = sim.speicher_voll_um
        speicher_leer_um = sim.speicher_leer_um

        sum_verbrauch = 0.0
        sum_netzbezug = 0.0
        sum_einspeisung = 0.0

        for b in sim.stunden_bilanz:
            sum_pv += b.pv_kwh
            sum_verbrauch += b.verbrauch_kwh
            sum_netzbezug += b.netzbezug_kwh
            sum_einspeisung += b.einspeisung_kwh

            stunden.append(StundenPrognose(
                stunde=b.stunde,
                pv_kw=round(b.pv_kwh, 3),
                verbrauch_kw=round(b.verbrauch_kwh, 3),
                netto_kw=round(b.netto_kwh, 3),
                netzbezug_kw=round(b.netzbezug_kwh, 3),
                einspeisung_kw=round(b.einspeisung_kwh, 3),
                soc_prozent=b.soc_prozent,
            ))

        # `eigenverbrauch` ist der PV-Eigenverbrauch (was die Anlage selbst nutzt,
        # inklusive der Speicherladung) — dieselbe Größe wie in
        # `core/berechnungen/tagesbilanz.py`, deshalb gleich benannt.
        eigenverbrauch = sum_pv - sum_einspeisung
        # N129: die Autarkie hat einen ANDEREN Zähler — den netzunabhängig
        # gedeckten Verbrauch. Bis 2026-07-28 stand hier der PV-Eigenverbrauch,
        # und weil der bei ladendem Speicher den Tagesverbrauch übersteigen kann,
        # meldete die Vorschau Autarkiegrade bis 125 %. Der Layer-SoT
        # (`kennzahlen.autarkie_prozent`) verzichtet ausdrücklich auf einen Cap
        # mit der Begründung „strukturell ≤ 100 %, weil Eigenverbrauch Teilmenge
        # des Gesamtverbrauchs ist" — diese Zusicherung gilt nur für den
        # richtigen Zähler. Ein Cap wäre hier die falsche Antwort gewesen: er
        # hätte 125 % auf 100 % gedrückt und den Fehler unsichtbar gemacht,
        # statt ihn zu beheben (ADR-001: Formel im Layer, nicht inline).
        autarkie = (
            autarkie_prozent(sum_verbrauch - sum_netzbezug, sum_verbrauch)
            if sum_verbrauch > 0 else 0.0
        )

    return TagesPrognoseResponse(
        datum=datum.isoformat(),
        stunden=stunden,
        pv_summe_kwh=round(sum_pv, 2),
        verbrauch_summe_kwh=round(sum_verbrauch, 2) if sum_verbrauch is not None else None,
        netzbezug_summe_kwh=round(sum_netzbezug, 2) if sum_netzbezug is not None else None,
        einspeisung_summe_kwh=round(sum_einspeisung, 2) if sum_einspeisung is not None else None,
        eigenverbrauch_kwh=round(eigenverbrauch, 2) if eigenverbrauch is not None else None,
        autarkie_prozent=round(autarkie, 1) if autarkie is not None else None,
        speicher_kapazitaet_kwh=round(speicher_kap, 1) if speicher_kap > 0 else None,
        speicher_voll_um=speicher_voll_um,
        speicher_leer_um=speicher_leer_um,
        verbrauch_basis=vp["basis"] if vp else None,
        pv_quelle=pv_quelle,
        daten_tage=vp["daten_tage"] if vp else None,
        hinweise=hinweise,
    )
