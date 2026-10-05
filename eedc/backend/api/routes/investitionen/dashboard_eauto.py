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
from backend.utils.investition_value import param_zahl
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeiseverguetung_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import (
    ART_GEMESSEN,
    ART_REST,
    ART_SCHAETZUNG,
    QUELLE_NULL,
    attribute_emob_pool_by_km,
    berechne_eauto_ersparnis_periode,
    compute_emob_pool_attribution,
    dienstliche_ladung_der_zeile,
    eigener_verbrauch_l_100km,
    emob_heimladung_im_monat,
    monate_des_autos,
    waehle_extern_paar,
)
from backend.core.wirtschaftlichkeit_defaults import EXTERNE_LADUNG_DEFAULT_EURO_KWH
from backend.services.emob_kontext import lade_emob_kontext
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


def _speicher_addieren(summe, entscheid, inv_id: int):
    """N-569-Ergänzung: „davon aus dem Speicher" des Monats zur Summe — ``None`` bleibt
    ``None``, solange kein Monat eine Aussage hat (ohne Speicherzähler keine Unterzeile)."""
    a = entscheid.je_auto.get(inv_id) if entscheid is not None else None
    if a is None or a.speicher_kwh is None:
        return summe
    return (summe or 0.0) + a.speicher_kwh


