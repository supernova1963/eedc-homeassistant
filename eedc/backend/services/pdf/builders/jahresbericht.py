"""
Daten-Aggregation für den Jahresbericht.

Extrahiert die bisher in `api/routes/import_export/pdf_operations.py` inline
ausgeführte Logik und liefert ein einziges `context`-Dict, das das
Jinja2-Template direkt verwenden kann.

Reine Datenschicht — keine HTTP-, keine Render-Aufrufe.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.calculations import (
    CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_STROM_KG_KWH,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.strompreis import Strompreis

from ..charts import autarkie_chart, energie_fluss_chart, pv_erzeugung_chart

MONATSNAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


async def build_jahresbericht_context(
    db: AsyncSession,
    anlage_id: int,
    jahr: Optional[int] = None,
) -> dict:
    """
    Lädt alle Daten und liefert ein flaches Context-Dict für `jahresbericht.html`.

    Args:
        db: AsyncSession
        anlage_id: ID der Anlage
        jahr: Optional. Fehlt es, wird der gesamte Zeitraum erzeugt.

    Raises:
        LookupError: Wenn die Anlage nicht existiert.
    """
    # ── 1. Anlage ───────────────────────────────────────────────────────
    res = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = res.scalar_one_or_none()
    if not anlage:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")

    ist_gesamtzeitraum = jahr is None

    # ── 2. Strompreis (neuester Eintrag) ────────────────────────────────
    res = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage_id)
        .order_by(Strompreis.gueltig_ab.desc())
        .limit(1)
    )
    strompreis = res.scalar_one_or_none()
    netzbezug_cent = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0
    einspeise_cent = strompreis.einspeiseverguetung_cent_kwh if strompreis else 8.2

    # ── 3. Investitionen ────────────────────────────────────────────────
    # KEIN aktiv-Filter (Issue #123): Jahresbericht ist historisch, spätere
    # Stilllegung darf Komponenten-Daten nicht rückwirkend entfernen. Wenn ein
    # Jahr ausgewählt ist, wird zusätzlich auf den Einsatzzeitraum gefiltert.
    from backend.utils.investition_filter import aktiv_im_jahr
    inv_stmt = select(Investition).where(Investition.anlage_id == anlage_id)
    if jahr is not None:
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    res = await db.execute(inv_stmt)
    investitionen = res.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    hat_emobilitaet = any(i.typ in ("e-auto", "wallbox") for i in investitionen)
    hat_bkw = any(i.typ == "balkonkraftwerk" for i in investitionen)

    speicher_kapazitaet = 0.0
    for inv in investitionen:
        if inv.typ == "speicher":
            speicher_kapazitaet += (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0

    # ── 4. PVGIS-Prognose (letzte aktive) ───────────────────────────────
    res = await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )
    pvgis_prognosen = res.scalars().all()
    pvgis_by_month: dict[int, float] = {}
    for p in pvgis_prognosen:
        if p.monatswerte:
            for mw in p.monatswerte:
                m = mw.get("monat", 0)
                pvgis_by_month[m] = pvgis_by_month.get(m, 0) + (mw.get("e_month_kwh", 0) or 0)

    # ── 5. InvestitionMonatsdaten ───────────────────────────────────────
    inv_ids = [i.id for i in investitionen]
    all_imd: list[InvestitionMonatsdaten] = []
    if inv_ids:
        if ist_gesamtzeitraum:
            res = await db.execute(
                select(InvestitionMonatsdaten).where(
                    InvestitionMonatsdaten.investition_id.in_(inv_ids)
                )
            )
        else:
            res = await db.execute(
                select(InvestitionMonatsdaten).where(
                    InvestitionMonatsdaten.investition_id.in_(inv_ids),
                    InvestitionMonatsdaten.jahr == jahr,
                )
            )
        all_imd = list(res.scalars().all())

    # ── 6. Monatsdaten (Zähler-Werte) ───────────────────────────────────
    if ist_gesamtzeitraum:
        res = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
    else:
        res = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .where(Monatsdaten.jahr == jahr)
            .order_by(Monatsdaten.monat)
        )
    monatsdaten_list = list(res.scalars().all())

    if ist_gesamtzeitraum and monatsdaten_list:
        alle_jahre = sorted({m.jahr for m in monatsdaten_list})
    elif ist_gesamtzeitraum:
        start_jahr = anlage.installationsdatum.year if anlage.installationsdatum else datetime.now().year - 1
        alle_jahre = list(range(start_jahr, datetime.now().year + 1))
    else:
        alle_jahre = [jahr]
    start_jahr = alle_jahre[0]
    end_jahr = alle_jahre[-1]

    md_by_year_month: dict[tuple[int, int], Monatsdaten] = {
        (m.jahr, m.monat): m for m in monatsdaten_list
    }

    # PV-Erzeugung pro Jahr/Monat aus IMD
    pv_by_year_month: dict[tuple[int, int], float] = {}
    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if inv and inv.typ in ("pv-module", "balkonkraftwerk"):
            pv = (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0) or 0
            key = (imd.jahr, imd.monat)
            pv_by_year_month[key] = pv_by_year_month.get(key, 0) + pv

    # ── 7. Aggregate Wärmepumpe / E-Mob / Speicher ──────────────────────
    pv_gesamt = 0.0
    einsp_gesamt = 0.0
    netz_gesamt = 0.0
    ev_gesamt = 0.0

    speicher_ladung = 0.0
    speicher_entladung = 0.0
    wp_waerme = wp_heizung = wp_warmwasser = wp_strom = 0.0
    emob_km = emob_ladung = emob_pv = emob_netz = emob_v2h = 0.0

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue
        d = imd.verbrauch_daten or {}
        if inv.typ == "speicher":
            speicher_ladung += d.get("ladung_kwh", 0) or 0
            speicher_entladung += d.get("entladung_kwh", 0) or 0
        elif inv.typ == "waermepumpe":
            heiz = d.get("heizenergie_kwh", 0) or d.get("heizung_kwh", 0) or 0
            ww = d.get("warmwasser_kwh", 0) or 0
            wp_heizung += heiz
            wp_warmwasser += ww
            wp_waerme += d.get("waerme_kwh", 0) or (heiz + ww)
            wp_strom += d.get("stromverbrauch_kwh", 0) or 0
        elif inv.typ in ("e-auto", "wallbox"):
            emob_km += d.get("km_gefahren", 0) or 0
            emob_ladung += d.get("ladung_kwh", 0) or 0
            emob_pv += d.get("ladung_pv_kwh", 0) or 0
            emob_netz += d.get("ladung_netz_kwh", 0) or 0
            emob_v2h += d.get("v2h_entladung_kwh", 0) or 0

    # ── 8. Monats-Tabelle aufbauen ──────────────────────────────────────
    monats_zeilen: list[dict] = []

    def _zeile_fuer(j: int, m: int) -> dict:
        nonlocal pv_gesamt, einsp_gesamt, netz_gesamt, ev_gesamt
        md = md_by_year_month.get((j, m))
        pv = pv_by_year_month.get((j, m), 0)
        einsp = (md.einspeisung_kwh or 0) if md else 0
        netz = (md.netzbezug_kwh or 0) if md else 0
        ev = max(0.0, pv - einsp) if pv > 0 else 0.0
        gesamt = ev + netz
        autarkie = _safe_div(ev, gesamt) * 100
        spez = _safe_div(pv, anlage.leistung_kwp or 0)
        einsp_eur = einsp * einspeise_cent / 100
        ev_eur = ev * netzbezug_cent / 100
        pv_gesamt += pv
        einsp_gesamt += einsp
        netz_gesamt += netz
        ev_gesamt += ev
        return {
            "jahr": j,
            "monat": m,
            "monat_name": f"{MONATSNAMEN[m]} {j}" if ist_gesamtzeitraum else MONATSNAMEN[m],
            "pv_erzeugung_kwh": pv,
            "pvgis_prognose_kwh": pvgis_by_month.get(m, 0),
            "eigenverbrauch_kwh": ev,
            "einspeisung_kwh": einsp,
            "netzbezug_kwh": netz,
            "autarkie_prozent": autarkie,
            "spezifischer_ertrag": spez,
            "einsp_erloes_euro": einsp_eur,
            "ev_ersparnis_euro": ev_eur,
            "netto_ertrag_euro": einsp_eur + ev_eur,
        }

    if ist_gesamtzeitraum:
        for j in alle_jahre:
            for m in range(1, 13):
                if (j, m) in md_by_year_month or (j, m) in pv_by_year_month:
                    monats_zeilen.append(_zeile_fuer(j, m))
    else:
        for m in range(1, 13):
            monats_zeilen.append(_zeile_fuer(jahr, m))

    # ── 9. Jahres-KPIs / Finanzen / CO₂ ─────────────────────────────────
    gesamtverbrauch = ev_gesamt + netz_gesamt
    autarkie_jahr = _safe_div(ev_gesamt, gesamtverbrauch) * 100
    ev_quote = _safe_div(ev_gesamt, pv_gesamt) * 100
    spez_ertrag_jahr = _safe_div(pv_gesamt, anlage.leistung_kwp or 0)

    einspeise_erloes = einsp_gesamt * einspeise_cent / 100
    ev_ersparnis = ev_gesamt * netzbezug_cent / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis

    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    investition_alternativ = sum(
        i.anschaffungskosten_alternativ or 0
        for i in investitionen
        if i.anschaffungskosten_alternativ
    )
    investition_mehrkosten = investition_gesamt - investition_alternativ
    betriebskosten_jahr = sum(i.betriebskosten_jahr or 0 for i in investitionen)

    anzahl_monate = len(monats_zeilen)
    betriebskosten_zeitraum = betriebskosten_jahr * anzahl_monate / 12 if anzahl_monate else 0
    netto_nach_bk = netto_ertrag - betriebskosten_zeitraum
    rendite = (netto_nach_bk / investition_mehrkosten * 100) if investition_mehrkosten > 0 else None
    amortisation_pct = (netto_nach_bk / investition_mehrkosten * 100) if investition_mehrkosten > 0 else 0

    co2_pv = ev_gesamt * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = wp_waerme * CO2_FAKTOR_GAS_KG_KWH if hat_waermepumpe else 0
    co2_emob = emob_km * 0.12 if hat_emobilitaet else 0
    co2_gesamt = co2_pv + co2_wp + co2_emob

    speicher_zyklen = _safe_div(speicher_ladung, speicher_kapazitaet) if speicher_kapazitaet else None
    speicher_eff = _safe_div(speicher_entladung, speicher_ladung) * 100 if speicher_ladung else None
    wp_cop = _safe_div(wp_waerme, wp_strom) if wp_strom else None
    emob_pv_anteil = _safe_div(emob_pv, emob_ladung) * 100 if emob_ladung else None

    # ── 10. String-Vergleich SOLL/IST ───────────────────────────────────
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    gesamt_kwp = sum(i.leistung_kwp or 0 for i in pv_module) or (anlage.leistung_kwp or 1)
    pvgis_neueste = max(pvgis_prognosen, key=lambda p: p.abgerufen_am) if pvgis_prognosen else None
    prognose_monate: dict[int, float] = {}
    if pvgis_neueste and pvgis_neueste.monatswerte:
        for mw in pvgis_neueste.monatswerte:
            prognose_monate[mw.get("monat", 0)] = mw.get("e_m", 0) or 0
    anzahl_jahre = len(alle_jahre) if ist_gesamtzeitraum else 1

    string_vergleiche = []
    for inv in pv_module:
        kwp = inv.leistung_kwp or 0
        anteil = kwp / gesamt_kwp if gesamt_kwp else 0
        ist_kwh = sum(
            (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0) or 0
            for imd in all_imd
            if imd.investition_id == inv.id
        )
        prognose_kwh = sum(prognose_monate.values()) * anteil * anzahl_jahre
        if prognose_kwh > 0 or ist_kwh > 0:
            abw = ist_kwh - prognose_kwh
            abw_pct = (abw / prognose_kwh * 100) if prognose_kwh > 0 else 0
            spez = (ist_kwh / kwp / anzahl_jahre) if kwp else 0
            string_vergleiche.append({
                "bezeichnung": inv.bezeichnung,
                "leistung_kwp": kwp,
                "ausrichtung": inv.ausrichtung,
                "neigung_grad": inv.neigung_grad,
                "prognose_kwh": prognose_kwh,
                "ist_kwh": ist_kwh,
                "abweichung_kwh": abw,
                "abweichung_prozent": abw_pct,
                "spezifischer_ertrag": spez,
            })

    # ── 11. Charts (Base64 Data-URIs) ───────────────────────────────────
    monats_labels = [z["monat_name"] for z in monats_zeilen]
    chart_pv = chart_fluss = chart_autarkie = None
    if monats_zeilen:
        chart_pv = pv_erzeugung_chart(
            monats_labels,
            [z["pv_erzeugung_kwh"] for z in monats_zeilen],
            [z["pvgis_prognose_kwh"] for z in monats_zeilen] if not ist_gesamtzeitraum else None,
        )
        chart_fluss = energie_fluss_chart(
            monats_labels,
            [z["eigenverbrauch_kwh"] for z in monats_zeilen],
            [z["einspeisung_kwh"] for z in monats_zeilen],
            [z["netzbezug_kwh"] for z in monats_zeilen],
        )
        chart_autarkie = autarkie_chart(
            monats_labels,
            [z["autarkie_prozent"] for z in monats_zeilen],
        )

    # ── 12. Kontext-Dict ────────────────────────────────────────────────
    return {
        "erzeugt_am": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "ist_gesamtzeitraum": ist_gesamtzeitraum,
        "jahr": jahr,
        "start_jahr": start_jahr,
        "end_jahr": end_jahr,
        "zeitraum_label": (
            f"Gesamtzeitraum {start_jahr}–{end_jahr}"
            if ist_gesamtzeitraum else f"Jahresbericht {jahr}"
        ),
        "anlage": {
            "name": anlage.anlagenname,
            "leistung_kwp": anlage.leistung_kwp,
            "installationsdatum": anlage.installationsdatum,
            "mastr_id": anlage.mastr_id,
            "standort_plz": anlage.standort_plz,
            "standort_ort": anlage.standort_ort,
            "standort_strasse": anlage.standort_strasse,
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
        },
        "tarif": {
            "anbieter": strompreis.anbieter if strompreis else None,
            "tarifname": strompreis.tarifname if strompreis else None,
            "netzbezug_cent": netzbezug_cent,
            "einspeise_cent": einspeise_cent,
            "grundpreis_euro_monat": strompreis.grundpreis_euro_monat if strompreis else None,
            "gueltig_ab": strompreis.gueltig_ab if strompreis else None,
        },
        "kpis": {
            "pv_erzeugung_kwh": pv_gesamt,
            "eigenverbrauch_kwh": ev_gesamt,
            "einspeisung_kwh": einsp_gesamt,
            "netzbezug_kwh": netz_gesamt,
            "gesamtverbrauch_kwh": gesamtverbrauch,
            "autarkie_prozent": autarkie_jahr,
            "ev_quote_prozent": ev_quote,
            "spezifischer_ertrag": spez_ertrag_jahr,
            "einspeise_erloes_euro": einspeise_erloes,
            "ev_ersparnis_euro": ev_ersparnis,
            "netto_ertrag_euro": netto_ertrag,
            "betriebskosten_zeitraum_euro": betriebskosten_zeitraum,
            "netto_nach_bk_euro": netto_nach_bk,
            "investition_gesamt_euro": investition_gesamt,
            "investition_mehrkosten_euro": investition_mehrkosten,
            "rendite_prozent": rendite,
            "amortisation_prozent": amortisation_pct,
        },
        "speicher": {
            "vorhanden": hat_speicher,
            "kapazitaet_kwh": speicher_kapazitaet,
            "ladung_kwh": speicher_ladung,
            "entladung_kwh": speicher_entladung,
            "vollzyklen": speicher_zyklen,
            "effizienz_prozent": speicher_eff,
        },
        "waermepumpe": {
            "vorhanden": hat_waermepumpe,
            "waerme_kwh": wp_waerme,
            "heizung_kwh": wp_heizung,
            "warmwasser_kwh": wp_warmwasser,
            "strom_kwh": wp_strom,
            "cop": wp_cop,
        },
        "emob": {
            "vorhanden": hat_emobilitaet,
            "km": emob_km,
            "ladung_kwh": emob_ladung,
            "ladung_pv_kwh": emob_pv,
            "ladung_netz_kwh": emob_netz,
            "v2h_kwh": emob_v2h,
            "pv_anteil_prozent": emob_pv_anteil,
        },
        "bkw": {"vorhanden": hat_bkw},
        "co2": {
            "pv_kg": co2_pv,
            "wp_kg": co2_wp,
            "emob_kg": co2_emob,
            "gesamt_kg": co2_gesamt,
        },
        "monats_zeilen": monats_zeilen,
        "string_vergleiche": string_vergleiche,
        "investitionen": [
            {
                "typ": i.typ,
                "bezeichnung": i.bezeichnung,
                "anschaffungsdatum": i.anschaffungsdatum,
                "leistung_kwp": i.leistung_kwp,
                "ausrichtung": i.ausrichtung,
                "neigung_grad": i.neigung_grad,
                "parameter": i.parameter or {},
            }
            for i in investitionen
        ],
        "charts": {
            "pv_erzeugung": chart_pv,
            "energie_fluss": chart_fluss,
            "autarkie": chart_autarkie,
        },
    }
