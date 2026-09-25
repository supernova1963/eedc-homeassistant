"""Finanz-Prognose — die Eingänge: alle Investitionen der Anlage (auch stillgelegte, #123), die historischen
Komponenten-Monatswerte samt E-Mob-Anreicherung und Wallbox-Pool (F-16/F-17), die Monats-Fakten (ADR-002/P10) und ihre
Summen, die historischen EV-Quoten je Kalendermonat, die aktive PVGIS-Prognose (P5), die Mehrkosten-Summen (N-137) und
die WP-/E-Auto-Parameter-Aggregate je Gerät.
"""
# Vorlage 7b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `aussichten/finanzen.py::get_finanz_prognose` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-aussichten.py` (alte gegen neue Antworten, bitgleich).

from sqlalchemy import select
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.models.monatsdaten import Monatsdaten
from backend.core.berechnungen import (
    relevante_kosten_aus_investitionen,
    alter_wirkungsgrad,
    ersetzt_keine_heizung,
)
from backend.services.strompreis_aggregator import lade_preis_aggregate_je_monat
from backend.services.monats_fakten import lade_monats_fakten
from backend.core.field_definitions import get_wp_strom_kwh
from backend.services.eauto_wirtschaftlichkeit import (
    build_emob_pool_ctx,
    eigener_verbrauch_l_100km,
    emob_heimladung_im_monat,
)
from backend.services.emob_ladeanteil import reichere_monatszeilen_an_mit_quoten
from backend.services.emob_heimlade_quellen import laufende_heimlade_quellen
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    ist_dienstlich,
)
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp


