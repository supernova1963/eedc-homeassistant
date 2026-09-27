"""Finanz-Prognose — die Hochrechnung nach vorn: Monatswerte aus PVGIS/TMY mit historischer EV-Quote oder
Komponentenmodell (N-277-Normierung des WP-PV-Anteils), die Alternativkosten-Ersparnis pro Jahr für Wärmepumpe (thermisch
gewichtet, Strom voll belastet S1b/N-459) und E-Auto (km-gewichtet, PHEV #331), die WP-PV-Größen je Gerät (N-354), BKW
und sonstige laufende Posten, der Jahres-Netto-Ertrag abzüglich USt.
"""
# Vorlage 7b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `aussichten/finanzen.py::get_finanz_prognose` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-aussichten.py` (alte gegen neue Antworten, bitgleich).

from typing import Optional
from backend.core.berechnungen import einspeise_erloes_euro, gas_kosten_altanlage
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.utils.investition_value import param_zahl
from backend.core.investition_parameter import PARAM_WAERMEPUMPE, PARAM_WAERMEPUMPE_DEFAULTS
from backend.services.wetter.pvgis import get_pvgis_tmy_defaults
from backend.api.routes.aussichten.basis import MONATSNAMEN
from backend.api.routes.aussichten.schemas import FinanzPrognoseMonatSchema
from datetime import date


