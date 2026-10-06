"""Waerme/Klima von *Cockpit → Monat*: Arbeitszahl aus dem Layer, die R2-Lagen der Abgrenzung, die anlagenweite Schranke
(E1b), die Tagesebene im laufenden Monat (N-472/A-5), S5 anlagenweit, SOLL 3.2b — sowie Komponenten-Flags und WP-Zaehler.
"""
# Vorlage 2 des Refactorings grosser Dateien (18.09.2026): Abschnitte des Endpunkts
# `get_aktueller_monat` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-aktueller-monat.py` (alte gegen neue Antworten, bitgleich).
from typing import Optional
from sqlalchemy import select
from backend.services.waermepumpe_kennzahlen_je_geraet import lade_kennzahlen_je_geraet
from backend.services.waerme_klima_block import (
    funktions_eingaenge_der_anlage,
    schranken_eingang,
    traegt_menge,
)
from backend.core.berechnungen.waermepumpe_kennzahl import (
    ARBEITSZAHL_FUNKTIONEN,
    abgrenzung_je_funktion,
    abgrenzungs_grund,
    systemarbeitszahl,
    waerme_gesamt_kwh,
)
from backend.services.wp_wirtschaftlichkeit import wp_ersparnis_berechnung, wp_ersparnis_zeile
from backend.api.routes.aktueller_monat.aggregation import _WP_STROM_K3_SUFFIX, _WP_WAERME_D1_SUFFIX
from backend.core.investition_parameter import ist_dienstlich
from backend.api.routes.aktueller_monat.vergleich import _zeittarif_preis


