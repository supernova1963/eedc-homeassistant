"""
Investitionen-Dashboards — API Routes.

Pro-Investitionstyp-Dashboards (E-Auto, Wärmepumpe, Speicher, Wallbox,
Balkonkraftwerk, Sonstiges) plus die Investition-Monatsdaten-Abfrage.
2026-05-20 aus investitionen.py ausgelagert; der gemeinsame Router wird
in investitionen/__init__.py aggregiert.
"""

from typing import Optional, Any, Iterable, NamedTuple
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from dataclasses import asdict
from datetime import date, datetime
import logging

from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_im_monat
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_einspeiseverguetung_cent,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.hub_leer_grund import bestimme_leer_grund
from backend.services.zaehlerstaende import (
    lade_zaehlerstaende,
    zaehler_art,
    zaehler_einheit,
)
from backend.core.investition_kennwerte import (
    ANZAHL_LESE_DEFAULT,
    get_bkw_kwp,
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.core.investition_parameter import (
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WALLBOX,
    PARAM_WALLBOX_DEFAULTS,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    attribute_emob_pool_by_km,
    attribute_month_share,
    berechne_eauto_ersparnis,
    berechne_eauto_ersparnis_periode,
    build_eauto_km_by_month,
    build_wb_pool_by_month,
    compute_emob_pool_attribution,
    eigener_verbrauch_l_100km,
    get_emob_heimladung_canonical,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    EXTERNE_LADUNG_DEFAULT_EURO_KWH,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.services.emob_ladeanteil import reichere_monatszeilen_an
from backend.services.monats_fakten import lade_monats_fakten
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    aggregiere_speicher_ist,
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
    ist_eta_degradation_alarm,
)
from backend.services.speicher_wirtschaftlichkeit import (
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
)
from backend.core.calculations import (
    CO2_FAKTOR_BENZIN_KG_LITER,
    CO2_FAKTOR_STROM_KG_KWH,
    co2_wp_ersparnis_kg,
)
from backend.core.field_definitions import (
    get_emob_pv_netz_kwh,
    get_sonstiges_verbrauch_kwh,
    get_speicher_netzladung_kwh,
    get_wp_strom_kwh,
    ist_gepflegte_sonstiges_kategorie,
    ist_zaehler_kategorie,
)
from backend.core.berechnungen import (
    betriebsart_strom_kwh,
    hat_gemessene_betriebsart,
)
from backend.core.betriebsmodus import HEIZEN as BM_HEIZEN
from backend.core.betriebsmodus import KUEHLEN as BM_KUEHLEN
from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD, MODUS_STROM_FELD
from backend.core.berechnungen import (
    heiz_effizienz_gepflegt,
    heizwaerme_ist_abgeleitet,
    bkw_eigenverbrauch_anteil,
    imd_typ_beitrag,
    sonstiges_richtung,
    eauto_effizienz_100km,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    gleitende_effizienz,
    pruefe_speicher_durchsatz_konsistenz,
    speicher_wirkungsgrad,
    spezifischer_ertrag_kwh_kwp,
    summe_graue_last,
    vollzyklen as berechne_vollzyklen,
)
from backend.api.routes.investitionen.crud import InvestitionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class GewichtetePreise(NamedTuple):
    """Mengengewichtete Ø-Tarife einer Periode, beide Preisseiten (ct/kWh).

    ``bezug_lookup`` trägt zusätzlich die **ungemittelten** Monatspreise, aus
    denen der Ø entstanden ist. Er geht an
    ``berechne_eauto_ersparnis_periode`` weiter, damit die Preisachse dort
    aufgelöst wird und nicht hier — sonst gäbe es die Mittelung an zwei Orten
    (F-18/N-181). Zwei getrennte Query-Schleifen über dieselben Monate wären
    der Preis dafür gewesen; so bleibt es bei einer.
    """
    bezug_cent: float
    einspeise_cent: float
    bezug_lookup: dict[tuple[int, int], float] = {}


async def _gewichtete_monatspreise(
    db: AsyncSession,
    anlage_id: int,
    verwendung: str,
    gewichte: dict[tuple[int, int], float],
    fallback_bezug: float,
    fallback_einspeise: float,
) -> GewichtetePreise:
    """Mengengewichtete Ø der Tarife, die in den Monaten der Periode galten.

    ADR-002/P8 für die Komponenten-Dashboards. Sie summieren Energien über die
    ganze Lebensdauer und bewerten sie EINMAL — mit dem heutigen Tarif hätte
    jede Preiserhöhung die komplette Historie rückwirkend neu bewertet.

    Warum ein gewichteter Ø statt einer strengen Monatsmultiplikation: Bei
    aktivem Wallbox-Pool (#262) ersetzt `attribute_emob_pool_by_km` die
    Monatswerte durch EINEN nach km verteilten Gesamtwert — eine
    Monatsaufteilung der Netzladung existiert dort nicht. Der Ø wird deshalb
    mit derselben Größe gewichtet, nach der auch attribuiert wird. Für Anlagen
    ohne Tarifwechsel ist das Ergebnis identisch zum bisherigen Wert.

    **Warum BEIDE Preisseiten aus einer Schleife kommen:** die Funktion hieß
    bis v4.0.7 `_gewichteter_monatspreis` und lieferte nur den Bezugspreis —
    die Einspeisevergütung daneben blieb der HEUTE gültige Wert. In jedem
    Spread (`bezug − einspeise` bei V2H und Speicher) standen damit zwei
    Summanden aus verschiedenen Zeitpunkten. Zwei getrennte Aufrufe wären
    zudem eine zweite Query-Schleife über dieselben Monate.

    Die Vergütung trägt bewusst dieselben Gewichte wie der Bezugspreis, auch
    wo die bewertete Menge eine andere ist (V2H-Entladung statt Netzladung):
    eine eigene Gewichtung wäre nur mit einer Monatsaufteilung der
    V2H-Energie ehrlich, und die existiert im Pool-Fall gerade nicht. Die
    Näherung ist damit dieselbe, die der Bezugspreis hier seit v4.0.5 macht.

    Args:
        gewichte: ``{(jahr, monat): menge}`` — Netzladung bzw. km je Monat.
        fallback_bezug: Bezugspreis ohne Gewichte (ct/kWh).
        fallback_einspeise: Einspeisevergütung ohne Gewichte (ct/kWh).
    """
    summe_gewicht = sum(g for g in gewichte.values() if g and g > 0)
    if summe_gewicht <= 0:
        return GewichtetePreise(fallback_bezug, fallback_einspeise, {})

    gewichteter_bezug = 0.0
    gewichtete_einspeisung = 0.0
    bezug_lookup: dict[tuple[int, int], float] = {}
    for (jahr, monat), gewicht in gewichte.items():
        if not gewicht or gewicht <= 0:
            continue
        m_tarife = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=date(jahr, monat, 1)
        )
        m_bezug = resolve_strompreis_for_komponente(
            m_tarife, verwendung, fallback=fallback_bezug
        )
        bezug_lookup[(jahr, monat)] = m_bezug
        gewichteter_bezug += m_bezug * gewicht
        gewichtete_einspeisung += resolve_einspeiseverguetung_cent(
            m_tarife, fallback=fallback_einspeise
        ) * gewicht
    return GewichtetePreise(
        gewichteter_bezug / summe_gewicht,
        gewichtete_einspeisung / summe_gewicht,
        bezug_lookup,
    )


class InvestitionMonatsdatenResponse(BaseModel):
    """Monatsdaten für eine Investition."""
    id: int
    investition_id: int
    jahr: int
    monat: int
    verbrauch_daten: dict[str, Any]
    einsparung_monat_euro: Optional[float]
    co2_einsparung_kg: Optional[float]

    class Config:
        from_attributes = True


class EAutoDashboardResponse(BaseModel):
    """E-Auto Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class WaermepumpeDashboardResponse(BaseModel):
    """Wärmepumpe Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SpeicherDashboardResponse(BaseModel):
    """Speicher Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]
    # Gleitende 12-Monats-Effizienz (carry-over-immun) — ersetzt die naive
    # Pro-Monats-Effizienz, die durch den SoC-Übertrag >100 % zappeln konnte.
    effizienz_verlauf: list[dict[str, Any]] = []


class WallboxDashboardResponse(BaseModel):
    """Wallbox Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class BalkonkraftwerkDashboardResponse(BaseModel):
    """Balkonkraftwerk Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SonstigesDashboardResponse(BaseModel):
    """Sonstiges Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


