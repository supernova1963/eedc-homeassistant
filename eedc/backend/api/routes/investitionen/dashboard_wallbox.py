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
from backend.services.eauto_wirtschaftlichkeit import summiere_emob_quelle
from backend.services.emob_kontext import lade_emob_kontext
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

    # Die Monate der Periode: jeder Monat mit einer privaten E-Auto- oder Wallbox-Zeile
    # in Betrieb (#153/#155/#236: vor der Anschaffung, nach der Stilllegung nicht).
    monate_set = set()

    # F-7: nur privat geladene Fahrzeuge/Wallboxen bilden die Heimladung, aus
    # der unten kWh, PV-Anteil und `ersparnis_vs_extern` entstehen.
    eauto_id_set = {e.id for e in eautos if not ist_dienstlich(e)}
    wallbox_id_set = {w.id for w in wallboxen if not ist_dienstlich(w)}
    # F-16 + N-555: der Kontext der einen Funktion (`services/emob_kontext.py`) — die
    # Zeilen mit abgeleitetem PV-Anteil (je Zeile), der Entscheid je Monat mit
    # Dienstwagen, Herkunft und den Quellen des laufenden Monats.
    _kontext = await lade_emob_kontext(
        db, anlage_id, [*eautos, *wallboxen], all_monatsdaten,
    )
    for (inv_id, jahr, monat), d in _kontext.daten.items():
        # Dienstwagen / dienstliche Wallbox bleiben draußen: ihre Zeile öffnet auch
        # keinen Periodenmonat. Sonst verlängert sie `anzahl_monate`, drückt
        # `ladevorgaenge_pro_monat` und zieht einen Monat ohne private Ladung in den
        # gewichteten Tarif-Ø (P8).
        if inv_id in eauto_id_set or inv_id in wallbox_id_set:
            monate_set.add((jahr, monat))
    emob_ctx = _kontext.ctx

    # ⭐ N-555 Stufe 2 (Konzept Regel 0, §6 „Wallbox-Sichten, Kachel Heimladung"): der
    # Wallbox-Hub zeigt die **Messung der Wallbox** — die Summe aller Ladungen an ihr,
    # mit Gast und Dienstwagen. Bis 26.09.2026 zeigte er den Heimladungs-Topf der
    # Anlage (je Monat Wallbox ODER E-Auto); trug ein Auto eine eigene Messung, stand
    # hier deren Summe statt dessen, was die Wallbox gezählt hat. PV-Anteil nach
    # Phase 5 (je Zeile), Extern und Ladevorgänge wie bisher aus dem Entscheid.
    # N-568: die Messung wird seitdem JE Wallbox gebildet (`_eigen_je_wb` unten) — die
    # Summe über alle Wallboxen stand hier bis 26.09.2026 auf jeder Karte.
    _pools = [e.pool for e in emob_ctx.entscheide.values()]
    gesamt_extern_kwh = sum(p.extern_kwh for p in _pools)
    gesamt_extern_euro = sum(p.extern_euro for p in _pools)
    gesamt_ladevorgaenge = sum(p.ladevorgaenge for p in _pools)
    anzahl_monate = len(monate_set)

    # Kosten Heimladung (nur Netzstrom, PV ist "kostenlos").
    # ADR-002/P8: Tarif über die Monate der Periode mitteln statt den heutigen
    # zu nehmen. Hier bewusst GLEICHGEWICHTET über `monate_set`: die
    # Heimladung kam bis N-555 aus EINEM Pool über den Zeitraum — eine
    # Netz-kWh-Aufteilung je Monat gab es an dieser Stelle nicht. Seit N-555 ist
    # sie die Summe der Monats-Entscheide; die Preisachse bleibt bewusst
    # gleichgewichtet (N-555 ändert keine Preisregel). Genauer als der heutige
    # Tarif, gröber als das mengengewichtete Mittel im E-Auto-Dashboard.
    # Nur die Bezugsseite: die Wallbox rechnet keinen Spread, ihre Kosten sind
    # bezogener Strom. `.bezug_cent` statt Tupel-Auspacken, damit sichtbar
    # bleibt, dass die zweite Preisseite hier absichtlich ungenutzt ist.
    wb_strompreis_cent = (await _gewichtete_monatspreise(
        db, anlage_id, "wallbox",
        {periode: 1.0 for periode in monate_set},
        fallback_bezug=strompreis_cent,
        fallback_einspeise=resolve_einspeiseverguetung_cent(tarife),
    )).bezug_cent
    # ⭐ N-555 Stufe 2 (Konzept Regel 3, §6 „Wallbox-Sichten", NF-1, Master 26.09.): die
    # **Ersparnis gegenüber externem Laden** und damit die Amortisation rechnen mit dem
    # TOPF — der privaten Heimladung (Σ der privaten Autos), nicht mit der Messung der
    # Wallbox darüber. Gast (nicht zugeordneter Rest) und Dienstwagen nützen dem Haushalt
    # nichts; bis 26.09.2026 stand hier die ganze Wallbox bzw. der Topf alter Bedeutung
    # (je Monat Wallbox ODER E-Auto) — mit Gast und Dienstwagen.
    #
    # ⭐ Und je Monat höchstens die **Messung der Wallbox** (F1 der Nachmessung, Master
    # 26.09.): sind die Autos zusammen mehr als die Wallbox (E2 — Streudaten, eine Quelle
    # am Auto, die unterwegs mitzählt, Steckdose), bleibt der Topf zwar die Summe der
    # Autos, aber die Wallbox kann nicht mehr ersparen, als sie geliefert hat; der
    # Daten-Checker meldet den Widerspruch (Regel 7). Ohne diese Kappung „sparte" die
    # Wallbox an den Demo-Beständen mit 7.698 kWh bei 4.208 kWh gezählter Ladung
    # (1.008 → 3.506 €, Amortisation 1,9 → 0,5 J.). Trägt die Wallbox im Monat keinen
    # Wert (leer), gibt es nichts zu kappen: dann gilt die Annahme E4 (die Heimladung
    # der Autos fand an der Wallbox statt) und die Basis ist der Topf.
    topf_ladung = topf_netz = 0.0
    for _e in emob_ctx.entscheide.values():
        _basis = _e.pool
        if _e.wallbox_hat_wert and _e.wallbox_summe.ladung_kwh < _e.pool.ladung_kwh:
            _basis = _e.wallbox_summe
        topf_ladung += _basis.ladung_kwh
        topf_netz += _basis.netz_kwh
    heim_kosten = topf_netz * wb_strompreis_cent / 100

    # Was hätte externe Ladung gekostet?
    # Durchschnittspreis extern (wenn vorhanden) oder Annahme 50 ct/kWh
    extern_preis_kwh = (gesamt_extern_euro / gesamt_extern_kwh) if gesamt_extern_kwh > 0 else 0.50
    heim_als_extern_kosten = topf_ladung * extern_preis_kwh

    # Ersparnis durch Heimladen (Wallbox-ROI)
    ersparnis_vs_extern = heim_als_extern_kosten - heim_kosten

    # ⭐ N-568 (26.09.2026, Konzept Heimladung Regel 0 „Wallbox-Sichten zeigen die Messung DER
    # Wallbox"): die Route liefert eine Karte JE Wallbox (der Hub rendert jede Karte aus
    # dieser Anlagen-Route, `komponentenAdapter.tsx` `wallbox.fetch` / `WallboxHubBloecke`).
    # Bis hierher trug jede Karte die Summe ALLER privaten Wallboxen als Kachel, der Verlauf
    # darunter aber nur ihre eigenen Zeilen — bei Garage + Carport zwei Zahlen in einer Karte
    # (r28 + zweite Wallbox: 4508 auf beiden Karten gegen 4208 bzw. 300 im Verlauf).
    # Jetzt: kWh, PV-Anteil und Ladevorgänge sind die Messung DIESER Wallbox; Ersparnis
    # gegenüber externem Laden (und damit die Amortisation gegen IHRE Anschaffungskosten)
    # ist der Anteil der Karte am Anlagen-Ergebnis nach ihrer Messung. Σ Karten = Anlage.
    # Bei einer Wallbox ist jeder Anteil exakt 1,0 (a / a) — die Karte bleibt bitgleich.
    _eigen_je_wb = {
        w.id: summiere_emob_quelle(
            d for (inv_id, _j, _m), d in _kontext.daten.items() if inv_id == w.id
        )
        for w in wallboxen
    }
    _private_wb = [w for w in wallboxen if w.id in wallbox_id_set]
    _kwh_privat = sum(_eigen_je_wb[w.id].ladung_kwh for w in _private_wb)
    _lv_privat = sum(_eigen_je_wb[w.id].ladevorgaenge for w in _private_wb)

    def _anteil_kwh(wb_id: int) -> float:
        """Anteil einer privaten Wallbox an der Anlage nach ihrer gemessenen kWh; ohne jede
        Messung gleich verteilt (trägt keine Wallbox einen Wert, rechnet die Ersparnis mit
        dem Topf der Autos, E4 — dann gibt es keine Messung, nach der sich teilen ließe)."""
        if _kwh_privat > 0:
            return _eigen_je_wb[wb_id].ladung_kwh / _kwh_privat
        return 1.0 / len(_private_wb)

    def _anteil_ladevorgaenge(wb_id: int) -> float:
        """Die Ladevorgänge der Anlage kommen je Monat aus dem Entscheid (Wallbox oder Autos,
        das Größere); die Karte trägt davon den Anteil nach IHREN gezählten Vorgängen —
        zählen die Wallboxen keine, nach ihrer kWh."""
        if _lv_privat > 0:
            return _eigen_je_wb[wb_id].ladevorgaenge / _lv_privat
        return _anteil_kwh(wb_id)

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
        # N-568: die Messung DIESER Wallbox und ihr Anteil am Anlagen-Ergebnis.
        wb_eigen = _eigen_je_wb[wallbox.id]
        if wb_dienstlich:
            wb_anteil = 0.0
            wb_ladevorgaenge = wb_eigen.ladevorgaenge
        else:
            wb_anteil = _anteil_kwh(wallbox.id)
            wb_ladevorgaenge = gesamt_ladevorgaenge * _anteil_ladevorgaenge(wallbox.id)
        wb_pv_anteil = (
            wb_eigen.pv_kwh / wb_eigen.ladung_kwh * 100 if wb_eigen.ladung_kwh > 0 else 0
        )
        wb_ersparnis = 0.0 if wb_dienstlich else ersparnis_vs_extern * wb_anteil

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
            # Heimladung: die Messung der Wallbox (Regel 0, mit Gast und Dienstwagen).
            # Die Kosten- und Ersparnis-Felder darunter rechnen mit der privaten
            # Heimladung (Topf, Regel 3) — s. `topf_ladung` oben.
            # N-568: je Karte die Messung DIESER Wallbox (Σ Karten = Anlage).
            'gesamt_heim_ladung_kwh': round(wb_eigen.ladung_kwh, 1),
            'ladung_pv_kwh': round(wb_eigen.pv_kwh, 1),
            'ladung_netz_kwh': round(wb_eigen.netz_kwh, 1),
            'pv_anteil_prozent': round(wb_pv_anteil, 1),
            # Externe Ladung zum Vergleich
            'extern_ladung_kwh': round(gesamt_extern_kwh, 1),
            'extern_kosten_euro': round(gesamt_extern_euro, 2),
            'extern_preis_kwh_euro': round(extern_preis_kwh, 2),
            # Kostenvergleich
            # N-568: Anteil der Karte (nach ihrer Messung) am Anlagen-Ergebnis.
            # Eine dienstliche Wallbox hat keinen Anteil an der privaten Heimladung (F-7):
            # ihre Karte nennt 0 statt der Kosten der privaten Wallboxen.
            'heim_kosten_euro': round(heim_kosten * wb_anteil, 2),
            'heim_als_extern_kosten_euro': round(heim_als_extern_kosten * wb_anteil, 2),
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
            'gesamt_ladevorgaenge': int(wb_ladevorgaenge),
            'ladevorgaenge_pro_monat': round(wb_ladevorgaenge / anzahl_monate, 1) if anzahl_monate > 0 else 0,
            'anzahl_monate': anzahl_monate,
        }

        dashboards.append(WallboxDashboardResponse(
            investition=wallbox,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
