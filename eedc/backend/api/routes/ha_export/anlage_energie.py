"""HA-Export, Anlagen-Sensoren — die Energie- und Finanzseite: die Monatszeilen aus den Monats-Fakten (ADR-002/P10) mit
Energie-Summen, Kennzahlen und spezifischem Ertrag, das Finanz-Aggregat (#326) mit sonstigen Positionen und dienstlichen
Ladekosten, die Investitions-KPIs (Mehrkosten N-352, Betriebskosten, Jahres-Ertrag §8/2) und die USt auf den Eigenverbrauch
(N-129/N-130).
"""
# Vorlage 8b des Refactorings grosser Dateien (18.09.2026): Phasen des Rechners
# `ha_export/anlage_sensoren.py::calculate_anlage_sensors` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Rechner orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-ha-export.py` (alte gegen neue Antworten, bitgleich).

from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    berechne_spez_ertrag_annualisiert,
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
    monatsgewichte_aus_pvgis,
    relevante_kosten_aus_investitionen,
)
from backend.services.prognose_auswahl import lade_aktive_prognose
from datetime import date
from backend.services.strompreis_aggregator import lade_preis_aggregate_je_monat
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten, pv_erzeugungs_monate
from backend.core.berechnungen.kapitalrechnung import jahres_ersparnis_euro
from backend.core.berechnungen.investitions_jahresertrag import (
    BEZEICHNUNG_ERTRAGSFELD,
    jahresertrag_posten,
)
from backend.models.investition import ERTRAGSFELD_TYPEN
from backend.core.berechnungen.ergebnis import ErgebnisEingang, berechne_ergebnis
from backend.services.ust_satz import ust_eigenverbrauch_zeitraum


