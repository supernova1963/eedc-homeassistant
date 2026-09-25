"""Finanz-Prognose — der Rückblick: die bisherigen Erträge aus Finanz-Zeilen mit Monats-Tarif (ADR-002/P8), die
rückblickenden Alternativkosten-Ersparnisse von Wärmepumpe und E-Auto, sonstige Positionen und dienstliche Ladekosten aus
den Monats-Fakten, anteilige Betriebskosten je Laufzeit (N-228) und die USt auf den Eigenverbrauch (N-129/N-130).
"""
# Vorlage 7b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `aussichten/finanzen.py::get_finanz_prognose` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-aussichten.py` (alte gegen neue Antworten, bitgleich).

from collections import defaultdict
from backend.core.berechnungen.investitions_jahresertrag import jahresertrag_posten
from backend.core.berechnungen.kapitalrechnung import jahres_ersparnis_euro
from backend.models.investition import ERTRAGSFELD_TYPEN
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    berechne_wp_alternativkosten_ersparnis,
)
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.berechnungen.waermepumpe_kennzahl import heizwaerme_kwh, waerme_gesamt_kwh
from backend.core.field_definitions import get_wp_warmwasser_kwh
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    emob_extern_im_monat,
    emob_heimladung_im_monat,
)
from backend.core.wirtschaftlichkeit_defaults import (
    NETZBEZUG_DEFAULT_CENT,
)
from datetime import date