async def lade_finanz_eingaenge(*, anlage, anlage_id, db):
    """Investitionen laden und nach Typ gruppieren, kWp der heute aktiven Erzeuger, historische Komponenten-Monatswerte
    (IMD im #236-Fenster) mit E-Mob-Anreicherung und Wallbox-Pool, Monatsdaten, Monats-Fakten und die daraus gefalteten
    Summen (PV, Speicher, V2H, Eigenverbrauch; E-Auto-PV und WP-Strom je Gerät).

    Aus `get_finanz_prognose` Zeilen 134-327 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # ALLE INVESTITIONEN LADEN — Issue #123: Hybrid-Sicht
    # Historische Aggregation braucht ALLE (auch stillgelegte) Investitionen,
    # damit Vergangenheit vollständig bleibt. Für die Prognose-Basis
    # (anlagenleistung_kwp) wird anschließend auf aktuell aktive PV gefiltert.
    # =====================================================================
    from datetime import date as _date
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
        )
    )
    alle_investitionen = result.scalars().all()

    # Nach Typ gruppieren (alle — auch historische)
    pv_module = [i for i in alle_investitionen if i.typ == "pv-module"]
    speicher = [i for i in alle_investitionen if i.typ == "speicher"]
    e_autos = [i for i in alle_investitionen
               if i.typ == "e-auto" and not ist_dienstlich(i)]
    waermepumpen = [i for i in alle_investitionen if i.typ == "waermepumpe"]
    balkonkraftwerke = [i for i in alle_investitionen if i.typ == "balkonkraftwerk"]
    sonstiges_investitionen = [i for i in alle_investitionen if i.typ == "sonstiges"]

    # Prognose-Basis: nur aktuell aktive PV (kWp für künftige Erträge)
    _heute = _date.today()
    aktuelle_pv_module = [m for m in pv_module if m.ist_aktiv_an(_heute)]
    aktuelle_bkw = [b for b in balkonkraftwerke if b.ist_aktiv_an(_heute)]
    # N36/P3: kWp über den SoT-Dispatcher — wie in `_lade_anlage_mit_pv`.
    # N-266: Selektor NACH dem `ist_aktiv_an`-Filter darüber — vor der
    # Anschaffung der Module trägt das BKW seine kWp noch selbst.
    anlagenleistung_kwp = sum(
        get_erzeuger_kwp(i)
        for i in erzeuger_traeger([*aktuelle_pv_module, *aktuelle_bkw])
    ) or anlage.leistung_kwp or 0

    # =====================================================================
    # HISTORISCHE DATEN LADEN
    # =====================================================================
    inv_ids = [i.id for i in alle_investitionen]
    inv_by_id_hist = {i.id: i for i in alle_investitionen}
    historische_inv_daten = {}

    if inv_ids:
        result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(inv_ids)
            )
        )
        # #236: IMD vor anschaffungs- / nach stilllegungsdatum überspringen
        for imd in result.scalars().all():
            inv_hist = inv_by_id_hist.get(imd.investition_id)
            if not inv_hist or not inv_hist.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            key = (imd.investition_id, imd.jahr, imd.monat)
            historische_inv_daten[key] = imd.verbrauch_daten or {}

    # F-16: der abgeleitete PV-Anteil der Heimladung gilt auch hier. Diese Route
    # liest die IMD direkt (P10-Restschuld) und speist daraus BEIDE Achsen — die
    # historische Ersparnis (`gesamt_eauto_pv`/`agg["netz_kwh"]`) und über
    # `netz_anteil` auch die **Prognose** (N-188). Ohne die Anreicherung stünde
    # der abgeleitete Anteil im Cockpit und 0 % in den Aussichten, und die
    # Prognose schriebe die ungeteilte Historie fort. Angereichert wird an genau
    # DIESER Stelle, weil sechs Lesestellen weiter unten aus derselben Map
    # schöpfen — eine je Lesestelle wäre die Kopie, die N-181 beschreibt.
    _emob_keys = [
        key
        for key in historische_inv_daten
        if (_inv := inv_by_id_hist.get(key[0])) is not None
        and _inv.typ in ("e-auto", "wallbox")
        and not ist_dienstlich(_inv)
    ]
    _emob_quoten: dict = {}
    if _emob_keys:
        _emob_daten, _emob_quoten = await reichere_monatszeilen_an_mit_quoten(
            db,
            anlage_id,
            [
                (
                    (jahr, monat),
                    inv_by_id_hist[inv_id].typ == "wallbox",
                    historische_inv_daten[(inv_id, jahr, monat)],
                )
                for (inv_id, jahr, monat) in _emob_keys
            ],
        )
        for key, daten in zip(_emob_keys, _emob_daten):
            historische_inv_daten[key] = daten

    # F-17: Wallbox-Pool-Attribution — die Lücke, die diese Route als EINZIGE
    # der fünf E-Mob-Sichten hatte. Bei einem evcc-Setup liegt die Heimladung
    # auf der *Wallbox*; die Schleifen unten filtern aber auf `inv_id == ea.id`
    # und sahen deshalb null Ladung. Folge auf beiden Achsen: die historische
    # Ersparnis zog **gar keine** Netz-Stromkosten ab, und `netz_anteil` fiel
    # in der Prognose auf den 0,5-Default, weil PV und Netz beide 0 waren.
    # An Gernots Anlage (Mär–Jul 2026, ausschließlich Sensordaten gemessen):
    # 0 statt 126,23 kWh Netz und 0 statt 619,77 kWh PV.
    _private_wallboxen = [
        i for i in inv_by_id_hist.values() if i.typ == "wallbox" and not ist_dienstlich(i)
    ]
    emob_pool_ctx = build_emob_pool_ctx(
        historische_inv_daten,
        {i.id for i in inv_by_id_hist.values() if i.typ == "e-auto" and not ist_dienstlich(i)},
        {i.id for i in _private_wallboxen},
        # N-555: der Entscheid je Monat braucht „Wallbox in Betrieb" und die Quote
        # der Schätzung (Konzept Regel 2-Ü, Regel 6).
        wallbox_in_betrieb=lambda j, m: any(w.ist_aktiv_im_monat(j, m) for w in _private_wallboxen),
        quoten=_emob_quoten,
        quellen_je_monat=await laufende_heimlade_quellen(
            db, anlage_id, list(inv_by_id_hist.values()),
        ),
    )

    # Monatsdaten für Eigenverbrauch etc.
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    monatsdaten = result.scalars().all()
    monatsdaten_dict = {(md.jahr, md.monat): md for md in monatsdaten}

    # =====================================================================
    # HISTORISCHE WERTE AGGREGIEREN — aus den Monats-Fakten (ADR-002/P10)
    # =====================================================================
    # Bis 2026-07-31 faltete dieser Block die IMD-Zeilen selbst zu Monatswerten,
    # und dabei fiel die PV-Auflösung aus P7 weg: die rohe Summe über
    # `verbrauch_daten["pv_erzeugung_kwh"]` liefert 0, wenn die Erzeugung nur
    # als Anlagen-Aggregat (`Monatsdaten.pv_erzeugung_kwh`) gepflegt ist — der
    # Normalfall bei manueller Pflege und beim Import mit einem Gesamt-PV-Sensor.
    # Folge (Befund F-5 der Drift-Inventur): 32,00 € statt 212,00 € Netto-Ertrag,
    # und damit ein um 85 % zu niedriger ROI-Fortschritt.
    # `lade_monats_fakten` löst genau einmal auf — inklusive Zeitfilter (#236),
    # Dienstwagen-Filter und Monatstarif ([[feedback_aggregations_drift]]).
    _preis_messung = await lade_preis_aggregate_je_monat(db, anlage_id)
    fakten = await lade_monats_fakten(db, anlage_id, preis_messung=_preis_messung)

    gesamt_eauto_pv = 0.0
    gesamt_wp_strom = 0.0

    # `pv_kwh` = Module + BKW (P9: der daraus abgeleitete Eigenverbrauch enthält
    # den BKW-Anteil bereits; ein zusätzlicher Rest-Term nur bei fehlender
    # BKW-Erzeugung, entschieden von `bkw_finanz_beitrag` in der Schicht).
    pv_pro_monat = {f.schluessel: f.erzeugung.pv_kwh for f in fakten}
    bkw_rest_ev_pro_monat = {
        f.schluessel: f.bkw.rest_eigenverbrauch_kwh for f in fakten
    }
    speicher_ladung_pro_monat = {f.schluessel: f.speicher.ladung_kwh for f in fakten}
    speicher_entladung_pro_monat = {
        f.schluessel: f.speicher.entladung_kwh for f in fakten
    }
    v2h_pro_monat = {f.schluessel: f.emob.v2h_entladung_kwh for f in fakten}

    gesamt_pv = sum(pv_pro_monat.values())
    gesamt_speicher_ladung = sum(speicher_ladung_pro_monat.values())
    gesamt_speicher_entladung = sum(speicher_entladung_pro_monat.values())
    gesamt_v2h = sum(v2h_pro_monat.values())

    # #304 Teil 2: Eigenverbrauch pro Monat kanonisch (PV + Speicher + V2H +
    # Erzeuger hinter dem Zähler), NICHT aus dem Legacy-Feld
    # `md.eigenverbrauch_kwh` — das bleibt bei IMD-basierten Setups leer und
    # ließ die EV-Quote/-Ersparnis kollabieren. Nur Monate MIT Zählerzeile: ohne
    # gemessene Einspeisung wäre die ganze Erzeugung als Eigenverbrauch
    # ausgewiesen — eine Aussage, die niemand belegen kann (P4).
    eigenverbrauch_pro_monat = {
        f.schluessel: f.kennzahlen.eigenverbrauch_kwh
        for f in fakten
        if f.meta.hat_zaehlerzeile
    }
    gesamt_ev = sum(eigenverbrauch_pro_monat.values())

    # E-Auto-PV-Ladung + WP-Strom bleiben per-Investition aggregiert: beide
    # Größen werden unten je Fahrzeug/Wärmepumpe mit DESSEN Parametern bewertet
    # (Vergleichsverbrauch, JAZ) — dafür reicht die Monatssumme nicht.
    eauto_pv_pro_inv: dict[int, float] = {}
    for ea in e_autos:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == ea.id and ea.ist_aktiv_im_monat(jahr, monat):
                # N-199/F-17/N-555: die Heimladung DIESES Autos im Monat nach dem
                # Entscheid der einen Funktion — Wallbox-Anteil nach km, eigene
                # Heim-Felder (über den SoT-Leser, `Total − PV` bei evcc), die
                # Schätzung aus dem Fahrverbrauch oder 0.
                pv_ladung, _ = emob_heimladung_im_monat(
                    emob_pool_ctx, inv_id,
                    daten.get("km_gefahren", 0) or 0, jahr, monat, daten,
                )
                gesamt_eauto_pv += pv_ladung
                eauto_pv_pro_inv[ea.id] = eauto_pv_pro_inv.get(ea.id, 0.0) + pv_ladung

    # N-279: zusätzlich je Gerät gemerkt — die Anzeige-Felder (`wp_verbrauch_kwh`,
    # PV-Nutzung) meinen ALLE Wärmepumpen, der Alternativkosten-Vergleich unten
    # aber nur die, die überhaupt etwas ersetzt haben. Ohne die Aufteilung wurde
    # der Strom einer Neubau-WP von der Ersparnis der ersetzenden abgezogen.
    # Muster wie `eauto_pv_pro_inv` darüber; `wp_mit_ersatz` steht erst weiter
    # unten, deshalb hier je Investition statt in zwei Summen.
    wp_strom_pro_inv: dict[int, float] = {}
    for wp in waermepumpen:
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                strom = get_wp_strom_kwh(daten, wp.parameter)
                gesamt_wp_strom += strom
                wp_strom_pro_inv[wp.id] = wp_strom_pro_inv.get(wp.id, 0.0) + strom
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_heute", "_preis_messung", "alle_investitionen", "anlagenleistung_kwp", "balkonkraftwerke", "e_autos", "eauto_pv_pro_inv", "eigenverbrauch_pro_monat", "emob_pool_ctx", "fakten", "gesamt_eauto_pv", "gesamt_ev", "gesamt_pv", "gesamt_speicher_entladung", "gesamt_speicher_ladung", "gesamt_v2h", "gesamt_wp_strom", "historische_inv_daten", "inv_by_id_hist", "monatsdaten", "monatsdaten_dict", "pv_pro_monat", "speicher", "waermepumpen", "wp_strom_pro_inv",) if k in _loc}


async def quoten_und_pvgis(
    *,
    anlage_id,
    db,
    e_autos,
    eigenverbrauch_pro_monat,
    gesamt_eauto_pv,
    gesamt_ev,
    gesamt_pv,
    gesamt_speicher_entladung,
    gesamt_speicher_ladung,
    gesamt_v2h,
    gesamt_wp_strom,
    monatsdaten,
    pv_pro_monat,
    speicher,
    waermepumpen,
):
    """Historische EV-Quote je Kalendermonat mit Fallback-Komponentenmodell, Speicher-Effizienz und Komponentenbeiträge
    pro Monat; dazu die aktive PVGIS-Prognose als Monatswerte (Auswahl-SoT, P5).

    Aus `get_finanz_prognose` Zeilen 328-383 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # QUOTEN BERECHNEN (aus historischen Daten oder Defaults)
    # =====================================================================

    anzahl_monate_hist = len(monatsdaten) if monatsdaten else 1

    # Historische EV-Quote pro Kalendermonat berechnen
    # Nutzt die echte Gesamt-EV-Quote (inkl. Speicher, V2H, WP) aus Monatsdaten
    hist_ev_quoten_lists = {}  # {kalendermonat: [quote1, quote2, ...]}
    for md in monatsdaten:
        pv_monat = pv_pro_monat.get((md.jahr, md.monat), 0)
        ev_monat = eigenverbrauch_pro_monat.get((md.jahr, md.monat), 0)
        if pv_monat > 0 and ev_monat > 0:
            quote = min(1.0, ev_monat / pv_monat)
            hist_ev_quoten_lists.setdefault(md.monat, []).append(quote)

    # Durchschnitt pro Kalendermonat (falls mehrere Jahre vorhanden)
    hist_ev_quoten = {m: sum(q) / len(q) for m, q in hist_ev_quoten_lists.items()}

    # Gesamt-Durchschnitt als Fallback für Monate ohne historische Daten
    avg_hist_ev_quote = (
        sum(hist_ev_quoten.values()) / len(hist_ev_quoten)
        if hist_ev_quoten else None
    )

    # Fallback-Komponentenmodell nur wenn KEINE historischen EV-Quoten vorhanden
    if avg_hist_ev_quote is None:
        basis_ev_quote = 0.30  # Default ohne Daten
        if gesamt_pv > 0 and gesamt_ev > 0:
            ev_ohne_speicher = max(0, gesamt_ev - gesamt_speicher_entladung - gesamt_v2h)
            basis_ev_quote = ev_ohne_speicher / gesamt_pv if gesamt_pv > 0 else 0.30
            basis_ev_quote = min(0.70, max(0.15, basis_ev_quote))
    else:
        basis_ev_quote = avg_hist_ev_quote  # Wird nur für Monate ohne hist. Daten genutzt

    # Speicher-Effizienz (Entladung/Ladung)
    speicher_effizienz = 0.90  # Default 90%
    if gesamt_speicher_ladung > 0:
        speicher_effizienz = min(0.95, gesamt_speicher_entladung / gesamt_speicher_ladung)

    # Komponentenbeiträge pro Monat (für Anzeige-Felder in der Prognose)
    speicher_ev_erhohung_monat = gesamt_speicher_entladung / anzahl_monate_hist if speicher else 0
    v2h_beitrag_monat = gesamt_v2h / anzahl_monate_hist if e_autos else 0
    eauto_pv_monat = gesamt_eauto_pv / anzahl_monate_hist if e_autos else 0
    wp_strom_monat_avg = gesamt_wp_strom / anzahl_monate_hist if waermepumpen else 0

    # =====================================================================
    # PVGIS-PROGNOSE — die aktive (Auswahl-SoT, P5)
    # =====================================================================
    pvgis = await lade_aktive_prognose(db, anlage_id)

    pvgis_monatswerte = {}
    if pvgis and pvgis.monatswerte:
        for mw in pvgis.monatswerte:
            pvgis_monatswerte[mw.get("monat")] = mw.get("e_m", 0)
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("anzahl_monate_hist", "avg_hist_ev_quote", "basis_ev_quote", "eauto_pv_monat", "hist_ev_quoten", "pvgis", "pvgis_monatswerte", "speicher_ev_erhohung_monat", "v2h_beitrag_monat", "wp_strom_monat_avg",) if k in _loc}