async def monatsfakten_und_energie(*, anlage, db, investitionen, monatsdaten):
    """Preis-Messung und Monats-Fakten laden; PV, sonstige Erzeugung, Einspeisung, Netzbezug, Speicher-Ladung/-Entladung,
    V2H, Eigenverbrauch/Direktverbrauch/Gesamtverbrauch, Autarkie, EV-Quote und der annualisierte spezifische Ertrag.

    Aus `calculate_anlage_sensors` Zeilen 166-285 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # =====================================================================
    # MONATSZEILE AUS DEN MONATS-FAKTEN (ADR-002/P10)
    # =====================================================================
    # Bis 2026-07-31 hat diese Funktion die IMD-Zeilen in VIER getrennten
    # Queries + Schleifen selbst gefaltet (Erzeuger · Speicher · V2H · sonstige
    # Positionen), jede mit ihrer eigenen Filter-Handschrift. Die Rechnung war
    # korrekt — Befund F-5 der Drift-Inventur traf andere Sichten. Umgehängt
    # wird sie trotzdem, weil eine selbst faltende Sicht die nächste Drift-Quelle
    # ist (`docs/KONZEPT-MONATS-FAKTEN.md` §11).
    #
    # Die Schicht lädt Investitionen bewusst OHNE `aktiv`-Vorfilter und
    # entscheidet je Monat über `ist_aktiv_im_monat` (#123: historische
    # Kennzahlen dürfen später stillgelegte Komponenten nicht rückwirkend
    # ausblenden). Der `aktiv_jetzt()`-Vorfilter oben bleibt für alles, was einen
    # HEUTIGEN Zustand beschreibt (kWp, Investitionssummen, Komponenten-Listen);
    # die MENGEN kommen ab jetzt aus der Schicht. Das ist derselbe Schnitt wie
    # im Cockpit — und es ist eine bewegte Zahl für Anlagen mit stillgelegter
    # Komponente (s. Übergabe N-11).
    _tarif_cache: dict[date, dict] = {}
    # Wie der Tarif-Cache: EINE gruppierte Preismessung für Schicht und Finanzzeile.
    _preis_messung = await lade_preis_aggregate_je_monat(db, anlage.id)
    fakten = await lade_monats_fakten(
        db, anlage.id, tarif_cache=_tarif_cache, preis_messung=_preis_messung,
    )

    # PV je Monat über den Read-time-SoT (Messwerte + Aggregat-Lückenfüllung)
    # statt einer rohen IMD-Summe. Die rohe Summe kannte das Anlagen-Aggregat
    # gar nicht: eine Anlage, deren frühe Monate nur als Gesamtwert vorliegen
    # (Umstellung auf Pro-String-Messung mitten in der Historie), verlor diese
    # Monate im PV-Sensor, im spezifischen Ertrag und in den Finanzzeilen.
    #
    # DI-2-B: Erzeuger hinter dem EINEN Hauszähler zählen in die EV-/Autarkie-/
    # CO₂-Bilanz — deckungsgleich mit dem Cockpit (Layer-SoT
    # `erzeugung_hinter_zaehler_kwh`, v3.45.4):
    #   • Balkonkraftwerk zählt als PV (Cockpit-Konvention) → in `pv_erzeugung`.
    #   • Sonstige Erzeuger (Mini-BHKW/KWK) speisen ebenfalls hinter den Zähler →
    #     zählen in EV/Autarkie, bleiben aber aus den PV-eigenen Kennzahlen
    #     (spez. Ertrag/PR) und aus der PV-Erzeugungs-Anzeige draußen.
    # Falle 1 der S1-Übergabe: `erzeugung.pv_kwh` für die PV-Achse und die
    # Finanz-Zeile, `erzeugung.hinter_zaehler_kwh` für die Bilanz.
    pv_erzeugung = sum(f.erzeugung.pv_kwh for f in fakten)
    sonstiges_erzeugung = sum(f.sonstiges.erzeugung_kwh for f in fakten)

    # Fallback: Falls keine InvestitionMonatsdaten vorhanden, berechne aus Einspeisung
    einspeisung = sum(m.einspeisung_kwh or 0 for m in monatsdaten)
    if pv_erzeugung == 0:
        # Schätzung: Erzeugung ≈ Einspeisung + geschätzter Eigenverbrauch
        pv_erzeugung = einspeisung + sum(m.eigenverbrauch_kwh or 0 for m in monatsdaten)

    # #304: netzbezug ist ein Zählerwert aus Monatsdaten (legitim). Eigen-/
    # Direkt-/Gesamtverbrauch NICHT aus den berechneten Legacy-Monatsdaten-
    # Feldern lesen — die bleiben bei IMD-basierten Setups leer (moderne
    # Quellen schreiben in InvestitionMonatsdaten), wodurch die Eigenverbrauchs-
    # quote zusammenbricht (2,2 % statt ~40 %). Sie werden unten zentral aus
    # PV(IMD) + Speicher(IMD) + Zählerwerten über den SoT-Helper berechnet.
    netzbezug = sum(m.netzbezug_kwh or 0 for m in monatsdaten)

    # Speicher-Summen aus den Monats-Fakten (kanonisch über `imd_typ_beitrag`)
    # statt Legacy Monatsdaten. Die frühere Handschrift las die Roh-Schlüssel
    # `ladung_kwh`/`entladung_kwh` direkt (P6-Klasse).
    batterie_ladung = sum(f.speicher.ladung_kwh for f in fakten)
    batterie_entladung = sum(f.speicher.entladung_kwh for f in fakten)

    # Fallback auf Legacy wenn keine InvestitionMonatsdaten
    if batterie_ladung == 0 and batterie_entladung == 0:
        batterie_ladung = sum(m.batterie_ladung_kwh or 0 for m in monatsdaten)
        batterie_entladung = sum(m.batterie_entladung_kwh or 0 for m in monatsdaten)

    # V2H (E-Auto → Haus) wird wie Speicher-Entladung als Eigenverbrauch gezählt.
    # Dienstwagen sind darin nicht mehr enthalten — die Schicht filtert sie,
    # die frühere Schleife hier nicht ([[feedback_dienstwagen_alle_checks]]).
    v2h_entladung = sum(f.emob.v2h_entladung_kwh for f in fakten)

    # #304: Eigenverbrauch/Direktverbrauch/Gesamtverbrauch + Quoten zentral über
    # den SoT-Helper aus IMD-gesourcten Energiemengen (PV + Speicher + V2H) und
    # den Zählerwerten (Einspeisung/Netzbezug) — kanonische Formel, deckungs-
    # gleich mit cockpit/uebersicht.py.
    # DI-2-B: Netzpunkt-Bilanz-Eingang = PV(inkl. BKW) + sonstige Erzeuger,
    # deckungsgleich mit dem Cockpit (`erzeugung_bilanz`, uebersicht.py:416).
    # `pv_erzeugung` selbst (inkl. BKW, ohne BHKW) bleibt für die PV-eigenen
    # Kennzahlen (spez. Ertrag) und die PV-Erzeugungs-Anzeige.
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv_erzeugung, sonstiges_erzeugung)
    kennzahlen = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=erzeugung_bilanz,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        speicher_ladung_kwh=batterie_ladung,
        speicher_entladung_kwh=batterie_entladung,
        v2h_entladung_kwh=v2h_entladung,
        abgabe_dritte_kwh=sum(f.sonstiges.abgabe_kwh for f in fakten),
    )
    direktverbrauch = kennzahlen.direktverbrauch_kwh
    eigenverbrauch = kennzahlen.eigenverbrauch_kwh
    gesamtverbrauch = kennzahlen.gesamtverbrauch_kwh
    autarkie = kennzahlen.autarkie_prozent
    ev_quote = kennzahlen.eigenverbrauchsquote_prozent
    # Spezifischer Ertrag — annualisiert über den SoT-Helper, deckungsgleich
    # mit der Cockpit-Kachel (Rainer-PN 2026-06-11: die alte Roh-Division
    # Lebenszeit-kWh ÷ heutiges kWp lieferte einen über die Laufzeit
    # aufkumulierten Wert, ~3× Jahreswert bei 3 Jahren Historie).
    # Aus derselben Quelle wie `pv_erzeugung`: jeder Monat mit aufgelöster PV
    # zählt, gemessen ODER über das Aggregat gefüllt. Der frühere
    # Zwei-Wege-Aufbau (IMD-Monate, sonst Monate mit Legacy-PV>0) ließ bei
    # gemischter Historie die Aggregat-Monate aus und machte den spezifischen
    # Ertrag dadurch zu hoch.
    # ⭐ N-621 H1 (Entscheid des Masters 04.10.2026): dieselbe Monatsmenge wie die
    # Kachel in *Cockpit → Übersicht* — EINE Funktion (`monats_fakten.pv_erzeugungs_monate`).
    # Bis dahin zählte hier nur ein Monat mit Modul-Eintrag: Monate, in denen nur ein
    # Balkonkraftwerk erzeugt hat, fehlten im Nenner, während ihre kWh in `pv_erzeugung`
    # standen (reine BKW-Anlage: 143,75 statt 586,73 kWh/kWp).
    spez_covered_months = pv_erzeugungs_monate(fakten)
    spez_gewichte = None
    if spez_covered_months:
        pvgis = await lade_aktive_prognose(db, anlage.id)
        spez_gewichte = monatsgewichte_aus_pvgis(
            pvgis.monatswerte if pvgis else None
        ) or None
    spez_ertrag = berechne_spez_ertrag_annualisiert(
        pv_erzeugung_kwh=pv_erzeugung,
        covered_months=spez_covered_months,
        investitionen=investitionen,
        fallback_kwp=anlage.leistung_kwp or 0.0,
        monatsgewichte=spez_gewichte,
    )
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("_preis_messung", "_tarif_cache", "autarkie", "batterie_entladung", "batterie_ladung", "direktverbrauch", "eigenverbrauch", "einspeisung", "erzeugung_bilanz", "ev_quote", "fakten", "gesamtverbrauch", "netzbezug", "pv_erzeugung", "spez_ertrag",) if k in _loc}


async def finanz_aggregat(*, _preis_messung, _tarif_cache, anlage, db, fakten, strompreis):
    """Sonstige Positionen, Erzeuger-Erlöse und dienstliche Ladekosten aus den Fakten; Einspeise-Erlös, EV-Ersparnis und
    Netto-Ertrag über `berechne_finanz_aggregat` (#326, Monats-Tarif P8).

    Aus `calculate_anlage_sensors` Zeilen 286-353 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # Finanzen (#326) — über den SoT-Helper `berechne_finanz_aggregat`, damit
    # HA-Export dieselbe Netto-Ertrag-Zahl liefert wie Cockpit/Jahresbericht.
    # Einspeise-Erlös §51-bereinigt + EV-Ersparnis pro Monat mit dem Monats-
    # Flexpreis (`resolve_netzbezug_preis_cent` → Fallback fixer Tarif). Anwender
    # ohne Strompreis-Sensor (m_neg=None) sehen die alte ungekürzte Berechnung;
    # bei vorhandenem Tages-Aggregat wird die in Negativpreis-Stunden
    # eingespeiste kWh-Menge unvergütet. Sonstige (manuell gepflegt) wie im
    # Cockpit im Netto-Ertrag.
    # Sonstige Positionen: aus den Monats-Fakten — sie falten IMD-Positionen
    # (typ-unabhängig, #310) UND die Basis-Positionen der Monatsdaten-Zeile
    # (G19-1) an einer Stelle, gleiche Netto-Faltung wie Cockpit/Jahresbericht.
    sonstige_netto_gesamt = sum(f.sonstiges.netto_euro for f in fakten)
    # Konzept §9 Weg 2 — eigener Summand neben dem Anlagen-Einspeiseerlös.
    erzeuger_erloes_gesamt = sum(f.sonstiges.einspeise_erloes_euro for f in fakten)
    # F-19: die AUSGABEN gehen in den Kapitaleinsatz. Die dienstlichen
    # Ladekosten weiter unten gehören ausdrücklich nicht hierher — sie sind
    # laufender Aufwand, kein eingesetztes Kapital.
    sonstige_ausgaben_gesamt = sum(f.sonstiges.ausgaben_euro for f in fakten)
    # §8/3: dasselbe für die Ertragsseite — gebraucht, um die Projektion der
    # Jahres-Ersparnis unten von den gepflegten Positionen zu befreien.
    # Bauschritt 7 (2026-08-10): und sie **mindern den Kapitaleinsatz**. Der
    # Sensor `netto_ertrag_euro` behält beide Seiten (Zeitraum-Bilanz).
    sonstige_ertraege_gesamt = sum(f.sonstiges.ertraege_euro for f in fakten)

    # Dienstliche Ladekosten — bis 2026-07-31 hat der HA-Export sie als einzige
    # der drei Sichten **gar nicht** abgezogen (N-13): der Sensor
    # `netto_ertrag_euro` stand bei Dienstwagen-Anlagen über der Cockpit-Kachel,
    # auf die er sich bezieht. Gleiche Formel, gleicher Layer-SoT
    # (ADR-001) wie Cockpit/Übersicht und Aussichten; die Mengen kommen aus den
    # Monats-Fakten (Dienstwagen-Filter + PV/Netz-Split, P10).
    sonstige_netto_gesamt -= berechne_dienstliche_ladekosten(
        DienstlicheLadungZeile(
            ladung_pv_kwh=f.emob.dienstlich_ladung_pv_kwh,
            ladung_netz_kwh=f.emob.dienstlich_ladung_netz_kwh,
            netzbezug_preis_cent=f.tarif.netzbezug_preis_cent,
            wallbox_preis_cent=f.tarif.wallbox_preis_effektiv_cent,
        )
        for f in fakten
    ).gesamt_euro

    einspeise_erloes = 0
    ev_ersparnis = 0
    # Ohne Tarif gibt es keinen bewerteten Strom — dann tragen nur die Sonstigen Positionen (wie bisher: auch der
    # Erzeuger-Erlös zählte in diesem Fall nicht). Der Netto-Ertrag selbst entsteht in `investitionen_und_ust` über
    # die Ergebnis-Leiter (03.10.2026), sobald die USt feststeht.
    bkw_ersparnis = 0.0
    erzeuger_erloes = 0.0
    if strompreis:
        # #326: FinanzMonatsZeile über den gemeinsamen Builder (einzige erlaubte
        # Konstruktions-Stelle, Wächter) — er löst den Tarif PRO MONAT auf
        # (historische Tarife via gueltig_ab/gueltig_bis), nicht den neuesten
        # Strompreis für alle Jahre. Deckungsgleich mit Cockpit/Jahresbericht
        # (rilmor-mhrs: Jahres-Tarife 23,90→32,80 ct). Die Eingabe entsteht aus
        # dem Monats-Fakt (P10) statt aus fünf site-eigenen Maps; `pv_kwh` darin
        # ist „Module + BKW" (P9); fehlt einem Modul der Wert ohne Anlagenwert, trägt
        # sie seit N-626 die vorhandenen Werte. Nur Monate MIT Zählerzeile — ohne gemessene Einspeisung/Bezug
        # gibt es keine Finanz-Zeile.
        finanz_zeilen: list[FinanzMonatsZeile] = [
            await baue_finanz_zeile(
                db, anlage.id, finanz_zeile_eingabe(f), tarif_cache=_tarif_cache,
                preis_messung=_preis_messung,
            )
            for f in fakten if f.meta.hat_zaehlerzeile
        ]
        _finanz = berechne_finanz_aggregat(
            finanz_zeilen, sonstige_netto_euro=sonstige_netto_gesamt,
            erzeuger_erloes_euro=erzeuger_erloes_gesamt
        )
        einspeise_erloes = _finanz.einspeise_erloes_euro
        ev_ersparnis = _finanz.ev_ersparnis_euro
        bkw_ersparnis = _finanz.bkw_ersparnis_euro
        erzeuger_erloes = _finanz.erzeuger_erloes_euro
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("bkw_ersparnis", "einspeise_erloes", "erzeuger_erloes", "ev_ersparnis", "sonstige_ausgaben_gesamt", "sonstige_ertraege_gesamt", "sonstige_netto_gesamt",) if k in _loc}


