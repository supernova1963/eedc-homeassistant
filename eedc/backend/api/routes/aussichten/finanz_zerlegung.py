"""Finanz-Prognose — die Zerlegung auf Komponenten: die Komponenten-Beiträge der Prognose (Speicher-Spread mit
PV/Netz-Anteil #264, V2H, E-Auto, Wärmepumpe je Gerät), ROI-Fortschritt und Amortisation über den Kapitalrechnungs-SoT
(N-137/F-19) sowie der bisherige Ertrag je Investition als Zerlegung des Zählers (Bauschritt 5, `ertrag_zerlegung`).
"""
# Vorlage 7b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `aussichten/finanzen.py::get_finanz_prognose` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-aussichten.py` (alte gegen neue Antworten, bitgleich).

import logging
from backend.core.berechnungen import (
    berechne_amortisations_fortschritt,
    kapitaleinsatz_euro,
    berechne_wp_alternativkosten_ersparnis,
    verteile_nach_gewichten,
)
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
)
from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
from backend.utils.investition_value import param_zahl
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.api.routes.aussichten.schemas import (
    ErtragJeInvestitionSchema,
    KomponentenBeitragSchema,
)
from datetime import date as _date

# Eigener Logger wie in Vorlage 7 — die Warnung des Ladepreis-Lookups traegt jetzt diesen Modulnamen.
logger = logging.getLogger(__name__)


