"""Komponenten-Dashboard E-Auto.

GET /api/investitionen/dashboard/e-auto/{anlage_id}
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
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import (
    QUELLE_NULL,
    QUELLE_SCHAETZUNG,
    QUELLE_WALLBOX,
    attribute_emob_pool_by_km,
    berechne_eauto_ersparnis_periode,
    build_emob_pool_ctx,
    build_wb_pool_by_month,
    compute_emob_pool_attribution,
    dienstliche_ladung_der_zeile,
    eigener_verbrauch_l_100km,
    emob_heimladung_im_monat,
    waehle_extern_paar,
)
from backend.core.wirtschaftlichkeit_defaults import EXTERNE_LADUNG_DEFAULT_EURO_KWH
from backend.services.emob_ladeanteil import reichere_monatszeilen_an_mit_quoten
from backend.services.emob_heimlade_quellen import laufende_heimlade_quellen
from backend.core.berechnungen.speicher_wirtschaftlichkeit import berechne_v2h_ersparnis
from backend.core.calculations import CO2_FAKTOR_BENZIN_KG_LITER, CO2_FAKTOR_STROM_KG_KWH
from backend.core.berechnungen import eauto_effizienz_100km, eauto_effizienz_zeitraum
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse, _gewichtete_monatspreise

router = APIRouter()


class EAutoDashboardResponse(BaseModel):
    """E-Auto Dashboard Daten."""
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
    _emob_daten, _emob_quoten = await reichere_monatszeilen_an_mit_quoten(
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
    # N-555 (Konzept Regel 1 + 2-Ü + 6): der Entscheid der einen Funktion je
    # Monat — die Kacheln und die Tabelle fragen ihn, welcher Monat der Wallbox,
    # den eigenen Heim-Feldern, der Schätzung oder der 0 gehört.
    emob_ctx = build_emob_pool_ctx(
        emob_daten_by_md,
        {e.id for e in private_eautos},
        _wb_id_set,
        wallbox_in_betrieb=lambda j, m: any(
            w.ist_aktiv_im_monat(j, m) for w in private_wallboxen
        ),
        quoten=_emob_quoten,
        quellen_je_monat=await laufende_heimlade_quellen(
            db, anlage_id, [*private_eautos, *private_wallboxen],
        ),
    )

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

        # N-555: Heimladung je Monat nach dem Entscheid. Die Monate, die der
        # Wallbox gehören, verteilt weiter der globale km-Anteil unten (die
        # Verteilung des Topfs bleibt, Stufe 1); alle übrigen Monate tragen die
        # eigenen Heim-Felder, die Schätzung aus dem Fahrverbrauch oder 0.
        pv_ohne_wallbox = netz_ohne_wallbox = 0.0
        netz_pro_monat_ohne_wallbox: dict[tuple[int, int], float] = {}
        # N-557: kWh/100 km je Monat nach der Layer-Regel, der Zeitraum ist
        # Σ Monatswerte ÷ Σ km (`eauto_effizienz_zeitraum`).
        effizienz_monate = []
        for md in monatsdaten:
            # F-16: mit abgeleitetem PV-Anteil, wo keiner gepflegt ist.
            d = _emob_daten_von(eauto, md)
            km_this = d.get('km_gefahren', 0) or 0
            gesamt_km += km_this
            if km_this > 0:
                km_pro_monat.append((md.jahr, md.monat, km_this))
                km_gewichte[(md.jahr, md.monat)] = km_this
            gesamt_verbrauch += d.get('verbrauch_kwh', 0)
            if dienstlich:
                # Dienstwagen unverändert (Stufe 1): seine Felder, sonst sein
                # Fahrverbrauch als Netz — bitgleich, nur ausdrücklich.
                _dl = dienstliche_ladung_der_zeile(d)
                pv, netz = _dl.pv_kwh, _dl.netz_kwh
            else:
                # #262/N-555: PV/Netz nach dem Entscheid des Monats (SoT-Leser
                # für die eigenen Felder, `Total − PV` bei evcc-Importen).
                pv, netz = emob_heimladung_im_monat(
                    emob_ctx, eauto.id, km_this, md.jahr, md.monat, d,
                )
            gesamt_pv_ladung += pv
            gesamt_netz_ladung += netz
            if netz:
                netz_pro_monat[(md.jahr, md.monat)] = netz
            _entscheid = emob_ctx.entscheide.get((md.jahr, md.monat))
            if dienstlich or _entscheid is None or _entscheid.quelle != QUELLE_WALLBOX:
                pv_ohne_wallbox += pv
                netz_ohne_wallbox += netz
                if netz:
                    netz_pro_monat_ohne_wallbox[(md.jahr, md.monat)] = netz
            gesamt_extern_ladung += d.get('ladung_extern_kwh', 0)
            gesamt_extern_kosten += d.get('ladung_extern_euro', 0)
            gesamt_v2h += d.get('v2h_entladung_kwh', 0)
            effizienz_monate.append(eauto_effizienz_100km(
                d.get('verbrauch_kwh', 0) or 0,
                pv + netz + (d.get('ladung_extern_kwh', 0) or 0),
                km_this,
            ))

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
            # Die Wallbox-Monate: globaler km-Anteil wie bisher. N-555: dazu die
            # Monate, die NICHT der Wallbox gehören (Steckerlader neben einer
            # Wallbox mit 0, Schätzung) — bis 25.09.2026 fielen sie hier weg,
            # sobald die Wallbox irgendwann einmal Heimladung trug.
            gesamt_pv_ladung = share.pv_kwh + pv_ohne_wallbox
            gesamt_netz_ladung = share.netz_kwh + netz_ohne_wallbox
            # N-555 F-5: Extern nach der Topf-Regel — das Paar mit den höheren
            # Kosten aus Wallbox-Anteil und eigenen Zeilen. Bis 25.09.2026 stand
            # hier immer der Wallbox-Anteil (meist 0), das Extern des Autos fiel weg.
            gesamt_extern_ladung, gesamt_extern_kosten = waehle_extern_paar(
                share.extern_kwh, share.extern_euro,
                gesamt_extern_ladung, gesamt_extern_kosten,
            )

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
        # N-555: die Nicht-Wallbox-Monate dieses Autos tragen ihr eigenes Gewicht.
        for k, v in netz_pro_monat_ohne_wallbox.items():
            netz_gewichte_pool[k] = netz_gewichte_pool.get(k, 0.0) + v
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
        # N-557 (Konzept Regel 10): Σ Monatswerte ÷ Σ km — jeder Monat nach der
        # Layer-Regel (gemessen vor Heim + Extern). Bis 25.09.2026 teilte die
        # Karte den Fahrverbrauch der Monate MIT Sensor durch die km ALLER Monate.
        eff = eauto_effizienz_zeitraum(effizienz_monate)

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
            if not dienstlich:
                # N-555: die Zeile zeigt, was der Entscheid des Monats DIESEM Auto
                # gibt — Wallbox-Anteil nach km (#262, wie bisher), die eigenen
                # Heim-Felder, die Schätzung aus dem Fahrverbrauch oder 0. Eine
                # Schätzung ist gekennzeichnet (`ladung_geschaetzt`), nie gespeichert.
                _e = emob_ctx.entscheide.get((md.jahr, md.monat))
                if _e is not None and _e.quelle in (
                    QUELLE_WALLBOX, QUELLE_SCHAETZUNG, QUELLE_NULL,
                ):
                    _pv, _netz = emob_heimladung_im_monat(
                        emob_ctx, eauto.id, d.get('km_gefahren', 0) or 0,
                        md.jahr, md.monat, d,
                    )
                    if _e.quelle == QUELLE_WALLBOX and _pv + _netz <= 0:
                        pass  # kein km-Anteil: die Rohzeile bleibt (wie bisher)
                    else:
                        d['ladung_pv_kwh'] = round(_pv, 2)
                        d['ladung_netz_kwh'] = round(_netz, 2)
                        d['ladung_kwh'] = round(_pv + _netz, 2)
                        if _e.quelle == QUELLE_SCHAETZUNG:
                            d['ladung_geschaetzt'] = True
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