def investitionen_und_ust(
    *, anlage, fakten, investitionen, monatsdaten, alle_investitionen,
    einspeise_erloes, ev_ersparnis, bkw_ersparnis, erzeuger_erloes, sonstige_netto_gesamt,
):
    """Investitionssumme, relevante Kosten (Layer-SoT, N-352), Betriebskosten und Jahres-Ertrag der heute aktiven
    Investitionen (§8/2), USt auf den Eigenverbrauch je Kalenderjahr (N-129/N-130) — mindert den Netto-Ertrag.

    Aus `calculate_anlage_sensors` Zeilen 354-461 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # CO2 (DI-2): der HA-Sensor „CO2 Einsparung" trägt jetzt die volle
    # Cockpit-Bilanz (PV-Eigenverbrauch + WP + E-Mobilität) statt nur
    # `pv_erzeugung × f_strom`. Berechnung weiter unten, nachdem WP- und
    # E-Mob-Aggregate stehen (kanonischer Helper `berechne_co2_bilanz`).

    # Investitions-KPIs berechnen
    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    # N-352: über den Layer-SoT, nicht als eigene Form daneben. Hier stand bis
    # 2026-08-30 `Σ gesamt − Σ alternativ` — **ungeklemmt und anlagenweit**,
    # wortgleich die Form, die N-136 im Jahresbericht-PDF behoben hat. Der SoT
    # klemmt **je Position**; trägt eine Position eine teurere Alternative (ein
    # Verbrenner gegen ein E-Auto ist der Regelfall), zog ihr Überschuss die
    # Mehrkosten der **anderen** Positionen herunter.
    # ⚑ DAS TRAF ZWEI AUSGELIEFERTE SENSOREN: `roi_prozent` zu hoch und
    # `amortisation_jahre` zu kurz (an der Probe gemessen: 7,81 statt 10,42
    # Jahre). Die Korrektur ist eine **Wertänderung** und als solche gemeldet.
    relevante_kosten = relevante_kosten_aus_investitionen(investitionen)
    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in investitionen)
    # §8/2: das Gegenstück auf der Ertragsseite. `investitionen` ist bereits
    # `aktiv_jetzt()`-gefiltert (heutiger Zustand), es fehlt nur die Typ-Grenze
    # — nur dort wird das Feld gepflegt und vom ROI-Dashboard gelesen. Ohne
    # diesen Summanden trügen die HA-Sensoren `jahres_ersparnis_euro`,
    # `roi_prozent` und `amortisation_jahre` eine andere Zahl als die
    # Oberfläche, sobald jemand einen Jahres-Ertrag pflegt.
    # §9.2 Geldseite (11c): über denselben SoT wie ROI-Dashboard und
    # Aussichten. `investitionen` ist bereits `aktiv_jetzt()`-gefiltert
    # (`:421`) — ein Sensor ist eine Prognose, er zählt nur, was heute läuft;
    # das ROI-Dashboard filtert bewusst anders (#123).
    #
    # ⛔ **Hier zählt NUR der geschätzte Posten extra — und das ist der
    # Unterschied zu den Aussichten.** Der gemessene Abgabe-Erlös steckt in
    # dieser Sicht bereits in `bilanz_ohne_sonstige` (er ist seit `:602` Teil
    # von `_finanz.netto_ertrag_euro`) und würde als zweiter Summand doppelt
    # zählen. **Gemessen am 06.09.2026:** ohne diese Grenze meldete der Sensor
    # `jahres_ersparnis_euro` **960 € statt 480 €** — die Probe
    # `test_abgabe_geldseite_drei_sichten.py` hat es beim ersten Lauf gefangen.
    # Die Aussichten haben das Problem nicht: dort ist der Erlös in keiner
    # anderen Prognose-Größe enthalten.
    #
    # ⚑ Der SoT wird trotzdem gebraucht, und zwar für den **Vorrang**: Pflegt
    # jemand an einem Abgabe-Gerät BEIDES, liefert `jahresertrag_posten` den
    # gemessenen Posten — dessen Bezeichnung filtern wir hier heraus, und das
    # statische „Ertrag/Jahr" desselben Geräts zählt damit korrekt NICHT mit.
    _ertrag_posten = [
        p
        for i in investitionen
        if i.typ in ERTRAGSFELD_TYPEN
        for p in (jahresertrag_posten(i, fakten),)
        if p is not None and p.bezeichnung == BEZEICHNUNG_ERTRAGSFELD
    ]
    jahres_ertraege_ges = jahres_ersparnis_euro(_ertrag_posten)

    # USt auf den Eigenverbrauch — der EINE Eingang `services/ust_satz.py` (G1/E9, 03.10.2026): je Kalenderjahr die IM
    # JAHR aktiven Investitionen (deshalb `alle_investitionen` — `investitionen` ist hier `aktiv_jetzt()`-gefiltert),
    # die abgeschlossenen Monate mit aktivem Erzeuger und die Σ der Monats-Eigenverbräuche. Bis dahin: heute aktive
    # Investitionen, Perioden-EV und ein Monatsdaten-Rückfall je Jahr — eine dritte Lesart desselben Satzes.
    ust_eigenverbrauch = ust_eigenverbrauch_zeitraum(anlage, alle_investitionen, fakten)
    # Stufe 1 der Ergebnis-Leiter — dieselbe Funktion wie Übersicht, PDF und Cockpit → Monat/Jahr (Sensor
    # `netto_ertrag_euro`). Die Herleitung geht als `berechnung`-Attribut mit (alle Posten, nicht nur drei).
    _leiter = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=einspeise_erloes, ev_ersparnis=ev_ersparnis, bkw_rest_ersparnis=bkw_ersparnis,
        erzeuger_erloes=erzeuger_erloes, sonstige_netto=sonstige_netto_gesamt, ust_anteil=ust_eigenverbrauch,
    ))
    netto_ertrag = _leiter.netto_ertrag
    netto_herleitung = _leiter.herleitung["netto_ertrag"]
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("betriebskosten_ges", "investition_gesamt", "jahres_ertraege_ges", "netto_ertrag", "netto_herleitung", "relevante_kosten",) if k in _loc}

