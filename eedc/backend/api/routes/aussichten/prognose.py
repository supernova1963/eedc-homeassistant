"""Aussichten — PV-Ertragsprognosen.

GET /api/aussichten/kurzfristig/{anlage_id} — 7–16 Tage aus der Wettervorhersage (Prognose-Kanon)
GET /api/aussichten/langfristig/{anlage_id} — Monate aus PVGIS-TMY und Trend
"""
# Reiner Umzug aus `api/routes/aussichten.py` (18.09.2026, Vorlage 7 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import bad_request
from backend.core.berechnungen.ergebnis import quote
from backend.api.deps import get_db
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.utils import wetter_symbol_aus_tag
from backend.services.wetter.pvgis import get_pvgis_tmy_defaults
from backend.services.wetter.models import WETTER_MODELLE
from backend.services.prognose_service import berechne_pv_ertrag_tag
from backend.services.pv_orientation import resolve_system_losses
from backend.api.routes.aussichten.basis import MONATSNAMEN, _lade_anlage_mit_pv
from backend.api.routes.aussichten.schemas import KurzfristPrognoseResponse, LangfristPrognoseResponse, MonatsPrognoseSchema, TagesPrognoseSchema, TrendAnalyseSchema

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
                pr = quote(ist_kwh, soll_kwh, 1)  # Layer, Päckchen Z1c (Nenner > 0 durch die Bedingung)
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
