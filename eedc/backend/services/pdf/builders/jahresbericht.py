"""
Daten-Aggregation für den Jahresbericht.

Extrahiert die bisher in `api/routes/import_export/pdf_operations.py` inline
ausgeführte Logik und liefert ein einziges `context`-Dict, das das
Jinja2-Template direkt verwenden kann.

Reine Datenschicht — keine HTTP-, keine Render-Aufrufe.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    FinanzMonatsZeile,
    autarkie_prozent,
    berechne_finanz_aggregat,
    berechne_verbrauchs_kennzahlen,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    spezifischer_ertrag_kwh_kwp,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.utils.sonstige_positionen import berechne_sonstige_netto
from backend.core.field_definitions import get_wp_strom_kwh
from backend.services.eauto_wirtschaftlichkeit import get_emob_heimladung_canonical
from backend.core.calculations import (
    CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_STROM_KG_KWH,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.strompreis import Strompreis

from ..charts import autarkie_chart, energie_fluss_chart, pv_erzeugung_chart
from .finanzbericht import TYP_LABELS as _INV_TYP_LABELS

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

    # ── 2. Strompreis (neuester Eintrag — nur für die Tarif-Anzeige im
    #        Berichtskopf). Die Finanzrechnung pro Monat löst den jeweils
    #        gültigen Tarif separat über `lade_tarife_fuer_anlage` auf
    #        (historische Tarife, #326/rilmor-mhrs) — siehe `_tarif_fuer_monat`
    #        unten. Cockpit/Auswertungen rechnen identisch.
    res = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage_id)
        .order_by(Strompreis.gueltig_ab.desc())
        .limit(1)
    )
    strompreis = res.scalar_one_or_none()
    netzbezug_cent = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else NETZBEZUG_DEFAULT_CENT
    einspeise_cent = strompreis.einspeiseverguetung_cent_kwh if strompreis else EINSPEISEVERGUETUNG_DEFAULT_CENT

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
        # #236: IMD vor anschaffungs- / nach stilllegungsdatum überspringen
        all_imd = [
            imd for imd in res.scalars().all()
            if (inv := inv_by_id.get(imd.investition_id))
            and inv.ist_aktiv_im_monat(imd.jahr, imd.monat)
        ]

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

    # #326: Sonstige Erträge/Ausgaben pro Jahr/Monat — damit die Monats-
    # Ertragsspalte deckungsgleich mit dem Jahres-Netto ist (rilmor-mhrs:
    # Dez 2022 musste negativ werden, Monatszeilen müssen auf den Summary
    # aufgehen). Σ dieser Werte == `sonstige_netto_gesamt` (jedes IMD hat
    # genau ein (jahr, monat)).
    sonstige_by_ym: dict[tuple[int, int], float] = {}
    for imd in all_imd:
        netto = berechne_sonstige_netto(imd.verbrauch_daten)
        if netto:
            key = (imd.jahr, imd.monat)
            sonstige_by_ym[key] = sonstige_by_ym.get(key, 0) + netto

    # ── 7. Aggregate Wärmepumpe / E-Mob / Speicher ──────────────────────
    pv_gesamt = 0.0
    einsp_gesamt = 0.0
    netz_gesamt = 0.0
    ev_gesamt = 0.0

    speicher_ladung = 0.0
    speicher_entladung = 0.0
    # #304: Speicher/V2H pro Monat für die SoT-Eigenverbrauchsformel (s.u.)
    speicher_ladung_by_ym: dict[tuple[int, int], float] = {}
    speicher_entladung_by_ym: dict[tuple[int, int], float] = {}
    v2h_by_ym: dict[tuple[int, int], float] = {}
    wp_waerme = wp_heizung = wp_warmwasser = wp_strom = 0.0
    emob_km = emob_v2h = 0.0
    # E-Mob-Heimladung: rohe IMD je Quelle sammeln, danach EINE kanonische
    # Quelle wählen (Phase 2a). Früher summierte diese Schleife `ladung_kwh`
    # roh über E-Auto UND Wallbox — bei evcc-Setups, die denselben Stromfluss
    # auf beide Investitionen schreiben, ergab das Doppelzählung. km + V2H
    # bleiben E-Auto-spezifisch (Vehicle-Sicht).
    eauto_imd_data: list[dict] = []
    wb_imd_data: list[dict] = []

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue
        d = imd.verbrauch_daten or {}
        if inv.typ == "speicher":
            lad = d.get("ladung_kwh", 0) or 0
            entl = d.get("entladung_kwh", 0) or 0
            speicher_ladung += lad
            speicher_entladung += entl
            key = (imd.jahr, imd.monat)
            speicher_ladung_by_ym[key] = speicher_ladung_by_ym.get(key, 0) + lad
            speicher_entladung_by_ym[key] = speicher_entladung_by_ym.get(key, 0) + entl
        elif inv.typ == "waermepumpe":
            heiz = d.get("heizenergie_kwh", 0) or d.get("heizung_kwh", 0) or 0
            ww = d.get("warmwasser_kwh", 0) or 0
            wp_heizung += heiz
            wp_warmwasser += ww
            wp_waerme += d.get("waerme_kwh", 0) or (heiz + ww)
            wp_strom += get_wp_strom_kwh(d, inv.parameter)
        elif inv.typ == "e-auto":
            eauto_imd_data.append(d)
            emob_km += d.get("km_gefahren", 0) or 0
            v2h = d.get("v2h_entladung_kwh", 0) or 0
            emob_v2h += v2h
            key = (imd.jahr, imd.monat)
            v2h_by_ym[key] = v2h_by_ym.get(key, 0) + v2h
        elif inv.typ == "wallbox":
            wb_imd_data.append(d)

    emob_pool = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_imd_data,
        wallbox_imd_data=wb_imd_data,
    )
    emob_ladung = emob_pool.ladung_kwh
    emob_pv = emob_pool.pv_kwh
    emob_netz = emob_pool.netz_kwh

    # ── 8. Monats-Tabelle aufbauen ──────────────────────────────────────
    # #326: Tarif PRO MONAT (historische Tarife) statt Einheitstarif — die
    # FinanzMonatsZeile wird über den gemeinsamen Builder `baue_finanz_zeile`
    # gebaut (einzige erlaubte Konstruktions-Stelle, Konformitäts-Wächter), damit
    # Cockpit/Auswertungen/HA-Export/Jahresbericht garantiert dieselben Eingaben
    # nutzen. Der Builder löst den Monatstarif auf; das Display liest Preis/Erlös
    # aus der zurückgegebenen Zeile zurück (single source).
    from backend.services.finanz_zeilen import FinanzZeileEingabe, baue_finanz_zeile

    _tarif_cache: dict[date, dict] = {}
    monats_zeilen: list[dict] = []
    finanz_zeilen: list[FinanzMonatsZeile] = []

    async def _zeile_fuer(j: int, m: int) -> dict:
        nonlocal pv_gesamt, einsp_gesamt, netz_gesamt, ev_gesamt
        md = md_by_year_month.get((j, m))
        pv = pv_by_year_month.get((j, m), 0)
        einsp = (md.einspeisung_kwh or 0) if md else 0
        netz = (md.netzbezug_kwh or 0) if md else 0
        # #304: Eigenverbrauch über den SoT-Helper (PV + Speicher + V2H) statt
        # der naiven Formel PV − Einspeisung, die den Speicher ignorierte —
        # deckungsgleich mit Cockpit/HA-Export/Aussichten.
        key = (j, m)
        kennzahlen = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=pv,
            einspeisung_kwh=einsp,
            netzbezug_kwh=netz,
            speicher_ladung_kwh=speicher_ladung_by_ym.get(key, 0),
            speicher_entladung_kwh=speicher_entladung_by_ym.get(key, 0),
            v2h_entladung_kwh=v2h_by_ym.get(key, 0),
        )
        ev = kennzahlen.eigenverbrauch_kwh
        gesamt = ev + netz
        autarkie = autarkie_prozent(ev, gesamt)
        spez = spezifischer_ertrag_kwh_kwp(pv, anlage.leistung_kwp or 0) or 0.0
        m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, j, m)
        zeile = await baue_finanz_zeile(db, anlage_id, FinanzZeileEingabe(
            jahr=j, monat=m,
            einspeisung_kwh=einsp, netzbezug_kwh=netz, pv_erzeugung_kwh=pv,
            speicher_ladung_kwh=speicher_ladung_by_ym.get(key, 0),
            speicher_entladung_kwh=speicher_entladung_by_ym.get(key, 0),
            v2h_entladung_kwh=v2h_by_ym.get(key, 0),
            neg_preis_kwh=m_neg,
            monatsdaten=md,
        ), tarif_cache=_tarif_cache)
        finanz_zeilen.append(zeile)
        # Display aus der Zeile (gleicher Tarif wie der Aggregat-Helper):
        einsp_eur = einspeise_erloes_euro(
            einspeisung_kwh=einsp,
            neg_preis_kwh=m_neg,
            verguetung_ct_kwh=zeile.einspeiseverguetung_cent,
        ).erloes_euro
        ev_eur = ev * zeile.netzbezug_preis_cent / 100
        sonstige_eur = sonstige_by_ym.get((j, m), 0)
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
            "sonstige_netto_euro": sonstige_eur,
            "netto_ertrag_euro": einsp_eur + ev_eur + sonstige_eur,
        }

    if ist_gesamtzeitraum:
        for j in alle_jahre:
            for m in range(1, 13):
                if (
                    (j, m) in md_by_year_month
                    or (j, m) in pv_by_year_month
                    or (j, m) in sonstige_by_ym
                ):
                    monats_zeilen.append(await _zeile_fuer(j, m))
    else:
        for m in range(1, 13):
            monats_zeilen.append(await _zeile_fuer(jahr, m))

    # ── 9. Jahres-KPIs / Finanzen / CO₂ ─────────────────────────────────
    gesamtverbrauch = ev_gesamt + netz_gesamt
    autarkie_jahr = autarkie_prozent(ev_gesamt, gesamtverbrauch)
    ev_quote = eigenverbrauchsquote_prozent(ev_gesamt, pv_gesamt)  # cappt jetzt 100 %
    spez_ertrag_jahr = spezifischer_ertrag_kwh_kwp(pv_gesamt, anlage.leistung_kwp or 0) or 0.0

    # #326: Sonstige Erträge/Ausgaben (manuell gepflegt) gehören in den
    # Netto-Ertrag — exakt wie Cockpit/Auswertungen. `all_imd` ist bereits auf
    # den Einsatzzeitraum (ist_aktiv_im_monat, #236) gefiltert.
    sonstige_netto_gesamt = sum(
        berechne_sonstige_netto(imd.verbrauch_daten) for imd in all_imd
    )
    # #326: Finanz-Summary über den SoT-Helper = Σ der per-Monat-Zeilen (EV mit
    # Monats-Flexpreis + §51-bereinigter Einspeise-Erlös) + Sonstige.
    _finanz = berechne_finanz_aggregat(
        finanz_zeilen, sonstige_netto_euro=sonstige_netto_gesamt
    )
    einspeise_erloes = _finanz.einspeise_erloes_euro
    ev_ersparnis = _finanz.ev_ersparnis_euro
    netto_ertrag = _finanz.netto_ertrag_euro

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
    # JAZ/COP nur wenn beide Seiten gemessen sind (Klima ohne Wärmemengenzähler).
    wp_cop = _safe_div(wp_waerme, wp_strom) if (wp_strom and wp_waerme) else None
    emob_pv_anteil = _safe_div(emob_pv, emob_ladung) * 100 if emob_ladung else None

    # ── WP-Counter (#238): Kompressor-Starts + Betriebsstunden über den
    # Berichtszeitraum aus TagesZusammenfassung.komponenten_starts summiert.
    # Quelle/Logik analog zum Monatsbericht (aktueller_monat.py); respektiert
    # Anschaffungs-/Stilllegungsdatum je WP über ist_aktiv_im_monat.
    wp_starts_summe: Optional[int] = None
    wp_betriebsstunden_summe: Optional[float] = None
    if hat_waermepumpe:
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from sqlalchemy import extract as _extract
        wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
        tz_stmt = (
            select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
            .where(TagesZusammenfassung.anlage_id == anlage_id)
            .where(TagesZusammenfassung.komponenten_starts.is_not(None))
        )
        if jahr is not None:
            tz_stmt = tz_stmt.where(_extract("year", TagesZusammenfassung.datum) == jahr)
        tz_res = await db.execute(tz_stmt)
        starts_total = 0
        stunden_total = 0.0
        hat_starts = hat_stunden = False
        for datum_, komp in tz_res.all():
            aktive_ids = {
                str(i.id) for i in wp_invs
                if i.ist_aktiv_im_monat(datum_.year, datum_.month)
            }
            if not aktive_ids:
                continue
            for inv_id_str, c in ((komp or {}).get("wp_starts_anzahl") or {}).items():
                if inv_id_str in aktive_ids and isinstance(c, (int, float)) and c > 0:
                    starts_total += int(c)
                    hat_starts = True
            for inv_id_str, h in ((komp or {}).get("wp_betriebsstunden") or {}).items():
                if inv_id_str in aktive_ids and isinstance(h, (int, float)) and h > 0:
                    stunden_total += float(h)
                    hat_stunden = True
        if hat_starts:
            wp_starts_summe = starts_total
        if hat_stunden:
            wp_betriebsstunden_summe = round(stunden_total, 1)
    # Ø Laufzeit pro Start (h) als Auslegungs-Indikator — nur wenn beides vorhanden.
    wp_laufzeit_pro_start = (
        round(wp_betriebsstunden_summe / wp_starts_summe, 2)
        if wp_starts_summe and wp_betriebsstunden_summe else None
    )

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
            "sonstige_netto_euro": sonstige_netto_gesamt,
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
            "starts_summe": wp_starts_summe,
            "betriebsstunden_summe": wp_betriebsstunden_summe,
            "laufzeit_pro_start_h": wp_laufzeit_pro_start,
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
                "typ_label": _INV_TYP_LABELS.get(i.typ, i.typ),
                "bezeichnung": i.bezeichnung,
                "anschaffungsdatum": i.anschaffungsdatum,
                "leistung_kwp": i.leistung_kwp,
                "ausrichtung": i.ausrichtung,
                "neigung_grad": i.neigung_grad,
                "parameter": i.parameter or {},
                # #303 (kingcap1): Komponenten-Auflistung im WeasyPrint-Bericht
                # mit denselben Feldern wie der reportlab-Pfad — sonst fehlt z. B.
                # der Speicher als Komponente.
                "kosten_euro": i.anschaffungskosten_gesamt,
                "alternativkosten_euro": i.anschaffungskosten_alternativ,
                "parent_bezeichnung": (
                    inv_by_id.get(i.parent_investition_id).bezeichnung
                    if i.parent_investition_id and i.parent_investition_id in inv_by_id
                    else None
                ),
            }
            for i in investitionen
        ],
        "charts": {
            "pv_erzeugung": chart_pv,
            "energie_fluss": chart_fluss,
            "autarkie": chart_autarkie,
        },
    }
