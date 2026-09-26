"""Finanzen von *Cockpit → Monat*: Tarife und Preise des Monats, Komponenten-Ersparnis, Betriebskosten und sonstige
Positionen, die T-Konto-Zeilen je Investition und das eMob-Aggregat mit Effizienz und spezifischem Ertrag.
"""
# Vorlage 2 des Refactorings grosser Dateien (18.09.2026): Abschnitte des Endpunkts
# `get_aktueller_monat` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-aktueller-monat.py` (alte gegen neue Antworten, bitgleich).
from datetime import date
from typing import Optional
from sqlalchemy import select
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.strompreis_aggregator import aufgeloester_monatspreis
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_einspeise_preis_cent
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp
from backend.core.berechnungen import (
    berechne_netzbezug_kosten,
    eauto_effizienz_100km,
    einspeise_erloes_euro,
    spezifischer_ertrag_kwh_kwp,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.services.eauto_wirtschaftlichkeit import (
    compute_emob_pool_attribution,
    entscheide_emob_heimladung,
)
from backend.services.emob_kontext import lade_emob_kontext
from backend.services.monats_fakten import SonstigesFakten
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.investition_parameter import ist_dienstlich
from backend.api.routes.aktueller_monat.schemas import InvestitionFinancialDetail
from backend.api.routes.aktueller_monat.tkonto import _baue_investition_financial
from backend.api.routes.aktueller_monat.vergleich import _zeittarif_preis


async def finanzen_des_monats(*, _zt_cache, anlage_id, db, eigenverbrauch, einspeisung, jahr, monat, netzbezug):
    """Finanzen: Tarife, Netzbezugskosten, Einspeise-Erloes, EV-Ersparnis, Netto-Ertrag (N-267: eigener Tarif-Cache je Aufruf).

    Aus `get_aktueller_monat` Zeilen 772-899 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Finanzen ──
    einspeise_erloes = None
    einspeisung_neg_preis = None
    nicht_vergueteter_erloes = None
    netzbezug_kosten = None
    netzbezug_arbeitspreis_kosten = None
    ev_ersparnis = None
    netto_ertrag = None
    netzbezug_preis_cent = None
    netzbezug_preis_effektiv_cent = None
    netzbezug_preis_herkunft = None
    netzbezug_preis_abdeckung = None
    einspeise_cent = None
    grundgebuehr = None
    zaehlergebuehr_jahr = None

    # Die Monatszeile trägt sowohl den flexiblen Durchschnittspreis als auch die
    # Gas-/Kraftstoffpreise. Sie wird VOR dem Finanzblock geladen, weil der
    # Durchschnittspreis in die Kosten eingeht (siehe unten) — vorher lag der
    # Load hinter der Berechnung und stand erst zu spät zur Verfügung.
    md_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    md_for_gas = md_result.scalar_one_or_none()
    monats_gaspreis = md_for_gas.gaspreis_cent_kwh if md_for_gas else None
    monats_benzinpreis = md_for_gas.kraftstoffpreis_euro if md_for_gas else None
    # Flexibler Tarif: Durchschnittspreis aus Monatsdaten lesen
    netzbezug_durchschnittspreis = (
        md_for_gas.netzbezug_durchschnittspreis_cent if md_for_gas else None
    )

    # Tarif DES angezeigten Monats (ADR-002/P8) — der Endpoint bedient jeden
    # Monat über `jahr`/`monat`, nicht nur den laufenden. Mit dem heutigen Tarif
    # wich er von Cockpit/Monat ab, sobald ein Tarifwechsel dazwischenlag; und
    # ein Tarif ab Monatsmitte hätte hier sofort gegolten, dort erst im
    # Folgemonat (Stichtag = Monatserster). Wie `stichtag_vj` weiter oben.
    tarife = await lade_tarife_fuer_anlage(
        db, anlage_id, target_date=date(jahr, monat, 1)
    )
    allgemein_tarif = tarife.get("allgemein")
    if allgemein_tarif:
        # G19-1 K3: jährliche Zählergebühr (Ausweis in der Jahresaufstellung,
        # NICHT verrechnet) — Frontend zeigt sie nur im Jahres-Finanzblock.
        zaehlergebuehr_jahr = allgemein_tarif.zaehlergebuehr_euro_jahr
    if allgemein_tarif:
        # N-267: mit Zeitfenstern der gewichtete Preis, sonst die Spalte.
        netzbezug_preis_cent = await _zeittarif_preis(
            db, anlage_id, jahr, monat, allgemein_tarif,
            NETZBEZUG_DEFAULT_CENT, _zt_cache,
        )
        einspeise_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif.einspeiseverguetung_cent_kwh is not None else EINSPEISEVERGUETUNG_DEFAULT_CENT
        # #392: variable Einspeisevergütung — der gepflegte Satz des Monats
        # schlägt den Stammwert. Anders als beim Netzbezug (der „Verwendeter
        # Tarif" und Effektiv-Preis getrennt ausliefert) gibt es hier nur EIN
        # Response-Feld — Erlös, T-Konto und Anzeige tragen dieselbe Zahl.
        # Laufender Monat ohne gepflegten Wert → Stammwert (Auftrag #392).
        einspeise_cent = resolve_einspeise_preis_cent(md_for_gas, einspeise_cent)
        # Der Preis, mit dem GELD gerechnet wird: bei flexiblem Tarif der
        # verbrauchsgewichtete Monatsdurchschnitt, sonst der Tarif-Arbeitspreis.
        # `netzbezug_preis_cent` bleibt daneben der ausgelieferte Tarif-Wert
        # (Response-Feld „Verwendeter Tarif") und wird NICHT überschrieben.
        #
        # Bis v4.0.6 versprach hier nur ein Kommentar die Überschreibung — gebaut
        # war sie nie: Netzbezugskosten, EV-Ersparnis und der WP-Fallback des
        # laufenden Monats rechneten mit dem Tarifpreis, während der Vorjahres-
        # Pfad (`_load_vorjahr`) und die per-Investition-Details längst den
        # Durchschnitt nahmen. Derselbe Monat trug damit je nach Sicht zwei
        # Beträge, und in Cockpit → Monat passte die Ø-Preis-Kachel nicht zu
        # ihrer eigenen Kostenzeile (Forum simon42 #89667, Algie).
        #
        # Aufgelöst über den SoT-Helper, NICHT über `durchschnitt or tarif`:
        # ein Monats-Ø von **0,0 ct** ist bei dynamischem Tarif real (viele
        # Negativpreis-Stunden) und wäre als falsy stillschweigend auf den
        # Tarifpreis zurückgefallen — die 0-Werte-Falle.
        # ⭐ **#412 (11.09.2026): die Kaskade hat eine dritte Stufe bekommen** —
        # gepflegt → **gemessen** → Zeitfenster → Stamm. Zwischen dem
        # abgerechneten Ø und dem Tarifpreis fehlte die **Messung**: Wer einen
        # dynamischen Tarif hat, sah im laufenden Monat den festen Tarif,
        # obwohl eedc die Stundenpreise mitschreibt (OB73-gif).
        _preis = await aufgeloester_monatspreis(
            db, anlage_id, jahr, monat, md_for_gas, allgemein_tarif,
        )
        netzbezug_preis_effektiv_cent = _preis.cent
        netzbezug_preis_herkunft = _preis.herkunft
        netzbezug_preis_abdeckung = _preis.abdeckung

        if einspeisung is not None:
            # §51 EEG: siehe `_load_vorjahr` für Begründung.
            m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, jahr, monat)
            m_erloes = einspeise_erloes_euro(
                einspeisung_kwh=einspeisung,
                neg_preis_kwh=m_neg,
                verguetung_ct_kwh=einspeise_cent,
            )
            einspeise_erloes = round(m_erloes.erloes_euro, 2)
            # Den Abzug mitgeben, sonst ist die Kürzung im Erlös unsichtbar.
            # `m_neg is None` = Anlage nicht §51-pflichtig / keine Mitschrift.
            if m_neg is not None:
                einspeisung_neg_preis = round(m_erloes.nicht_verguetete_kwh, 1)
                nicht_vergueteter_erloes = round(m_erloes.nicht_vergueteter_erloes_euro, 2)
        if netzbezug is not None:
            grundpreis = allgemein_tarif.grundpreis_euro_monat or 0
            netzbezug_kosten = round(
                berechne_netzbezug_kosten(
                    netzbezug, netzbezug_preis_effektiv_cent, grundpreis
                ), 2
            )
            # Der reine Arbeitspreis-Anteil OHNE Grundpreis. Reiner Ausweis für
            # die Ø-Preis-Kachel: dort stehen kWh und € nebeneinander, und wer
            # sie dividiert, muss auf die Kopfzahl kommen. Mit den Gesamtkosten
            # ging das nie auf (559 kWh · 210,45 € ⇒ 37,6 ct statt 33 ct —
            # Forum simon42 #89667, Algie). Kein zweiter Kostenposten.
            netzbezug_arbeitspreis_kosten = round(
                netzbezug * netzbezug_preis_effektiv_cent / 100, 2
            )
            # G19-1 K3 (R19-3): Grundgebühr separat ausweisen — steckt bereits
            # in netzbezug_kosten (kein zweiter Posten, nur Annotation).
            grundgebuehr = round(grundpreis, 2)
        if eigenverbrauch is not None:
            ev_ersparnis = round(eigenverbrauch * netzbezug_preis_effektiv_cent / 100, 2)

        if einspeise_erloes is not None and ev_ersparnis is not None:
            netto_ertrag = round(einspeise_erloes + ev_ersparnis, 2)
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("allgemein_tarif", "einspeise_cent", "einspeise_erloes", "einspeisung_neg_preis", "ev_ersparnis", "grundgebuehr", "monats_benzinpreis", "monats_gaspreis", "netto_ertrag", "netzbezug_arbeitspreis_kosten", "netzbezug_durchschnittspreis", "netzbezug_kosten", "netzbezug_preis_abdeckung", "netzbezug_preis_cent", "netzbezug_preis_effektiv_cent", "netzbezug_preis_herkunft", "nicht_vergueteter_erloes", "tarife", "zaehlergebuehr_jahr",) if k in _loc}


def komponenten_ersparnis(*, get_val):
    """Komponenten-Ersparnis: WP-Strom/-Waerme und die Ersparnis-Startwerte fuer WP und E-Mob.

    Aus `get_aktueller_monat` Zeilen 900-911 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Komponenten-Ersparnis ──
    wp_ersparnis = None
    wp_ersparnis_berechnung_text: Optional[str] = None
    emob_ersparnis = None

    # Monats-Gaspreis (für WP-Ersparnis hier + Per-Investition-Block unten) wird
    # oben mit der Monatszeile geladen. Drift-Audit Domäne A1 / Issue #178: ohne
    # diesen Override fiel der Code auf hartcodierte 10ct zurück.

    wp_waerme = get_val("wp_waerme_kwh")
    wp_strom = get_val("wp_strom_kwh")
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("emob_ersparnis", "wp_ersparnis", "wp_ersparnis_berechnung_text", "wp_strom", "wp_waerme",) if k in _loc}