def investitionen_und_parameter(
    *,
    alle_investitionen,
    anzahl_monate_hist,
    e_autos,
    eauto_pv_pro_inv,
    waermepumpen,
    wp_strom_pro_inv,
):
    """Relevante Kosten (Mehrkosten, Layer-SoT) gesamt und je Typ; WP-Aggregate nur für Geräte mit Ersatz (N-88/N-279)
    und E-Auto-Aggregate je Fahrzeug (Benzin-Vergleich, PHEV #331).

    Aus `get_finanz_prognose` Zeilen 384-535 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # INVESTITIONEN SUMMIEREN (mit Alternativkosten-Berechnung)
    # =====================================================================
    # Relevante Kosten = MEHRKOSTEN gegenüber der Alternative, je Position
    # geklemmt — über den Layer-SoT (ADR-001), dieselbe Zahl wie USt-Bemessung
    # (N-129/N-130) und ROI-Sicht.
    #
    # N-137/N-134: Hier stand bis 04.08. eine **Hybrid-Summe** — PV-System voll
    # + WP-/eAuto-Mehrkosten + Sonstiges voll —, und ihre Mehrkosten kamen aus
    # `inv.parameter["alternativ_kosten_euro"]`. Dieser Schlüssel hat baumweit
    # KEINEN Schreiber (gemessen): kein Formular, kein Wizard, kein Import setzt
    # ihn. Gepflegt wird die Spalte `anschaffungskosten_alternativ`, die der
    # Daten-Checker mit WARNING einfordert („werden für ROI-Berechnung
    # benötigt") — die Summe fiel also immer auf die Festannahmen 8.000/35.000 €
    # zurück und ignorierte genau das Feld, nach dem eedc fragt. Dieselbe
    # Hybrid-Summe stand ein zweites Mal in `cockpit/uebersicht.py`.
    #
    # Sichtbare Folge: keine. Die Summe erreichte über diesen Endpoint keine
    # Oberfläche (kein `.tsx` las `investition_gesamt_euro`) — sie war der
    # Nenner des Amortisations-Fortschritts, den es am Bildschirm nicht gab.
    # Mit der neuen Fortschritts-Kachel in Auswertungen → ROI wird sie sichtbar,
    # deshalb wird sie jetzt richtig.
    investition_gesamt = relevante_kosten_aus_investitionen(alle_investitionen)

    # Aufschlüsselung für die Response — dieselbe Klemmung je Position, nur nach
    # Typ gruppiert. `investition_pv_system` und `investition_sonstige` sind
    # dort, wo keine Alternative gepflegt ist, weiterhin die Vollkosten; das ist
    # keine Sonderregel, sondern `max(0, gesamt − 0)`.
    PV_RELEVANTE_TYPEN = [
        "pv-module", "wechselrichter", "speicher", "wallbox", "balkonkraftwerk"
    ]
    investition_pv_system = 0.0
    investition_wp_mehrkosten = 0.0
    investition_eauto_mehrkosten = 0.0
    investition_sonstige = 0.0
    for inv in alle_investitionen:
        relevant = relevante_kosten_aus_investitionen([inv])
        if inv.typ in PV_RELEVANTE_TYPEN:
            investition_pv_system += relevant
        elif inv.typ == "waermepumpe":
            investition_wp_mehrkosten += relevant
        elif inv.typ == "e-auto":
            investition_eauto_mehrkosten += relevant
        else:
            investition_sonstige += relevant

    # =====================================================================
    # ALTERNATIVKOSTEN-PARAMETER LADEN
    # =====================================================================

    # Wärmepumpe: per-WP-Parameter (Alter Energieträger Gas/Öl, Preis,
    # fixe Zusatzkosten). Vorher: eine `for wp`-Schleife schrieb
    # `wp_alter_preis_cent` und `wp_alter_wirkungsgrad` last-write-wins in
    # globale Variablen — bei zwei WPs mit unterschiedlichen Energieträgern
    # (Gas + Öl) wurde der Wirkungsgrad der letzten auf beide angewendet.
    # Bug #7 (v3.25.0): Default vereinheitlicht auf zentrale 12 ct/kWh aus
    # PARAM_WAERMEPUMPE_DEFAULTS (vorher hier 10.0, andernorts 12.0).
    #
    # N-88/F2b: Wer nichts ersetzt hat, gehoert in keine dieser Groessen — weder
    # mit Wirkungsgrad noch mit Zusatzkosten noch mit seiner Waerme. Deshalb EINE
    # gefilterte Liste statt drei `continue`: Die Schleife darunter greift mit
    # `wp_aggregate[wp.id]` zu und wuerde bei einem uebersprungenen Geraet mit
    # KeyError abstuerzen.
    wp_mit_ersatz = [
        wp for wp in waermepumpen
        if not ersetzt_keine_heizung(
            (wp.parameter or {}).get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
        )
    ]
    wp_aggregate: dict[int, dict] = {}
    for wp in wp_mit_ersatz:
        params = wp.parameter or {}
        wp_aggregate[wp.id] = {
            "alter_preis_cent": (
                params.get(
                    PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
                    PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
                ) or PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]
            ),
            "alter_wirkungsgrad": alter_wirkungsgrad(
                params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"])
            ),
            "zusatzkosten_jahr": params.get(
                PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0,
            ) or 0,
            "thermisch_kwh": 0.0,
        }
    wp_alternativ_zusatzkosten_jahr = sum(
        a["zusatzkosten_jahr"] for a in wp_aggregate.values()
    )
    # N-279: derselbe Monats-Ø wie `wp_strom_monat_avg`, aber nur über die
    # Geräte, die etwas ersetzt haben. Er speist AUSSCHLIESSLICH den
    # Alternativkosten-Vergleich; die Anzeige-Felder bleiben beim Gesamt-Ø,
    # denn `wp_verbrauch_kwh` meint den Verbrauch der Anlage, nicht den des
    # Vergleichs. Ohne die Trennung stand die Stromkostenseite auf einer
    # größeren Menge als die Gaskostenseite — der Strom einer Neubau-WP
    # schmälerte die Ersparnis der ersetzenden.
    gesamt_wp_strom_mit_ersatz = sum(
        wp_strom_pro_inv.get(wp.id, 0.0) for wp in wp_mit_ersatz
    )
    wp_strom_mit_ersatz_monat_avg = (
        gesamt_wp_strom_mit_ersatz / anzahl_monate_hist if wp_mit_ersatz else 0
    )

    # E-Auto: Benzin-Vergleich.
    # Pro E-Auto: `benzinpreis_default` (Fallback wenn `kraftstoffpreis_euro`
    # in Monatsdaten fehlt) und `vergleich_l_100km` (Verbrauch des
    # Vergleichs-Verbrenners). Vorher las eine `for ea`-Schleife diese Werte
    # in zwei globale Variablen — last-write-wins, bei zwei E-Autos mit
    # unterschiedlichen Parametern wurden die Werte des LETZTEN auf BEIDE
    # angewendet. Per-E-Auto-Aggregat (`eauto_aggregate[ea.id]`) ersetzt das.
    eauto_aggregate: dict[int, dict] = {}
    for ea in e_autos:
        params = ea.parameter or {}
        eauto_aggregate[ea.id] = {
            "bezeichnung": ea.bezeichnung,
            "benzinpreis_default": params.get(
                PARAM_E_AUTO["BENZINPREIS_EURO"],
                PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
            ) or PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
            "vergleich_l_100km": params.get(
                PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
                PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
            ) or PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
            # #331: der REAL getankte Verbrauch eines Plug-in-Hybrids — `None`
            # bei einem BEV, dann bleibt hier jede Zahl wie vorher. Diese Route
            # rechnet die E-Auto-Ersparnis als VIERTE Read-Site selbst (Cockpit,
            # E-Auto-Dashboard und HA-Export gehen über
            # `eauto_wirtschaftlichkeit`); ohne diesen Wert zeigte
            # Auswertungen → Finanzen für einen Hybrid mehr Ersparnis als jede
            # andere Sicht. [[feedback_aggregations_drift]]
            "eigener_l_100km": eigener_verbrauch_l_100km(params),
            "fahranteil_prozent": params.get(
                PARAM_E_AUTO["ELEKTRISCHER_FAHRANTEIL_PROZENT"]
            ),
            "verbrauch_kwh_100km": params.get(
                PARAM_E_AUTO["VERBRAUCH_KWH_100KM"],
                PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"],
            ) or PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"],
            "km": 0.0,
            "netz_kwh": 0.0,
            "fahrverbrauch_kwh": 0.0,
            "pv_kwh": eauto_pv_pro_inv.get(ea.id, 0.0),
            "bisherige_ersparnis": 0.0,
            # Invariante: immer gesetzt — der Jahres-Block unten (Zeile ~1589)
            # läuft nur bei gesamt_km > 0. Ohne diese Init crasht die
            # Komponenten-Schleife (Zeile ~1757) bei einem E-Auto OHNE
            # historische km (frisch angelegt, noch keine Daten) → 500 auf der
            # gesamten Aussichten-Finanzseite.
            "jahres_ersparnis": 0.0,
        }
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("eauto_aggregate", "investition_eauto_mehrkosten", "investition_gesamt", "investition_pv_system", "investition_sonstige", "investition_wp_mehrkosten", "wp_aggregate", "wp_alternativ_zusatzkosten_jahr", "wp_mit_ersatz", "wp_strom_mit_ersatz_monat_avg",) if k in _loc}