async def waerme_klima_monat(*, resolved=None, _tages_wp_mengen, kanal_wp_zeilen=None, _zt_cache, allgemein_tarif, anlage_id, db, get_val, investitionen, jahr, monat, monats_fakt, monats_gaspreis, netzbezug_preis_effektiv_cent, tarife, teilzeitraum, wp_strom, wp_waerme):
    """Arbeitszahl (R2/W-3), die drei R2-Lagen ueber die eine Layer-Stelle, E1b-Schranke, Tagesebene im laufenden Monat (N-472/A-5), S5 anlagenweit (WK-16i), SOLL 3.2b: welche Funktionen die Verletzung trifft.

    Aus `get_aktueller_monat` Zeilen 807-1080 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Arbeitszahl aus dem Layer, nicht aus dem Client (R2/W-3) ────────────
    #
    # ⚠ **Der abgeleitete Anteil kommt IMMER aus den Monats-Fakten**, auch wenn
    # die Mengen oben aus einer anderen Quelle gewonnen wurden. Er beschreibt
    # die **Herkunft der IMD-Zeilen** dieses Monats, und die ändert sich nicht
    # dadurch, dass eine Menge über HA-Statistik statt aus der Datenbank kam.
    # Im Zweifel sperrt er — „unbekannt" ist besser als „falsch" (P4).
    wp_waerme_abgeleitet_kwh = (
        monats_fakt.wp.waerme_abgeleitet_kwh if monats_fakt is not None else 0.0
    )
    # ── R2: alle drei erkennbaren Lagen, über die eine Layer-Stelle ─────────
    #
    # **Gerät:** Trägt der Block Strom von Geräten, deren Wärme fehlt? Der Block
    # *Wärme/Klima* aggregiert alle Wärmepumpen der Anlage — bei dietmar1968
    # „Wärmepumpe · Klimaanlage" — und nur eines meldete Wärme.
    #
    # **Anwender-Angabe:** Heizstab-Strom auf dem WP-Zähler (Fall H-C) oder ein
    # bivalenter Zweiterzeuger am selben Kreis. Beides ist aus keiner Messreihe
    # ableitbar; die Reihenfolge (Angabe schlägt Erkennung) steht im Layer.
    #
    # **Zeitraum (SOLL §4.2 Fall 3):** ⭐ Diese Sicht ist die **einzige** mit
    # Vier-Quellen-Auflösung — und `teilzeitraum` weist genau die Felder aus,
    # deren Endwert nur einen Ausschnitt des Monats misst (#361, coolxmad #353:
    # ein frisch eingerichteter Connector, der erst mitten im Monat zu zählen
    # begann). Steht **genau eine** der beiden Seiten darin, tragen Q und E
    # verschieden lange Zeiträume und der Quotient wäre einer aus zwei
    # Wirklichkeiten.
    #
    # ⛔ **Bewusst kein Zählen von Tagen mit Wert.** Der naheliegende Weg —
    # „an wie vielen Tagen des Monats gab es überhaupt eine Zahl?" — kann
    # *„kein Wert, weil das Gerät stand"* nicht von *„kein Wert, weil der Sensor
    # fehlte"* unterscheiden. Bei einer Wärmepumpe im Juli ist Ersteres der
    # Normalfall; ein Wächter darauf meldete jeden Sommer bei jeder Anlage.
    # Genau die Fehlalarm-Klasse, die §2i-6 schon einmal eingefangen hat.
    _wp_seiten_teilzeitraum = sum(
        1 for f in ("wp_waerme_kwh", "wp_strom_kwh") if f in teilzeitraum
    )
    wp_abgrenzung_verletzt = abgrenzungs_grund(
        abgrenzung_stoerung=(
            monats_fakt.wp.abgrenzung_stoerung if monats_fakt is not None else None
        ),
        # R2/Bauart (SOLL §5): Wärmepumpe und Split-Klimaanlage in einer Zahl.
        bauarten_gemischt=(
            monats_fakt is not None and monats_fakt.wp.bauarten_gemischt
        ),
        geraete_ohne_waerme=(
            monats_fakt is not None
            and monats_fakt.wp.waerme_deckt_nicht_alle_geraete
        ),
        zeitraum_versetzt=_wp_seiten_teilzeitraum == 1,
        # N-441: die Gegenrichtung. ⚠ Sie haengt **hinter** `zeitraum_versetzt`
        # in der Kette (`abgrenzungs_grund`), weil hier — und nur hier — beide
        # zugleich wahr sein koennen: Der Zeitraum-Versatz entsteht aus der
        # Vier-Quellen-Aufloesung dieses Monats. Vorn eingehaengt haette das
        # neue Glied dort einen heute gezeigten Grund samt Hub-Link getauscht.
        geraete_verschieden=(
            monats_fakt is not None and monats_fakt.wp.geraete_verschieden
        ),
    )
    # ⭐ **Die Frage „welche Funktion trifft die Verletzung?" steht weiter
    # unten** (SOLL §3.2b; seit WK-16i hinter den Geräte-Kennzahlen, denn aus
    # ihnen beantwortet der laufende Monat sie).
    # W-14 + E4: Der funktionsfremde Strom (Kühlen · Lüften · Entfeuchten) kommt
    # — wie der abgeleitete Anteil darüber — IMMER aus den Monats-Fakten. Er
    # beschreibt die Aufteilung der IMD-Zeilen dieses Monats, und die ändert sich
    # nicht dadurch, dass eine Menge über HA-Statistik statt aus der Datenbank
    # kam. Eine Größe statt drei Summanden: die Aufzählung an vier Aufrufern war
    # die Bauform, an der W-14 entstanden ist.
    #
    # ⭐ **SOLL-§9-E7/Option A (12.09.2026): der ABZUG, nicht die Menge.** Hier
    # stand bis dahin `modus_strom_funktionsfremd_kwh`. Bei getrennter
    # Strommessung mit nur **abgeleiteter** Aufteilung kürzte das den Nenner um
    # eine Menge, die er nie enthielt — der Split verteilt
    # `strom_heizen + strom_warmwasser`, er stellt nichts daneben. Die
    # Mengen-Größe bleibt daneben stehen und trägt weiter die Aufteilung (K1).
    wp_strom_funktionsfremd_kwh = (
        monats_fakt.wp.modus_strom_funktionsfremd_abzug_kwh
        if monats_fakt is not None else 0.0
    )
    # ── E1b: die ANLAGENWEITE Zahl, als Schranke statt als Strich ──────────
    #
    # ⭐ **Entscheid Gernot, 14.09.2026.** Hier stand `arbeitszahl(...)` mit
    # `wp_abgrenzung_verletzt` — und damit sperrten **zwei** Lagen die Zahl, die
    # sie gar nicht falsch machen, sondern nur zu **klein**: gemischte Bauarten
    # (`GRUND_BAUARTEN_GEMISCHT`) und Geräte ohne Wärmemeldung
    # (`GRUND_GERAETE_OHNE_WAERME`). In beiden steht Strom im Nenner, dem keine
    # gemessene Wärme gegenübersteht; der Quotient ist dann eine **untere
    # Schranke** — und die ist eine wahre Aussage.
    #
    # ⚠ **Die übrigen Gründe sperren weiter, und das ist der Kern der
    # Unterscheidung:** Fremdanteil-Angabe, Zeitraum-Versatz, „Wärme und Strom
    # von verschiedenen Geräten" und „… aus verschiedenen Monaten" kippen die
    # Zahl nach **oben** oder in unbekannte Richtung. Eine untere Schranke wäre
    # dort eine Falschaussage. Deshalb dieselbe Kette ein zweites Mal — ohne die
    # beiden Glieder, die zur Schranke werden.
    _wp_invs_fuer_block = [i for i in investitionen if i.typ == "waermepumpe"]
    _wp_kennzahlen_je_geraet = await lade_kennzahlen_je_geraet(
        db, anlage_id, _wp_invs_fuer_block, von=(jahr, monat), bis=(jahr, monat),
    )
    # ── N-472/A-5: dieselbe Tabelle im laufenden Monat, aus der Tagesebene ──
    #
    # ⛔ **Der Dienst liest `InvestitionMonatsdaten` — die es im laufenden Monat
    # nicht gibt.** Die Tabelle *Zahlen je Gerät* blieb deshalb leer, während
    # Kachel und Verlauf darüber dieselben Tage vollständig zeigten; genau das
    # Bild, gegen das dieses Paket gebaut ist, eine Ebene tiefer.
    #
    # ⭐ **Die Kennzahl entsteht trotzdem in derselben Funktion.** Der Dienst
    # trägt für diesen Fall seit WK-16ab `mengen_aus_tageswerten` — dieselbe
    # zweite Herkunft, die *Cockpit → Tag* benutzt; nur der Zeitraum ist ein
    # Monat statt eines Tages. Es entsteht **keine** zweite Rechenstelle.
    #
    # ⚠ **Ersetzt wird nur, was leer ist.** Trägt ein Gerät für diesen Monat
    # schon eine Zeile (gepflegter Teilmonat, Import), gewinnt sie — dieselbe
    # Präzedenz wie oben in der Quellen-Kaskade.
    # ── HA-Bauform E4d: im Monat ohne WP-Zeile aus den Kanal-Zeilen — VOR der Tagesebene ──
    # Dieselbe Faltung wie eine Monatszeile (``mengen_aus_monatszeilen``), weil die Kanal-Zeile deren Form hat
    # (``monats_fakten.wp_kanal_zeile``). Ersetzt wird nur, was leer ist; die Tagesebene darunter bleibt der Rückfall.
    if kanal_wp_zeilen:
        from types import SimpleNamespace

        from backend.services.monats_fakten import wp_kanal_zeile
        from backend.services.waermepumpe_kennzahlen_je_geraet import (
            kennzahlen_aus_mengen,
            mengen_aus_monatszeilen,
        )
        _wp_invs_by_id_k = {i.id: i for i in _wp_invs_fuer_block}
        _ersetzt_k: list = []
        for _k in _wp_kennzahlen_je_geraet:
            _z = kanal_wp_zeilen.get(_k.inv_id)
            _inv = _wp_invs_by_id_k.get(_k.inv_id)
            if _z is None or _inv is None or traegt_menge(_k.mengen):
                _ersetzt_k.append(_k)
                continue
            _daten, _herkunft = wp_kanal_zeile(_inv, _z)
            _ersetzt_k.append(kennzahlen_aus_mengen(mengen_aus_monatszeilen(_inv, [SimpleNamespace(
                verbrauch_daten=_daten, source_provenance=_herkunft, jahr=jahr, monat=monat,
            )])[0]))
        _wp_kennzahlen_je_geraet = _ersetzt_k
    if _tages_wp_mengen:
        from backend.services.waermepumpe_kennzahlen_je_geraet import (
            kennzahlen_aus_mengen,
            mengen_aus_tageswerten,
        )
        _wp_invs_by_id = {i.id: i for i in _wp_invs_fuer_block}
        _ersetzt: list = []
        for _k in _wp_kennzahlen_je_geraet:
            _m = _tages_wp_mengen.get(str(_k.inv_id))
            _inv = _wp_invs_by_id.get(_k.inv_id)
            if _m is None or _inv is None or traegt_menge(_k.mengen):
                _ersetzt.append(_k)
                continue
            _ersetzt.append(kennzahlen_aus_mengen(mengen_aus_tageswerten(
                _inv,
                strom_kwh=_m.strom_kwh,
                waerme_kwh=waerme_gesamt_kwh(
                    _m.waerme_kwh or None,
                    _m.heizung_kwh + _m.warmwasser_kwh,
                    None,
                ),
                heizung_kwh=_m.heizung_kwh,
                warmwasser_kwh=_m.warmwasser_kwh,
                strom_heizen_kwh=_m.strom_heizen_kwh,
                strom_warmwasser_kwh=_m.strom_warmwasser_kwh,
                kaelte_kwh=_m.kaelte_kwh,
                modus_strom_kuehlen_kwh=_m.modus_strom_kuehlen_kwh,
                funktionsfremd_abzug_kwh=_m.funktionsfremd_abzug_kwh,
                waerme_ist_gesamt=bool(_m.waerme_kwh),
                # E4d: gemessene 0 (mindestens ein Tag mit Wert) — „kein Betrieb" statt „kein Zähler".
                strom_gemessen="strom_kwh" in getattr(_m, "gemessen", ()),
                waerme_gemessen=bool({"waerme_kwh", "heizung_kwh", "warmwasser_kwh"}
                                     & set(getattr(_m, "gemessen", ()))),
            )))
        _wp_kennzahlen_je_geraet = _ersetzt
    # ── S5 anlagenweit (WK-16i, N-503): die Eingänge der Funktions-Zahlen ──
    #
    # ⛔ **Sie kamen bis zum 15.09.2026 ausschließlich aus den Monats-Fakten**,
    # und der laufende Monat hat keine `Monatsdaten`-Zeile. Im Kasten stand
    # deshalb *„Strom nicht getrennt je Funktion gemessen → Getrennte
    # Strommessung einschalten"*, während die Tabelle **direkt darunter** 5,58
    # und 3,32 zeigte (r28/Prüfstand, September 2026) — zwei Leser, ein
    # Bildschirm (dieselbe Klasse wie N-492).
    #
    # ⭐ **S5 gilt für alle anlagenweiten Wärme/Klima-Eingänge, nicht nur für
    # die Kacheln.** Trägt die Monatszeile eine Menge, gilt sie — sonst
    # entstehen die Eingänge aus **denselben** Geräte-Mengen, die die Tabelle
    # oben speist. Die Faltung steht an EINER Stelle
    # (`waerme_klima_block.funktions_eingaenge_der_anlage`); hier wird sie nur
    # gerufen, und beide Herkünfte tragen dieselben Feldnamen (F-56).
    _wp_zeile_traegt = monats_fakt is not None and traegt_menge(monats_fakt.wp)
    _wp_funktion = (
        monats_fakt.wp if _wp_zeile_traegt
        else funktions_eingaenge_der_anlage(_wp_kennzahlen_je_geraet)
    )
    # ── SOLL §3.2b (10.09.2026): WELCHE Funktionen die Verletzung trifft ──
    #
    # Bis dahin galt sie unbesehen fuer beide Zeilen — bei einer Waermepumpe
    # neben einer Split-Klimaanlage standen deshalb drei Striche, waehrend der
    # Komponenten-Hub fuer dasselbe Geraet 3,0 und 2,5 auswies.
    #
    # ⚠ Die Gleichheit wird je Funktion aus den BEITRAEGEN gezaehlt, nicht aus
    # der Bauart: `strom_warmwasser_kwh` wird ungefiltert gelesen, und
    # `heizenergie_kwh` traegt kein `!luft_luft` — beides kann eine Klimaanlage
    # tragen. Nur Gleichheit in BEIDE Richtungen schuetzt vor einer falschen
    # Zahl (zu hoch wie zu niedrig).
    #
    # ⭐ **Aus derselben Quelle wie die Mengen darüber** (WK-16i). ⚠ Ein Dict aus
    # lauter `None` wirkt wie das frühere `None` (`abgrenzung_je_funktion` legt
    # `global_grund` dann ohnehin auf alle Funktionen); neu ist allein, dass der
    # Rückfall die Deckung **beantworten** kann, statt sie offenzulassen.
    _wp_deckung_je_funktion = {
        f: _wp_funktion.deckung_je_funktion(f) for f in ARBEITSZAHL_FUNKTIONEN
    }
    _wp_abgrenzung_je_funktion = abgrenzung_je_funktion(
        abgrenzung_stoerung=(
            monats_fakt.wp.abgrenzung_stoerung if monats_fakt is not None else None
        ),
        bauarten_gemischt=(
            monats_fakt is not None and monats_fakt.wp.bauarten_gemischt
        ),
        geraete_ohne_waerme=(
            monats_fakt is not None
            and monats_fakt.wp.waerme_deckt_nicht_alle_geraete
        ),
        zeitraum_versetzt=_wp_seiten_teilzeitraum == 1,
        deckung_je_funktion=_wp_deckung_je_funktion,
    )
    _wp_strom_ohne_waerme, _wp_geraete_ohne_waerme = schranken_eingang(
        _wp_kennzahlen_je_geraet,
    )
    wp_abgrenzung_sperrt = abgrenzungs_grund(
        abgrenzung_stoerung=(
            monats_fakt.wp.abgrenzung_stoerung if monats_fakt is not None else None
        ),
        zeitraum_versetzt=_wp_seiten_teilzeitraum == 1,
        geraete_verschieden=(
            monats_fakt is not None and monats_fakt.wp.geraete_verschieden
        ),
    )
    from backend.core.berechnungen.waermepumpe_kennzahl import kein_betrieb_grund_der_achsen
    from backend.services.waerme_klima_block import achsen_der_anlage

    wp_arbeitszahl = systemarbeitszahl(
        wp_waerme, wp_strom,
        # E4d (Bauplan §8a): Strom 0 und Wärme 0 GEMESSEN (beide nicht None — die Quellen-Kaskade führt eine 0 nur, wo
        # gemessen wurde) ⇒ Stufe 3 „kein Heizbetrieb …" statt „kein Stromverbrauch erfasst".
        kein_betrieb_grund=kein_betrieb_grund_der_achsen(achsen_der_anlage(_wp_kennzahlen_je_geraet)),
        waerme_abgeleitet_kwh=wp_waerme_abgeleitet_kwh,
        kuehlstrom_kwh=wp_strom_funktionsfremd_kwh,
        strom_ohne_waerme_kwh=_wp_strom_ohne_waerme,
        geraete_ohne_waerme=_wp_geraete_ohne_waerme,
        abgrenzung_verletzt=wp_abgrenzung_sperrt,
    )
    # B4 (C-2): Herkunft und Vorbehalt — der Faktor nur bei EINER Wärmepumpe
    # (bei mehreren gibt es keinen einen Faktor, der Text nennt dann die Regel).
    from backend.core.berechnungen.modus_split import heiz_effizienz_gepflegt
    from backend.core.berechnungen.waermepumpe_kennzahl import (
        ersparnis_vorbehalt as _ersparnis_vorbehalt,
        waerme_herkunft as _waerme_herkunft,
    )
    _wp_invs_alle = [i for i in investitionen if i.typ == "waermepumpe"]
    _wp_abgeleitet = wp_waerme_abgeleitet_kwh > 0
    wp_waerme_herkunft = _waerme_herkunft(
        _wp_abgeleitet,
        heiz_effizienz_gepflegt(_wp_invs_alle[0].parameter)
        if (_wp_abgeleitet and len(_wp_invs_alle) == 1) else None,
    )
    wp_ersparnis_vorbehalt = _ersparnis_vorbehalt(
        waerme_abgeleitet=_wp_abgeleitet,
        abgrenzung=monats_fakt.wp.abgrenzung_stoerung if monats_fakt is not None else None,
    )

    if allgemein_tarif:
        # ⭐ N-609 (04.10.2026): auch ohne Gerätezeile ist die WP-Ersparnis die Σ der Gerätezeilen — je
        # Wärmepumpe mit IHREN Parametern über die eine Zeilenregel (`wp_ersparnis_zeile`). Hier stand bis dahin
        # ein Aggregat über die Summenmengen mit dem Parametersatz der ERSTEN Wärmepumpe: laufender Monat mit
        # zwei WP 1,44 statt 5,76 €, Juni ohne Abschluss 14,40 statt 57,60 €. Gibt es T-Konto-Zeilen, gewinnen
        # sie danach (`wp_aggregat_aus_zeilen`) — dieser Wert ist der Monat OHNE Gerätezeile.
        #
        # Die Mengen je Gerät kommen aus der Quellen-Kaskade (`resolved`, K3/D1-Vorauflösung je Gerät) — NICHT aus
        # `wp_geraete` der Antwort: die gibt es nur im laufenden Monat und dort aus der Tagesebene, die erst ab
        # ihrem ersten Tag misst (gemessen: Juni None, Tagesspur ab 02.07. 10,08 statt 5,76 €).
        #
        # Ohne eigenen WP-Tarif gilt der allgemeine Bezugspreis — bei flexiblem
        # Tarif also der Monatsdurchschnitt, wie im per-Investition-Block
        # (`wp_p`) schon immer. N-267: ein eigener WP-Tarif kann eigene Fenster
        # tragen (§14a-Nachttarife), deshalb ueber denselben Helfer.
        wp_preis_cent = await _zeittarif_preis(
            db, anlage_id, jahr, monat, tarife.get("waermepumpe"),
            netzbezug_preis_effektiv_cent, _zt_cache,
        )
        _resolved = resolved or {}
        _wp_aktiv = [
            i for i in investitionen
            if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
        ]
        _zeilen = []
        for _inv in _wp_aktiv:
            _w = _resolved.get(f"inv_{_inv.id}_{_WP_WAERME_D1_SUFFIX}")
            _s = _resolved.get(f"inv_{_inv.id}_{_WP_STROM_K3_SUFFIX}")
            # E-B: Kühlen ersetzt keine Heizung (#263 K-2). Der Kühlanteil je Gerät aus der Tagesebene; bei genau
            # EINER Wärmepumpe ist der anlagenweite Kühlanteil der ihre.
            _tm = (_tages_wp_mengen or {}).get(str(_inv.id))
            _kg = (
                monats_fakt.wp.je_geraet.get(_inv.id)
                if kanal_wp_zeilen and monats_fakt is not None else None
            )
            _kuehl = (
                _kg.strom_kuehlen_kwh if _kg is not None      # E4d: der Kühlanteil des Geräts aus den Kanal-Zeilen
                else _tm.modus_strom_kuehlen_kwh if _tm is not None
                else ((get_val("wp_modus_kuehlen_kwh") or 0.0) if len(_wp_aktiv) == 1 else 0.0)
            )
            _waerme_g = _w[0] if _w is not None else None
            _strom_g = _s[0] if _s is not None else None
            _z = wp_ersparnis_zeile(
                waerme_kwh=_waerme_g,
                strom_kwh=_strom_g,
                strom_kuehlen_kwh=_kuehl,
                strompreis_cent=wp_preis_cent,
                parameter=_inv.parameter,
                gaspreis_cent=monats_gaspreis,
                # E4d: die Quellen-Kaskade führt eine WP-0 nur, wo gemessen wurde (`_NULL_IST_MESSWERT_TYPEN`,
                # `_collect_saved_data`) — Strom 0 und Wärme 0 ist hier also „kein Betrieb", Ersparnis 0 €.
                null_ist_kein_betrieb=True,
            )
            if _z is not None:
                _zeilen.append((_inv, _z, _waerme_g, _strom_g))
        if _zeilen:
            wp_ersparnis = round(sum(round(_z.ersparnis_euro, 2) for _, _z, _, _ in _zeilen), 2)
            # Die Herleitung nennt bei mehreren Geräten jedes — dieselbe Form wie `wp_aggregat_aus_zeilen`.
            wp_ersparnis_berechnung_text = "\n".join(
                (f"{_inv.bezeichnung}: " if len(_zeilen) > 1 else "")
                + wp_ersparnis_berechnung(_z, _waerme_g, _strom_g, wp_preis_cent, _inv.parameter)
                for _inv, _z, _waerme_g, _strom_g in _zeilen
            )
        else:
            wp_ersparnis = None
            wp_ersparnis_berechnung_text = None

    # G20-2 (Gernot 2026-07-20): Die eMob-Ersparnis-Aggregation folgt weiter unten
    # als **Summe der Per-Fahrzeug-Ersparnisse** (dieselben Werte wie die
    # investitionen_financials-Zeilen), NACHDEM diese gebaut sind. Der frühere
    # Einmal-Lauf über die Gesamt-km mit dem parameter-Satz des ERSTEN E-Autos
    # (pick_emob_ref_parameter) rechnete bei unterschiedlichem Verbrauch je Fahrzeug
    # falsch (Demo: 167,79 € statt 65,37 + 85,59 = 150,96 €).
    # [[feedback_aggregator_symmetrie]] [[feedback_aggregations_drift]]

    # BKW-Ersparnis wird NICHT separat ausgewiesen — BKW-Erzeugung fließt in
    # pv_erzeugung_total und damit in eigenverbrauch ein → bereits in ev_ersparnis enthalten.
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_wp_abgrenzung_je_funktion", "_wp_funktion", "_wp_kennzahlen_je_geraet", "wp_abgrenzung_verletzt", "wp_arbeitszahl", "wp_ersparnis", "wp_ersparnis_berechnung_text", "wp_ersparnis_vorbehalt", "wp_waerme_abgeleitet_kwh", "wp_waerme_herkunft",) if k in _loc}


async def flags_und_wp_counter(*, anlage_id, db, investitionen, jahr, monat):
    """Komponenten-Flags und WP-Counter pro Monat aus der TagesZusammenfassung (#169/#238).

    Aus `get_aktueller_monat` Zeilen 1537-1618 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 2.
    """
    # ── Komponenten-Flags ──
    # #239 detLAN: pro Monat filtern, nicht pro Anlage. Sonst wird die
    # Sektion (z.B. Wärmepumpe) im Monatsbericht angezeigt, bevor die
    # Investition angeschafft wurde — alle Werte sind dann "—", was den
    # User irritiert ("Investition vor Anschaffung darstellen" #236 P2).
    hat_speicher = any(
        i.typ == "speicher" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_waermepumpe = any(
        i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )

    # ── Issue #169/#238: WP-Counter pro Monat aus TagesZusammenfassung ──
    # Quelle: TagesZusammenfassung.komponenten_starts (JSON, Form
    # {"wp_starts_anzahl": {"<inv_id>": <int>}, "wp_betriebsstunden": {...}}). Pro
    # Tag des Monats werden die Werte aller WP-Investitionen summiert (= Tagessumme
    # der Anlage), daraus max(Tagessumme) und Σ(Tagessumme im Monat). Zeigt was EEDC
    # erfasst hat — Drift gegenüber dem Hersteller-Counter (Cockpit) wird im
    # Daten-Checker ausgewiesen, nicht hier verrechnet. Starts = int, Stunden = float.
    wp_starts_max_tag: Optional[int] = None
    wp_starts_summe_monat: Optional[int] = None
    wp_betriebsstunden_max_tag: Optional[float] = None
    wp_betriebsstunden_summe_monat: Optional[float] = None
    if hat_waermepumpe:
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from sqlalchemy import extract
        wp_invs = [
            i for i in investitionen
            if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
        ]
        wp_inv_id_strs = {str(i.id) for i in wp_invs}
        tz_result = await db.execute(
            select(TagesZusammenfassung.komponenten_starts)
            .where(TagesZusammenfassung.anlage_id == anlage_id)
            .where(extract("year", TagesZusammenfassung.datum) == jahr)
            .where(extract("month", TagesZusammenfassung.datum) == monat)
            .where(TagesZusammenfassung.komponenten_starts.is_not(None))
        )

        def _tagessumme(komp: dict | None, feld: str) -> float:
            """Summe eines Counter-Felds über alle aktiven WP-Investitionen an einem Tag."""
            feld_map = (komp or {}).get(feld) or {}
            tag_sum = 0.0
            for inv_id_str, wert in feld_map.items():
                if inv_id_str in wp_inv_id_strs and isinstance(wert, (int, float)) and wert > 0:
                    tag_sum += float(wert)
            return tag_sum

        starts_tagessummen: list[int] = []
        stunden_tagessummen: list[float] = []
        for (komp_starts,) in tz_result.all():
            s = _tagessumme(komp_starts, "wp_starts_anzahl")
            if s > 0:
                starts_tagessummen.append(int(s))
            h = _tagessumme(komp_starts, "wp_betriebsstunden")
            if h > 0:
                stunden_tagessummen.append(h)
        if starts_tagessummen:
            wp_starts_max_tag = max(starts_tagessummen)
            wp_starts_summe_monat = sum(starts_tagessummen)
        if stunden_tagessummen:
            wp_betriebsstunden_max_tag = round(max(stunden_tagessummen), 1)
            wp_betriebsstunden_summe_monat = round(sum(stunden_tagessummen), 1)


    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox")
        and not ist_dienstlich(i)
        and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_balkonkraftwerk = any(
        i.typ == "balkonkraftwerk" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_sonstiges = any(
        i.typ == "sonstiges" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("hat_balkonkraftwerk", "hat_emobilitaet", "hat_sonstiges", "hat_speicher", "hat_waermepumpe", "wp_betriebsstunden_max_tag", "wp_betriebsstunden_summe_monat", "wp_starts_max_tag", "wp_starts_summe_monat",) if k in _loc}