async def finanz_zeilen_und_tarife(
    *,
    _heute,
    _preis_messung,
    alle_investitionen,
    anlage_id,
    db,
    fakten,
    monatsdaten,
):
    """Betriebskosten und Jahres-Ertrag der heute aktiven Investitionen (N-228, §8/2), die Finanz-Zeilen je Monat über
    `baue_finanz_zeile` (P8/P10) und die Tarif-Closure `_tarife_fuer_stichtag` für die rückblickenden Schleifen.

    18.09.2026 (Nebenfund aus Vorlage 7b): die zweite Closure `_monats_tarif` samt ihrem Lookup `_md_by_periode` ist
    entfernt — sie hatte seit `766b73b8` (die E-Auto-Historie bewertet ihre Ladung über den Layer mit dem Preis ihres
    Monats) keinen Aufrufer mehr; den #392-Vergütungs-Override der Altmonate trägt seither `baue_finanz_zeile`.

    Aus `get_finanz_prognose` Zeilen 536-655 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # BISHERIGE ERTRÄGE BERECHNEN (inkl. Alternativkosten!)
    # =====================================================================
    # N-228: nur **heute aktive** Komponenten — dieser Wert geht ausschließlich
    # in ZUKUNFTS-Größen (Jahres-Netto-Ertrag, Amortisationsdauer, USt-
    # Bemessung). Eine 2023 stillgelegte Wärmepumpe verursacht keine
    # Versicherung mehr; sie verlängerte die Amortisation trotzdem dauerhaft.
    # Der RÜCKBLICK ist davon unberührt — er rechnet weiter unten mit
    # `betriebskosten_hist_je_inv` über die tatsächliche Laufzeit.
    # `ha_export/anlage_energie.py` filtert an derselben Stelle seit jeher (`aktiv_jetzt()`),
    # die vier Sichten waren darüber uneins.
    _heute_bk = date.today()
    betriebskosten_ges = sum(
        i.betriebskosten_jahr or 0
        for i in alle_investitionen
        if i.ist_aktiv_im_monat(_heute_bk.year, _heute_bk.month)
    )
    # §8/2 des Wirtschaftlichkeits-Konzepts: das Gegenstück zu den
    # Betriebskosten auf der Ertragsseite. Ein Jahresbetrag an der Investition
    # ist per FORM wiederkehrend (§2/1) und wirkt deshalb auch in der Prognose;
    # bis 2026-08-10 kannte diese Sicht das Feld nicht (0 Treffer).
    #
    # ⚠ Zwei Einschränkungen gegenüber `betriebskosten_ges`, beide bewusst:
    # (a) nur die Typen, an denen das Feld überhaupt pflegbar und gelesen wird
    #     (`ERTRAGSFELD_TYPEN`) — sonst stünde ein Wert an einer PV-Zeile hier
    #     im Zähler, während *Auswertungen → ROI* ihn ignoriert;
    # (b) nur **heute aktive** Investitionen — eine stillgelegte Komponente
    #     bringt keinen künftigen Ertrag. Der Rückblick oben ist davon
    #     unberührt, er rechnet aus gemessenen Monatswerten.
    # ⚑ §9.2 Geldseite (11c): der Jahres-Ertrag je Investition kommt aus dem
    # SoT `jahresertrag_posten` — für ein Gerät der Kategorie *Abgabe an
    # Dritte* aus seinen gemessenen Monatserlösen, sonst aus „Ertrag/Jahr"
    # (§8/1). Der Vorrang ist dort entschieden, nicht hier.
    # ⛔ Der Filter (b) bleibt: eine Prognose zählt nur, was heute läuft. Das
    # ROI-Dashboard filtert bewusst ANDERS (ohne Jahr auch stillgelegte, #123
    # „Vergangenheit nicht löschen") — zwei Fragen, zwei Umfänge.
    _ertrag_posten = [
        p
        for i in alle_investitionen
        if i.typ in ERTRAGSFELD_TYPEN and i.ist_aktiv_an(_heute)
        for p in (jahresertrag_posten(i, fakten),)
        if p is not None
    ]
    ertrag_jahr_ges = jahres_ersparnis_euro(_ertrag_posten)
    bisherige_ertraege = 0.0
    bisherige_eauto_ersparnis = 0.0

    # #326-Vollmigration: Einspeise-Erlös §51 + EV-/BKW-Ersparnis laufen über
    # den SoT-Helper `berechne_finanz_aggregat` — per-Monat mit Monats-Flexpreis
    # UND Monats-Tarif (gueltig_ab-Stichtag), deckungsgleich mit Cockpit,
    # Jahresbericht-PDF und HA-Export ([[feedback_aggregations_drift]]). Die
    # aussichten-spezifischen Anteile (WP-/E-Auto-Alternativkosten, Prognose)
    # bleiben lokal — sie sind keine Aggregat-Semantik.
    #
    # ADR-002/P10: die Eingabe der Zeile entsteht aus dem `MonatsFakt`
    # (`finanz_zeile_eingabe`), nicht mehr aus site-eigenen Maps. Damit trägt
    # sie die P7-Auflösung, den §51-Negativpreis und den Monats-Flexpreis, ohne
    # dass diese Sicht eine der drei Regeln selbst kennt.
    #
    # `meta.erzeuger_aktiv` ist die Anschaffungsdatum-Grenze für den
    # anlagenweiten PV-Ertrag (Einspeise-Erlös + EV-Ersparnis): WP/E-Auto/
    # Sonstige begrenzen ihre Monate bereits über `ist_aktiv_im_monat` (#236),
    # dieser Pfad zusätzlich auf das aktive Fenster der Erzeuger hinter dem
    # Zähler ([[feedback_anschaffungsdatum_grenze]]). Ohne registrierten
    # Erzeuger bleibt das Verhalten unverändert.
    _tarif_cache: dict[date, dict] = {}
    finanz_zeilen: list[FinanzMonatsZeile] = []
    # Dieselben Zeilen je Kalenderjahr — die USt rechnet je Jahr (N-130), und
    # `eigenverbrauch_kwh` des Aggregats ist die Summe der Monatswerte, das
    # Zerlegen ist also exakt.
    finanz_zeilen_je_jahr: dict[int, list[FinanzMonatsZeile]] = defaultdict(list)
    for f in fakten:
        if not f.meta.hat_zaehlerzeile or not f.meta.erzeuger_aktiv:
            continue
        _zeile = await baue_finanz_zeile(
            db, anlage_id, finanz_zeile_eingabe(f), tarif_cache=_tarif_cache,
            preis_messung=_preis_messung,
        )
        finanz_zeilen.append(_zeile)
        finanz_zeilen_je_jahr[f.jahr].append(_zeile)

    async def _tarife_fuer_stichtag(jahr: int, monat: int) -> dict:
        """Kompletter Tarifsatz des Monats (allgemein + WP/Wallbox).

        Teilt sich `_tarif_cache` mit `baue_finanz_zeile` → keine Extra-Queries.
        """
        stichtag = date(jahr, monat, 1)
        if stichtag not in _tarif_cache:
            _tarif_cache[stichtag] = await lade_tarife_fuer_anlage(
                db, anlage_id, target_date=stichtag
            )
        return _tarif_cache[stichtag]

    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_tarife_fuer_stichtag", "betriebskosten_ges", "bisherige_eauto_ersparnis", "bisherige_ertraege", "ertrag_jahr_ges", "finanz_zeilen", "finanz_zeilen_je_jahr",) if k in _loc}


async def alternativkosten_rueckblick(
    *,
    _tarife_fuer_stichtag,
    e_autos,
    eauto_aggregate,
    emob_pool_ctx,
    historische_inv_daten,
    inv_by_id_hist,
    monatsdaten,
    monatsdaten_dict,
    netzbezug_preis,
    waermepumpen,
    wp_aggregate,
    wp_mit_ersatz,
    wp_netzbezug_preis,
):
    """WP-Ersparnis gegenüber Gas/Öl (Layer-SoT) mit WP-Arbeitspreis je Monat, thermische Mengen je Gerät (N-391/D1) und
    die E-Auto-Ersparnis je Fahrzeug mit Monatspreisen (N-181/F-18, Wallbox-Pool F-17).

    Aus `get_finanz_prognose` Zeilen 656-791 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # Wärmepumpe Alternativkosten-Ersparnis (vs. Gas/Öl) — die „bisherige"-
    # Ersparnis-FORMEL liegt jetzt im SoT-Helper `berechne_wp_alternativkosten_
    # ersparnis` (core/berechnungen/alternativkosten.py), identisch zum HA-Export
    # ([[feedback_aggregations_drift]]). `historische_inv_daten` ist bereits
    # per-Investition auf das aktive Fenster gefiltert (Z. ~948–953), erfüllt
    # also den Helper-Kontrakt; der Monats-Gaspreis (Monatsdaten → per-WP-Default-
    # Fallback im Helper) wird als Perioden-Map durchgereicht.
    gaspreis_by_periode = {
        (md.jahr, md.monat): md.gaspreis_cent_kwh for md in monatsdaten
    }
    # WP-Arbeitspreis je Monat (ADR-002/P8) — deckungsgleich mit dem HA-Export.
    wp_preis_by_periode: dict[tuple[int, int], float] = {}
    for (_inv_id, _p_jahr, _p_monat) in historische_inv_daten:
        _periode = (_p_jahr, _p_monat)
        if _periode not in wp_preis_by_periode:
            _p_tarife = await _tarife_fuer_stichtag(_p_jahr, _p_monat)
            wp_preis_by_periode[_periode] = resolve_strompreis_for_komponente(
                _p_tarife, "waermepumpe", fallback=netzbezug_preis
            )
    bisherige_wp_ersparnis = berechne_wp_alternativkosten_ersparnis(
        waermepumpen,
        historische_inv_daten,
        gaspreis_by_periode,
        wp_preis_by_periode,
        wp_netzbezug_preis,
    )

    # Thermische Wärmemengen pro WP/gesamt — getrennte Concern: nur die
    # WP-PROGNOSE (Z. ~1520) braucht sie (thermisch-gewichtete alter_preis/
    # Wirkungsgrad-Mischung). Bewusst NICHT im Ersparnis-Helper, der reine
    # Aggregat-Σ liefert.
    gesamt_wp_thermisch = 0.0
    for wp in wp_mit_ersatz:
        wp_agg = wp_aggregate[wp.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id == wp.id and wp.ist_aktiv_im_monat(jahr, monat):
                # N-379: dieselbe Lesetuer wie im Layer — sonst traegt die
                # Aussicht eine Waermemenge weiter, die es am Geraet nicht gibt.
                #
                # N-391/D1 (14.09.2026): und derselbe Vorrang „Gesamtwert vor
                # Summanden" wie in `alternativkosten.py` eine Bildschirmseite
                # weiter oben — die beiden Schleifen lesen dieselbe Zeile und
                # duerfen sie nicht verschieden verstehen. Ohne D1 wog eine
                # Waermepumpe mit EINEM Waermemengenzaehler in der thermischen
                # Mischung mit **0 kWh**: `gesamt_wp_thermisch` blieb 0, die
                # WP-Prognose fiel ganz aus (gemessen ueber `get_finanz_prognose`:
                # `wp_alternativ_ersparnis_euro` **0,0** statt **790,0**), und
                # `wp_ersparnis_je_inv` liess das Geraet leer ausgehen.
                thermisch = waerme_gesamt_kwh(
                    daten.get("waerme_kwh"),
                    heizwaerme_kwh(daten),   # N-398
                    get_wp_warmwasser_kwh(daten, wp.parameter),
                )
                gesamt_wp_thermisch += thermisch
                wp_agg["thermisch_kwh"] += thermisch

    # E-Auto Alternativkosten-Ersparnis
    # Ersparnis = Benzin-Kosten - Netzstrom-Kosten
    # Pro Monat + pro E-Auto, damit unterschiedliche Vergleichsverbräuche
    # und Benzinpreis-Defaults pro Fahrzeug korrekt einfließen. Vorher las
    # diese Schleife `eauto_vergleich_l_100km` aus einer last-write-wins-
    # Variable außerhalb — bei mehreren E-Autos wurden alle mit dem Wert
    # des letzten gerechnet.
    #
    # N-181/F-18: die **Rechnung** liegt seit 2026-08-08 im Layer-SoT; diese
    # Schleife sammelt nur noch. Sie war die vierte von vier Formen der
    # Preisauflösung — als einzige monatsgenau, dafür über den **allgemeinen**
    # Tarif statt des Wallbox-Tarifs, den Cockpit und Hub nehmen. Beide Achsen
    # der Abweichung fallen mit dem Umhängen weg.
    _benzin_lookup_aus = {
        k: (md.kraftstoffpreis_euro if md.kraftstoffpreis_euro is not None else None)
        for k, md in monatsdaten_dict.items()
    }
    _strompreis_lookup_aus: dict[tuple[int, int], float] = {}
    for ea in e_autos:
        agg = eauto_aggregate[ea.id]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != ea.id or not ea.ist_aktiv_im_monat(jahr, monat):
                continue
            km = daten.get("km_gefahren", 0) or 0
            # N-199/F-17/N-555: Netz-Anteil DIESES Autos nach dem Entscheid des
            # Monats (Wallbox-Anteil nach km · eigene Heim-Felder · Schätzung · 0).
            _, netz = emob_heimladung_im_monat(
                emob_pool_ctx, inv_id, km, jahr, monat, daten,
            )
            agg["km"] += km
            agg["netz_kwh"] += netz
            # N-555 (§12): externe Ladekosten nach der Topf-Regel, wie Hub und HA-Sensor.
            _, _extern_euro = emob_extern_im_monat(emob_pool_ctx, km, jahr, monat, daten)
            agg["extern_euro"] = agg.get("extern_euro", 0.0) + _extern_euro
            agg["fahrverbrauch_kwh"] += daten.get("verbrauch_kwh", 0) or 0
            if km > 0:
                agg.setdefault("km_monate", []).append((jahr, monat, km))
            if netz > 0:
                agg.setdefault("netz_monate", []).append((jahr, monat, netz))
            # ADR-002/P8: Tarif DES MONATS inkl. Flex-Ø, jetzt über den
            # Wallbox-Tarif (`resolve_strompreis_for_komponente`), damit die
            # Sicht dieselbe Größe bewertet wie Cockpit und Komponenten-Hub.
            if (jahr, monat) not in _strompreis_lookup_aus:
                _m_tarife = await _tarife_fuer_stichtag(jahr, monat)
                _m_allgemein = _m_tarife.get("allgemein")
                _m_wallbox = resolve_strompreis_for_komponente(
                    _m_tarife, "wallbox",
                    fallback=(
                        _m_allgemein.netzbezug_arbeitspreis_cent_kwh
                        if _m_allgemein else NETZBEZUG_DEFAULT_CENT
                    ),
                )
                _strompreis_lookup_aus[(jahr, monat)] = resolve_netzbezug_preis_cent(
                    monatsdaten_dict.get((jahr, monat)), _m_wallbox
                )

    for ea in e_autos:
        agg = eauto_aggregate[ea.id]
        if not agg.get("km_monate"):
            continue
        _erg = berechne_eauto_ersparnis_periode(
            km_pro_monat=agg["km_monate"],
            ladung_netz_kwh_gesamt=agg["netz_kwh"],
            # N-555 (§12, Entscheid Gernot 25.09.2026): externe Ladekosten
            # gehören in die Stromkosten — so rechnen E-Auto-Hub, T-Konto,
            # Cockpit und die HA-Sensoren. Hier stand bis dahin bewusst 0,0
            # („noch nie eingegangen"); die bisherige E-Auto-Ersparnis und
            # damit der ROI-Fortschritt lagen um genau diese Kosten zu hoch.
            ladung_extern_euro_gesamt=agg.get("extern_euro", 0.0),
            wallbox_strompreis_cent=netzbezug_preis,
            eauto_parameter=inv_by_id_hist.get(ea.id).parameter if inv_by_id_hist.get(ea.id) else ea.parameter,
            monats_benzinpreis_lookup=_benzin_lookup_aus,
            fahrverbrauch_kwh_gesamt=agg["fahrverbrauch_kwh"] or None,
            monats_strompreis_lookup=_strompreis_lookup_aus,
            netz_pro_monat=agg.get("netz_monate") or None,
        )
        agg["bisherige_ersparnis"] = _erg.ersparnis_euro
        agg["km_verbrenner"] = _erg.km_verbrenner
    bisherige_eauto_ersparnis = sum(a["bisherige_ersparnis"] for a in eauto_aggregate.values())
    gesamt_km = sum(a["km"] for a in eauto_aggregate.values())
    gesamt_eauto_netz = sum(a["netz_kwh"] for a in eauto_aggregate.values())

    # BKW-Ersparnis: kommt aus `berechne_finanz_aggregat` (bkw_eigenverbrauch_kwh
    # in den Finanz-Zeilen oben) — kein eigener Loop mehr.
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("bisherige_eauto_ersparnis", "bisherige_wp_ersparnis", "gaspreis_by_periode", "gesamt_eauto_netz", "gesamt_km", "gesamt_wp_thermisch", "wp_preis_by_periode",) if k in _loc}