def monatsprognose(
    *,
    anlage,
    anlagenleistung_kwp,
    avg_hist_ev_quote,
    basis_ev_quote,
    e_autos,
    eauto_pv_monat,
    einspeiseverguetung,
    hist_ev_quoten,
    monate,
    netzbezug_preis,
    pvgis_monatswerte,
    speicher,
    speicher_ev_erhohung_monat,
    v2h_beitrag_monat,
    waermepumpen,
    wp_mit_ersatz,
    wp_strom_mit_ersatz_monat_avg,
    wp_strom_monat_avg,
):
    """Je Prognosemonat PV-Erzeugung, Eigenverbrauch (historische Quote oder Komponentenmodell), Einspeisung, Erlös und
    Ersparnis mit dem heutigen Tarif; die Jahres-Akkumulatoren und die Lesetür `_gepflegter_pv_anteil` (N-277/N-354).

    Aus `get_finanz_prognose` Zeilen 915-1107 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # MONATSPROGNOSEN ERSTELLEN
    # =====================================================================
    heute = date.today()
    start_monat = heute.month
    start_jahr = heute.year
    monatswerte = []

    jahres_erzeugung = 0.0
    jahres_eigenverbrauch = 0.0
    jahres_einspeisung = 0.0
    jahres_einspeise_erloes = 0.0
    jahres_ev_ersparnis = 0.0
    jahres_speicher_beitrag = 0.0
    jahres_v2h_beitrag = 0.0
    jahres_wp_verbrauch = 0.0
    #: N-279: dieselbe saisonale Hochrechnung, nur über `wp_mit_ersatz`.
    #: Bewusst parallel mitgeführt statt aus `jahres_wp_verbrauch` skaliert —
    #: eine abgeleitete Zahl wäre eine zweite Bildungsvorschrift für dieselbe
    #: Größe (P4) und würde bei einer künftigen Änderung der Saisonfaktoren
    #: stillschweigend auseinanderlaufen.
    jahres_wp_verbrauch_mit_ersatz = 0.0
    jahres_eauto_pv = 0.0

    # Saisonale Faktoren für WP (Heizperiode)
    WP_SAISON_FAKTOREN = {
        1: 1.8, 2: 1.6, 3: 1.3, 4: 0.8, 5: 0.4, 6: 0.2,
        7: 0.2, 8: 0.2, 9: 0.4, 10: 0.8, 11: 1.3, 12: 1.7
    }

    def _pv_kwh_im_kalendermonat(monat: int) -> float:
        """PVGIS-Wert des Monats, sonst TMY-Schätzung — EINE Vorschrift.

        N-277: Die Monatsschleife unten brauchte diese Zahl schon immer; seit
        der Normierung braucht sie auch der Vorlauf. Als Funktion statt zweimal
        ausgeschrieben, sonst laufen die beiden bei der nächsten Änderung
        auseinander (P4).
        """
        pv = pvgis_monatswerte.get(monat, 0)
        if pv <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude if anlage.latitude else 48.0)
            pv = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85
        return pv

    def _pv_faktor(monat: int) -> float:
        """Saisonale Skalierung: Monatsertrag gegen den Monats-Ø des Jahres."""
        if not pvgis_monatswerte:
            return 1.0
        return _pv_kwh_im_kalendermonat(monat) / (sum(pvgis_monatswerte.values()) / 12)

    # ── N-277: der gepflegte PV-Anteil der Wärmepumpe(n) ────────────────────
    #
    # Hier stand bis 2026-08-30 eine feste `0.5`, und das Feld „PV-Anteil (%) —
    # Anteil des WP-Stroms aus PV" wurde nirgends gelesen.
    #
    # ⚠ DIE ZAHL WIRD NICHT EINFACH ERSETZT, und das ist der Kern: Die `0.5` war
    # **kein Jahresanteil**, sondern ein Basiswert VOR der Dämpfung
    # `* (pv_faktor ** 0.5)`. Effektiv lieferte sie rund 38 % im Jahresmittel —
    # die Winterdämpfung, die eine Wärmepumpe braucht, war also bereits da
    # (Januar ~27 %, Juli ~65 %). Wer `0.5` stumpf durch den gepflegten Wert
    # ersetzt, bekommt bei gepflegten 30 % effektiv 23 %: der Anwender pflegt
    # 30 und sieht 23.
    #
    # ⇒ Die saisonale FORM bleibt, die JAHRESSUMME wird auf den gepflegten Wert
    # normiert. Damit bedeutet das Formularfeld, was draufsteht.
    #
    # ⚠ Was das Modell weiterhin nicht kann: Es bildet das PV-ANGEBOT ab, nicht
    # die GLEICHZEITIGKEIT (die WP läuft nachts und morgens, die PV mittags).
    # Der reale Deckungsgrad liegt darunter. Ein Gleichzeitigkeitsmodell
    # bräuchte ein Lastprofil — das es in genau diesem Fallback-Fall (keine
    # historische EV-Quote) per Definition nicht gibt.
    def _gepflegter_pv_anteil(wp) -> Optional[float]:
        """Der gepflegte PV-Anteil **eines** Geräts als Bruch — die EINE Lesetür.

        ⭐ **Sie steht seit N-354 (13.09.2026) als Funktion da, weil sie zwei
        Leser hat:** diesen Fallback hier und die Komponenten-Beiträge weiter
        unten. Zweimal `.get(PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"], …)` wäre
        genau die Bauform, gegen die dieser Fund gebaut ist — dieselbe Größe,
        zwei Bildungsvorschriften in einer Datei.

        ⚠ ``None`` heißt **hier** „nicht gepflegt" und wird von den beiden
        Lesern unterschiedlich behandelt; die Entscheidung gehört zum Leser,
        nicht zur Lesetür (s. dort).
        """
        # N-571, Ausnahme-Bauform (s. `param_zahl`-Docstring): DREI Wege.
        # Fehlender Key = nie gepflegt ⇒ Default 30; vorhandener Key mit
        # `null` ODER `""` (geleertes Formularfeld) = ausdrücklich
        # zurückgenommen ⇒ None, das Gerät fällt aus dem Mittel (N-277 —
        # gemessenes Verhalten, nicht im Vorbeigehen ändern). Ein pauschaler
        # Default machte aus der Rücknahme wieder 30 und bewegte den
        # Eigenverbrauchs-Fallback; `float("")` warf vorher ValueError/500.
        params = wp.parameter or {}
        if PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"] not in params:
            roh = PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"]
        else:
            roh = param_zahl(params, PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"])
        return float(roh) / 100.0 if roh is not None else None

    if waermepumpen:
        # Mehrere Wärmepumpen: Mittelwert. `wp_strom_monat_avg` ist ohnehin
        # anlagenweit, eine Gewichtung je Gerät hätte hier keinen Nenner.
        #
        # ⚠ Ein Gerät mit ausdrücklich `None` fällt aus dem **Mittel** heraus —
        # der Wert der übrigen gilt dann für alle. Das ist gemessenes Verhalten
        # aus N-277 und speist den Eigenverbrauchs-Fallback, also eine wirksame
        # Zahl: nicht im Vorbeigehen ändern.
        _anteile = [
            a for a in (_gepflegter_pv_anteil(wp) for wp in waermepumpen)
            if a is not None
        ]
        wp_pv_anteil = (sum(_anteile) / len(_anteile)) if _anteile else 0.0
    else:
        wp_pv_anteil = 0.0

    # Normierung über die ZWÖLF KALENDERMONATE, nicht über den Prognosehorizont
    # — sonst hinge der Jahresanteil an der Länge der Anfrage.
    _saison_summe = sum(WP_SAISON_FAKTOREN.values())
    _gewicht_summe = sum(
        WP_SAISON_FAKTOREN[m] * (_pv_faktor(m) ** 0.5) for m in range(1, 13)
    )
    wp_pv_norm = (_saison_summe / _gewicht_summe) if _gewicht_summe > 0 else 1.0

    for i in range(monate):
        monat = ((start_monat - 1 + i) % 12) + 1
        jahr = start_jahr + ((start_monat - 1 + i) // 12)

        # PV-Erzeugung aus PVGIS oder Schätzung
        pv_kwh = pvgis_monatswerte.get(monat, 0)
        if pv_kwh <= 0:
            tmy = get_pvgis_tmy_defaults(monat, anlage.latitude if anlage.latitude else 48.0)
            pv_kwh = tmy["globalstrahlung_kwh_m2"] * anlagenleistung_kwp * 0.85

        # PV-Faktor für saisonale Skalierung der Anzeige-Felder
        pv_faktor = pv_kwh / (sum(pvgis_monatswerte.values()) / 12) if pvgis_monatswerte else 1.0

        # Eigenverbrauch: Historische Quote nutzen, Fallback auf Komponentenmodell
        if monat in hist_ev_quoten:
            # Historische EV-Quote für diesen Kalendermonat vorhanden
            eigenverbrauch_kwh = pv_kwh * hist_ev_quoten[monat]
        elif avg_hist_ev_quote is not None:
            # Kein hist. Datum für diesen Monat → Durchschnitt der vorhandenen
            eigenverbrauch_kwh = pv_kwh * avg_hist_ev_quote
        else:
            # Gar keine historischen Daten → Komponentenmodell als Fallback
            basis_ev = pv_kwh * basis_ev_quote
            speicher_fallback = speicher_ev_erhohung_monat * pv_faktor if speicher else 0
            v2h_fallback = v2h_beitrag_monat if e_autos else 0
            wp_saison_fb = WP_SAISON_FAKTOREN.get(monat, 1.0)
            wp_verbrauch_fb = wp_strom_monat_avg * wp_saison_fb if waermepumpen else 0
            # N-277: gepflegter Anteil × Saisonform × Normierung (s. Vorlauf oben)
            wp_pv_fb = wp_verbrauch_fb * wp_pv_anteil * (pv_faktor ** 0.5) * wp_pv_norm
            eigenverbrauch_kwh = basis_ev + speicher_fallback + v2h_fallback + wp_pv_fb

        eigenverbrauch_kwh = min(eigenverbrauch_kwh, pv_kwh)  # Kann nicht mehr als erzeugt
        einspeisung_kwh = pv_kwh - eigenverbrauch_kwh

        # Komponentenbeiträge für Anzeige (informativ, beeinflusst EV nicht)
        speicher_beitrag = speicher_ev_erhohung_monat * pv_faktor if speicher else 0
        v2h_beitrag = v2h_beitrag_monat if e_autos else 0
        eauto_pv = eauto_pv_monat * pv_faktor if e_autos else 0
        wp_saison = WP_SAISON_FAKTOREN.get(monat, 1.0)
        wp_verbrauch = wp_strom_monat_avg * wp_saison if waermepumpen else 0
        wp_verbrauch_mit_ersatz = (
            wp_strom_mit_ersatz_monat_avg * wp_saison if wp_mit_ersatz else 0
        )

        # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None — Prognose-
        # Monate haben keine Negativpreis-Historie (der historische Pfad oben
        # bei den Monatsdaten nutzt get_neg_preis_einspeisung_monat).
        einspeise_erloes = einspeise_erloes_euro(
            einspeisung_kwh, None, einspeiseverguetung
        ).erloes_euro
        ev_ersparnis = eigenverbrauch_kwh * netzbezug_preis / 100
        netto_ertrag = einspeise_erloes + ev_ersparnis

        monatswerte.append(FinanzPrognoseMonatSchema(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            pv_erzeugung_kwh=round(pv_kwh, 1),
            eigenverbrauch_kwh=round(eigenverbrauch_kwh, 1),
            einspeisung_kwh=round(einspeisung_kwh, 1),
            einspeise_erloes_euro=round(einspeise_erloes, 2),
            ev_ersparnis_euro=round(ev_ersparnis, 2),
            netto_ertrag_euro=round(netto_ertrag, 2),
            speicher_beitrag_kwh=round(speicher_beitrag, 1),
            v2h_beitrag_kwh=round(v2h_beitrag, 1),
            wp_verbrauch_kwh=round(wp_verbrauch, 1),
        ))

        jahres_erzeugung += pv_kwh
        jahres_eigenverbrauch += eigenverbrauch_kwh
        jahres_einspeisung += einspeisung_kwh
        jahres_einspeise_erloes += einspeise_erloes
        jahres_ev_ersparnis += ev_ersparnis
        jahres_speicher_beitrag += speicher_beitrag
        jahres_v2h_beitrag += v2h_beitrag
        jahres_wp_verbrauch += wp_verbrauch
        jahres_wp_verbrauch_mit_ersatz += wp_verbrauch_mit_ersatz
        jahres_eauto_pv += eauto_pv
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_gepflegter_pv_anteil", "heute", "jahres_eauto_pv", "jahres_eigenverbrauch", "jahres_einspeise_erloes", "jahres_einspeisung", "jahres_erzeugung", "jahres_ev_ersparnis", "jahres_speicher_beitrag", "jahres_v2h_beitrag", "jahres_wp_verbrauch", "jahres_wp_verbrauch_mit_ersatz", "monatswerte", "start_jahr", "start_monat",) if k in _loc}


def jahres_alternativkosten(
    *,
    _gepflegter_pv_anteil,
    alle_investitionen,
    anlage,
    anzahl_monate_hist,
    balkonkraftwerke,
    betriebskosten_ges,
    bisherige_bkw_ersparnis,
    bisherige_dienstlich_ladekosten,
    e_autos,
    eauto_aggregate,
    ertrag_jahr_ges,
    gesamt_eauto_netz,
    gesamt_eauto_pv,
    gesamt_km,
    gesamt_wp_strom,
    gesamt_wp_thermisch,
    heute,
    jahres_eauto_pv,
    jahres_eigenverbrauch,
    jahres_einspeise_erloes,
    jahres_erzeugung,
    jahres_ev_ersparnis,
    jahres_wp_verbrauch,
    jahres_wp_verbrauch_mit_ersatz,
    monatsdaten,
    netzbezug_preis,
    waermepumpen,
    wp_aggregate,
    wp_alternativ_zusatzkosten_jahr,
    wp_mit_ersatz,
    wp_netzbezug_preis,
    wp_strom_pro_inv,
):
    """WP-Ersparnis pro Jahr (thermisch gewichtet, Strom voll belastet), WP-PV-kWh und -Ersparnis je Gerät (N-354),
    E-Auto-Ersparnis pro Jahr und je Fahrzeug, BKW- und sonstige laufende Posten, Jahres-Netto-Ertrag abzüglich USt.

    Aus `get_finanz_prognose` Zeilen 1108-1351 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # ALTERNATIVKOSTEN-EINSPARUNGEN PRO JAHR (für Prognose)
    # =====================================================================

    # Wärmepumpe: Ersparnis gegenüber Gas/Öl
    # Durchschnittswerte aus historischen Daten hochrechnen.
    # Aggregat-Werte für die Saisonalprognose: thermisch-gewichteter
    # Durchschnitt über die WPs. Bei genau einer WP = deren Wert (kein
    # Verhaltens-Unterschied). Bei mehreren WPs mit unterschiedlichen
    # Energieträgern (z. B. Gas + Öl) mathematisch saubere Mischung statt
    # last-write-wins.
    jahres_wp_ersparnis = 0.0
    if wp_mit_ersatz and gesamt_wp_thermisch > 0 and anzahl_monate_hist > 0:
        # Thermische Energie pro Jahr (hochgerechnet)
        wp_thermisch_jahr = gesamt_wp_thermisch / anzahl_monate_hist * 12
        # thermisch-gewichtete Aggregat-Werte
        wp_alter_preis_cent_agg = sum(
            a["thermisch_kwh"] * a["alter_preis_cent"] for a in wp_aggregate.values()
        ) / gesamt_wp_thermisch
        wp_alter_wirkungsgrad_agg = sum(
            a["thermisch_kwh"] * a["alter_wirkungsgrad"] for a in wp_aggregate.values()
        ) / gesamt_wp_thermisch
        # Prognose-Gaspreis: Ø der historischen Monatspreise, Fallback Aggregat
        hist_gaspreise = [
            md.gaspreis_cent_kwh for md in monatsdaten
            if md.gaspreis_cent_kwh is not None
        ]
        prognose_gaspreis = (
            sum(hist_gaspreise) / len(hist_gaspreise)
            if hist_gaspreise
            else wp_alter_preis_cent_agg
        )
        # Was es mit Gas kosten würde (Energiepreis + fixe Zusatzkosten)
        gas_kosten_jahr = (
            gas_kosten_altanlage(
                wp_thermisch_jahr, wp_alter_wirkungsgrad_agg, prognose_gaspreis
            )
            + wp_alternativ_zusatzkosten_jahr
        )
        # WP-Stromkosten pro Jahr — der GANZE Strom zum Netztarif.
        #
        # ⛔ **SOLL Wärme/Klima S1b (Entscheid 13.09.2026, N-459).** Bis hierher
        # stand ein fester PV-Abschlag von 50 % (`WP_PV_ANTEIL_DEFAULT`) und
        # ließ 206,53 €/Jahr der Demo-Anlage unbelastet. Der Abzug war eine
        # **Doppelzählung**: dieselbe Kilowattstunde trägt schon auf der
        # PV-Seite — `jahres_ev_ersparnis` bewertet den ganzen Eigenverbrauch
        # zum Netzpreis, und der WP-Strom hinter dem Hauszähler steckt darin
        # (im Fallback-Zweig sogar ausdrücklich als Summand, N-277). Ein Fluss
        # trägt genau einmal zum Finanz-Netto bei (ADR-002/P9).
        # ⚠ Der am Gerät gepflegte „PV-Anteil (%)" gehört NICHT hierher: er
        # beantwortet eine Mengenfrage (Eigenverbrauchs-Fallback N-277, Zuordnung
        # je Gerät N-354), keine Preisfrage. Wer ihn hier einsetzt, halbiert die
        # Doppelzählung, statt sie zu beseitigen.
        # N-279: dieselbe Grundmenge wie `gas_kosten_jahr` darüber — also NUR die
        # Geräte mit Ersatz. `jahres_wp_verbrauch` (alle WPs) stand hier bis
        # 2026-08-29 und machte die Differenz unsymmetrisch: der Zähler zählte
        # die Wärme der ersetzenden Geräte, der Abzug den Strom ALLER. Eine
        # Wärmepumpe im Neubau senkte damit die ausgewiesene Ersparnis der
        # zweiten, die tatsächlich eine Gasheizung ersetzt hat.
        wp_strom_jahr = jahres_wp_verbrauch_mit_ersatz
        wp_stromkosten_netz_jahr = wp_strom_jahr * wp_netzbezug_preis / 100
        # Netto-Ersparnis
        jahres_wp_ersparnis = gas_kosten_jahr - wp_stromkosten_netz_jahr

    # ── N-354: die zwei WP-PV-Größen, EINMAL gebildet und je Gerät ──────────
    #
    # ⛔ **Bis zum 13.09.2026 standen sie zweimal verschieden in dieser Datei:**
    # `jahres_wp_verbrauch * 0.5` in den Komponenten-Beiträgen und dieselbe feste
    # 50-%-Konstante im Response-Feld — obwohl das Formularfeld „PV-Anteil (%)"
    # am Gerät gepflegt wird, und beide **je Gerät mit dem ANLAGEN-Aggregat**:
    # bei zwei Wärmepumpen stand derselbe volle Betrag zweimal in der Liste.
    #
    # ⭐ **Diese zwei Größen sind seit S1b die EINZIGEN Leser des Felds** (dazu
    # der Eigenverbrauchs-Fallback oben) — es beantwortet eine Mengenfrage. Die
    # Geld- und CO₂-Formeln belasten den WP-Strom voll und lesen es nicht.
    #
    # ⭐ **Die Lesetür ist dieselbe wie beim Eigenverbrauchs-Fallback oben**
    # (`_gepflegter_pv_anteil`) — der Muster-Commit ist `029533d1` (N-277).
    # ⚠ **Der RECHENWEG von dort ist NICHT übertragbar** und wird bewusst nicht
    # kopiert: Der Fallback oben normiert über die zwölf Kalendermonate, weil
    # er eine Saisonform trägt. Hier steht ein Jahreswert ohne Saisonform; eine
    # Normierung hätte nichts zu normieren.
    #
    # ⚠ **`None` heißt hier „nicht gepflegt" ⇒ Default**, anders als im Mittel
    # oben, wo ein solches Gerät herausfällt. Je Gerät gibt es niemanden, an
    # dessen Wert man sich anlehnen könnte — der Default ist die einzige
    # Auskunft, die bleibt.
    #
    # ⭐ **Der eigene Nenner je Gerät ist sein gemessener Stromanteil**
    # (`wp_strom_pro_inv`, dieselbe Quelle wie `gesamt_wp_strom`). Damit gilt
    # Σ Geräte == Anlage exakt, ohne eine zweite Hochrechnung neben der
    # saisonalen Schleife zu erfinden. Ohne Historie ist `gesamt_wp_strom` 0 —
    # dann ist auch `jahres_wp_verbrauch` 0, und beide Seiten sind 0.
    wp_pv_kwh_je_inv: dict[int, float] = {}
    for _wp in waermepumpen:
        _anteil = _gepflegter_pv_anteil(_wp)
        if _anteil is None:
            _anteil = float(PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"]) / 100.0
        _geraete_anteil = (
            wp_strom_pro_inv.get(_wp.id, 0.0) / gesamt_wp_strom
            if gesamt_wp_strom > 0 else 0.0
        )
        wp_pv_kwh_je_inv[_wp.id] = jahres_wp_verbrauch * _geraete_anteil * _anteil
    wp_pv_kwh_total = sum(wp_pv_kwh_je_inv.values())

    #: Die Alternativkosten-Ersparnis je Gerät — thermisch gewichtet, wie die
    #: Aggregate, aus denen `jahres_wp_ersparnis` entsteht. **Nur Geräte mit
    #: Ersatz**: Eine Wärmepumpe im Neubau hat nichts ersetzt und bekam bis
    #: hierher trotzdem die volle Ersparnis der Anlage in die Liste geschrieben.
    wp_ersparnis_je_inv: dict[int, float] = {}
    if gesamt_wp_thermisch > 0:
        for _wp in wp_mit_ersatz:
            wp_ersparnis_je_inv[_wp.id] = jahres_wp_ersparnis * (
                wp_aggregate[_wp.id]["thermisch_kwh"] / gesamt_wp_thermisch
            )

    # E-Auto: Ersparnis gegenüber Benzin.
    # Aggregat-Werte für die saisonal-skalierte Jahresprognose: km-gewichteter
    # Durchschnitt von `vergleich_l_100km` und `benzinpreis_default` über die
    # E-Autos. Bei einem einzigen E-Auto = dessen Wert (kein Verhaltens-
    # Unterschied). Bei mehreren = mathematisch saubere Mischung statt der
    # vorherigen last-write-wins-Variable.
    jahres_eauto_km_ersparnis = 0.0
    if e_autos and gesamt_km > 0 and anzahl_monate_hist > 0:
        # km pro Jahr (hochgerechnet)
        km_jahr = gesamt_km / anzahl_monate_hist * 12
        # km-gewichtete Aggregat-Werte über die E-Autos
        eauto_vergleich_l_100km_agg = sum(
            a["km"] * a["vergleich_l_100km"] for a in eauto_aggregate.values()
        ) / gesamt_km
        eauto_benzinpreis_default_agg = sum(
            a["km"] * a["benzinpreis_default"] for a in eauto_aggregate.values()
        ) / gesamt_km
        # Prognose-Benzinpreis: Ø der historischen Monatspreise, Fallback Aggregat
        hist_kraftstoffpreise = [
            md.kraftstoffpreis_euro for md in monatsdaten
            if md.kraftstoffpreis_euro is not None
        ]
        prognose_benzinpreis = (
            sum(hist_kraftstoffpreise) / len(hist_kraftstoffpreise)
            if hist_kraftstoffpreise
            else eauto_benzinpreis_default_agg
        )
        # Was es mit Benzin kosten würde
        benzin_liter_jahr = km_jahr / 100 * eauto_vergleich_l_100km_agg
        benzin_kosten_jahr = benzin_liter_jahr * prognose_benzinpreis
        # E-Auto Netz-Stromkosten pro Jahr (PV-Ladung ist in EV-Ersparnis)
        netz_anteil = gesamt_eauto_netz / (gesamt_eauto_pv + gesamt_eauto_netz) if (gesamt_eauto_pv + gesamt_eauto_netz) > 0 else 0.5
        eauto_netz_kwh_jahr = (jahres_eauto_pv / (1 - netz_anteil) * netz_anteil) if netz_anteil < 1 else 0
        eauto_stromkosten_netz_jahr = eauto_netz_kwh_jahr * netzbezug_preis / 100
        # #331: die fortgeschriebene Tankrechnung der Plug-in-Hybride. Der
        # Verbrenner-Anteil je Fahrzeug steht aus der Historie oben fest und
        # wird mit derselben Quote hochgerechnet wie die Kilometer.
        fossile_kosten_jahr = 0.0
        for _agg in eauto_aggregate.values():
            if _agg["eigener_l_100km"] is None or _agg["km"] <= 0:
                continue
            _km_v_jahr = _agg.get("km_verbrenner", 0.0) / anzahl_monate_hist * 12
            _agg["fossile_kosten_jahr"] = (
                _km_v_jahr / 100 * _agg["eigener_l_100km"] * prognose_benzinpreis
            )
            fossile_kosten_jahr += _agg["fossile_kosten_jahr"]
        # Netto-Ersparnis
        jahres_eauto_km_ersparnis = (
            benzin_kosten_jahr - eauto_stromkosten_netz_jahr - fossile_kosten_jahr
        )
        # Per-E-Auto-Aufschlüsselung (für Komponenten-Anzeige).
        # Benzin-Kostenteil: pro E-Auto mit dessen `vergleich_l_100km` exakt.
        # Strom-Kostenteil: km-anteilig aus dem Aggregat (Vereinfachung — der
        # eigentliche Netz-Anteil wird auf Aggregat-Ebene aus PV-Quote
        # abgeleitet, eine saubere Pro-EA-Saisonprognose wäre ein eigener
        # Refactor). Die Summe der Pro-EA-Ersparnisse stimmt mit dem Aggregat
        # überein.
        for ea in e_autos:
            agg = eauto_aggregate[ea.id]
            if agg["km"] <= 0:
                agg["jahres_ersparnis"] = 0.0
                continue
            km_jahr_ea = agg["km"] / anzahl_monate_hist * 12
            benzin_kosten_jahr_ea = km_jahr_ea / 100 * agg["vergleich_l_100km"] * prognose_benzinpreis
            stromkosten_ea = eauto_stromkosten_netz_jahr * (agg["km"] / gesamt_km)
            # #331: derselbe Posten wie im Aggregat oben — sonst wäre die Summe
            # der Pro-Fahrzeug-Zeilen nicht mehr das Aggregat.
            agg["jahres_ersparnis"] = (
                benzin_kosten_jahr_ea - stromkosten_ea
                - agg.get("fossile_kosten_jahr", 0.0)
            )

    # BKW Jahres-Ersparnis (aus historischem Durchschnitt hochgerechnet).
    # P9-konform 0, sobald das BKW seine Erzeugung mitschreibt: dann steckt es
    # in `gesamt_pv` und damit in `jahres_ev_ersparnis` — der Posten trägt nur
    # noch die Anlagen, deren BKW ausschließlich Eigenverbrauch führt.
    jahres_bkw_ersparnis = 0.0
    if balkonkraftwerke and anzahl_monate_hist > 0 and bisherige_bkw_ersparnis > 0:
        jahres_bkw_ersparnis = bisherige_bkw_ersparnis / anzahl_monate_hist * 12

    # F-19: die sonstigen AUSGABEN werden nicht mehr in die Zukunft
    # hochgerechnet. Das war die unangenehmste der vier Rechenstellen — eine
    # einmalige Reparatur belastete hier **jedes künftige Prognosejahr**, und
    # zwar dauerhaft: der historische Schnitt trug sie für immer weiter. Sie
    # gehört einmalig in den Kapitaleinsatz, nicht jährlich in den Ertrag.
    #
    # §8/3 (2026-08-10): jetzt gilt dasselbe für die sonstigen **Erträge**.
    # Eine Position im Monatsabschluss ist per FORM einmal geflossen (§2/2) —
    # sie in die Zukunft zu verlängern unterstellt eine Wiederholung, die
    # niemand behauptet hat. Der Ort für einen *wiederkehrenden* Ertrag ist
    # seit §8/1 das Feld „Ertrag/Jahr" an der Investition (`ertrag_jahr_ges`
    # oben); vor diesem Schritt gab es ihn nicht, und deshalb musste er in
    # dieser Reihenfolge gefahren werden.
    #
    # ⚠ Was hier bleibt: **nur** die dienstlichen Ladekosten. Sie stecken als
    # Abzug in `bisherige_sonstige_netto`, sind aber keine gepflegte Position,
    # sondern laufender Aufwand, den der Code selbst rechnet — er fällt jeden
    # Monat wieder an. Ein Nullsetzen der ganzen Zeile hätte ihn still aus der
    # Prognose entfernt.
    #
    # ⚑ Der **Fortschritt** (Messung, §4) trägt die Erträge unverändert weiter:
    # er rechnet aus `bisherige_ertraege`, nicht aus dieser Projektion.
    jahres_sonstige_netto = 0.0
    _sonstige_laufend = -bisherige_dienstlich_ladekosten
    if anzahl_monate_hist > 0 and _sonstige_laufend != 0:
        jahres_sonstige_netto = _sonstige_laufend / anzahl_monate_hist * 12

    # Gesamter Jahres-Netto-Ertrag inkl. Alternativkosten, BKW, Sonstige,
    # Betriebskosten und dem Jahres-Ertrag an der Investition (§8/2).
    jahres_netto_ertrag = jahres_einspeise_erloes + jahres_ev_ersparnis + jahres_wp_ersparnis + jahres_eauto_km_ersparnis + jahres_bkw_ersparnis + jahres_sonstige_netto + ertrag_jahr_ges - betriebskosten_ges

    # USt auf Eigenverbrauch bei Regelbesteuerung.
    # N-130 greift hier NICHT: `jahres_*` sind auf zwölf Monate hochgerechnete
    # Jahresmengen, kein Zeitraum-Aggregat ⇒ genau EIN Anteil mit `monate=12`.
    # Geändert hat sich nur die Bemessungsgrundlage (N-129).
    ust_eigenverbrauch = ust_eigenverbrauch_fuer_anlage(
        anlage,
        jahresanteile=[UstJahresanteil(
            jahr=heute.year,
            eigenverbrauch_kwh=jahres_eigenverbrauch,
            pv_kwh=jahres_erzeugung,
            monate=12,
        )],
        bemessungsgrundlage_euro=bemessungsgrundlage_aus_investitionen(alle_investitionen),
        betriebskosten_jahr_euro=betriebskosten_ges,
    )
    jahres_netto_ertrag -= ust_eigenverbrauch
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("jahres_eauto_km_ersparnis", "jahres_netto_ertrag", "jahres_wp_ersparnis", "ust_eigenverbrauch", "wp_ersparnis_je_inv", "wp_pv_kwh_je_inv", "wp_pv_kwh_total",) if k in _loc}

