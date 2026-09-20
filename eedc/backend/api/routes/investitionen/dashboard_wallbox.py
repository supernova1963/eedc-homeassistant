"""Komponenten-Dashboard Wallbox.

GET /api/investitionen/dashboard/wallbox/{anlage_id}
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.investition_parameter import PARAM_WALLBOX, PARAM_WALLBOX_DEFAULTS, ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import get_emob_heimladung_canonical
from backend.services.emob_ladeanteil import reichere_monatszeilen_an
from backend.core.calculations import berechne_roi
from backend.core.berechnungen.kapitalrechnung import (
    ErsparnisPosten,
    annahme_dauer_text,
    jahres_ersparnis_euro,
    kapitaleinsatz_euro,
)
from backend.core.berechnungen.investitionskosten import relevante_kosten_aus_investitionen
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse, _gewichtete_monatspreise

router = APIRouter()


class WallboxDashboardResponse(BaseModel):
    """Wallbox Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]

@router.get("/dashboard/wallbox/{anlage_id}", response_model=list[WallboxDashboardResponse])
async def get_wallbox_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus Wallbox-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Wallbox Dashboard für eine Anlage.

    Zeigt Wallboxen mit Heimladung (aus E-Auto-Daten) und Ersparnis vs. externe Ladung.
    Die Wallbox-Daten kommen primär aus den E-Auto-Monatsdaten (ladung_pv_kwh + ladung_netz_kwh).

    **Befund F-7**, zweite Hälfte: die Heimladung ist hier eine *anlagenweite*
    Summe, kein per-Gerät-Wert — ein dienstlich geladenes Fahrzeug ging also
    ungefiltert in ``ersparnis_vs_extern`` ein und wurde auf **jeder**
    Wallbox-Karte als private Ersparnis ausgewiesen. Der Filter sitzt jetzt an
    der Quelle (``private_*``), damit Pool, kWh und Euro dieselbe Grundmenge
    haben ([[feedback_dienstwagen_alle_checks]]).
    """
    # Wallbox-Tarif laden
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wallbox_tarif = tarife.get("wallbox")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "wallbox")

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WALLBOX.value)
    )
    wallboxen = inv_result.scalars().all()

    if not wallboxen:
        return []

    # E-Auto Monatsdaten für die Anlage laden (für Heimladung-Berechnung)
    eauto_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
    )
    eautos = eauto_result.scalars().all()

    # Batch-Query: Alle Monatsdaten für E-Autos + Wallboxen auf einmal laden
    eauto_ids = [e.id for e in eautos]
    wallbox_ids = [w.id for w in wallboxen]
    all_inv_ids = eauto_ids + wallbox_ids

    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(all_inv_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # E-Auto- und Wallbox-IMD getrennt sammeln, dann via SoT-Helper zu EINER
    # konsistenten Heimladungs-Trias poolen (#262 junky84): evcc-Portal-Import
    # schreibt die Ladedaten in die Wallbox-Investition (data_import.py::_schreibe_wallbox),
    # das Premium-Setup (separate E-Auto-Sensoren) aus E-Auto-Sicht. Früher
    # feldweises `max()` über pv/netz getrennt — das konnte pv aus der einen
    # und netz aus der anderen Quelle nehmen → PV-Anteil > 100 %. Jetzt
    # gewinnt die Quelle mit der größeren Heimladung die komplette Trias,
    # identisch zu Cockpit-Übersicht, Komponenten und EAutoDashboard.
    monate_set = set()

    # Issue #153 / #155: Daten vor Anschaffungsdatum ignorieren
    inv_by_id = {e.id: e for e in eautos}
    inv_by_id.update({w.id: w for w in wallboxen})

    def _nicht_aktiv_im_monat(inv_id: int, jahr: int, monat: int) -> bool:
        """#236: nicht-aktive Monate (vor anschaffungs- / nach stilllegungsdatum) überspringen."""
        inv = inv_by_id.get(inv_id)
        if not inv:
            return False
        return not inv.ist_aktiv_im_monat(jahr, monat)

    # F-7: nur privat geladene Fahrzeuge/Wallboxen bilden die Heimladung, aus
    # der unten kWh, PV-Anteil und `ersparnis_vs_extern` entstehen.
    eauto_id_set = {e.id for e in eautos if not ist_dienstlich(e)}
    wallbox_id_set = {w.id for w in wallboxen if not ist_dienstlich(w)}
    # F-16: die Zeilen laufen erst durch die Ableitung des PV-Anteils, dann in
    # den Pool. Dieser Hub liest die IMD direkt (P10-Restschuld) und zeigte
    # deshalb `pv_anteil_prozent` = 0, während Cockpit und Auswertungen für
    # dieselbe Heimladung einen abgeleiteten Anteil nannten.
    _wb_zeilen = [
        (inv_id, md)
        for inv_id, md_list in md_by_inv.items()
        for md in md_list
        if not _nicht_aktiv_im_monat(inv_id, md.jahr, md.monat)
        and inv_id in (eauto_id_set | wallbox_id_set)
    ]
    _wb_daten = await reichere_monatszeilen_an(
        db,
        anlage_id,
        [
            ((md.jahr, md.monat), inv_id in wallbox_id_set, md.verbrauch_daten or {})
            for inv_id, md in _wb_zeilen
        ],
    )
    eauto_imd_data: list[dict] = []
    wb_imd_data: list[dict] = []
    for (inv_id, md), d in zip(_wb_zeilen, _wb_daten):
        # Dienstwagen / dienstliche Wallbox sind oben schon heraus: ihre Zeile
        # öffnet auch keinen Periodenmonat. Sonst verlängert sie `anzahl_monate`,
        # drückt `ladevorgaenge_pro_monat` und zieht einen Monat ohne private
        # Ladung in den gewichteten Tarif-Ø (P8).
        if inv_id in eauto_id_set:
            eauto_imd_data.append(d)
        else:
            wb_imd_data.append(d)
        monate_set.add((md.jahr, md.monat))

    emob_pool = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_imd_data,
        wallbox_imd_data=wb_imd_data,
    )
    gesamt_heim_pv = emob_pool.pv_kwh
    gesamt_heim_netz = emob_pool.netz_kwh
    gesamt_extern_kwh = emob_pool.extern_kwh
    gesamt_extern_euro = emob_pool.extern_euro
    gesamt_ladevorgaenge = emob_pool.ladevorgaenge
    gesamt_heim_ladung = emob_pool.ladung_kwh
    anzahl_monate = len(monate_set)

    # PV-Anteil der Heimladung
    pv_anteil = (gesamt_heim_pv / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0

    # Kosten Heimladung (nur Netzstrom, PV ist "kostenlos").
    # ADR-002/P8: Tarif über die Monate der Periode mitteln statt den heutigen
    # zu nehmen. Hier bewusst GLEICHGEWICHTET über `monate_set`: die
    # Heimladung kommt aus `get_emob_heimladung_canonical`, das die IMD-Dicts
    # zu einem Pool zusammenfasst — eine Netz-kWh-Aufteilung je Monat gibt es
    # an dieser Stelle nicht. Genauer als der heutige Tarif, gröber als das
    # mengengewichtete Mittel im E-Auto-Dashboard.
    # Nur die Bezugsseite: die Wallbox rechnet keinen Spread, ihre Kosten sind
    # bezogener Strom. `.bezug_cent` statt Tupel-Auspacken, damit sichtbar
    # bleibt, dass die zweite Preisseite hier absichtlich ungenutzt ist.
    wb_strompreis_cent = (await _gewichtete_monatspreise(
        db, anlage_id, "wallbox",
        {periode: 1.0 for periode in monate_set},
        fallback_bezug=strompreis_cent,
        fallback_einspeise=resolve_einspeiseverguetung_cent(tarife),
    )).bezug_cent
    heim_kosten = gesamt_heim_netz * wb_strompreis_cent / 100

    # Was hätte externe Ladung gekostet?
    # Durchschnittspreis extern (wenn vorhanden) oder Annahme 50 ct/kWh
    extern_preis_kwh = (gesamt_extern_euro / gesamt_extern_kwh) if gesamt_extern_kwh > 0 else 0.50
    heim_als_extern_kosten = gesamt_heim_ladung * extern_preis_kwh

    # Ersparnis durch Heimladen (Wallbox-ROI)
    ersparnis_vs_extern = heim_als_extern_kosten - heim_kosten

    dashboards = []
    for wallbox in wallboxen:
        # Wallbox-eigene Monatsdaten aus Batch-Ergebnis
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(wallbox.id, [])
            if wallbox.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        params = wallbox.parameter or {}
        # Bug #6 v3.25.0: vorher 'leistung_kw' (toter Schema-Key), Form/Wizard schreiben
        # 'max_ladeleistung_kw' → Dashboard zeigte immer 11 kW Default unabhängig vom User-Setup.
        leistung_kw = params.get(PARAM_WALLBOX["MAX_LADELEISTUNG_KW"], PARAM_WALLBOX_DEFAULTS["max_ladeleistung_kw"])

        # F-7: eine dienstliche Wallbox trägt keine private Ersparnis. Die
        # anlagenweite Heimladung steht daneben weiter — sie ist gemessen.
        wb_dienstlich = ist_dienstlich(wallbox)
        wb_ersparnis = 0.0 if wb_dienstlich else ersparnis_vs_extern

        # N-230: die Amortisationsdauer entsteht HIER, aus denselben zwei
        # SoT-Hälften wie überall sonst — nicht im Client aus
        # `Anschaffung ÷ Ersparnis`. Der Client teilte durch die **rohen
        # Anschaffungskosten**; der Nenner ist aber der **Kapitaleinsatz**
        # (`kapitalrechnung`): relevante Kosten (also abzüglich der
        # Alternativkosten) plus kumulierte sonstige Ausgaben, minus die
        # sonstigen Erträge. Eine geförderte Wallbox bekam damit eine zu
        # lange Dauer — die Förderung ist Geld, das nie eingesetzt wurde.
        #
        # Der ZÄHLER bleibt bewusst die **gemessene** Heimlade-Ersparnis:
        # `ErsparnisPosten` ist genau dafür gebaut („annualisiert jeden
        # Posten mit SEINER eigenen Monatszahl", F-20) und bildet die
        # bisherige Hochrechnung `Ersparnis ÷ Monate × 12` im SoT nach.
        # ⭐ ENTSCHIEDEN AM 2026-09-01 (Gernot), N-351 — hier stand bis dahin
        # „eine offene Frage und bewusst NICHT hier entschieden". Sie lautete:
        # gehoert diese gemessene Ersparnis auch in die ROI-Zeile derselben
        # Wallbox? ANTWORT: NEIN, und der Grund ist keine Bequemlichkeit.
        #
        # Diese Zahl beantwortet eine ISOLIERTE Frage — „was war diese Box
        # gegenueber oeffentlichem Laden wert?" — und dafuer ist sie richtig.
        # In die Kapitalrechnung der ANLAGE gehoert sie nicht: dort steckt die
        # Heimladung bereits in der E-Auto-Zeile, deren Formel
        # `Benzinkosten − E-Auto-Netzstromkosten` rechnet und damit schon
        # unterstellt, dass zuhause geladen wurde (`aussichten/finanz_prognose.py`,
        # `jahres_eauto_km_ersparnis`; Kommentar dort: „PV-Ladung ist in
        # EV-Ersparnis"). Beides zu addieren rechnete dieselbe Kilowattstunde
        # gegen ZWEI einander ausschliessende Alternativen — in der
        # Benzin-Welt wird gar nicht geladen, in der Saeulen-Welt kein Benzin
        # gekauft. Das ist die Klasse aus v4.0.20 (55,9 ct fuer dieselbe kWh).
        #
        # Gernots Begruendung im Wortlaut: „Es war mein Verstaendnisfehler,
        # zwanghaft eine Ersparnis der Wallbox zu fordern, die sie nicht hat.
        # Wir fassen es ja als E-Mobilitaet sowieso zusammen."
        #
        # Die ROI-Zeile der Wallbox traegt deshalb KEINEN eigenen Zaehler; sie
        # steht seit demselben Tag ehrlich auf „nicht bewertet"
        # (`crud.py`-Sammelzweig) statt auf 0. ⛔ NICHT NEU AUFROLLEN.
        wb_betriebskosten = wallbox.betriebskosten_jahr or 0
        wb_sonstige_ausgaben = 0.0
        wb_sonstige_ertraege = 0.0
        for md in monatsdaten:
            _s = berechne_sonstige_summen(md.verbrauch_daten)
            wb_sonstige_ausgaben += _s["ausgaben_euro"]
            wb_sonstige_ertraege += _s["ertraege_euro"]
        wb_kapitaleinsatz = kapitaleinsatz_euro(
            relevante_kosten_euro=relevante_kosten_aus_investitionen([wallbox]),
            sonstige_ausgaben_euro=wb_sonstige_ausgaben,
            sonstige_ertraege_euro=wb_sonstige_ertraege,
        )
        # Brutto an `berechne_roi`, die Betriebskosten getrennt daneben —
        # identisch zu `crud.py::_roi_dashboard`, damit beide Sichten
        # dieselbe Rechnung fahren und nicht nur dieselben Zutaten.
        wb_jahres_ersparnis = jahres_ersparnis_euro([
            ErsparnisPosten(
                bezeichnung="Heimladung statt extern",
                summe_euro=wb_ersparnis,
                monate=anzahl_monate,
            )
        ])
        wb_roi = berechne_roi(
            wb_kapitaleinsatz, wb_jahres_ersparnis, 0, wb_betriebskosten
        )

        zusammenfassung = {
            # Heimladung (aus E-Auto-Daten)
            'gesamt_heim_ladung_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_heim_pv, 1),
            'ladung_netz_kwh': round(gesamt_heim_netz, 1),
            'pv_anteil_prozent': round(pv_anteil, 1),
            # Externe Ladung zum Vergleich
            'extern_ladung_kwh': round(gesamt_extern_kwh, 1),
            'extern_kosten_euro': round(gesamt_extern_euro, 2),
            'extern_preis_kwh_euro': round(extern_preis_kwh, 2),
            # Kostenvergleich
            'heim_kosten_euro': round(heim_kosten, 2),
            'heim_als_extern_kosten_euro': round(heim_als_extern_kosten, 2),
            'ersparnis_vs_extern_euro': round(wb_ersparnis, 2),
            # Amortisation aus dem Kapitalrechnungs-SoT (N-230). `None` heißt
            # „nicht bewertbar" und ist nicht 0 — `berechne_roi` liefert das
            # bei Kapitaleinsatz ≤ 0 (vollständig gefördert) oder ohne
            # Ersparnis, und geraten wird dort nicht.
            'kapitaleinsatz_euro': round(wb_kapitaleinsatz, 2),
            'jahres_ersparnis_euro': round(wb_jahres_ersparnis, 2),
            'amortisation_jahre': wb_roi['amortisation_jahre'],
            # Bauschritt 6 des Wirtschaftlichkeits-Konzepts: eine Dauer ohne
            # genannte Annahme gibt es nicht — und der Text folgt den DATEN,
            # nicht dem Modellnamen. Der Client hielt hier eine feste
            # Konstante („Modell A"), die bei gepflegten Betriebskosten die
            # eigene Rechnung falsch beschrieben hätte.
            'amortisation_annahme': annahme_dauer_text(
                betriebskosten_jahr_euro=wb_betriebskosten
            ),
            # Wallbox-Info
            'dienstlich': wb_dienstlich,
            'leistung_kw': leistung_kw,
            'gesamt_ladevorgaenge': int(gesamt_ladevorgaenge),
            'ladevorgaenge_pro_monat': round(gesamt_ladevorgaenge / anzahl_monate, 1) if anzahl_monate > 0 else 0,
            'anzahl_monate': anzahl_monate,
        }

        dashboards.append(WallboxDashboardResponse(
            investition=wallbox,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