def betriebskosten_und_sonstige_positionen(*, investitionen, monats_fakt):
    """Betriebskosten anteilig, sonstige Ertraege/Ausgaben ueber alle Investitionen, Gesamtnettoertrag (Startwert).

    Aus `get_aktueller_monat` Zeilen 1186-1235 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Betriebskosten anteilig ──
    betriebskosten_anteilig = None
    betriebskosten_anteilig_jahr = None
    betriebskosten_anteilig_anzahl = None
    # A6: dieselbe Filtermenge trägt Σ Monatsanteil UND Σ Jahresbetrag/Anzahl —
    # ein zweiter Durchlauf mit anderem Filter wäre eine Herleitung, die auf
    # eine andere Zahl führt als die Zeile daneben.
    bk_jahre = [
        (i.betriebskosten_jahr or 0)
        for i in investitionen
        if (i.betriebskosten_jahr or 0) > 0
    ]
    bk_summe = sum(j / 12 for j in bk_jahre)
    if bk_summe > 0:
        betriebskosten_anteilig = round(bk_summe, 2)
        betriebskosten_anteilig_jahr = round(sum(bk_jahre), 2)
        betriebskosten_anteilig_anzahl = len(bk_jahre)

    # ── Sonstige Erträge / Ausgaben über alle Investitionen aggregieren ──
    # Pro Investition gehen Detail-Zeilen ins T-Konto (siehe
    # investitionen_financials weiter unten). Aggregate als eigenes Feld
    # exponiert, damit das Frontend Monatsergebnis-Korrekturen sauber rechnen
    # kann ohne `gesamtnettoertrag` zu verschieben (verhindert Drift mit
    # bestehender `sonderkosten`-Logik in MonatsabschlussView).
    #
    # Aus den Monats-Fakten (P10): dort gilt die Sichtbarkeitsregel einmal
    # (`aktiv` = wie gelöscht **plus** Laufzeit Anschaffung→Stilllegung, detLAN
    # [[feedback_anschaffungsdatum_grenze]], #236/#308 — Finanzpositionen sind
    # keine Ausnahme), und die Positionen hängen dort wie hier NICHT am Typ
    # (#310). Symmetrie zur Komponenten-Zeitreihe: dieselbe Quelle.
    #
    # G19-1: Basis-Positionen (Monatsdaten.sonstige_positionen, Anlage-Ebene)
    # wirken GENAU wie IMD-Positionen: eigene T-Konto-Zeile „Anlage — Sonstige …"
    # (anlage_*-Felder, reiner Ausweis) + einmalig in die Totals gefaltet
    # (R15-5-Muster: kein zweiter Kostenposten). `SonstigesFakten` hält beides
    # getrennt: die Totals tragen den Anlage-Anteil bereits.
    _sonstiges_fakten = monats_fakt.sonstiges if monats_fakt else SonstigesFakten()
    sonstige_ertraege_total = _sonstiges_fakten.ertraege_euro
    sonstige_ausgaben_total = _sonstiges_fakten.ausgaben_euro
    sonstige_netto_total = _sonstiges_fakten.netto_euro
    anlage_sonstige_ertraege = _sonstiges_fakten.anlage_ertraege_euro
    anlage_sonstige_ausgaben = _sonstiges_fakten.anlage_ausgaben_euro

    # ── Gesamtnettoertrag = Erlöse + Einsparungen − Kosten ──
    # G20-2: erst NACH den Per-Investition-Financials berechnet, damit
    # `emob_ersparnis` die Summe der Fahrzeug-Zeilen ist (siehe unten). Sonstige
    # Positionen werden NICHT eingerechnet — sie werden separat im T-Konto
    # gerendert und im Monatsergebnis (nettoNachAllem) addiert.
    gesamtnettoertrag = None
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("anlage_sonstige_ausgaben", "anlage_sonstige_ertraege", "betriebskosten_anteilig", "betriebskosten_anteilig_anzahl", "betriebskosten_anteilig_jahr", "gesamtnettoertrag", "sonstige_ausgaben_total", "sonstige_ertraege_total", "sonstige_netto_total",) if k in _loc}


async def t_konto_je_investition(*, _zt_cache, allgemein_tarif, anlage_id, db, einspeise_cent, investitionen, jahr, monat, monats_benzinpreis, monats_gaspreis, netzbezug_preis_effektiv_cent, tarife):
    """Per-Investition Finanzdetails (T-Konto) — laedt die InvestitionMonatsdaten je Investition (P10-Ausnahme PER_INVESTITION).

    Aus `get_aktueller_monat` Zeilen 1817-1930 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Per-Investition Finanzdetails (T-Konto) ──
    investitionen_financials: list[InvestitionFinancialDetail] = []
    if investitionen and allgemein_tarif:
        netz_p = netzbezug_preis_effektiv_cent or NETZBEZUG_DEFAULT_CENT
        # `einspeise_cent` ist oben bereits mit `is not None` aufgelöst — ein
        # `or` hätte hier nur noch den gepflegten Wert **0** überschrieben und
        # dem T-Konto eine andere Vergütung gegeben als der Zeile darüber.
        einsp_p = einspeise_cent if einspeise_cent is not None else EINSPEISEVERGUETUNG_DEFAULT_CENT
        wp_p = await _zeittarif_preis(
            db, anlage_id, jahr, monat, tarife.get("waermepumpe"), netz_p, _zt_cache,
        )
        wb_p = await _zeittarif_preis(
            db, anlage_id, jahr, monat, tarife.get("wallbox"), netz_p, _zt_cache,
        )
        # WP-Ersparnis pro Investition siehe wp_wirtschaftlichkeit.berechne_wp_ersparnis()
        # — nicht mehr lokal mit hartcodiertem Gaspreis berechnet (Drift-Audit A1).
        # Der monatliche Gaspreis-Override wird oben (md_for_gas) bereits geladen.

        # Alle InvestitionMonatsdaten in einem Query laden
        all_ids = [i.id for i in investitionen]
        all_imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(all_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        imd_by_inv: dict[int, dict] = {}
        _imd_objekte = all_imd_result.scalars().all()
        for imd in _imd_objekte:
            imd_by_inv[imd.investition_id] = imd.verbrauch_daten or {}

        # Wallbox-Pool-Attribution für die E-Auto-Komponente: bei evcc-Setups
        # steht die Ladung auf der Wallbox-IMD, das E-Auto trägt nur km. Ohne
        # diese Attribution rechnet die Komponente mit netz=0 + extern=0 und
        # weicht vom Hauptwert (Pool-Tile) ab — Drift gleicher Sicht.
        # F-16: der abgeleitete PV-Anteil erreicht auch DIESEN Block. Er ist der
        # letzte Rest, der `InvestitionMonatsdaten` selbst faltet (N-107, von C1d
        # bewusst offen gelassen) — und er sitzt in derselben Route wie die
        # Heimladungs-Trias aus den Monats-Fakten. Ohne die Anreicherung stünden
        # in EINER Sicht zwei PV-Anteile derselben Ladung nebeneinander.
        # N-555 Stufe 2: Zeilen und Entscheid des Monats aus dem einen Kontext
        # (`services/emob_kontext.py`) — mit Dienstwagen, dienstlicher Wallbox, Herkunft
        # von „Heim: gesamt" und den Quellen des laufenden Monats (Regel 1, 2, 3, 8).
        _kontext = await lade_emob_kontext(
            db, anlage_id, [i for i in investitionen if i.aktiv], _imd_objekte,
        )
        _emob_invs = [
            i for i in investitionen
            if i.aktiv
            and i.ist_aktiv_im_monat(jahr, monat)
            and not ist_dienstlich(i)
            and i.id in imd_by_inv
            and i.typ in ("e-auto", "wallbox")
        ]
        for i in _emob_invs:
            imd_by_inv[i.id] = _kontext.daten.get((i.id, jahr, monat), imd_by_inv[i.id])

        # Wallbox-Pool-Attribution auf denselben (angereicherten) Zeilen — nur noch für
        # die externe Ladung (F-5, `waehle_extern_paar`).
        eauto_imd_data = [imd_by_inv[i.id] for i in _emob_invs if i.typ == "e-auto"]
        wb_imd_data = [imd_by_inv[i.id] for i in _emob_invs if i.typ == "wallbox"]
        emob_pool_attr = compute_emob_pool_attribution(
            eauto_imd_data=eauto_imd_data,
            wallbox_imd_data=wb_imd_data,
        )
        # N-555: der Entscheid des Monats — dieselbe Funktion wie die Schicht.
        emob_entscheid = _kontext.ctx.entscheide.get((jahr, monat)) or entscheide_emob_heimladung(
            eauto_je_inv={}, wallbox_zeilen=[],
        )

        for inv in investitionen:
            # Anschaffungs-/Stilllegungsdatum begrenzen die Zeile
            # ([[feedback_anschaffungsdatum_grenze]]). Ohne diesen Filter trug
            # das T-Konto die anteiligen **Betriebskosten** jeder aktiven
            # Investition in JEDEN Monat — auch Jahre vor dem Kauf: gemeldet von
            # rilmor-mhrs (#402, ein E-Auto seit 14.08.2026 stand mit 4,17 € im
            # September 2025) und an einer Probe-Anlage nachgestellt.
            #
            # ⚠ Die Asymmetrie war im selben Modul sichtbar und ist der Beleg,
            # dass hier ein Filter fehlte, statt einer zu viel zu sein: der
            # **Vorjahres**-Aufruf desselben Helfers filtert seit jeher
            # (`_emob_aktiv`, weiter oben), und `komponenten_geraete` zwölf
            # Zeilen darüber nennt sich ausdrücklich „deckungsgleich mit der
            # Aggregation (ist_aktiv_im_monat)". `aussichten/finanzen.py` rechnet die
            # historischen Betriebskosten ebenfalls über die tatsächliche
            # Laufzeit — dort steht seit dem Bau „die vier Sichten waren
            # darüber uneins". Dies war die vierte.
            #
            # Nur die Betriebskosten stammen aus einem Jahresparameter und
            # konnten deshalb überhaupt vor dem Kauf entstehen; alle anderen
            # Größen kommen aus den Monatsdaten und sind dort naturgemäß leer.
            if not inv.ist_aktiv_im_monat(jahr, monat):
                continue
            detail = _baue_investition_financial(
                inv,
                imd_by_inv.get(inv.id, {}),
                netz_p=netz_p,
                einsp_p=einsp_p,
                wp_p=wp_p,
                wb_p=wb_p,
                monats_gaspreis=monats_gaspreis,
                monats_benzinpreis=monats_benzinpreis,
                emob_pool_attr=emob_pool_attr,
                emob_entscheid=emob_entscheid,
            )
            if detail is not None:
                investitionen_financials.append(detail)

    # #358 Phase 1: Σ Speicher-Ersparnis des Monats — AUFGESAMMELT aus den
    # T-Konto-Zeilen, nicht zweitgerechnet. Damit kann die Kachel nie eine
    # andere Zahl zeigen als die Zeile darunter (die Klasse hinter N-129/N-130).
    # `None`, solange keine Speicher-Zeile finanziell relevant ist.
    _sp_zeilen = [d for d in investitionen_financials if d.typ == "speicher"]
    if _sp_zeilen:
        speicher_ersparnis = round(
            sum(d.ersparnis_euro or 0 for d in _sp_zeilen), 2
        )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("investitionen_financials", "speicher_ersparnis",) if k in _loc}