def _bloecke_kennzeichnen(d: dict, entscheid, inv_id: int) -> None:
    """N-555 Stufe 3 (Auftrag S3-4): ein Monat, dessen Heimladung aus Ladeblöcken stammt, sagt
    es — „aus n Ladevorgängen" (Sprünge über der Kleinstgrenze, D-4) und, wenn ein Vorgang
    die Wallbox-Stunden nicht deckt (``stunden_gedeckt`` < 0,95), wie viele. Die Menge selbst
    steht schon aus dem Entscheid in ``ladung_*`` (Σ monatsverteilter Sprünge, G2)."""
    a = entscheid.je_auto.get(inv_id) if entscheid is not None else None
    if a is not None and a.speicher_kwh:
        # N-569-Ergänzung: davon aus dem Speicher (Teil von `ladung_pv_kwh`).
        d['ladung_speicher_kwh'] = round(a.speicher_kwh, 2)
    bm = (entscheid.bloecke_je_auto.get(inv_id) if entscheid is not None else None)
    if bm is None:
        return
    d['ladung_aus_bloecken'] = True
    d['ladevorgaenge_bloecke'] = bm.ladevorgaenge
    if bm.ladevorgaenge_ungedeckt:
        d['ladevorgaenge_ungedeckt'] = bm.ladevorgaenge_ungedeckt

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

    # F-16 + N-555: der Kontext der einen Funktion (`services/emob_kontext.py`) — die
    # Zeilen mit abgeleitetem PV-Anteil (Phase 5, je Zeile), der Entscheid je Monat mit
    # Dienstwagen, dienstlicher Wallbox, Herkunft von „Heim: gesamt" und den Quellen des
    # laufenden Monats. Dieser Hub liest `InvestitionMonatsdaten` direkt (P10-Restschuld).
    _kontext = await lade_emob_kontext(
        db, anlage_id, [*eautos, *wallboxen], all_monatsdaten,
    )
    emob_ctx = _kontext.ctx
    emob_daten_by_md = _kontext.daten

    def _emob_daten_von(inv, md) -> dict:
        """Die Zeile mit abgeleitetem PV-Anteil — Fallback ist das Original.

        Der Fallback greift für Monate außerhalb der Laufzeit (sie gehören nicht in den
        Entscheid, F-7 / [[feedback_dienstwagen_alle_checks]]); dienstliche Zeilen stehen
        unverändert im Kontext.
        """
        return emob_daten_by_md.get(
            (inv.id, md.jahr, md.monat), md.verbrauch_daten or {}
        )

    # Nur noch für die EXTERNE Ladung (F-5, Topf-Regel `waehle_extern_paar`): der
    # km-Anteil am Extern der Wallbox-Zeilen. Die Heimladung verteilt seit N-555 Stufe 2
    # die eine Funktion je Monat (`entscheid.je_auto`).
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
        # N-569-Ergänzung: davon aus dem Speicher (Teil der PV-Heimladung) — nur Ausweis.
        gesamt_speicher: Optional[float] = None
        # #260: km pro Monat sammeln, damit berechne_eauto_ersparnis_periode
        # mit dem jeweils gültigen Monats-Benzinpreis rechnen kann.
        km_pro_monat: list[tuple[int, int, float]] = []

        # ADR-002/P8: Gewichte je Monat mitführen, um den Tarif über die
        # tatsächlich gültigen Monatstarife zu mitteln statt über den heutigen.
        netz_pro_monat: dict[tuple[int, int], float] = {}
        km_gewichte: dict[tuple[int, int], float] = {}

        # N-555 Stufe 2: Heimladung je Monat nach dem Entscheid der einen Funktion
        # (`entscheid.je_auto`) — gemessen, Anteil am Rest der Wallbox nach km (bei 0 km
        # zusammen gleich verteilt, E6), Schätzung aus dem Fahrverbrauch oder 0. Bis
        # 26.09.2026 verteilte dieser Hub die Wallbox-Monate mit EINEM km-Anteil über den
        # ganzen Zeitraum (`attribute_emob_pool_by_km`) — ein Auto, das in einem Monat viel
        # und im anderen wenig fuhr, bekam den Durchschnitt, und ein Auto mit eigener
        # Messung neben der Wallbox bekam trotzdem seinen km-Anteil statt seiner Werte.
        # N-557: kWh/100 km je Monat nach der Layer-Regel, der Zeitraum ist
        # Σ Monatswerte ÷ Σ km (`eauto_effizienz_zeitraum`).
        effizienz_monate = []
        # N-634: die Regel-3-Menge des Dienstwagens je Monat — dieselbe Zahl, die die Kachel
        # unten summiert, trägt auch seine Tabellenzeile (``(pv, netz, gemessen)``).
        dienst_je_monat: dict[tuple[int, int], tuple[float, float, bool]] = {}
        for md in monatsdaten:
            # F-16: mit abgeleitetem PV-Anteil, wo keiner gepflegt ist.
            d = _emob_daten_von(eauto, md)
            km_this = d.get('km_gefahren', 0) or 0
            gesamt_km += km_this
            if km_this > 0:
                km_pro_monat.append((md.jahr, md.monat, km_this))
                km_gewichte[(md.jahr, md.monat)] = km_this
            gesamt_verbrauch += d.get('verbrauch_kwh', 0)
            _entscheid = emob_ctx.entscheide.get((md.jahr, md.monat))
            if dienstlich:
                # Regel 3: die dienstliche Menge DIESES Dienstwagens aus dem Entscheid —
                # seine Messung, sonst sein Fahrverbrauch als Netz; neben einer
                # dienstlichen Wallbox in Betrieb zählt sie nicht (die Wallbox ist dort
                # die dienstliche Ladung).
                _dl = (
                    _entscheid.dienstlich_je_inv.get(eauto.id)
                    if _entscheid is not None else None
                ) or dienstliche_ladung_der_zeile(d)
                if _entscheid is not None and eauto.id not in _entscheid.dienstlich_je_inv:
                    pv = netz = 0.0
                    dienst_je_monat[(md.jahr, md.monat)] = (0.0, 0.0, True)
                else:
                    pv, netz = _dl.pv_kwh, _dl.netz_kwh
                    dienst_je_monat[(md.jahr, md.monat)] = (pv, netz, _dl.gemessen)
            else:
                pv, netz = emob_heimladung_im_monat(
                    emob_ctx, eauto.id, km_this, md.jahr, md.monat, d,
                )
                gesamt_speicher = _speicher_addieren(gesamt_speicher, _entscheid, eauto.id)
            gesamt_pv_ladung += pv
            gesamt_netz_ladung += netz
            if netz:
                netz_pro_monat[(md.jahr, md.monat)] = netz
            gesamt_extern_ladung += d.get('ladung_extern_kwh', 0)
            gesamt_extern_kosten += d.get('ladung_extern_euro', 0)
            gesamt_v2h += d.get('v2h_entladung_kwh', 0)
            effizienz_monate.append(eauto_effizienz_100km(
                d.get('verbrauch_kwh', 0) or 0,
                pv + netz + (d.get('ladung_extern_kwh', 0) or 0),
                km_this,
            ))

        # N-555 Stufe 2 (Konzept Regel 2 Schritt 3): Monate OHNE Zeile, in denen das Auto
        # Rest der Wallbox bekommt (Empfänger sind alle privaten Autos in Betrieb) — sonst
        # gingen Topf und Summe der Fahrzeuge auseinander. N-564: dieselbe Monatsmenge
        # bekommt unten die Tabelle — je Monat eine Zeile „aus Wallbox-Rest", damit Kachel
        # und Summe der Tabelle dieselbe Zahl ergeben (bis 26.09.2026 zeigte sie nur Zeilen).
        monate_ohne_zeile: list[tuple[int, int]] = []
        if not dienstlich:
            _mit_zeile = {(md.jahr, md.monat) for md in monatsdaten}
            for _j, _m, _ in monate_des_autos(emob_ctx, eauto.id, {}):
                if (_j, _m) in _mit_zeile or not eauto.ist_aktiv_im_monat(_j, _m):
                    continue
                monate_ohne_zeile.append((_j, _m))
                pv, netz = emob_heimladung_im_monat(emob_ctx, eauto.id, 0.0, _j, _m, {})
                gesamt_speicher = _speicher_addieren(
                    gesamt_speicher, emob_ctx.entscheide.get((_j, _m)), eauto.id,
                )
                gesamt_pv_ladung += pv
                gesamt_netz_ladung += netz
                if netz:
                    netz_pro_monat[(_j, _m)] = netz

        # N-555 F-5: Extern nach der Topf-Regel — das Paar mit den höheren Kosten aus
        # dem km-Anteil am Extern der Wallbox-Zeilen und den eigenen Zeilen des Autos.
        # F-7: ein Dienstwagen schöpft nicht aus dem privaten Topf.
        share = attribute_emob_pool_by_km(pool_attr, 0 if dienstlich else gesamt_km)
        if not dienstlich and pool_attr.use_wb_pool and share.netz_kwh + share.pv_kwh > 0:
            gesamt_extern_ladung, gesamt_extern_kosten = waehle_extern_paar(
                share.extern_kwh, share.extern_euro,
                gesamt_extern_ladung, gesamt_extern_kosten,
            )

        # ADR-002/P8: Tarif über die Monate der Periode mitteln — gewichtet mit der
        # Netzladung DIESES Autos je Monat (F-18). Seit N-555 Stufe 2 ist das seine
        # Menge aus dem Entscheid; vorher im Wallbox-Fall die Netzladung der ganzen
        # Wallbox je Monat (für ein Auto an der Wallbox dieselben Gewichte, für zwei
        # die falschen — der Preis des Monats, in dem das ANDERE Auto lud, zog mit).
        preis_gewichte = netz_pro_monat
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
        # N-571: param_zahl — `""` aus Import/Altbestand passierte das
        # `is not None` und beendete die Sicht mit TypeError/500; nicht
        # gepflegt ⇒ Spread-Modell (heutige Semantik).
        v2h_preis_override = param_zahl(params, 'v2h_entlade_preis_cent')
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
            # N-569-Ergänzung (Anhang E): davon aus dem Speicher, in % der Heimladung — Teil
            # des PV-Anteils; `None` ohne Speicherzähler (keine Unterzeile). Nur Ausweis.
            'speicher_anteil_heim_prozent': (
                round(gesamt_speicher / gesamt_heim_ladung * 100, 1)
                if gesamt_speicher is not None and gesamt_heim_ladung > 0 and not dienstlich
                else None
            ),
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
                # N-555: die Zeile zeigt, was der Entscheid des Monats DIESEM Auto gibt
                # (`je_auto`) — seine Messung, sein Anteil am Rest der Wallbox, die
                # Schätzung aus dem Fahrverbrauch oder 0. Eine Schätzung ist
                # gekennzeichnet (`ladung_geschaetzt`), nie gespeichert. Eine eigene
                # Messung steht schon so in der Zeile (bis auf die Teilung von
                # „Heim: gesamt" mit dem PV-Anteil der Wallbox) und wird mit übernommen.
                _e = emob_ctx.entscheide.get((md.jahr, md.monat))
                _a = _e.je_auto.get(eauto.id) if _e is not None else None
                # Wie bis Stufe 1: ein Rest-Anteil von 0 lässt die Rohzeile stehen, eine 0
                # nur, wenn der ganze Monat 0 ist.
                if _a is not None and (
                    _a.art in (ART_GEMESSEN, ART_SCHAETZUNG)
                    or _a.ladung_kwh > 0
                    or _e.quelle == QUELLE_NULL
                ):
                    d['ladung_pv_kwh'] = round(_a.pv_kwh, 2)
                    d['ladung_netz_kwh'] = round(_a.netz_kwh, 2)
                    d['ladung_kwh'] = round(_a.pv_kwh + _a.netz_kwh, 2)
                    if _a.art == ART_SCHAETZUNG:
                        d['ladung_geschaetzt'] = True
                _bloecke_kennzeichnen(d, _e, eauto.id)
            else:
                # ⭐ N-634 (05.10.2026): die Zeile des Dienstwagens trägt seine Lademenge wie die
                # eines privaten Autos — F-7 oben behält „die physischen Größen (km, Ladung,
                # PV-Anteil, V2H)" ausdrücklich; weg fällt nur die Ersparnis. Bis dahin fehlte
                # `ladung_kwh` in der Zeile, während die Kachel 60 kWh nannte. PV/Netz sind die
                # Regel-3-Menge der Kachel (`dienst_je_monat`), damit Kachel = Σ Tabelle (N-564)
                # auch hier gilt; der Fahrverbrauch als Schätzung (kein Ladefeld) ist
                # gekennzeichnet wie beim privaten Auto.
                _pv, _netz, _gemessen = dienst_je_monat.get((md.jahr, md.monat), (0.0, 0.0, True))
                d['ladung_pv_kwh'] = round(_pv, 2)
                d['ladung_netz_kwh'] = round(_netz, 2)
                d['ladung_kwh'] = round(_pv + _netz, 2)
                if not _gemessen and _pv + _netz > 0:
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

        # ⭐ N-564 (Konzept Regel 2 Schritt 3, Entscheid Master 26.09.2026): ein Monat, in dem
        # das Auto Rest der Wallbox bekommt, aber keine eigene Monatszeile hat, steht in der
        # Kachel „Heimladung" (Schleife oben) — bis hierher fehlte er in der Tabelle, und die
        # Summe der Tabelle ergab die Kachel nicht (Nachmessung Stufe 2, F3: Tesla 28 Monate
        # in der Kachel, 25 Zeilen). Jetzt trägt die Tabelle für genau diese Monate eine Zeile
        # **ohne km** und ohne ID (sie ist nicht gespeichert), mit `ladung_*` aus dem Entscheid
        # (`je_auto`), gekennzeichnet `ladung_aus_rest`. Sie ist Anzeige, kein Datensatz: der
        # Monatsabschluss und jede Zählung „erfasster Monate" sehen sie nicht.
        for _j, _m in monate_ohne_zeile:
            _e = emob_ctx.entscheide.get((_j, _m))
            _a = _e.je_auto.get(eauto.id) if _e is not None else None
            if _a is None:
                continue
            _d: dict[str, Any] = {
                'ladung_pv_kwh': round(_a.pv_kwh, 2),
                'ladung_netz_kwh': round(_a.netz_kwh, 2),
                'ladung_kwh': round(_a.pv_kwh + _a.netz_kwh, 2),
            }
            if _a.art == ART_REST:
                _d['ladung_aus_rest'] = True
            elif _a.art == ART_SCHAETZUNG:
                _d['ladung_geschaetzt'] = True
            _bloecke_kennzeichnen(_d, _e, eauto.id)
            monatsdaten_response.append(InvestitionMonatsdatenResponse(
                id=None,
                investition_id=eauto.id,
                jahr=_j,
                monat=_m,
                verbrauch_daten=_d,
                einsparung_monat_euro=None,
                co2_einsparung_kg=None,
            ))
        if monate_ohne_zeile:
            monatsdaten_response.sort(key=lambda r: (r.jahr, r.monat))

        dashboards.append(EAutoDashboardResponse(
            investition=eauto,
            monatsdaten=monatsdaten_response,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