def bisherige_ertraege_summe(
    *,
    alle_investitionen,
    anlage,
    betriebskosten_ges,
    bisherige_eauto_ersparnis,
    bisherige_wp_ersparnis,
    fakten,
    finanz_zeilen,
    finanz_zeilen_je_jahr,
    pv_pro_monat,
):
    """Sonstige Positionen und Erzeuger-Erlöse aus den Monats-Fakten, dienstliche Ladekosten (Layer-SoT), das
    Finanz-Aggregat, anteilige Betriebskosten je Laufzeit (N-228), die rückblickende USt (N-129/N-130) — daraus die
    bisherigen Erträge.

    Aus `get_finanz_prognose` Zeilen 792-914 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # Sonstige Positionen — **aus den Monats-Fakten** (Bauschritt 4 des
    # Wirtschaftlichkeits-Konzepts §8, zugleich eine P10-Bereinigung).
    #
    # ⚑ Bis 2026-08-10 lief hier eine eigene Schleife über
    # `historische_inv_daten` — also ausschließlich über
    # `InvestitionMonatsdaten`. Damit fehlte genau der Erfassungsort, den das
    # Handbuch für „mehrere Komponenten" vorsieht: die Positionen auf der
    # **Monatsdaten-Zeile** (G19-1). Gemessen am 10.08.: eine anlagenweite
    # Ausgabe von 3.000 € bewegte den Kapitaleinsatz dieser Route um **0 €**,
    # während der HA-Sensor sie voll trug (18.000 gegen 15.000) — und eine
    # anlagenweite Förderung war im Fortschritt schlicht unsichtbar.
    #
    # `f.sonstiges` fasst beide Orte zusammen (IMD **typ-unabhängig**, #310,
    # plus die Basis-Positionen der Monatsdaten-Zeile) und bringt den
    # Laufzeit-Filter (#236) bereits mit — die Schleife hatte ihn von Hand
    # nachgebaut.
    #
    # F-19 + Bauschritt 7: beide Seiten daneben getrennt — sie gehen in den
    # Kapitaleinsatz (Ausgaben erhöhend, Erträge mindernd). Die dienstlichen
    # Ladekosten unten sind laufender Aufwand und gehören ausdrücklich nicht in
    # den Nenner (SoT `berechnungen/kapitalrechnung.py`).
    bisherige_sonstige_netto = sum(f.sonstiges.netto_euro for f in fakten)
    # Konzept §9 Weg 2: gepflegte Erlöse von Erzeugern mit eigenem
    # Einspeisetarif. Eigener Summand — er bewertet nicht den Anlagenzähler.
    bisherige_erzeuger_erloes = sum(f.sonstiges.einspeise_erloes_euro for f in fakten)
    bisherige_sonstige_ausgaben = sum(f.sonstiges.ausgaben_euro for f in fakten)
    bisherige_sonstige_ertraege = sum(f.sonstiges.ertraege_euro for f in fakten)

    # Dienstliche E-Auto/Wallbox-Ladekosten abziehen — Mengen aus den
    # Monats-Fakten (P10: Dienstwagen-Filter, Laufzeit-Fenster und PV/Netz-Split
    # löst die Schicht auf), Bewertung über den Layer-SoT (ADR-001).
    # Bis 2026-07-31 hat dieser Block beides selbst getan und dabei ZWEI Preise
    # anders gewählt als das Cockpit: den Netzanteil zum **allgemeinen**
    # Arbeitspreis statt zum Wallbox-Tarif (N-12) und den PV-Anteil zur
    # Einspeisevergütung statt zum Netzbezugspreis (N-18). Das Cockpit ist der
    # Kanon (Gernot 2026-07-31), hier läuft jetzt dieselbe Formel.
    bisherige_dienstlich_ladekosten = berechne_dienstliche_ladekosten(
        DienstlicheLadungZeile(
            ladung_pv_kwh=f.emob.dienstlich_ladung_pv_kwh,
            ladung_netz_kwh=f.emob.dienstlich_ladung_netz_kwh,
            netzbezug_preis_cent=f.tarif.netzbezug_preis_cent,
            wallbox_preis_cent=f.tarif.wallbox_preis_effektiv_cent,
        )
        for f in fakten
    ).gesamt_euro
    bisherige_sonstige_netto -= bisherige_dienstlich_ladekosten

    # Finanz-Aggregat (Einspeise-Erlös §51 + EV- + BKW-Ersparnis + Sonstige)
    # + aussichten-spezifische Alternativkosten-Ersparnisse (WP, E-Auto).
    _finanz = berechne_finanz_aggregat(
        finanz_zeilen, sonstige_netto_euro=bisherige_sonstige_netto,
        erzeuger_erloes_euro=bisherige_erzeuger_erloes
    )
    bisherige_bkw_ersparnis = _finanz.bkw_ersparnis_euro
    bisherige_ertraege = (
        _finanz.netto_ertrag_euro + bisherige_wp_ersparnis + bisherige_eauto_ersparnis
    )

    # Anteilige Betriebskosten für den historischen Zeitraum abziehen — je
    # Komponente über IHRE Laufzeit (N-228).
    #
    # ⚑ Bis 2026-08-10 stand hier `betriebskosten_ges × Monate / 12`: die
    # anlagenweite Jahressumme über den GANZEN Beobachtungszeitraum, also auch
    # über Monate, in denen eine Komponente noch nicht angeschafft oder bereits
    # stillgelegt war. Eine 2024 gekaufte Wärmepumpe zahlte damit Versicherung
    # ab 2023. **Am Dev-Bestand gemessen: 1.291,67 € statt 725,00 € — 566,67 €
    # zu viel**, allein aus zwei Komponenten mit gepflegten Betriebskosten.
    #
    # Die Größe wird **einmal** gebildet und zweimal benutzt: hier als Summe und
    # unten in der Zerlegung je Zeile (Bauschritt 5). Genau deshalb ließ sich
    # N-228 nicht abtrennen — mit dem alten Abzug trug der Rest der Zerlegung
    # die Differenz systematisch, und ein Rest, der eine bekannte Ursache hat,
    # ist keine Restgröße mehr, sondern ein verstecktes Vorzeichen.
    _monate_beobachtet = {(f.jahr, f.monat) for f in fakten}
    betriebskosten_hist_je_inv: dict[int, float] = {}
    for _inv in alle_investitionen:
        _bk = _inv.betriebskosten_jahr or 0
        if not _bk:
            continue
        _aktive = sum(
            1 for (_j, _m) in _monate_beobachtet if _inv.ist_aktiv_im_monat(_j, _m)
        )
        if _aktive:
            betriebskosten_hist_je_inv[_inv.id] = _bk * _aktive / 12
    betriebskosten_hist = sum(betriebskosten_hist_je_inv.values())
    bisherige_ertraege -= betriebskosten_hist

    # USt auf Eigenverbrauch bei Regelbesteuerung — auch RÜCKBLICKEND. Sie stand
    # bisher nur in der Jahres-Prognose (`jahres_netto_ertrag`, weiter unten);
    # die bisherigen Erträge trugen sie nicht, obwohl der Cockpit-Netto-Ertrag
    # sie abzieht. Bei Regelbesteuerung lagen ROI-Fortschritt und Amortisation
    # damit um den USt-Betrag zu günstig (#326-Inventur, Dimension 2).
    #
    # N-130: Der Rückblick geht IMMER über den gesamten bisherigen Zeitraum —
    # er war damit von der Zeitraum-Kollaps-Klasse durchgehend betroffen, nicht
    # nur bei gesetztem Filter. `sum(pv_pro_monat.values())` stand als
    # „Jahres-Erzeugung" gegen eine Ein-Jahres-AfA. N-129: Bemessungsgrundlage
    # über den Layer-SoT (Mehrkosten) statt der Vollkosten.
    _pv_je_jahr: dict[int, float] = defaultdict(float)
    for (_j, _m), _pv in pv_pro_monat.items():
        _pv_je_jahr[_j] += _pv
    # Bauschritt 5: als eigene Größe, weil die Zerlegung sie braucht — die USt
    # hängt am Eigenverbrauch und damit an der ERZEUGUNGS-Seite, sie muss also
    # denselben Weg gehen wie Einspeise-Erlös und EV-Ersparnis. Vorher stand
    # hier ein direktes `-=`; der Betrag war danach nicht mehr greifbar.
    bisherige_ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[
            UstJahresanteil(
                jahr=_j,
                eigenverbrauch_kwh=berechne_finanz_aggregat(
                    finanz_zeilen_je_jahr[_j]
                ).eigenverbrauch_kwh,
                pv_kwh=_pv_je_jahr.get(_j, 0.0),
                monate=len(finanz_zeilen_je_jahr[_j]),
            )
            for _j in sorted(finanz_zeilen_je_jahr)
        ],
        bemessungsgrundlage_euro=bemessungsgrundlage_aus_investitionen(alle_investitionen),
        betriebskosten_jahr_euro=betriebskosten_ges,
    )
    bisherige_ertraege -= bisherige_ust_eigenverbrauch
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_finanz", "betriebskosten_hist_je_inv", "bisherige_bkw_ersparnis", "bisherige_dienstlich_ladekosten", "bisherige_ertraege", "bisherige_sonstige_ausgaben", "bisherige_sonstige_ertraege", "bisherige_ust_eigenverbrauch",) if k in _loc}