async def komponenten_beitraege_zusammenstellen(
    *,
    anlage_id,
    db,
    e_autos,
    eauto_aggregate,
    einspeiseverguetung,
    historische_inv_daten,
    jahres_eauto_pv,
    jahres_speicher_beitrag,
    jahres_v2h_beitrag,
    netzbezug_preis,
    speicher,
    waermepumpen,
    wp_ersparnis_je_inv,
    wp_pv_kwh_je_inv,
):
    """Speicher-Netzanteil und Ladepreis aus der Historie (Etappe B/C, #264; der Ladepreis-Lookup darf die Antwort nie
    killen), dann je Speicher, E-Auto (V2H, Benzin, PV-Ladung) und Wärmepumpe (PV-Nutzung, Ersparnis) ein
    `KomponentenBeitragSchema`.

    Aus `get_finanz_prognose` Zeilen 1352-1529 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # KOMPONENTEN-BEITRÄGE ZUSAMMENSTELLEN
    # =====================================================================
    komponenten_beitraege = []

    # Etappe B (#264): Speicher-Spread-Service bekommt jetzt PV/Netz-Anteil.
    # Wir leiten den historischen Netz-Anteil an der Ladung ab und projizieren
    # ihn auf den prognostizierten Speicher-Beitrag. Ohne IST-Netzladung
    # (z. B. reiner PV-Speicher) bleibt das Verhalten exakt wie bisher.
    speicher_ladung_hist_total = 0.0
    speicher_netzladung_hist_total = 0.0
    if speicher:
        for sp in speicher:
            for (inv_id, jhr, mon), daten in historische_inv_daten.items():
                if inv_id != sp.id or not sp.ist_aktiv_im_monat(jhr, mon):
                    continue
                speicher_ladung_hist_total += float(daten.get("ladung_kwh") or 0)
                speicher_netzladung_hist_total += float(
                    daten.get("ladung_netz_kwh")
                    or daten.get("speicher_ladung_netz_kwh")
                    or 0
                )

    speicher_netz_anteil = (
        speicher_netzladung_hist_total / speicher_ladung_hist_total
        if speicher_ladung_hist_total > 0 else 0.0
    )
    # N-571: param_zahl — ein geleertes Feld ("") im `sum` beendete sonst
    # Cockpit → Aussicht mit TypeError/500, ohne jedes Gate, für jede Anlage
    # mit Speicher (das Feld ist im Formular vorbelegt und damit leerbar).
    speicher_wirkungsgrad_avg = (
        sum(
            param_zahl(
                sp.parameter,
                PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
                PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
            )
            for sp in speicher
        ) / len(speicher)
        if speicher else PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"]
    )
    # Ladepreis nur bei arbitragefähigen Speichern relevant — sonst ist die
    # Netzladung kostenneutrale Durchleitung (z. B. Backup-Ladung).
    arbitrage_speicher = [
        sp for sp in speicher
        if (sp.parameter or {}).get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"])
    ]
    speicher_lade_preis_cent = (
        sum(
            param_zahl(
                sp.parameter,
                PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"],
                PARAM_SPEICHER_DEFAULTS["lade_durchschnittspreis_cent"],
            )
            for sp in arbitrage_speicher
        ) / len(arbitrage_speicher)
        if arbitrage_speicher else None
    )

    # Etappe C (#264): stundengranularen effektiven Ladepreis aus TEP
    # vorziehen — Tibber/aWATTar-Setups bekommen den echten gewichteten
    # Mittelwert über die Lade-Stunden statt User-Param-Schätzung.
    if speicher and arbitrage_speicher:
        installs_c = [sp.anschaffungsdatum for sp in speicher if sp.anschaffungsdatum]
        if installs_c:
            try:
                eff_ladepreis_c = await berechne_effektiver_ladepreis(
                    db,
                    anlage_id=anlage_id,
                    von=min(installs_c),
                    bis=_date.today(),
                )
                # Etappe C1: Helper liefert immer ein Ergebnis. Nur belastbare
                # Quellen (dyn-tarif/boersenpreis) den Param-Mittelwert überstimmen
                # lassen — bei `datenbasis-zu-duenn` oder `keine-netzladung`
                # bleibt der Param-Wert aus Etappe B.
                if (
                    eff_ladepreis_c is not None
                    and eff_ladepreis_c.effektiver_ladepreis_cent is not None
                    and eff_ladepreis_c.quelle in ("dyn-tarif", "boersenpreis")
                ):
                    speicher_lade_preis_cent = eff_ladepreis_c.effektiver_ladepreis_cent
            except Exception as e:  # noqa: BLE001
                # Helper darf Aussichten-Antwort nie killen — bei Fehler
                # bleibt der Param-Mittelwert aus Etappe B.
                logger.warning(
                    "aussichten: effektiver-Ladepreis-Lookup fehlgeschlagen "
                    "(anlage=%s): %s", anlage_id, e,
                )
    # Aus Entladung auf Ladung zurückrechnen (η-Verluste), daraus den
    # projizierten Netz-Anteil-kWh der Prognoseperiode bestimmen.
    speicher_wirkungsgrad_frac = max(0.5, speicher_wirkungsgrad_avg / 100)
    prog_speicher_ladung = jahres_speicher_beitrag / speicher_wirkungsgrad_frac
    prog_speicher_netzladung = prog_speicher_ladung * speicher_netz_anteil

    # Speicher (Drift-Audit D: Spread-Modell statt Voll-Strompreis)
    if speicher:
        speicher_ersparnis = berechne_speicher_ersparnis(
            entladung_kwh=jahres_speicher_beitrag,
            bezug_preis_cent=netzbezug_preis,
            einspeise_verg_cent=einspeiseverguetung,
            ladung_netz_kwh=prog_speicher_netzladung,
            wirkungsgrad_prozent=speicher_wirkungsgrad_avg,
            lade_preis_cent=speicher_lade_preis_cent,
        ).ersparnis_euro
        for sp in speicher:
            komponenten_beitraege.append(KomponentenBeitragSchema(
                typ="speicher",
                bezeichnung=sp.bezeichnung,
                beitrag_kwh_jahr=round(jahres_speicher_beitrag, 0),
                beitrag_euro_jahr=round(speicher_ersparnis, 2),
                beschreibung="Eigenverbrauchserhöhung durch Zwischenspeicherung",
            ))

    # E-Auto / V2H (Drift-Audit D: Spread-Modell für V2H analog Speicher)
    if e_autos:
        v2h_ersparnis = berechne_v2h_ersparnis(
            v2h_entladung_kwh=jahres_v2h_beitrag,
            bezug_preis_cent=netzbezug_preis,
            einspeise_verg_cent=einspeiseverguetung,
        ).ersparnis_euro
        eauto_ersparnis = jahres_eauto_pv * netzbezug_preis / 100
        for ea in e_autos:
            # Prüfe ob V2H aktiv (Bug #1 v3.25.0: Form/Wizard schreiben v2h_faehig,
            # vorher las dieser Code nutzt_v2h → V2H-Anzeige im Aussichten-Tab war tot.)
            nutzt_v2h = ea.parameter.get(PARAM_E_AUTO["V2H_FAEHIG"], False) if ea.parameter else False
            if nutzt_v2h and jahres_v2h_beitrag > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-v2h",
                    bezeichnung=f"{ea.bezeichnung} (V2H)",
                    beitrag_kwh_jahr=round(jahres_v2h_beitrag, 0),
                    beitrag_euro_jahr=round(v2h_ersparnis, 2),
                    beschreibung="Rückspeisung vom E-Auto ins Haus",
                ))
            # Benzin-Ersparnis als Komponenten-Beitrag — pro E-Auto getrennt
            ea_agg = eauto_aggregate.get(ea.id)
            ea_jahres_ersparnis = ea_agg["jahres_ersparnis"] if ea_agg else 0.0
            ea_vergleich_l_100km = ea_agg["vergleich_l_100km"] if ea_agg else PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"]
            if ea_jahres_ersparnis > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-benzin",
                    bezeichnung=f"{ea.bezeichnung} (vs. Benzin)",
                    beitrag_kwh_jahr=0,  # Nicht in kWh messbar
                    beitrag_euro_jahr=round(ea_jahres_ersparnis, 2),
                    beschreibung=f"Ersparnis ggü. {ea_vergleich_l_100km}L/100km Benziner",
                ))
            if jahres_eauto_pv > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="e-auto-ladung",
                    bezeichnung=f"{ea.bezeichnung} (PV-Ladung)",
                    beitrag_kwh_jahr=round(jahres_eauto_pv, 0),
                    beitrag_euro_jahr=round(eauto_ersparnis, 2),
                    beschreibung="PV-Direktladung statt Netzbezug",
                ))

    # Wärmepumpe — N-354: je Gerät sein eigener Beitrag, nicht das Anlagen-Aggregat
    if waermepumpen:
        alter_energietraeger = "Gas"
        for wp in waermepumpen:
            if wp.parameter:
                ae = wp.parameter.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"], PARAM_WAERMEPUMPE_DEFAULTS["alter_energietraeger"])
                alter_energietraeger = "Öl" if ae == "oel" else "Gas"
            # PV-Direktverbrauch — gepflegter Anteil × eigener Stromanteil
            wp_pv_kwh = wp_pv_kwh_je_inv.get(wp.id, 0.0)
            komponenten_beitraege.append(KomponentenBeitragSchema(
                typ="waermepumpe-pv",
                bezeichnung=f"{wp.bezeichnung} (PV-Nutzung)",
                beitrag_kwh_jahr=round(wp_pv_kwh, 0),
                beitrag_euro_jahr=round(wp_pv_kwh * netzbezug_preis / 100, 2),
                beschreibung="PV-Direktverbrauch für Heizung/Warmwasser",
            ))
            # Alternativkosten-Ersparnis gegenüber Gas/Öl — nur für das Gerät,
            # das tatsächlich etwas ersetzt hat, und nur mit seinem Anteil.
            wp_ersparnis = wp_ersparnis_je_inv.get(wp.id, 0.0)
            if wp_ersparnis > 0:
                komponenten_beitraege.append(KomponentenBeitragSchema(
                    typ="waermepumpe-ersparnis",
                    bezeichnung=f"{wp.bezeichnung} (vs. {alter_energietraeger})",
                    beitrag_kwh_jahr=0,  # Nicht direkt in kWh
                    beitrag_euro_jahr=round(wp_ersparnis, 2),
                    beschreibung=f"Ersparnis gegenüber {alter_energietraeger}heizung",
                ))
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("komponenten_beitraege", "prog_speicher_netzladung", "speicher_lade_preis_cent", "speicher_wirkungsgrad_avg",) if k in _loc}


def roi_und_fortschritt(
    *,
    _finanz,
    alle_investitionen,
    betriebskosten_hist_je_inv,
    bisherige_ertraege,
    bisherige_sonstige_ausgaben,
    bisherige_sonstige_ertraege,
    bisherige_ust_eigenverbrauch,
    eauto_aggregate,
    fakten,
    gaspreis_by_periode,
    heute,
    historische_inv_daten,
    investition_gesamt,
    jahres_netto_ertrag,
    waermepumpen,
    wp_netzbezug_preis,
    wp_preis_by_periode,
):
    """Kapitaleinsatz und Amortisations-Fortschritt (Layer-SoT, N-137/F-19) und die Zerlegung des Zählers auf die
    ROI-Zeilen: Erzeugungs-Gewichte je Zeile, direkte Zuordnung je Gerät, Betriebskosten je Komponente, Rest sichtbar.

    Aus `get_finanz_prognose` Zeilen 1530-1687 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 7b.
    """
    # =====================================================================
    # ROI UND AMORTISATION
    # =====================================================================
    # Layer-SoT (ADR-001) statt vier Zeilen Arithmetik an dieser Stelle — dieselbe
    # Formel speist seit N-137 die Kachel „Amortisations-Fortschritt" in
    # Auswertungen → ROI. Der Fortschritt ist reine MESSUNG (kumulierte Erträge
    # ÷ relevante Kosten); `jahres_netto_ertrag` geht nur in die Restlaufzeit ein.
    # F-19: Nenner ist der Kapitaleinsatz — relevante Kosten plus die
    # kumulierten sonstigen Netto-Kosten. Damit rechnet der Fortschritt gegen
    # dieselbe Größe wie ROI-Dashboard und HA-Sensoren; `investition_gesamt`
    # selbst bleibt die Mehrkosten-Größe (N-137, zugleich USt-Grundlage).
    kapitaleinsatz = kapitaleinsatz_euro(
        relevante_kosten_euro=investition_gesamt,
        sonstige_ausgaben_euro=bisherige_sonstige_ausgaben,
        sonstige_ertraege_euro=bisherige_sonstige_ertraege,
    )
    # ⚠ Und der Zähler **ohne beide Seiten** der sonstigen Positionen — sonst
    # stünde dieselbe Reparatur (bzw. dieselbe Förderung) zweimal in derselben
    # Formel. Die Ausgaben werden wieder aufgeschlagen, weil sie im Netto
    # abgezogen waren; die Erträge werden abgezogen, weil sie darin enthalten
    # sind (Bauschritt 7).
    #
    # Das ausgewiesene Feld `bisherige_ertraege_euro` bleibt davon
    # **unberührt**: es ist die Zeitraum-Bilanz und deckungsgleich mit dem
    # Cockpit-Netto-Ertrag (`test_aussichten_finanz_aggregat_symmetrie.py`).
    # Ein erster Bau zog den Betrag dort ab und brach genau diese Zusicherung —
    # die Trennlinie verläuft zwischen ANGEZEIGTER Bilanz und Kapitalrechnung,
    # nicht zwischen zwei Rechenwegen.
    ertraege_fuer_kapitalrechnung = (
        bisherige_ertraege + bisherige_sonstige_ausgaben - bisherige_sonstige_ertraege
    )
    _amort = berechne_amortisations_fortschritt(
        relevante_kosten_euro=kapitaleinsatz,
        bisherige_ertraege_euro=ertraege_fuer_kapitalrechnung,
        jahres_netto_ertrag_euro=jahres_netto_ertrag,
        aktuelles_jahr=heute.year,
    )
    roi_fortschritt = _amort.fortschritt_prozent
    amortisation_erreicht = _amort.erreicht
    amortisation_prognose_jahr = _amort.prognose_jahr
    restlaufzeit_monate = _amort.rest_monate

    # =====================================================================
    # FORTSCHRITT JE INVESTITION — Bauschritt 5 des Konzepts (§8)
    # =====================================================================
    # ⚑ **Zerlegung, keine zweite Rechnung.** Der Zähler oben wird auf die
    # ROI-Zeilen VERTEILT; niemand rechnet eine Komponenten-Ersparnis ein
    # zweites Mal. Damit gilt `Σ Zeilen + Rest == gesamt` per Konstruktion —
    # die Zusicherung kann nicht auseinanderlaufen, und was sich nicht
    # zurechnen lässt, steht als Rest da statt still auf den Zeilen zu landen
    # (die N-220-Lehre: eine Zusicherung, die nur an einer Fixture hängt,
    # trägt nicht).
    #
    # Der Schlüssel der Erzeugungsseite ist die **gemessene Erzeugung** je
    # Zeile (Entscheid Maintainer 2026-08-10), nicht die Nennleistung: kWp
    # sagt, was ein Modul könnte, kWh sagt, was es beigetragen hat.
    from backend.api.routes.investitionen.crud import _gruppiere_investitionen
    from backend.core.berechnungen.ertrag_zerlegung import zerlege_kumulierten_ertrag

    _pv_systeme, _, _orphan_module = _gruppiere_investitionen(alle_investitionen)
    # Modul -> ROI-Zeile. Ein Modul mit gültigem Parent zählt auf den
    # Wechselrichter (dort steht die Zeile), ein Orphan-Modul auf sich selbst.
    _modul_zu_zeile: dict[int, int] = {
        m.id: wr_id for wr_id, sys in _pv_systeme.items() for m in sys["pv_module"]
    }

    _erz_gewichte: dict[int, float] = {}
    _bkw_gewichte: dict[int, float] = {}
    for _f in fakten:
        for _mod_id, _wert in (_f.erzeugung.pv_je_modul or {}).items():
            _zeile = _modul_zu_zeile.get(_mod_id, _mod_id)
            _erz_gewichte[_zeile] = (
                _erz_gewichte.get(_zeile, 0.0) + _wert.pv_erzeugung_kwh
            )
        for _bkw_id, _kwh in (_f.bkw.erzeugung_je_investition or {}).items():
            _bkw_gewichte[_bkw_id] = _bkw_gewichte.get(_bkw_id, 0.0) + (_kwh or 0.0)
    # Das BKW erzeugt hinter demselben Zähler und trägt deshalb auch die
    # Erlösseite mit — es hat aber zusätzlich seinen eigenen Ersparnis-Posten
    # (P9), der unten direkt zugeordnet wird.
    for _bkw_id, _kwh in _bkw_gewichte.items():
        _erz_gewichte[_bkw_id] = _erz_gewichte.get(_bkw_id, 0.0) + _kwh

    # Was am Zähler entsteht: Einspeise-Erlös + EV-Ersparnis, abzüglich der USt
    # auf den Eigenverbrauch — sie hängt an derselben Menge und geht deshalb
    # denselben Weg.
    _erzeugungs_erloes = (
        _finanz.einspeise_erloes_euro
        + _finanz.ev_ersparnis_euro
        - bisherige_ust_eigenverbrauch
    )

    _direkt: dict[int, float] = {}
    _abzug: dict[int, float] = {}

    # Wärmepumpe je Gerät — derselbe Layer-SoT, nur je WP gerufen.
    # ⚠ Bei MEHREREN WPs mit unterschiedlicher Monatsabdeckung ist die Summe
    # der Einzelaufrufe nicht bitgleich zum Gesamtaufruf: der anteilige
    # Zusatzkosten-Term rechnet dort mit der VEREINIGUNG der Monate. Die
    # Differenz landet sichtbar im Rest, statt eine Zeile zu verfälschen.
    for _wp in waermepumpen:
        _direkt[_wp.id] = _direkt.get(_wp.id, 0.0) + berechne_wp_alternativkosten_ersparnis(
            [_wp],
            historische_inv_daten,
            gaspreis_by_periode,
            wp_preis_by_periode,
            wp_netzbezug_preis,
        )

    # E-Auto je Fahrzeug — liegt bereits je Investition vor.
    for _ea_id, _agg in eauto_aggregate.items():
        _direkt[_ea_id] = _direkt.get(_ea_id, 0.0) + (_agg.get("bisherige_ersparnis") or 0.0)

    # BKW-Ersparnis (P9) auf die Balkonkraftwerke, nach ihrer Erzeugung.
    for _bkw_id, _betrag in verteile_nach_gewichten(
        _finanz.bkw_ersparnis_euro, _bkw_gewichte
    ).items():
        _direkt[_bkw_id] = _direkt.get(_bkw_id, 0.0) + _betrag

    # Erzeuger-Erlös je Gerät (§9 Weg 2, Bauschritt 9) — er liegt
    # komponentenscharf vor und wird deshalb **direkt zugeordnet**, nicht
    # verteilt. Bis zu dieser Stelle landete er im nicht zurechenbaren Rest,
    # obwohl seine Zeile bekannt ist: die Bauschritt-5-Regel lautet „alles
    # komponentenscharf Vorliegende direkt".
    for _f in fakten:
        for _inv_id, _g in (_f.sonstiges.je_geraet or {}).items():
            if _g.einspeise_erloes_euro:
                _direkt[_inv_id] = _direkt.get(_inv_id, 0.0) + _g.einspeise_erloes_euro

    # ⚑ **Gepflegte Monatspositionen tauchen hier seit Bauschritt 7 auf KEINER
    # Seite mehr auf** — weder als Zuschlag (Ertrag) noch als Abzug (Ausgabe).
    # Beide stehen im NENNER der Zeile (`kapitaleinsatz` im ROI-Dashboard, das
    # den Nenner je Zeile liefert). Sie zusätzlich in den Zähler zu verteilen
    # hieße, dieselbe Position zweimal zu verrechnen — bis 2026-08-10 tat der
    # Block hier genau das mit der Ertragsseite, weil sie damals noch im Zähler
    # stand.

    # Betriebskosten je Komponente — **dieselbe** Größe, die oben in Summe vom
    # Zähler abgezogen wurde (N-228). Sie hier ein zweites Mal zu bilden wäre
    # genau die Drift, die diese Zerlegung vermeiden soll.
    for _inv_id, _betrag in betriebskosten_hist_je_inv.items():
        _zeile = _modul_zu_zeile.get(_inv_id, _inv_id)
        _abzug[_zeile] = _abzug.get(_zeile, 0.0) + _betrag

    _zerlegung = zerlege_kumulierten_ertrag(
        gesamt_euro=ertraege_fuer_kapitalrechnung,
        erzeugungs_erloes_euro=_erzeugungs_erloes,
        erzeugungs_gewichte=_erz_gewichte,
        direkt_je_investition=_direkt,
        abzug_je_investition=_abzug,
    )
    fortschritt_je_investition = [
        ErtragJeInvestitionSchema(
            investition_id=_inv_id,
            bisherige_ertraege_euro=round(_betrag, 2),
        )
        for _inv_id, _betrag in sorted(_zerlegung.je_investition.items())
    ]
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_zerlegung", "amortisation_erreicht", "amortisation_prognose_jahr", "fortschritt_je_investition", "kapitaleinsatz", "restlaufzeit_monate", "roi_fortschritt",) if k in _loc}