def emob_aggregat_und_kennzahlen(*, anlage, einspeise_erloes, emob_ladung_extern=None, emob_ersparnis, ev_ersparnis, get_val, investitionen, investitionen_financials, jahr, monat, netzbezug_kosten, pv, wp_ersparnis):
    """G20-2: eMob-Ersparnis-Aggregat = Summe der Fahrzeug-Zeilen, Gesamtnettoertrag, E-Auto-Effizienz, spezifischer Ertrag.

    Aus `get_aktueller_monat` Zeilen 1931-1990 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── G20-2: eMob-Ersparnis-Aggregat = Σ der Per-Fahrzeug-Ersparnisse ──
    # Deckungsgleich mit den investitionen_financials-Zeilen (jede mit dem
    # parameter-Satz IHRES Fahrzeugs), statt Einmal-Lauf über die Gesamt-km mit
    # dem Referenz-Parameter des ersten E-Autos. Nur die vs-Verbrenner-Zeilen
    # (E-Auto + km-fahrende Wallbox) — die Wallbox-PV-Ladung-Ersparnis gehört
    # nicht in dieses Aggregat (wie zuvor). Dienstwagen sind bereits durch
    # `_baue_investition_financial` ausgeschlossen ([[feedback_aggregator_symmetrie]]).
    _emob_rows = [
        d for d in investitionen_financials
        if d.typ in ("e-auto", "wallbox")
        and d.ersparnis_label == "Ersparnis vs. Verbrenner"
        and d.ersparnis_euro is not None
    ]
    if _emob_rows:
        emob_ersparnis = round(sum(d.ersparnis_euro for d in _emob_rows), 2)
        # N-555 (Nebenfund 2): der Rechenweg dazu aus denselben Zeilen — mit den
        # Werten, mit denen gerechnet wurde, statt fester Defaults im Client.
        emob_ersparnis_berechnung = "\n".join(
            f"{d.bezeichnung}: {d.berechnung}" if len(_emob_rows) > 1 else d.berechnung
            for d in _emob_rows if d.berechnung
        ) or None

    # Gesamtnettoertrag jetzt bilden (emob_ersparnis = Summe der Fahrzeug-Zeilen).
    if einspeise_erloes is not None and ev_ersparnis is not None and netzbezug_kosten is not None:
        gesamtnettoertrag = round(
            einspeise_erloes + ev_ersparnis
            + (wp_ersparnis or 0)
            + (emob_ersparnis or 0)
            - netzbezug_kosten,
            2,
        )

    # N-557 (Konzept Regel 10): „Ladung gesamt" = Heimladung + Extern, soweit
    # Extern bekannt ist. Eine eigene Größe — `emob_ladung_kwh` bleibt Heim.
    _heim = get_val("emob_ladung_kwh")
    emob_ladung_gesamt = (
        round((_heim or 0) + (emob_ladung_extern or 0), 2)
        if _heim is not None or emob_ladung_extern is not None else None
    )

    # Ø Verbrauch (kWh/100 km) via zentralem Helper aus den FINALEN (ggf. connector-
    # überschriebenen) Werten — gemessener Fahrverbrauch hat Vorrang vor Ladung.
    # N-557: die Näherung ist Heim + Extern, wie der Vertrag des Helfers es verlangt
    # (`core/berechnungen/emob.py`); bis 25.09.2026 bekam er hier nur die Heimladung.
    emob_eff = eauto_effizienz_100km(
        get_val("emob_verbrauch_kwh") or 0,
        emob_ladung_gesamt or 0,
        get_val("emob_km") or 0,
    )

    # Spez. Ertrag über den Nenner-SoT (F-58). Hier stand bis 2026-08-24 der
    # gepflegte `anlage.leistung_kwp` mit der Begründung „gleiche Basis wie der
    # Community-Vergleich". Das machte Cockpit/Monat zur einzigen Sicht mit
    # einem anderen Nenner als Cockpit/Jahr (`cockpit/uebersicht.py` rechnet
    # seit jeher die Σ der Erzeuger) — zwei Zahlen für dieselbe Kennzahl.
    # Der Community-Vergleich selbst ist unberührt: er läuft über die Payload
    # in `community_service.py`, die weiterhin den gepflegten Wert meldet
    # (der Anlagen-Hash des Servers wird daraus gebildet).
    from calendar import monthrange as _monthrange_spez

    # N-355: `pv` statt `pv or 0`. Das `or 0` machte aus „für diesen Monat liegt
    # keine PV-Zahl vor" eine **gemessene Null** — der Anwender sah
    # `0,0 kWh/kWp` neben einer PV-Erzeugung „—". Der Nenner-Zweig des SoT
    # deckte nur die fehlende kWp ab; der Zähler-Zweig ist jetzt dort.
    spez_ertrag = spezifischer_ertrag_kwh_kwp(
        pv,
        anlagen_kwp(
            investitionen,
            # Stichtag Monatsende: ein im Monat zugebauter String gehört in den
            # Nenner dieses Monats, ein stillgelegter nicht mehr.
            date(jahr, monat, _monthrange_spez(jahr, monat)[1]),
            mit_bkw=True,
            referenzwert=anlage.leistung_kwp,
        ),
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("emob_eff", "emob_ersparnis", "emob_ersparnis_berechnung", "emob_ladung_gesamt", "gesamtnettoertrag", "spez_ertrag",) if k in _loc}