@router.get("/dashboard/e-auto/{anlage_id}", response_model=list[EAutoDashboardResponse])
async def get_eauto_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus Wallbox-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db),
):
    """
    E-Auto Dashboard für eine Anlage.

    Zeigt alle E-Autos mit Monatsdaten, km-Statistik, PV-Anteil, Ersparnis.

    **Befund F-7 der Drift-Inventur 2026-07-31**, hier behoben: diese Datei
    enthielt keinen einzigen ``ist_dienstlich``-Aufruf, während Cockpit,
    Aussichten, Jahresbericht-PDF und HA-Export das Flag längst führen
    ([[feedback_dienstwagen_alle_checks]]). Ein dienstlich geladenes Fahrzeug
    erschien im Komponenten-Hub als **private** Ersparnis.

    Zwei Wirkungen, bewusst getrennt:

    1. **Der Pool wird privat gebildet.** Ein Dienstwagen und eine dienstliche
       Wallbox gehen nicht mehr in ``compute_emob_pool_attribution`` ein — sonst
       zieht ihre Ladung die km-anteilige Attribution der privaten Fahrzeuge
       nach oben. Das ist derselbe Schnitt, den die Monats-Fakten-Schicht
       macht (``EmobFakten``: gefiltert, aber als ``dienstlich_*`` getrennt
       ausgewiesen statt verworfen).
    2. **Die Karte bleibt, die Ersparnis nicht.** Das Fahrzeug ist registriert
       und seine physischen Größen (km, Ladung, PV-Anteil, V2H) sind gemessen —
       es zu verstecken wäre ein Lösch-Feature
       ([[feedback_reparatur_statt_loesch_features]]). Die Euro- und
       CO₂-Ersparnis steht auf 0 und die Zusammenfassung trägt ``dienstlich``,
       damit die Oberfläche den Grund nennen kann statt eine stille Null zu
       zeigen.
    """
    # Wallbox-Tarif laden (E-Auto lädt über Wallbox)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wallbox_tarif = tarife.get("wallbox")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "wallbox")
    # Einspeisevergütung für V2H-Spread-Berechnung (Drift-Audit D). Nur der
    # FALLBACK — der bewertete Wert kommt je E-Auto aus `_gewichtete_monats-
    # preise` unten, weil der Spread sonst einen Monatspreis gegen die heutige
    # Vergütung rechnet (ADR-002/P8, beide Seiten).
    einspeise_verg_fallback_cent = resolve_einspeiseverguetung_cent(tarife)

    # E-Autos laden — Issue #123: Dashboard ist historische Übersicht,
    # stillgelegte E-Autos bleiben mit ihrer Historie sichtbar.
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
    )
    eautos = inv_result.scalars().all()

    if not eautos:
        return []

    # Batch-Query: E-Auto-Monatsdaten + Wallbox-Monatsdaten auf einmal laden
    # (#262 junky84: evcc-Portal-Import schreibt Ladedaten in die Wallbox-
    # Investition; ohne diesen Pool sähe das E-Auto-Dashboard nichts).
    eauto_ids = [e.id for e in eautos]
    wallbox_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WALLBOX.value)
    )
    wallboxen = wallbox_result.scalars().all()
    wallbox_ids = [w.id for w in wallboxen]

    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(eauto_ids + wallbox_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # F-7: der Pool ist eine PRIVATE Größe. Ein dienstlich geladenes Fahrzeug
    # gehört nicht hinein — sonst verteilt `attribute_emob_pool_by_km` seine
    # Ladung anteilig auf die privaten Fahrzeuge und überhöht deren Ersparnis.
    private_eautos = [e for e in eautos if not ist_dienstlich(e)]
    private_wallboxen = [w for w in wallboxen if not ist_dienstlich(w)]

    # F-16: der abgeleitete PV-Anteil der Heimladung gilt auch hier. Dieser Hub
    # liest `InvestitionMonatsdaten` direkt (P10-Restschuld), sieht die
    # Monats-Fakten also nie — ohne diese Anreicherung zeigte seine KPI-Kachel
    # „PV-Anteil" weiter 0 %, während Auswertungen → Komponenten für DIESELBE
    # Größe einen abgeleiteten Anteil nennt. Der Torwächter (gepflegter Wert
    # gewinnt) und die Query-Vorprüfung stecken im Service.
    _wb_id_set = {w.id for w in private_wallboxen}
    _emob_zeilen = [
        (inv, md)
        for inv in (*private_eautos, *private_wallboxen)
        for md in md_by_inv.get(inv.id, [])
        if inv.ist_aktiv_im_monat(md.jahr, md.monat)
    ]
    _emob_daten = await reichere_monatszeilen_an(
        db,
        anlage_id,
        [
            ((md.jahr, md.monat), inv.id in _wb_id_set, md.verbrauch_daten or {})
            for inv, md in _emob_zeilen
        ],
    )
    emob_daten_by_md: dict[tuple[int, int, int], dict] = {
        (inv.id, md.jahr, md.monat): daten
        for (inv, md), daten in zip(_emob_zeilen, _emob_daten)
    }

    def _emob_daten_von(inv, md) -> dict:
        """Die Zeile mit abgeleitetem PV-Anteil — Fallback ist das Original.

        Der Fallback greift für **dienstliche** Fahrzeuge und für Monate außerhalb
        der Laufzeit: beide gehören nicht in den privaten Pool und damit auch
        nicht in die Ableitung (F-7 / [[feedback_dienstwagen_alle_checks]]).
        """
        return emob_daten_by_md.get(
            (inv.id, md.jahr, md.monat), md.verbrauch_daten or {}
        )

    # Wallbox-Heimladung als Wahrheit, wenn größer als Σ E-Auto-Heimladung
    # (typisches evcc-Portal-Import-Setup). Km-Anteile pro E-Auto unten.
    pool_attr = compute_emob_pool_attribution(
        eauto_imd_data=[
            _emob_daten_von(e, md)
            for e in private_eautos for md in md_by_inv.get(e.id, [])
            if e.ist_aktiv_im_monat(md.jahr, md.monat)
        ],
        wallbox_imd_data=[
            _emob_daten_von(w, md)
            for w in private_wallboxen for md in md_by_inv.get(w.id, [])
            if w.ist_aktiv_im_monat(md.jahr, md.monat)
        ],
    )

    # #262 (junky84): Pro-Monat-Töpfe für die Detailtabelle. Die KPI-Kacheln
    # poolten die Wallbox-Ladung bereits km-anteilig (unten), die rohen
    # Monatszeilen aber nicht — daher zeigte die Tabelle nur die km-Spalte.
    # Hier dieselbe use_wb_pool-Entscheidung, nur monatsweise aufgelöst, damit
    # Zeilen und Kacheln konsistent bleiben.
    wb_pool_by_month = build_wb_pool_by_month(
        (md.jahr, md.monat, _emob_daten_von(w, md))
        for w in private_wallboxen for md in md_by_inv.get(w.id, [])
        if w.ist_aktiv_im_monat(md.jahr, md.monat)
    )
    eauto_km_by_month = build_eauto_km_by_month(
        (md.jahr, md.monat, _emob_daten_von(e, md))
        for e in private_eautos for md in md_by_inv.get(e.id, [])
        if e.ist_aktiv_im_monat(md.jahr, md.monat)
    )

    # #260 (NongJoWo): Benzinpreis pro Monat aus Anlage.monatsdaten (EU
    # Weekly Oil Bulletin, seit v3.17.0) — vorher zog dieses Dashboard nur
    # einen statischen Default 1.65 €/L und driftete damit gegen die
    # Cockpit-Übersicht, die seit v3.17.0 monatlich rechnet.
    anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    benzinpreis_lookup: dict[tuple[int, int], Optional[float]] = {
        (md.jahr, md.monat): md.kraftstoffpreis_euro
        for md in anlage_md_result.scalars().all()
    }

    dashboards = []
    for eauto in eautos:
        # F-7: dienstlich = die Mengen sind gemessen, die Ersparnis ist keine
        # private. Steuert unten die Pool-Attribution und die Euro-/CO₂-Zeilen.
        dienstlich = ist_dienstlich(eauto)

        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(eauto.id, [])
            if eauto.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        # Zusammenfassung berechnen
        gesamt_km = 0
        gesamt_verbrauch = 0
        gesamt_pv_ladung = 0
        gesamt_netz_ladung = 0
        gesamt_extern_ladung = 0
        gesamt_extern_kosten = 0
        gesamt_v2h = 0
        # #260: km pro Monat sammeln, damit berechne_eauto_ersparnis_periode
        # mit dem jeweils gültigen Monats-Benzinpreis rechnen kann.
        km_pro_monat: list[tuple[int, int, float]] = []

        # ADR-002/P8: Gewichte je Monat mitführen, um den Tarif über die
        # tatsächlich gültigen Monatstarife zu mitteln statt über den heutigen.
        netz_pro_monat: dict[tuple[int, int], float] = {}
        km_gewichte: dict[tuple[int, int], float] = {}

        for md in monatsdaten:
            # F-16: mit abgeleitetem PV-Anteil, wo keiner gepflegt ist.
            d = _emob_daten_von(eauto, md)
            km_this = d.get('km_gefahren', 0) or 0
            gesamt_km += km_this
            if km_this > 0:
                km_pro_monat.append((md.jahr, md.monat, km_this))
                km_gewichte[(md.jahr, md.monat)] = km_this
            gesamt_verbrauch += d.get('verbrauch_kwh', 0)
            # #262: PV/Netz via SoT-Helper (evcc-Import schreibt nur Total + PV).
            pv, netz = get_emob_pv_netz_kwh(d)
            gesamt_pv_ladung += pv
            gesamt_netz_ladung += netz
            if netz:
                netz_pro_monat[(md.jahr, md.monat)] = netz
            gesamt_extern_ladung += d.get('ladung_extern_kwh', 0)
            gesamt_extern_kosten += d.get('ladung_extern_euro', 0)
            gesamt_v2h += d.get('v2h_entladung_kwh', 0)

        # Wallbox-Pool-Fallback (#262 junky84): wenn die Wallbox-Investition
        # mehr Heim-Ladung enthält als alle E-Autos zusammen, sind die Daten
        # offenbar via evcc-Portal-Import in die Wallbox geflossen. Anteilig
        # nach gefahrenen km auf die E-Autos verteilen.
        # F-7: der Pool ist privat gebildet — ein Dienstwagen darf nicht daraus
        # schöpfen, sonst bekäme er km-anteilig fremde Ladung zugeschrieben.
        share = attribute_emob_pool_by_km(pool_attr, 0 if dienstlich else gesamt_km)
        ist_pool = (
            not dienstlich
            and pool_attr.use_wb_pool
            and share.netz_kwh + share.pv_kwh > 0
        )
        if ist_pool:
            gesamt_pv_ladung = share.pv_kwh
            gesamt_netz_ladung = share.netz_kwh
            gesamt_extern_ladung = share.extern_kwh
            gesamt_extern_kosten = share.extern_euro

        # ADR-002/P8: Tarif über die Monate der Periode mitteln.
        #
        # F-18: die Gewichte sind seit 2026-08-08 **auch im Pool-Fall** die
        # Netzladung je Monat. Vorher fiel der Pool-Fall auf km zurück, weil
        # `attribute_emob_pool_by_km` nur einen Gesamtwert verteilt — die
        # monatliche Aufteilung existiert aber sehr wohl, `wb_pool_by_month`
        # baut sie ein paar Zeilen weiter oben für die Detailtabelle. Der
        # Unterschied ist nicht akademisch: die Netzquote je km ist im Winter
        # deutlich höher, ein km-gewichteter Preis verschiebt sich damit
        # gegenüber dem kWh-gewichteten. Und Cockpit → Jahr rechnet jetzt mit
        # derselben Größe — ohne diese Angleichung wäre die eine Drift durch
        # eine andere ersetzt worden.
        netz_gewichte_pool = {
            k: v.netz_kwh for k, v in wb_pool_by_month.items() if v.netz_kwh > 0
        }
        preis_gewichte = netz_gewichte_pool if ist_pool else netz_pro_monat
        # Ohne jede Netzladung (reines PV-Laden) bleibt km der einzige
        # Schlüssel, den es gibt — ein leeres Gewicht ergäbe den Fallback.
        if not preis_gewichte:
            preis_gewichte = km_gewichte
        _preise = await _gewichtete_monatspreise(
            db, anlage_id, "wallbox",
            preis_gewichte,
            fallback_bezug=strompreis_cent,
            fallback_einspeise=einspeise_verg_fallback_cent,
        )
        eauto_strompreis_cent = _preise.bezug_cent
        eauto_einspeise_cent = _preise.einspeise_cent

        # Heim-Ladung (Wallbox) = PV + Netz
        gesamt_heim_ladung = gesamt_pv_ladung + gesamt_netz_ladung
        # Gesamt-Ladung = Heim + Extern
        gesamt_ladung = gesamt_heim_ladung + gesamt_extern_ladung
        # PV-Anteil nur auf Heim-Ladung bezogen
        pv_anteil_heim = (gesamt_pv_ladung / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0
        # PV-Anteil auf Gesamt-Ladung
        pv_anteil_gesamt = (gesamt_pv_ladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0

        # E-Auto-Ersparnis über die Periode mit per-Monat-Benzinpreis
        # (#260, NongJoWo): Σ km_monat × verbrauch × preis_monat aus dem
        # benzinpreis_lookup, statt einmaliger Multiplikation mit Default.
        params = eauto.parameter or {}
        eauto_result = berechne_eauto_ersparnis_periode(
            km_pro_monat=km_pro_monat,
            ladung_netz_kwh_gesamt=gesamt_netz_ladung,
            ladung_extern_euro_gesamt=gesamt_extern_kosten,
            wallbox_strompreis_cent=eauto_strompreis_cent,
            eauto_parameter=params,
            monats_benzinpreis_lookup=benzinpreis_lookup,
            # F-18: die Auflösung liegt im Layer — dieselbe Funktion, die
            # Cockpit, Aussichten und HA-Export rufen. Der Ø oben bleibt für
            # die Anzeige und den V2H-Spread.
            monats_strompreis_lookup=_preise.bezug_lookup,
            netz_pro_monat=[(j, m, g) for (j, m), g in preis_gewichte.items()],
            # #331: Σ `verbrauch_kwh` der Periode — der explizite elektrische
            # Fahrverbrauch dieses Fahrzeugs, nicht seine Ladung.
            fahrverbrauch_kwh_gesamt=gesamt_verbrauch or None,
        )
        benzin_kosten = eauto_result.benzin_kosten_euro
        heim_netz_kosten = gesamt_netz_ladung * eauto_strompreis_cent / 100
        strom_kosten_gesamt = eauto_result.strom_kosten_euro
        ersparnis_vs_benzin = eauto_result.ersparnis_euro
        benzin_verbrauch_100km = eauto_result.verwendeter_verbrauch_l_100km

        # V2H Ersparnis (Rückspeisung ins Haus, Drift-Audit D: Spread-Modell).
        # User kann `v2h_entlade_preis_cent` als expliziten Override pflegen;
        # ohne Override: Spread (Bezug − Einspeise) — die V2H-Energie hätte
        # alternativ eingespeist werden können.
        v2h_preis_override = params.get('v2h_entlade_preis_cent')
        if v2h_preis_override is not None:
            v2h_ersparnis = gesamt_v2h * v2h_preis_override / 100
        else:
            v2h_ersparnis = berechne_v2h_ersparnis(
                v2h_entladung_kwh=gesamt_v2h,
                bezug_preis_cent=eauto_strompreis_cent,
                einspeise_verg_cent=eauto_einspeise_cent,
            ).ersparnis_euro

        # Wallbox-Ersparnis: Was hätte externe Ladung gekostet?
        # Durchschnittlicher externer Preis (wenn vorhanden) oder kanon. Default.
        extern_preis_kwh = (
            gesamt_extern_kosten / gesamt_extern_ladung
            if gesamt_extern_ladung > 0
            else EXTERNE_LADUNG_DEFAULT_EURO_KWH
        )
        heim_ladung_als_extern = gesamt_heim_ladung * extern_preis_kwh
        heim_kosten_tatsaechlich = heim_netz_kosten  # PV ist kostenlos
        wallbox_ersparnis = heim_ladung_als_extern - heim_kosten_tatsaechlich

        # CO2 Ersparnis: Benzin vs. Strommix
        benzin_co2 = (gesamt_km / 100) * benzin_verbrauch_100km * CO2_FAKTOR_BENZIN_KG_LITER
        strom_co2 = gesamt_verbrauch * CO2_FAKTOR_STROM_KG_KWH
        # #331: die real getankten Liter des Verbrenner-Anteils mindern die
        # vermiedene Emission — dieselbe Menge, die als Kosten in
        # `eauto_result.fossile_kosten_euro` steht. Bei einem BEV ist sie 0.
        fossil_co2 = (
            eauto_result.km_verbrenner / 100
            * (eigener_verbrauch_l_100km(params) or 0.0)
            * CO2_FAKTOR_BENZIN_KG_LITER
        )
        co2_ersparnis = benzin_co2 - strom_co2 - fossil_co2

        # Ø Verbrauch (kWh/100 km) via zentralem Helper: gemessener verbrauch_kwh
        # hat Vorrang, sonst Näherung aus der Ladung (sonst zeigte die Karte 0,0,
        # wenn der User — korrekt — verbrauch_kwh nicht doppelt mappt). Quelle für
        # ehrliches UI-Label. Single Source: core/berechnungen/emob.py.
        eff = eauto_effizienz_100km(gesamt_verbrauch, gesamt_ladung, gesamt_km)

        # F-7: dienstlich gefahrene Kilometer sind keine private Ersparnis. Die
        # Mengen oben bleiben stehen (sie sind gemessen), die Bewertung fällt.
        fossile_kosten = eauto_result.fossile_kosten_euro
        if dienstlich:
            benzin_kosten = 0.0
            strom_kosten_gesamt = 0.0
            ersparnis_vs_benzin = 0.0
            v2h_ersparnis = 0.0
            wallbox_ersparnis = 0.0
            co2_ersparnis = 0.0
            # #331: der Kraftstoff eines Dienstwagens ist Sache des
            # Arbeitgebers und war nie in eedcs Bilanz — dieselbe Linie wie
            # der Benzinvergleich eine Zeile höher.
            fossile_kosten = 0.0

        zusammenfassung = {
            'gesamt_km': round(gesamt_km, 0),
            'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
            'durchschnitt_verbrauch_kwh_100km': round(eff.wert, 1) if eff.wert is not None else None,
            'verbrauch_quelle': eff.quelle,
            # Ladung aufgeschlüsselt
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'ladung_heim_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_pv_ladung, 1),
            'ladung_netz_kwh': round(gesamt_netz_ladung, 1),
            'ladung_extern_kwh': round(gesamt_extern_ladung, 1),
            'ladung_extern_euro': round(gesamt_extern_kosten, 2),
            # PV-Anteile
            'pv_anteil_heim_prozent': round(pv_anteil_heim, 1),
            'pv_anteil_gesamt_prozent': round(pv_anteil_gesamt, 1),
            # V2H
            'v2h_entladung_kwh': round(gesamt_v2h, 1),
            'v2h_ersparnis_euro': round(v2h_ersparnis, 2),
            # Kosten-Vergleich
            'benzin_kosten_alternativ_euro': round(benzin_kosten, 2),
            # #260 NongJoWo: tatsächlich verwendeter (km-gewichteter) Benzinpreis
            # für den Ersparnis-Tooltip — monatlich-dynamisch (EU Oil Bulletin)
            # mit Fallback auf Investitions-Parameter/Default.
            'verwendeter_benzinpreis_euro': round(eauto_result.verwendeter_benzinpreis_euro, 2),
            'strom_kosten_heim_euro': round(heim_netz_kosten, 2),
            'strom_kosten_extern_euro': round(gesamt_extern_kosten, 2),
            'strom_kosten_gesamt_euro': round(strom_kosten_gesamt, 2),
            'ersparnis_vs_benzin_euro': round(ersparnis_vs_benzin, 2),
            # #331: die real angefallene Tankrechnung des Verbrenner-Anteils —
            # als eigene Position, damit die Fläche sie BENENNEN kann statt sie
            # in der Ersparnis verschwinden zu lassen. 0 bei einem BEV.
            'fossile_kosten_euro': round(fossile_kosten, 2),
            'km_elektrisch': round(eauto_result.km_elektrisch, 0),
            'km_verbrenner': round(eauto_result.km_verbrenner, 0),
            'phev_anteil_quelle': eauto_result.anteil_quelle,
            # Wallbox-Ersparnis (durch Heimladen statt extern)
            'wallbox_ersparnis_euro': round(wallbox_ersparnis, 2),
            # Gesamt-Ersparnis
            'gesamt_ersparnis_euro': round(ersparnis_vs_benzin + v2h_ersparnis, 2),
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
            # F-7: Grund für die Nullen oben — die Oberfläche soll „dienstlich,
            # keine private Ersparnis" sagen können statt still 0 € zu zeigen.
            'dienstlich': dienstlich,
        }

        # #262: Detailzeilen mit dem km-anteiligen Wallbox-Pool anreichern, wenn
        # die Ladung in der Wallbox-Investition liegt (use_wb_pool). PV/Netz sind
        # die in der Tabelle gezeigten Spalten; verbrauch_kwh, V2H und km bleiben
        # roh (E-Auto-spezifisch). Override nur, wenn der Monat tatsächlich einen
        # Pool-Anteil hat — sonst Rohzeile unverändert.
        monatsdaten_response = []
        for md in monatsdaten:
            # F-16: dieselbe Zeile wie die Kacheln oben — die Tabelle zeigt die
            # PV-/Netz-Spalten, sie darf nicht ungeteilt daneben stehen.
            d = dict(_emob_daten_von(eauto, md))
            if pool_attr.use_wb_pool and not dienstlich:
                ms = attribute_month_share(
                    wb_pool_by_month.get((md.jahr, md.monat)),
                    d.get('km_gefahren', 0) or 0,
                    eauto_km_by_month.get((md.jahr, md.monat), 0),
                )
                if ms.pv_kwh + ms.netz_kwh > 0:
                    d['ladung_pv_kwh'] = round(ms.pv_kwh, 2)
                    d['ladung_netz_kwh'] = round(ms.netz_kwh, 2)
                    d['ladung_kwh'] = round(ms.pv_kwh + ms.netz_kwh, 2)
            monatsdaten_response.append(InvestitionMonatsdatenResponse(
                id=md.id,
                investition_id=md.investition_id,
                jahr=md.jahr,
                monat=md.monat,
                verbrauch_daten=d,
                einsparung_monat_euro=md.einsparung_monat_euro,
                co2_einsparung_kg=md.co2_einsparung_kg,
            ))

        dashboards.append(EAutoDashboardResponse(
            investition=eauto,
            monatsdaten=monatsdaten_response,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/waermepumpe/{anlage_id}", response_model=list[WaermepumpeDashboardResponse])
async def get_waermepumpe_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus WP-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Wärmepumpe Dashboard für eine Anlage.

    Zeigt alle Wärmepumpen mit COP, Heizkosten, Ersparnis vs. alte Heizung.
    """
    # WP-Tarif laden
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wp_tarif = tarife.get("waermepumpe")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "waermepumpe")

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WAERMEPUMPE.value)
    )
    waermepumpen = inv_result.scalars().all()

    if not waermepumpen:
        return []

    # Anlage einmal laden — get_counter_lifetime braucht sensor_mapping.
    anlage_result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = anlage_result.scalar_one_or_none()
    if anlage is None:
        return []

    from backend.services.sensor_snapshot_service import get_counter_lifetime

    # Batch-Query: Alle Monatsdaten für alle Wärmepumpen auf einmal laden
    wp_ids = [w.id for w in waermepumpen]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(wp_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Counter-Tagesinkremente (Starts + Betriebsstunden, Issue #169 / #238):
    # Quelle TagesZusammenfassung.komponenten_starts mit
    # {"wp_starts_anzahl": {"<inv_id>": <int>},
    #  "wp_betriebsstunden": {"<inv_id>": <float>}}.
    # Wird hier für Max/Tag-KPI + Σ-Betriebsstunden-Aggregat gebraucht.
    # Σ Lebensdauer-Starts kommt direkt aus dem Hersteller-Sensor
    # (`get_counter_lifetime`), Σ-Betriebsstunden ebenfalls direkt aus dem
    # Sensor — beide sind kumulative Counter, der Sensor ist die Wahrheit.
    # #308 (detLAN): Die Counter-Tagesinkremente MÜSSEN auf die WP-Laufzeit
    # (Anschaffung→Stilllegung) gefiltert werden — symmetrisch zum
    # Monatsdaten-Filter unten (`ist_aktiv_im_monat`). Ohne diesen Filter
    # summierte `summe_erfasst` die gesamte je erfasste Sensor-Historie
    # (inkl. Backfill-Tagen vor Anschaffung) und lief gegen den vollen
    # Lebensdauer-Zählerstand — physikalisch unmöglich (Σ seit Anschaffung
    # > Lebensdauer). Der LTS-Abruf selbst ist korrekt; gefehlt hat der
    # Anschaffungsdatum-Scope im Read-Pfad ([[feedback_anschaffungsdatum_grenze]]).
    # `ist_aktiv_im_zeitraum(tag, tag)` prüft Laufzeit-Fenster UND `aktiv`-Flag
    # (aktiv=False = wie gelöscht → nirgends, bis reaktiviert; Gernot 2026-06-05).
    # Symmetrisch zum Monatsdaten-Filter, der dieselbe Sichtbarkeitsregel nutzt.
    wp_by_id = {w.id: w for w in waermepumpen}
    tz_result = await db.execute(
        select(TagesZusammenfassung.datum, TagesZusammenfassung.komponenten_starts)
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(TagesZusammenfassung.komponenten_starts.is_not(None))
    )
    starts_by_inv: dict[int, list[int]] = {wid: [] for wid in wp_ids}
    stunden_by_inv: dict[int, list[float]] = {wid: [] for wid in wp_ids}
    for tz_datum, komp_starts in tz_result.all():
        wp_map = (komp_starts or {}).get("wp_starts_anzahl") or {}
        for inv_id_str, count in wp_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            wp = wp_by_id.get(inv_id)
            if wp is None or not wp.ist_aktiv_im_zeitraum(tz_datum, tz_datum):
                continue
            if isinstance(count, (int, float)) and count > 0:
                starts_by_inv[inv_id].append(int(count))
        stunden_map = (komp_starts or {}).get("wp_betriebsstunden") or {}
        for inv_id_str, hours in stunden_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            wp = wp_by_id.get(inv_id)
            if wp is None or not wp.ist_aktiv_im_zeitraum(tz_datum, tz_datum):
                continue
            if isinstance(hours, (int, float)) and hours > 0:
                stunden_by_inv[inv_id].append(float(hours))

    # Anlage-Monatsdaten für den Monats-Gaspreis (Vorrang vor dem
    # WP-Parameter-Default, wie in `aussichten.py` und im HA-Export).
    wp_anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    wp_anlage_md = {(m.jahr, m.monat): m for m in wp_anlage_md_result.scalars().all()}

    dashboards = []
    for wp in waermepumpen:
        # Issue #153 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(wp.id, [])
            if wp.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_strom = 0
        gesamt_strom_heizen = 0
        gesamt_strom_warmwasser = 0
        gesamt_heizung = 0
        gesamt_warmwasser = 0
        hat_getrennte_strom = False

        gesamt_heizung_getrennt = 0.0  # Heizung nur für Monate mit getrennter Strommessung
        gesamt_warmwasser_getrennt = 0.0  # Warmwasser nur für Monate mit getrennter Strommessung
        # #263 K-2 (Konzept §3.5): Wärme, die aus `Strom × JAZ` abgeleitet
        # wurde, darf in keine JAZ/COP eingehen — heraus käme exakt die
        # gepflegte JAZ. Dieser Endpoint liest die IMD-Zeilen direkt und wertet
        # die Herkunft deshalb selbst aus (die Fakten-Schicht trägt sie sonst
        # als `WpFakten.waerme_abgeleitet_kwh`).
        waerme_abgeleitet = False
        # #263 K-2 (S4): der Modus-Split. Teilmengen von `gesamt_strom` — sie
        # werden ausgewiesen, nie addiert (Konzept §3.1).
        gesamt_modus_heizen = 0.0
        gesamt_modus_kuehlen = 0.0
        gesamt_modus_abdeckung_h = 0.0
        gesamt_modus_bezug = 0.0
        # #263 — mindestens ein Monat bringt die Aufteilung GEMESSEN mit.
        modus_gemessen = False
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # **Gemessen schlägt abgeleitet** (ADR-002/P8), je Monatszeile.
            # `None` heißt „kein Zähler" und lässt die Ableitung stehen; eine
            # gemessene 0 ist dagegen eine echte Null.
            _gem_h = betriebsart_strom_kwh(d, BM_HEIZEN)
            _gem_k = betriebsart_strom_kwh(d, BM_KUEHLEN)
            _zeile_gemessen = hat_gemessene_betriebsart(d)
            modus_gemessen = modus_gemessen or _zeile_gemessen
            # Ganz oder gar nicht je Zeile — Begründung in
            # `core/berechnungen/imd_monatsaggregat.py`: ein Balken, dessen
            # eine Hälfte gemessen und die andere gerechnet ist, trüge ein
            # halbwahres Etikett.
            gesamt_modus_heizen += (
                (_gem_h or 0.0) if _zeile_gemessen
                else (d.get(MODUS_STROM_FELD[BM_HEIZEN], 0) or 0)
            )
            gesamt_modus_kuehlen += (
                (_gem_k or 0.0) if _zeile_gemessen
                else (d.get(MODUS_STROM_FELD[BM_KUEHLEN], 0) or 0)
            )
            _m_abdeckung = d.get(MODUS_ABDECKUNG_FELD, 0) or 0
            gesamt_modus_abdeckung_h += _m_abdeckung
            if _m_abdeckung > 0 or _zeile_gemessen:
                gesamt_modus_bezug += get_wp_strom_kwh(d, wp.parameter)
            gesamt_strom += d.get('stromverbrauch_kwh', 0)
            gesamt_heizung += d.get('heizenergie_kwh', 0)
            gesamt_warmwasser += d.get('warmwasser_kwh', 0)
            waerme_abgeleitet = waerme_abgeleitet or heizwaerme_ist_abgeleitet(
                md.source_provenance
            )
            # ⚠ `strom_heizen_kwh` heißt hier **getrennte Strommessung** (zwei
            # physische Zähler), NICHT der Modus-Split von #263 K-2. Der trägt
            # eigene Feldnamen (`modus_strom_*`, Entscheid E-G) — genau damit
            # diese Anwesenheitsprüfung nicht mitkippt und die Klimaanlage
            # unten kein `cop_heizen` aus abgeleiteter Wärme bekommt.
            if 'strom_heizen_kwh' in d:
                hat_getrennte_strom = True
                gesamt_strom_heizen += d.get('strom_heizen_kwh', 0)
                gesamt_strom_warmwasser += d.get('strom_warmwasser_kwh', 0)
                gesamt_heizung_getrennt += d.get('heizenergie_kwh', 0)
                gesamt_warmwasser_getrennt += d.get('warmwasser_kwh', 0)

        gesamt_waerme = gesamt_heizung + gesamt_warmwasser
        durchschnitt_cop = (
            gesamt_waerme / gesamt_strom
            if gesamt_strom > 0 and not waerme_abgeleitet else 0
        )

        # Drift-Audit Domäne A1 / Issue #178: vorher las dieser Endpoint
        # `gas_kwh_preis_cent` (toter Key, Form schreibt `alter_preis_cent_kwh`)
        # und ignorierte den Wirkungsgrad-Faktor → Ergebnis +16€ Drift.
        #
        # ADR-002/P8: JE MONAT rechnen statt Energien über die Lebensdauer zu
        # summieren und einmal mit dem HEUTIGEN Tarif zu multiplizieren. Ein
        # Tarifwechsel hätte sonst die gesamte WP-Historie neu bewertet. Der
        # Helper ist linear und kennt keine Jahres-Fixkosten, die Summe der
        # Monate ist also identisch, solange der Preis konstant ist. Nebenbei
        # erledigt das den TODO „monatlicher Gaspreis-Override": er wird jetzt
        # wie in `aussichten.py` je Monat gezogen.
        wp_kosten = 0.0
        alte_heizung_kosten = 0.0
        # F-42: Die Ersparnis kommt aus dem Layer-SoT (ADR-001), statt hier als
        # Differenz `alte_heizung_kosten - wp_kosten` nachgebaut zu werden. Bei
        # bewertbaren Wärmepumpen sind beide Wege zahlengleich — der Helper ist
        # linear —, es bewegt sich also keine bestehende Zahl.
        #
        # ⚑ **Gemessen, nicht behauptet:** Diese Umstellung allein ist NICHT der
        # Schutz. Der Sprengsatz „Differenz statt SoT-Summe" blieb stumm, weil
        # die `bewertbar`-Sperre unten den Wert ohnehin auf `None` zieht. Rot
        # wird erst die Kombination *Differenz **und** keine Sperre* — dann
        # stünde für eine Klimaanlage `0 € Gas − 1.312 € Strom` als **negative
        # Ersparnis** im Hub. Wer eine der beiden Hälften entfernt, muss die
        # andere prüfen; der Prüfer dafür ist
        # `test_f42_route_ersparnis_wird_nie_negativ`.
        ersparnis = 0.0
        # Trägt mindestens ein Monat einen echten Vergleich? Sonst gibt es
        # keine Ersparnis-, Alt-Kosten- und CO₂-Zahl, die etwas behauptet.
        bewertbar = False
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            m_waerme = (d.get('heizenergie_kwh', 0) or 0) + (d.get('warmwasser_kwh', 0) or 0)
            m_strom = d.get('stromverbrauch_kwh', 0) or 0
            if m_waerme <= 0 and m_strom <= 0:
                continue
            m_tarife = await lade_tarife_fuer_anlage(
                db, anlage_id, target_date=date(md.jahr, md.monat, 1)
            )
            m_wp_preis = resolve_strompreis_for_komponente(
                m_tarife, "waermepumpe", fallback=strompreis_cent
            )
            m_anlage_md = wp_anlage_md.get((md.jahr, md.monat))
            m_ergebnis = berechne_wp_ersparnis(
                wp_waerme_kwh=m_waerme,
                wp_strom_kwh=m_strom,
                wp_strompreis_cent=m_wp_preis,
                wp_parameter=wp.parameter,
                monats_gaspreis_cent=(
                    m_anlage_md.gaspreis_cent_kwh if m_anlage_md else None
                ),
                # E-B: Kühlen ersetzt keine Heizung — sein Strom gehört nicht
                # in den Vergleich (sonst: gemessene −45,04 € Ersparnis).
                strom_kuehlen_kwh=d.get(MODUS_STROM_FELD[BM_KUEHLEN], 0) or 0,
            )
            wp_kosten += m_ergebnis.wp_kosten_euro
            alte_heizung_kosten += m_ergebnis.alte_heizung_kosten_euro
            ersparnis += m_ergebnis.ersparnis_euro
            bewertbar = bewertbar or m_ergebnis.bewertbar

        # CO2-Ersparnis: kanonischer Helfer (ADR-001, DI-1/DI-2-A). Vorher rechnete
        # dieser Endpoint `wärme × f_gas − strom × f_strom` OHNE den Gas-Kessel-
        # Wirkungsgrad (η_gas) — die vermiedene Gas-Wärme muss aber erst über η_gas
        # in Brennstoff zurückgerechnet werden. Als 4. WP-CO₂-Read-Site driftete das
        # Dashboard nach DI-1 sichtbar gegen Cockpit/Jahresbericht/Nachhaltigkeit
        # (Demo lifetime: 2303,6 → 2744,3 kg, = Σ der Cockpit-Jahreswerte).
        # N-88/F2b: der Traeger entscheidet mit — ohne ersetzte Heizung gibt es
        # keine vermiedene Verbrennung (Filter im SoT, nicht hier).
        co2_ersparnis = co2_wp_ersparnis_kg(
            gesamt_waerme, gesamt_strom,
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]),
            # E-B: Kühlen ersetzt keine Heizung (#263 K-2).
            strom_kuehlen_kwh=gesamt_modus_kuehlen,
        )

        # Kompressor-Starts: Σ Lebensdauer kommt direkt aus dem Hersteller-
        # Sensor (Hersteller zählt seit Werks-Inbetriebnahme, das ist die
        # Wahrheit). Drift zwischen Hersteller-Counter und EEDC-Tagesinkrementen
        # wird im Daten-Checker sichtbar gemacht, nicht im Read-Pfad versteckt.
        # Max/Tag bleibt aus EEDC-Tagesinkrementen (echte Höchst-Tagessumme).
        # #238/#290 (detLAN-Kompromiss): Hauptwert der Kachel ist die seit
        # Anschaffung von eedc erfasste Summe der Tagesinkremente (Anzeige
        # konsequent ab Anschaffungsdatum limitiert, auch wenn der Hersteller-
        # Counter weiter zurückreicht). Der rohe Lebensdauer-Zählerstand
        # (`get_counter_lifetime`) bleibt erhalten, wandert aber nur noch als
        # Zählerstand in die Kachel-Info/Tooltip.
        wp_starts_list = starts_by_inv.get(wp.id, [])
        starts_lifetime = await get_counter_lifetime(
            db, anlage, wp, 'wp_starts_anzahl'
        )
        kompressor_starts_gesamt = (
            int(round(starts_lifetime)) if starts_lifetime is not None else None
        )
        kompressor_starts_summe_erfasst = (
            int(round(sum(wp_starts_list))) if wp_starts_list else None
        )
        kompressor_starts_max_tag = max(wp_starts_list) if wp_starts_list else None

        # Betriebsstunden (#238 detLAN): Σ Lebensdauer + Max/Tag analog zu den
        # Starts. KPI „Ø Laufzeit pro Start" und „Starts pro Betriebsstunde"
        # nur sichtbar wenn beide Werte für denselben Lebensdauer-Stand vorhanden
        # sind — ansonsten wären sie Krücken, weil Starts- und Stunden-Sensor
        # zu unterschiedlichen Zeitpunkten in Betrieb genommen worden sein
        # können.
        wp_stunden_list = stunden_by_inv.get(wp.id, [])
        betriebsstunden_gesamt = await get_counter_lifetime(
            db, anlage, wp, 'wp_betriebsstunden'
        )
        betriebsstunden_summe_erfasst = (
            round(sum(wp_stunden_list), 1) if wp_stunden_list else None
        )
        betriebsstunden_max_tag = (
            round(max(wp_stunden_list), 1) if wp_stunden_list else None
        )
        # Ratios aus den seit-Anschaffung erfassten Summen (gleicher Zeitraum
        # für Starts und Stunden — die zwei Lebensdauer-Counter können zu
        # unterschiedlichen Zeitpunkten in Betrieb genommen worden sein).
        oe_laufzeit_pro_start_h: Optional[float] = None
        starts_pro_betriebsstunde: Optional[float] = None
        if (
            betriebsstunden_summe_erfasst is not None
            and kompressor_starts_summe_erfasst is not None
            and kompressor_starts_summe_erfasst > 0
            and betriebsstunden_summe_erfasst > 0
        ):
            oe_laufzeit_pro_start_h = round(
                betriebsstunden_summe_erfasst / kompressor_starts_summe_erfasst, 2
            )
            starts_pro_betriebsstunde = round(
                kompressor_starts_summe_erfasst / betriebsstunden_summe_erfasst, 3
            )

        zusammenfassung = {
            'gesamt_stromverbrauch_kwh': round(gesamt_strom, 1),
            'gesamt_heizenergie_kwh': round(gesamt_heizung, 1),
            'gesamt_warmwasser_kwh': round(gesamt_warmwasser, 1),
            'gesamt_waerme_kwh': round(gesamt_waerme, 1),
            # F-42: „nicht bewertet heißt keine Zahl" (N-258-Klasse). Ohne
            # gemessene Wärme ist die JAZ keine 0, sondern unbekannt; ohne
            # ersetzte Heizung gibt es weder Alt-Kosten noch Ersparnis noch
            # vermiedenes CO₂. Vorher stand hier für eine Klimaanlage mit
            # 4.375 kWh Verbrauch viermal „0,00" — während dieselbe Anlage in
            # Cockpit → Jahr „—" und in Auswertungen → ROI „nicht bewertet"
            # sagte. `None` statt 0 heilt alle drei Anzeigen auf einmal
            # (Komponenten-Hub, Cockpit → Aussicht, Kostenvergleich), weil die
            # Format-Kette im Client `null` bereits als „—" trägt.
            #
            # `wp_kosten_euro` bleibt eine Zahl: Strom × Preis ist immer
            # bestimmt und die einzige Aussage, die hier ohne Vergleich gilt.
            'durchschnitt_cop': (
                round(durchschnitt_cop, 2)
                if gesamt_waerme > 0 and not waerme_abgeleitet else None
            ),
            'wp_kosten_euro': round(wp_kosten, 2),
            'alte_heizung_kosten_euro': round(alte_heizung_kosten, 2) if bewertbar else None,
            'ersparnis_euro': round(ersparnis, 2) if bewertbar else None,
            'co2_ersparnis_kg': round(co2_ersparnis, 1) if bewertbar else None,
            'anzahl_monate': len(monatsdaten),
            # _summe_erfasst = seit Anschaffung von eedc erfasst (Kachel-Hauptwert);
            # _gesamt = roher Lebensdauer-Zählerstand (Kachel-Tooltip/Info, #238/#290).
            'kompressor_starts_summe_erfasst': kompressor_starts_summe_erfasst,
            'kompressor_starts_gesamt': kompressor_starts_gesamt,
            'kompressor_starts_max_tag': kompressor_starts_max_tag,
            'betriebsstunden_summe_erfasst': betriebsstunden_summe_erfasst,
            'betriebsstunden_gesamt': (
                round(betriebsstunden_gesamt, 1)
                if betriebsstunden_gesamt is not None else None
            ),
            'betriebsstunden_max_tag': betriebsstunden_max_tag,
            'oe_laufzeit_pro_start_h': oe_laufzeit_pro_start_h,
            'starts_pro_betriebsstunde': starts_pro_betriebsstunde,
        }

        # ── Modus-Split (#263 K-2, S4 · Konzept §4) ─────────────────────────
        # Alles oder nichts: ohne eine einzige erfasste Stunde gibt es keine
        # Aufteilung — und dann steht dort **keine 0**, sondern gar nichts.
        # Eine 0 hieße „hat nicht geheizt"; das weiß eedc ohne Modus-Signal
        # nicht (ADR-002/P4, die N-258-Klasse).
        # ⚠ **Zwei Wege hierher** (#263): abgeleitet (dann gibt es
        # Abdeckungs-Stunden) oder gemessen (dann gibt es keine — ein Zähler
        # zählt kWh, keine Stunden mit Signal). Nur die Abdeckung zu prüfen
        # hieße, eine gemessene Aufteilung nirgends zu zeigen.
        if gesamt_modus_abdeckung_h > 0 or modus_gemessen:
            zusammenfassung['modus_strom_heizen_kwh'] = round(gesamt_modus_heizen, 1)
            zusammenfassung['modus_strom_kuehlen_kwh'] = round(gesamt_modus_kuehlen, 1)
            # „nicht aufgeteilt" wird NIE gespeichert, sondern immer gerechnet
            # (Konzept §3.1, Folge 2) — damit ist es für Altmonate, Ausfälle
            # und Handpflege gleichermaßen vollständig. Auf 0 geklemmt: die
            # Invariante hält das schon im Schreibpfad, aber eine negative
            # Restmenge wäre auf jeder Fläche Unsinn.
            # Bezug ist der Strom der Monate MIT Split — nicht der Gesamtstrom
            # des Geräts über alle Monate. Sonst zählte ein Monat vor der
            # Sensor-Zuordnung als „nicht aufgeteilt" (dieselbe Klasse wie der
            # anlagenweite Bezug in `WpFakten.modus_nicht_aufgeteilt_kwh`).
            zusammenfassung['modus_nicht_aufgeteilt_kwh'] = round(
                max(0.0, gesamt_modus_bezug - gesamt_modus_heizen - gesamt_modus_kuehlen), 1
            )
            zusammenfassung['modus_abdeckung_h'] = round(gesamt_modus_abdeckung_h, 1)
            zusammenfassung['modus_gemessen'] = modus_gemessen
        # Die Kennzeichnung der Wärme steht unabhängig davon: sie gilt auch für
        # Monate, deren Split später verworfen wurde.
        zusammenfassung['waerme_abgeleitet'] = waerme_abgeleitet
        zusammenfassung['waerme_abgeleitet_faktor'] = (
            heiz_effizienz_gepflegt(wp.parameter) if waerme_abgeleitet else None
        )

        # Getrennte COP-Werte wenn separate Strommessung vorhanden.
        # ⚠ Auch hier gilt die JAZ-Sperre (#263 K-2, §3.5): ist die Heizwärme
        # abgeleitet, ist `cop_heizen` die gepflegte JAZ und kein Messwert.
        if hat_getrennte_strom:
            zusammenfassung['gesamt_strom_heizen_kwh'] = round(gesamt_strom_heizen, 1)
            zusammenfassung['gesamt_strom_warmwasser_kwh'] = round(gesamt_strom_warmwasser, 1)
            zusammenfassung['gesamt_heizung_getrennt_kwh'] = round(gesamt_heizung_getrennt, 1)
            zusammenfassung['gesamt_warmwasser_getrennt_kwh'] = round(gesamt_warmwasser_getrennt, 1)
            zusammenfassung['cop_heizen'] = round(
                gesamt_heizung_getrennt / gesamt_strom_heizen, 2
            ) if gesamt_strom_heizen > 0 and not waerme_abgeleitet else 0
            zusammenfassung['cop_warmwasser'] = round(
                gesamt_warmwasser_getrennt / gesamt_strom_warmwasser, 2
            ) if gesamt_strom_warmwasser > 0 and not waerme_abgeleitet else 0

        dashboards.append(WaermepumpeDashboardResponse(
            investition=wp,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/speicher/{anlage_id}", response_model=list[SpeicherDashboardResponse])
async def get_speicher_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None),
    einspeiseverguetung_cent: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Speicher Dashboard für eine Anlage.

    Zeigt alle Speicher mit Zyklen, Effizienz, Eigenverbrauchserhöhung.
    Drift-Audit E: Tarife aus DB statt 30/8-Defaults aus Query-Param.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )
    speicher_list = inv_result.scalars().all()

    if not speicher_list:
        return []

    # Tarife aus DB laden (falls Query-Params nicht explizit übergeben)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if strompreis_cent is None:
        strompreis_cent = resolve_strompreis_for_komponente(tarife, "allgemein")
    if einspeiseverguetung_cent is None:
        einspeiseverguetung_cent = resolve_einspeiseverguetung_cent(tarife)

    # Monatsdaten für Durchschnittspreis-Fallback laden
    anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    anlage_md_dict = {
        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
    }

    # Gewichteter Ø-Netzbezugspreis für Spread-Berechnung — Basistarif JE MONAT
    # (ADR-002/P8). Mit dem heutigen Tarif als Basis hätte eine Preiserhöhung
    # den Ø über die gesamte Speicher-Historie angehoben und damit den
    # Arbitrage-Spread rückwirkend verändert. Der Flex-Ø des Monats behält
    # weiterhin Vorrang (`resolve_netzbezug_preis_cent`).
    #
    # Die Einspeisevergütung läuft seit v4.0.7 durch DIESELBE Schleife: der
    # Spread ist `bezug − einspeise`, und solange nur der Minuend je Monat
    # aufgelöst wurde, stammten die beiden Summanden aus verschiedenen
    # Zeitpunkten. Gewichtet wird sie mit derselben Menge wie der Bezugspreis
    # — der Spread wird auf die Entladung angewendet, für die es hier keine
    # eigene Monatsaufteilung gibt.
    gew_preis_sum = 0.0
    gew_einspeise_sum = 0.0
    for m in anlage_md_dict.values():
        m_tarife = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=date(m.jahr, m.monat, 1)
        )
        m_basis = resolve_strompreis_for_komponente(
            m_tarife, "allgemein", fallback=strompreis_cent
        )
        gew_preis_sum += resolve_netzbezug_preis_cent(m, m_basis) * (m.netzbezug_kwh or 0)
        # #392: der Monatssatz der variablen Vergütung schlägt den Stamm-
        # Monatstarif — dieselbe zweite Auflösungsstufe wie beim Bezugspreis
        # eine Zeile darüber.
        gew_einspeise_sum += resolve_einspeise_preis_cent(
            m,
            resolve_einspeiseverguetung_cent(m_tarife, fallback=einspeiseverguetung_cent),
        ) * (m.netzbezug_kwh or 0)
    gew_kwh_sum = sum(m.netzbezug_kwh or 0 for m in anlage_md_dict.values())
    eff_strompreis_cent = gew_preis_sum / gew_kwh_sum if gew_kwh_sum > 0 else strompreis_cent
    eff_einspeise_cent = (
        gew_einspeise_sum / gew_kwh_sum if gew_kwh_sum > 0 else einspeiseverguetung_cent
    )

    # Batch-Query: Alle Monatsdaten für alle Speicher auf einmal laden
    speicher_ids = [s.id for s in speicher_list]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Etappe C (#264): TEP-basierter effektiver Ladepreis — anlageweit, einmal.
    # Periode = älteste Speicher-Installation bis heute (oder neueste
    # Stilllegung, wenn alle Speicher stillgelegt sind). Try/except-gekapselt:
    # das Dashboard darf nie an einem Helper sterben (analog aussichten.py).
    installs = [s.anschaffungsdatum for s in speicher_list if s.anschaffungsdatum]
    stilllegungen = [s.stilllegungsdatum for s in speicher_list if s.stilllegungsdatum]
    periode_von = min(installs) if installs else None
    periode_bis = (
        max(stilllegungen)
        if stilllegungen and len(stilllegungen) == len(speicher_list)
        else date.today()
    )
    eff_ladepreis = None
    if periode_von is not None:
        try:
            eff_ladepreis = await berechne_effektiver_ladepreis(
                db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
            )
        except Exception as e:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}: effektiver Ladepreis "
                f"fehlgeschlagen: {type(e).__name__}: {e}"
            )

    dashboards = []
    for speicher in speicher_list:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(speicher.id, [])
            if speicher.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_arbitrage_kwh = 0
        arbitrage_preis_sum = 0
        arbitrage_count = 0

        monats_reihe: list[tuple[int, int, float, float]] = []
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            md_ladung = d.get('ladung_kwh', 0) or 0
            md_entladung = d.get('entladung_kwh', 0) or 0
            gesamt_ladung += md_ladung
            gesamt_entladung += md_entladung
            monats_reihe.append((md.jahr, md.monat, md_ladung, md_entladung))
            # Arbitrage (Netzladung zu günstigen Zeiten) — Kanon-Key
            # `ladung_netz_kwh` + Legacy-Fallback über den SoT-Helper; der
            # rohe Legacy-Read las nach der v3.26-Key-Migration immer 0.
            netzladung = get_speicher_netzladung_kwh(d)
            if netzladung > 0:
                gesamt_arbitrage_kwh += netzladung
                preis = d.get('speicher_ladepreis_cent', 0) or 0
                # Fallback: Monatsdaten Ø-Preis für dynamische Tarife
                if preis <= 0:
                    anlage_md = anlage_md_dict.get((md.jahr, md.monat))
                    if anlage_md and anlage_md.netzbezug_durchschnittspreis_cent is not None:
                        preis = anlage_md.netzbezug_durchschnittspreis_cent
                if preis > 0:
                    arbitrage_preis_sum += preis * netzladung
                    arbitrage_count += netzladung

        # Effizienz — Σentladung/Σladung über die gesamte Historie. Über ein
        # langes Fenster mittelt sich der SoC-Übertrag aus (siehe
        # core/berechnungen/speicher.py); pro Monat wäre der Wert verzerrt.
        # Seit N-252 über den Layer-SoT: Er trägt dieselbe Rechnung, aber er
        # kappt bei 100 % und sagt dann, WARUM kein Wert kommt. Das `or 0`, das
        # hier stand, machte aus „nicht ermittelbar" eine glatte 0 % — dieselbe
        # Fake-0-Klasse wie in N-87.
        _eta = speicher_wirkungsgrad(
            gesamt_ladung, gesamt_entladung, None, langes_fenster_quelle="fenster_lang"
        )
        effizienz = _eta.prozent
        verlauf = gleitende_effizienz(monats_reihe)
        durchsatz = pruefe_speicher_durchsatz_konsistenz(gesamt_ladung, gesamt_entladung)
        if not durchsatz.konsistent:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                f"{durchsatz}"
            )

        # Vollzyklen über den Layer-SoT — ENTLADUNG ÷ Kapazität (Kanon seit
        # 2026-07-28). Vorher stand hier die Ladung, während der HA-Sensor
        # schon die Entladung nahm: zwei Zahlen unter demselben Namen.
        params = speicher.parameter or {}
        # N127: BRUTTO-Kapazität über den SoT-Helper, ohne Default. Hier stand
        # `.get(…, 10)` — ein Speicher ohne gepflegte Kapazität bekam still
        # 10 kWh und daraus eine Zyklenzahl, die es nie gab. Ohne Kapazität
        # gibt es keine Zyklenzahl: `None` („unbekannt"), nicht 0 („nie
        # zyklisiert"). Bei gepflegter Kapazität bleibt der bisherige
        # 0-Ersatz für „keine Entladung" unverändert.
        kapazitaet = get_speicher_kapazitaet_kwh(speicher)
        arbitrage_faehig = params.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"], PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"])
        vollzyklen = (
            (berechne_vollzyklen(gesamt_entladung, kapazitaet) or 0)
            if kapazitaet is not None else None
        )

        # Etappe C (#264): SoC-korrigierter η-IST pro Speicher.
        # aggregiere_speicher_ist als SoT-Helper statt Parallel-Summe.
        eta_ist = None
        if monatsdaten and periode_von is not None:
            try:
                ist_agg = aggregiere_speicher_ist(
                    [md.verbrauch_daten or {} for md in monatsdaten]
                )
                if ist_agg.jahres_faktor > 0:
                    # A31-2: netto mit stillem Brutto-Fallback über den SoT-
                    # Helper (bisher inline). Identisches Verhalten.
                    nutzbar = get_speicher_nutzbare_kapazitaet_kwh(speicher) or 0
                    eta_ist = await berechne_ist_wirkungsgrad(
                        db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
                        ladung_kwh=ist_agg.ladung_kwh_jahr / ist_agg.jahres_faktor,
                        entladung_kwh=ist_agg.entladung_kwh_jahr / ist_agg.jahres_faktor,
                        nutzbare_kapazitaet_kwh=float(nutzbar),
                        fenster_monate=ist_agg.anzahl_monate,
                    )
            except Exception as e:
                logger.warning(
                    f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                    f"η-IST fehlgeschlagen: {type(e).__name__}: {e}"
                )

        # Ersparnis über den Layer-SoT (#358): Spread zwischen Netzbezug und
        # Einspeisung, aber NUR auf dem PV-Anteil der Entladung. BEIDE Preis-
        # Seiten aus derselben Monatsschleife oben — ein Ø-Bezugspreis gegen die
        # heutige Vergütung wäre ein Spread aus zwei Zeitpunkten (ADR-002/P8).
        #
        # Hier stand der Spread als Inline-Formel auf der GESAMTEN Entladung,
        # daneben ein zweiter Posten „Arbitrage-Gewinn" auf der Netzladung — der
        # Hub addiert beide in der Wirtschaftlichkeits-Aufstellung
        # (`komponentenAdapter.tsx`), also wurde netzgeladene Energie zweimal
        # gutgeschrieben: einmal mit dem PV-Spread (den sie nicht verdient, sie
        # hätte nie eingespeist werden können) und einmal mit ihrem echten
        # Arbitrage-Vorteil. Der Layer trennt beides sauber; die zwei Posten
        # unten sind seither disjunkt und summieren sich auf `ersparnis`.
        arbitrage_avg_preis = (arbitrage_preis_sum / arbitrage_count) if arbitrage_count > 0 else 0
        _sp = berechne_speicher_ersparnis(
            entladung_kwh=gesamt_entladung,
            bezug_preis_cent=eff_strompreis_cent,
            einspeise_verg_cent=eff_einspeise_cent,
            ladung_netz_kwh=gesamt_arbitrage_kwh,
            # Nur ein ERMITTELTER η darf die Netz-/PV-Aufteilung steuern; ohne
            # ihn greift der dokumentierte Default (95 %). Vorher konnte hier
            # ein Wert über 100 % einlaufen und den Netz-Anteil aufblähen.
            **({"wirkungsgrad_prozent": effizienz} if effizienz else {}),
            lade_preis_cent=arbitrage_avg_preis if arbitrage_avg_preis > 0 else None,
        )
        ersparnis = _sp.ersparnis_euro
        arbitrage_gewinn = _sp.netz_anteil_euro

        zusammenfassung = {
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'gesamt_entladung_kwh': round(gesamt_entladung, 1),
            'effizienz_prozent': round(effizienz, 1) if effizienz is not None else None,
            'effizienz_quelle': _eta.quelle,
            'vollzyklen': round(vollzyklen, 1) if vollzyklen is not None else None,
            'zyklen_pro_monat': (
                (round(vollzyklen / len(monatsdaten), 1) if monatsdaten else 0)
                if vollzyklen is not None else None
            ),
            'kapazitaet_kwh': kapazitaet,
            # P4: die fehlende Kapazität sagt sich selbst, statt als 0 oder als
            # erfundene 10 durchzulaufen (N127). Das Frontend hängt daraus einen
            # Hinweis in das bestehende `hinweise`-Array des Speicher-Geräts.
            'kapazitaet_fehlt': kapazitaet is None,
            'ersparnis_euro': round(ersparnis, 2),
            # PV-Anteil und Arbitrage-Gewinn sind die beiden DISJUNKTEN Hälften
            # von `ersparnis_euro` (#358) — die Aufstellung im Hub addiert sie,
            # deshalb darf sich hier nichts überlappen.
            'pv_anteil_euro': round(_sp.pv_anteil_euro, 2),
            'anzahl_monate': len(monatsdaten),
            # Arbitrage-Daten
            'arbitrage_faehig': arbitrage_faehig,
            'arbitrage_kwh': round(gesamt_arbitrage_kwh, 1),
            'arbitrage_avg_preis_cent': round(arbitrage_avg_preis, 1) if arbitrage_avg_preis > 0 else None,
            'arbitrage_gewinn_euro': round(arbitrage_gewinn, 2),
            # Invariante: Σentladung ≤ Σladung — kumulativ unmöglich zu verletzen.
            'durchsatz_inkonsistent': not durchsatz.konsistent,
        }

        # Etappe C (#264): TEP-basierte KPIs fürs UI — effektiver Ladepreis
        # mit Quellen-Transparenz (C1/C4), SoC-korrigierter η-IST + Degradations-
        # Alarm (C3). Felder sind optional; das Frontend fällt sonst auf die
        # bestehenden Werte (arbitrage_avg_preis_cent, effizienz_prozent) zurück.
        if eff_ladepreis is not None:
            zusammenfassung['effektiver_ladepreis_cent'] = (
                round(eff_ladepreis.effektiver_ladepreis_cent, 2)
                if eff_ladepreis.effektiver_ladepreis_cent is not None else None
            )
            zusammenfassung['effektiver_ladepreis_quelle'] = eff_ladepreis.quelle
            if eff_ladepreis.quelle == "datenbasis-zu-duenn":
                zusammenfassung['ladepreis_abdeckung_prozent'] = round(
                    eff_ladepreis.abdeckung_prozent, 0
                )
        if eta_ist is not None:
            wirkungsgrad_param = params.get(
                PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
                PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
            )
            zusammenfassung['ist_wirkungsgrad_prozent'] = (
                round(eta_ist.wirkungsgrad_prozent, 1)
                if eta_ist.wirkungsgrad_prozent is not None else None
            )
            zusammenfassung['wirkungsgrad_quelle'] = eta_ist.quelle
            zusammenfassung['param_wirkungsgrad_prozent'] = round(wirkungsgrad_param, 1)
            if eta_ist.wirkungsgrad_prozent is not None:
                zusammenfassung['eta_degradation_alarm'] = ist_eta_degradation_alarm(
                    ist_wirkungsgrad_prozent=eta_ist.wirkungsgrad_prozent,
                    param_wirkungsgrad_prozent=wirkungsgrad_param,
                )

        dashboards.append(SpeicherDashboardResponse(
            investition=speicher,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
            effizienz_verlauf=[asdict(m) for m in verlauf],
        ))

    return dashboards


@router.get("/monatsdaten/{anlage_id}/{jahr}/{monat}", response_model=list[InvestitionMonatsdatenResponse])
async def get_investition_monatsdaten_by_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle InvestitionMonatsdaten für eine Anlage und einen bestimmten Monat zurück.

    Dies wird vom MonatsdatenForm benötigt, um beim Bearbeiten eines Monats
    die vorhandenen Investitionsdaten (E-Auto km, Speicher Ladung, etc.) zu laden.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        list[InvestitionMonatsdatenResponse]: Liste der InvestitionMonatsdaten
    """
    # Issue #123: MonatsdatenForm-Editor — zeige Investitionen, die in dem
    # bearbeiteten Monat aktiv waren (auch inzwischen stillgelegte).
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(aktiv_im_monat(jahr, monat))
    )
    investitionen = inv_result.scalars().all()

    # Batch-Query: Alle InvestitionMonatsdaten für diesen Monat auf einmal laden
    inv_ids = [inv.id for inv in investitionen]
    if not inv_ids:
        return []

    md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
        .where(InvestitionMonatsdaten.jahr == jahr)
        .where(InvestitionMonatsdaten.monat == monat)
    )
    return md_result.scalars().all()


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
    # schreibt die Ladedaten in die Wallbox-Investition (data_import.py:453),
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


@router.get("/dashboard/balkonkraftwerk/{anlage_id}", response_model=list[BalkonkraftwerkDashboardResponse])
async def get_balkonkraftwerk_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(
        None, description="Override: Strompreis (auto aus dem Monatstarif wenn leer)"
    ),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Balkonkraftwerk Dashboard für eine Anlage.

    Zeigt Balkonkraftwerke mit Erzeugung, Eigenverbrauch, Ersparnis.

    **Befund F-4 der Drift-Inventur 2026-07-31**, hier behoben — die Sicht
    bewertete zweimal an der Wirklichkeit vorbei:

    (a) ``strompreis_cent`` war ein **Pflicht-Query mit Default 30,0**, und
    keiner der beiden Frontend-Aufrufer (``v4/komponentenAdapter.tsx``,
    ``v4/BkwHubBloecke.tsx``) übergab je einen Preis — der Default griff also
    immer, unabhängig vom gepflegten Tarif. Jetzt kommt der Preis je Monat aus
    den Monats-Fakten (ADR-002/**P8**) und wird mit dem Eigenverbrauch des
    jeweiligen Monats gewichtet; der Query-Parameter bleibt als Override.

    (b) Bewertet wurde der **gemessene** ``eigenverbrauch_kwh``. Der ist im
    Normalfall 0 — beim Balkonkraftwerk ist ``pv_erzeugung_kwh`` das
    Pflichtfeld und das einzige, das Sensor-/MQTT-Pfad schreiben können. Der
    Hub zeigte deshalb **0 € Ersparnis**, während das Cockpit dieselbe Energie
    seit ``0faad16b`` (ADR-002/**P9**) korrekt bewertet. Jetzt entscheidet
    ``bkw_eigenverbrauch_anteil`` (ADR-001, ``core/berechnungen/bkw_finanz.py``)
    je Monat: gemessener EV bei fehlender Erzeugung, sonst der Anteil an der
    Hausbilanz — und **nicht bewertbar**, wo mangels Zählerzeile keine Bilanz
    existiert (P4), statt still 0 €.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.BALKONKRAFTWERK.value)
    )
    balkonkraftwerke = inv_result.scalars().all()

    if not balkonkraftwerke:
        return []

    # Batch-Query: Alle Monatsdaten für alle BKW auf einmal laden
    bkw_ids = [b.id for b in balkonkraftwerke]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(bkw_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Anlagen-Kontext je Monat aus der EINEN Aufbereitung (ADR-002/P10):
    # Hausbilanz-Eigenverbrauch, Erzeugung hinter dem Zähler und der Tarif, der
    # in DIESEM Monat galt. Die BKW-eigenen Mengen bleiben per-Investition —
    # dafür hat die Schicht bewusst keine Sicht (Register N-2).
    fakten_je_monat = {
        f.schluessel: f for f in await lade_monats_fakten(db, anlage_id)
    }

    dashboards = []
    for bkw in balkonkraftwerke:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(bkw.id, [])
            if bkw.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_speicher_ladung = 0
        gesamt_speicher_entladung = 0
        # F-4: die bewertete Menge und ihr Preis, beide je Monat aufgelöst.
        ev_bewertet_kwh = 0.0
        ersparnis_eigenverbrauch = 0.0
        ev_monate_nicht_bewertbar = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # Kanonische Auflösung statt Literal-Schlüsseln (ADR-002/P6):
            # `imd_typ_beitrag` kennt beide Schreibweisen der Erzeugung.
            beitrag = imd_typ_beitrag(bkw, d)
            gesamt_erzeugung += beitrag.bkw_erzeugung
            gesamt_eigenverbrauch += beitrag.bkw_eigenverbrauch
            gesamt_speicher_ladung += beitrag.bkw_speicher_ladung
            gesamt_speicher_entladung += beitrag.bkw_speicher_entladung
            gesamt_einspeisung += d.get('einspeisung_kwh', 0) or 0

            fakt = fakten_je_monat.get((md.jahr, md.monat))
            anteil = bkw_eigenverbrauch_anteil(
                bkw_erzeugung_kwh=beitrag.bkw_erzeugung,
                bkw_eigenverbrauch_gemessen_kwh=beitrag.bkw_eigenverbrauch,
                erzeugung_hinter_zaehler_kwh=(
                    fakt.erzeugung.hinter_zaehler_kwh if fakt else 0.0
                ),
                eigenverbrauch_gesamt_kwh=(
                    fakt.kennzahlen.eigenverbrauch_kwh if fakt else 0.0
                ),
                hat_zaehlerzeile=bool(fakt and fakt.meta.hat_zaehlerzeile),
            )
            if not anteil.bewertbar and beitrag.bkw_erzeugung > 0:
                ev_monate_nicht_bewertbar += 1
            ev_bewertet_kwh += anteil.kwh
            # P8: der Preis DIESES Monats, nicht der heutige — ein Tarifwechsel
            # hätte sonst die ganze Historie rückwirkend neu bewertet.
            preis_cent = (
                strompreis_cent
                if strompreis_cent is not None
                else (fakt.tarif.netzbezug_preis_cent if fakt else NETZBEZUG_DEFAULT_CENT)
            )
            ersparnis_eigenverbrauch += anteil.kwh * preis_cent / 100

        # Parameter
        params = bkw.parameter or {}
        leistung_wp = params.get('leistung_wp', 0)
        # Lese-Default 1 (`ANZAHL_LESE_DEFAULT`), nicht die Formular-Vorbelegung 2:
        # ein BKW ohne gepflegte `anzahl` wurde hier mit DOPPELTER Leistung und
        # damit halbem spez. Ertrag ausgewiesen (N-D).
        anzahl = params.get('anzahl') or ANZAHL_LESE_DEFAULT
        hat_speicher = params.get('hat_speicher', False)
        speicher_kapazitaet = params.get('speicher_kapazitaet_wh', 0)

        # Berechnungen — kWp über den SoT-Helper (ADR-002/P3-a). Die frühere
        # Formel hatte die Priorität UMGEKEHRT (`parameter` vor Spalte) und
        # ignorierte damit den vom Formular gepflegten Spaltenwert.
        gesamt_leistung_wp = get_bkw_kwp(bkw) * 1000

        # Einspeisung berechnen falls nicht explizit erfasst
        # Einspeisung = Erzeugung - Eigenverbrauch (unvergütet ins Netz).
        # Auf der BEWERTETEN Menge, wie Quote und CO₂ — sonst stünde hier 0 kWh
        # Einspeisung neben einer Eigenverbrauchsquote von 70 %.
        if gesamt_einspeisung == 0 and gesamt_erzeugung > 0 and ev_bewertet_kwh > 0:
            gesamt_einspeisung = max(0, gesamt_erzeugung - ev_bewertet_kwh)

        # Eigenverbrauchsquote — auf der BEWERTETEN Menge, nicht auf dem
        # gemessenen Feld: sonst nennt die Kachel 0 % neben einer Ersparnis > 0.
        eigenverbrauch_quote = eigenverbrauchsquote_prozent(ev_bewertet_kwh, gesamt_erzeugung)

        # Speicher-Effizienz über den Layer-SoT (N-252) — der integrierte
        # Speicher eines BKW rechnet nach derselben Regel wie jeder andere.
        _eta_bkw = speicher_wirkungsgrad(
            gesamt_speicher_ladung, gesamt_speicher_entladung, None,
            langes_fenster_quelle="fenster_lang",
        )
        speicher_effizienz = _eta_bkw.prozent

        # `ersparnis_eigenverbrauch` steht bereits — je Monat aus
        # `bkw_eigenverbrauch_anteil` × Monatstarif (s. Docstring, F-4).
        # Einspeisung bei BKW ist i.d.R. unvergütet (keine Einspeisevergütung ohne Anmeldung)
        # Wird nur als Info angezeigt, nicht als Erlös
        erloes_einspeisung = 0  # BKW-Einspeisung ist unvergütet
        gesamt_ersparnis = ersparnis_eigenverbrauch

        # CO2-Einsparung für Eigenverbrauch — dieselbe Menge wie die Ersparnis.
        # Der Kanon rechnet CO₂-PV auf dem EIGENVERBRAUCH (`berechne_co2_bilanz`,
        # DI-2); eingespeister Strom ist nicht die eigene Ersparnis.
        co2_ersparnis = ev_bewertet_kwh * CO2_FAKTOR_STROM_KG_KWH

        # Spezifischer Ertrag (kWh pro kWp)
        spezifischer_ertrag = spezifischer_ertrag_kwh_kwp(
            gesamt_erzeugung, gesamt_leistung_wp / 1000 if gesamt_leistung_wp > 0 else 0
        ) or 0

        zusammenfassung = {
            'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
            # Die BEWERTETE Menge (F-4): gemessen, wo gemessen wurde, sonst der
            # Anteil an der Hausbilanz. Der rohe Messwert steht daneben, damit
            # eine Pflege-Lücke sichtbar bleibt statt als 0 zu verschwinden.
            'gesamt_eigenverbrauch_kwh': round(ev_bewertet_kwh, 1),
            'eigenverbrauch_gemessen_kwh': round(gesamt_eigenverbrauch, 1),
            # P4: Monate mit Erzeugung, für die mangels Zählerzeile keine
            # Hausbilanz existiert — dort ist die Ersparnis nicht 0, sondern
            # unbekannt, und das Frontend darf das sagen.
            'monate_nicht_bewertbar': ev_monate_nicht_bewertbar,
            'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),  # Berechnet: unvergütet ins Netz
            'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
            'spezifischer_ertrag_kwh_kwp': round(spezifischer_ertrag, 0),
            # Leistung
            'leistung_wp': gesamt_leistung_wp,
            'anzahl_module': anzahl,
            # Speicher (falls vorhanden)
            'hat_speicher': hat_speicher,
            'speicher_kapazitaet_wh': speicher_kapazitaet,
            'speicher_ladung_kwh': round(gesamt_speicher_ladung, 1) if hat_speicher else 0,
            'speicher_entladung_kwh': round(gesamt_speicher_entladung, 1) if hat_speicher else 0,
            'speicher_effizienz_prozent': (
                round(speicher_effizienz, 1)
                if hat_speicher and speicher_effizienz is not None else None
            ),
            'speicher_effizienz_quelle': _eta_bkw.quelle if hat_speicher else None,
            # Finanzen
            'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
            'erloes_einspeisung_euro': round(erloes_einspeisung, 2),  # 0 bei BKW (unvergütet)
            'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
            # CO2
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(BalkonkraftwerkDashboardResponse(
            investition=bkw,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


def _monatsverbrauch_aus_verlauf(fenster) -> list[dict]:
    """Verbrauch je Kalendermonat aus einem Stand-Verlauf (#377).

    Aus einer **Bestands**reihe (Zählerstände) wird eine **Fluss**reihe
    (Verbrauch je Monat): je Monat der letzte bekannte Stand, dann die Differenz
    zum letzten Stand des Vormonats.

    ⚠ **Der erste Monat der Aufzeichnung bekommt keinen Wert.** Es gibt keinen
    Vormonatsstand, gegen den man ihn messen könnte — eine 0 dort wäre die
    Behauptung „in diesem Monat wurde nichts verbraucht" (ADR-002/P4).

    ⚠ Ein **Rücksprung** (neuer Zähler ohne Stilllegung) ergäbe eine negative
    Differenz. Sie wird ausgelassen statt gekappt: eine stille Kappung machte
    aus einem Widerspruch eine plausibel aussehende Zahl. Der Daten-Checker
    macht daraus einen Hinweis mit dem Weg (§4: stilllegen + neu anlegen).
    """
    if fenster is None or not fenster.verlauf:
        return []
    letzter_je_monat: dict[tuple[int, int], float] = {}
    for punkt in fenster.verlauf:
        letzter_je_monat[(punkt.zeitpunkt.year, punkt.zeitpunkt.month)] = punkt.stand

    out: list[dict] = []
    vorher: Optional[float] = None
    for (j, m) in sorted(letzter_je_monat):
        stand = letzter_je_monat[(j, m)]
        if vorher is not None and stand >= vorher:
            out.append({
                'jahr': j, 'monat': m,
                'verbrauch': round(stand - vorher, 3),
                'stand': stand,
            })
        vorher = stand
    return out


@router.get("/dashboard/sonstiges/{anlage_id}", response_model=list[SonstigesDashboardResponse])
async def get_sonstiges_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(
        None, description="Override: Strompreis (auto aus dem Monatstarif wenn leer)"
    ),
    einspeiseverguetung_cent: Optional[float] = Query(
        None, description="Override: Einspeisevergütung (auto aus dem Monatstarif wenn leer)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Sonstiges Dashboard für eine Anlage.

    Zeigt sonstige Investitionen (Mini-BHKW, Pelletofen, etc.) mit kategorie-abhängigen Daten.

    **Dieselbe Klasse wie Befund F-4 beim Balkonkraftwerk**, hier für BEIDE
    Preisseiten: die Query-Parameter waren Pflichtwerte mit den Defaults 30,0
    und 8,0 ct/kWh, und ``v4/komponentenAdapter.tsx`` ruft die Route ohne
    Preise auf — die Konstanten galten also immer, unabhängig vom gepflegten
    Tarif. Ein BHKW rechnete seine Ersparnis mit 30 ct, auch wenn der Vertrag
    auf 24 ct lautete.

    Jetzt kommen beide Preise je Monat aus dem dann gültigen Tarif
    (ADR-002/**P8**), gewichtet mit der Menge, die die jeweilige Kategorie
    tatsächlich bewertet: Eigenverbrauch beim Erzeuger, Netzbezug beim
    Verbraucher, Entladung beim Speicher. Die Query-Parameter bleiben als
    Override erhalten.
    """
    tarife_heute = await lade_tarife_fuer_anlage(db, anlage_id)
    fallback_bezug = (
        strompreis_cent
        if strompreis_cent is not None
        else resolve_strompreis_for_komponente(tarife_heute, "allgemein")
    )
    fallback_einspeise = (
        einspeiseverguetung_cent
        if einspeiseverguetung_cent is not None
        else resolve_einspeiseverguetung_cent(tarife_heute)
    )

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SONSTIGES.value)
    )
    sonstige = inv_result.scalars().all()

    if not sonstige:
        return []

    dashboards = []
    for inv in sonstige:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        # #308: SoT-Filter auf die Laufzeit (Anschaffung→Stilllegung), wie bei
        # den fünf anderen Dashboards in dieser Datei. Ohne ihn flossen Monate
        # vor Anschaffung / nach Stilllegung in die gesamt_*-Summen.
        monatsdaten = [
            md for md in md_result.scalars().all()
            if inv.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        params = inv.parameter or {}
        # N-244: ohne gepflegte Kategorie wird hier nicht mehr „Erzeuger"
        # geraten. Der Einwand aus N-250 („über viele Monate gibt es kein
        # einzelnes *hat Erzeugung*") stimmt für einen Monat — über den ganzen
        # Bestand ist die Frage beantwortbar, und genau den hat diese Schleife
        # schon geladen. Vorher aggregierte ein ungepflegtes **Verbrauchs**gerät
        # ausschließlich Erzeugungsfelder: der Hub zeigte lauter Nullen, obwohl
        # gepflegte Verbrauchswerte danebenlagen.
        kategorie = params.get('kategorie')
        if not ist_gepflegte_sonstiges_kategorie(kategorie):
            kategorie = sonstiges_richtung(
                None,
                hat_erzeugung=any(
                    (md.verbrauch_daten or {}).get('erzeugung_kwh') for md in monatsdaten
                ),
            )
        beschreibung = params.get('beschreibung', '')

        # Aggregation basierend auf Kategorie
        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_verbrauch = 0
        gesamt_bezug_pv = 0
        gesamt_bezug_netz = 0
        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_sonstige_ertraege = 0
        gesamt_sonstige_ausgaben = 0

        # Gewichte für die Tarif-Mittelung (ADR-002/P8): je Kategorie die
        # Menge, die unten auch bewertet wird. Ein Monat ohne bewertete Menge
        # trägt keinen Preis bei — sonst zöge ein datenloser Altmonat mit
        # altem Tarif den Ø nach unten.
        preis_gewichte: dict[tuple[int, int], float] = {}

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            summen = berechne_sonstige_summen(d)
            gesamt_sonstige_ertraege += summen["ertraege_euro"]
            gesamt_sonstige_ausgaben += summen["ausgaben_euro"]

            if kategorie == 'erzeuger':
                gesamt_erzeugung += d.get('erzeugung_kwh', 0)
                gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0)
                gesamt_einspeisung += d.get('einspeisung_kwh', 0)
                preis_gewichte[(md.jahr, md.monat)] = d.get('eigenverbrauch_kwh', 0) or 0
            elif kategorie == 'verbraucher':
                gesamt_verbrauch += get_sonstiges_verbrauch_kwh(d)
                gesamt_bezug_pv += d.get('bezug_pv_kwh', 0)
                gesamt_bezug_netz += d.get('bezug_netz_kwh', 0)
                preis_gewichte[(md.jahr, md.monat)] = (
                    (d.get('bezug_netz_kwh', 0) or 0) + (d.get('bezug_pv_kwh', 0) or 0)
                )
            elif kategorie == 'speicher':
                gesamt_ladung += d.get('ladung_kwh', 0)
                gesamt_entladung += d.get('entladung_kwh', 0)
                preis_gewichte[(md.jahr, md.monat)] = d.get('entladung_kwh', 0) or 0

        gesamt_sonstige_netto = gesamt_sonstige_ertraege - gesamt_sonstige_ausgaben

        # Beide Preisseiten je Monat, EIN Aufruf: bei den Kategorien
        # `erzeuger` und `speicher` gehen sie gemeinsam in eine Formel
        # (Eigenverbrauch gegen Einspeisung bzw. der Spread), und zwei
        # Zeitpunkte in einer Differenz sind genau der Fehler, den P8 meint.
        preise = await _gewichtete_monatspreise(
            db, anlage_id, "allgemein", preis_gewichte,
            fallback_bezug=fallback_bezug,
            fallback_einspeise=fallback_einspeise,
        )
        inv_strompreis_cent = preise.bezug_cent
        inv_einspeise_cent = preise.einspeise_cent

        # Berechnungen je nach Kategorie
        if kategorie == 'erzeuger':
            eigenverbrauch_quote = eigenverbrauchsquote_prozent(gesamt_eigenverbrauch, gesamt_erzeugung)
            ersparnis_eigenverbrauch = gesamt_eigenverbrauch * inv_strompreis_cent / 100
            # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None auf
            # Monatsdaten-Aggregat-Ebene → volle Einspeisung (verhaltensneutral).
            erloes_einspeisung = einspeise_erloes_euro(
                gesamt_einspeisung, None, inv_einspeise_cent
            ).erloes_euro
            gesamt_ersparnis = ersparnis_eigenverbrauch + erloes_einspeisung + gesamt_sonstige_netto
            co2_ersparnis = gesamt_eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
                'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
                'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),
                'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
                'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
                'erloes_einspeisung_euro': round(erloes_einspeisung, 2),
                'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
                'co2_ersparnis_kg': round(co2_ersparnis, 1),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif kategorie == 'verbraucher':
            pv_anteil = (gesamt_bezug_pv / gesamt_verbrauch * 100) if gesamt_verbrauch > 0 else 0
            kosten_netz = gesamt_bezug_netz * inv_strompreis_cent / 100
            # Ersparnis: PV-Strom statt Netzstrom + sonstige Erträge/Ausgaben
            ersparnis_pv = gesamt_bezug_pv * inv_strompreis_cent / 100 + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
                'bezug_pv_kwh': round(gesamt_bezug_pv, 1),
                'bezug_netz_kwh': round(gesamt_bezug_netz, 1),
                'pv_anteil_prozent': round(pv_anteil, 1),
                'kosten_netz_euro': round(kosten_netz, 2),
                'ersparnis_pv_euro': round(ersparnis_pv, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif ist_zaehler_kategorie(kategorie):
            # #377 — ein Zähler wird ERFASST, nicht BEWERTET.
            #
            # ⚠ **Ohne diesen Zweig fiele er in den Speicher-Zweig darunter**
            # (`else`) und bekäme eine Effizienz aus Ladung/Entladung, die er
            # nicht hat, sowie eine Ersparnis aus einem Spread, den es für Gas
            # nicht gibt — vier Nullen, die wie eine Aussage aussehen. Genau
            # das ist der v4.0.17-Befund bei der Klimaanlage, und die Antwort
            # ist dieselbe: **„nicht bewertet" sagen, statt Nullen zu zeigen.**
            #
            # Eine Wirtschaftlichkeit ist hier nicht bloß unbekannt, sie ist
            # nicht anwendbar: Gas- und Wasserkosten sind Haushaltskosten und
            # gehören nicht in die Bewertung der PV-Anlage (Präzedenz: der
            # Einspeise-Erlös eines Fremd-Erzeugers, `field_definitions.py`).
            zaehler_fenster = next(
                (
                    z for z in await lade_zaehlerstaende(
                        db, anlage_id,
                        datetime(1970, 1, 1), datetime.now(),
                        mit_verlauf=True, nur_aktive=False,
                    )
                    if z.investition_id == inv.id
                ),
                None,
            )
            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'zaehler_art': zaehler_art(inv),
                'einheit': zaehler_einheit(inv),
                'stand_anfang': zaehler_fenster.stand_anfang if zaehler_fenster else None,
                'stand_ende': zaehler_fenster.stand_ende if zaehler_fenster else None,
                'differenz': zaehler_fenster.differenz if zaehler_fenster else None,
                'anfang_vollstaendig': (
                    zaehler_fenster.anfang_vollstaendig if zaehler_fenster else True
                ),
                'verlauf': [
                    {'zeitpunkt': p.zeitpunkt.isoformat(), 'stand': p.stand}
                    for p in (zaehler_fenster.verlauf if zaehler_fenster else [])
                ],
                # Der Verbrauch JE MONAT — die Differenz zweier aufeinander
                # folgender Stände.
                #
                # ⚑ **Warum das Backend sie rechnet und nicht der Hub:** Ein
                # Zählerstand ist eine Bestandsgröße, sein Verbrauch eine
                # Flussgröße — das ist ein Wechsel der Größenart, keine
                # Formatierung. Im Client gerechnet gäbe es die Rechnung
                # „Ende − Anfang" ein zweites Mal, und die zweite läuft
                # irgendwann anders (die P10-Klasse).
                'monatsverbrauch': _monatsverbrauch_aus_verlauf(zaehler_fenster),
                # Bewusst KEINE der `gesamt_*`-, `ersparnis_*`- oder
                # `co2_*`-Größen: Ein Feld mit 0 wäre eine Behauptung.
                'bewertet': False,
                'nicht_bewertet_grund': (
                    "Ein Verbrauchszähler wird in eedc erfasst und angezeigt, aber "
                    "nicht bewertet: Gas, Wasser oder Heizöl sind Haushaltskosten "
                    "und gehören nicht in die Wirtschaftlichkeit der PV-Anlage."
                ),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        else:  # speicher
            # Layer-SoT statt eigener Division (N-252) — dieselbe Zahl wie
            # Speicher-Dashboard, Cockpit und HA-Sensor.
            _eta_sonst = speicher_wirkungsgrad(
                gesamt_ladung, gesamt_entladung, None, langes_fenster_quelle="fenster_lang"
            )
            effizienz = _eta_sonst.prozent
            # Ersparnis über den Layer-SoT (#358): Spread zwischen Netzbezug und
            # Einspeisung, beide Seiten aus derselben Monats-Mittelung
            # (ADR-002/P8). Der Spread stand hier als Inline-Formel; ein
            # Speicher unter „Sonstiges" erfasst keine Netzladung, der Aufruf
            # ist deshalb verhaltensgleich — er bindet die Definition nur an
            # ihre eine Heimat (ADR-001).
            ersparnis = berechne_speicher_ersparnis(
                entladung_kwh=gesamt_entladung,
                bezug_preis_cent=inv_strompreis_cent,
                einspeise_verg_cent=inv_einspeise_cent,
            ).ersparnis_euro + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_ladung_kwh': round(gesamt_ladung, 1),
                'gesamt_entladung_kwh': round(gesamt_entladung, 1),
                'effizienz_prozent': round(effizienz, 1) if effizienz is not None else None,
                'effizienz_quelle': _eta_sonst.quelle,
                'ersparnis_euro': round(ersparnis, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        dashboards.append(SonstigesDashboardResponse(
            investition=inv,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


# ============================================================================
# CO2-Amortisation (#284) — graue Herstellungs-Last je Anlage
# ============================================================================

class GraueLastPostenResponse(BaseModel):
    """Graue Herstellungs-Last (CO2) einer einzelnen Investition."""
    investition_id: Optional[int]
    typ: str
    bezeichnung: str
    graue_last_kg: float
    quelle: str  # override | default | fehlt | kein_default


class CO2AmortisationResponse(BaseModel):
    """Σ der grauen Herstellungs-Last (CO2) einer Anlage für die CO2-Amortisation.

    Das Frontend zeichnet `graue_last_gesamt_kg` als horizontale Linie in die
    kumulierte CO2-Einsparungskurve (CO2Tab) und markiert den Schnittpunkt
    „ab wann klimapositiv".
    """
    graue_last_gesamt_kg: float
    posten: list[GraueLastPostenResponse]


@router.get("/co2-amortisation/{anlage_id}", response_model=CO2AmortisationResponse)
async def get_co2_amortisation(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Σ der grauen Herstellungs-Last (CO2) über die Investitionen einer Anlage.

    Verwendet den SoT-Helper `core/berechnungen.summe_graue_last` (ADR-001):
    Override (`graue_last_kg`) ∨ Default-Richtwert nach Typ/Größe, Dienstwagen
    ausgeschlossen, inaktive Investitionen raus.
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    bericht = summe_graue_last(investitionen)

    return CO2AmortisationResponse(
        graue_last_gesamt_kg=bericht.gesamt_kg,
        posten=[
            GraueLastPostenResponse(
                investition_id=p.investition_id,
                typ=p.typ,
                bezeichnung=p.bezeichnung,
                graue_last_kg=p.graue_last_kg,
                quelle=p.quelle,
            )
            for p in bericht.posten
        ],
    )


class HubLeerGrundResponse(BaseModel):
    """Warum der Komponenten-Reiter eines Geräts ohne Zahlen dasteht (N-247)."""

    leer: bool
    art: Optional[str] = None
    meldung: Optional[str] = None
    details: Optional[str] = None
    link: Optional[str] = None
    link_label: Optional[str] = None


@router.get("/hub-leer-grund/{anlage_id}/{investition_id}", response_model=HubLeerGrundResponse)
async def get_hub_leer_grund(
    anlage_id: int,
    investition_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Der Grund, warum ein Gerät im Komponenten-Hub keine Monatswerte zeigt (N-247).

    **Der Grund kommt aus dem Backend, nicht aus einer Client-Ableitung**
    (Gernot 2026-08-06: „zweite Wahrheit ist nicht gut") — genau wie bei
    ``TagLeerGrund``/``getTagStatus``. Der Server prüft die Leere auch selbst
    nach, statt der Behauptung des Clients zu folgen: gezählt wird mit
    **demselben Filter wie die Dashboards** (``ist_aktiv_im_monat``), sonst
    könnte der Hinweis neben gefüllten Blöcken stehen.

    ``leer=False`` ⇒ das Gerät hat Monatswerte, die Sicht zeigt nichts an.
    """
    result = await db.execute(
        select(Investition)
        .where(Investition.id == investition_id)
        .where(Investition.anlage_id == anlage_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    md_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )
    hat_werte = any(
        inv.ist_aktiv_im_monat(md.jahr, md.monat) for md in md_result.scalars().all()
    )
    if hat_werte:
        return HubLeerGrundResponse(leer=False)

    grund = bestimme_leer_grund(
        aktiv=bool(inv.aktiv),
        anschaffungsdatum=inv.anschaffungsdatum,
        stilllegungsdatum=inv.stilllegungsdatum,
        heute=date.today(),
    )
    return HubLeerGrundResponse(
        leer=True,
        art=grund.art.value,
        meldung=grund.meldung,
        details=grund.details,
        link=grund.link,
        link_label=grund.link_label,
    )
