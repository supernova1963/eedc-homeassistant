"""Monatsdaten — die Phasen der Monatszeile von `GET /monatsdaten/aggregiert` (RF-27, 14.10.2026).

Reiner Umzug aus `api/routes/monatsdaten.py::list_monatsdaten_aggregiert`: der Anfrage-Kontext, die Finanzen und die
Arbeitszahl eines Monats und die Felder der Zeile in vier Gruppen (Reihenfolge der Antwort). Die Route, die Lader und
`_monatszeile`, die die Gruppen zur Antwortzeile fügt, bleiben in `monatsdaten.py`; dieses Modul kennt sie nicht.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen.anlagen_kwp import anlagen_kwp as berechne_anlagen_kwp
from backend.core.berechnungen.pv_verteilung import wandlungsverluste_prozent
from backend.core.berechnungen.waermepumpe_kennzahl import abgrenzungs_grund, arbeitszahl
from backend.core.berechnungen import berechne_finanz_aggregat, berechne_netzbezug_kosten
from backend.core.berechnungen.ergebnis import ErgebnisEingang, berechne_ergebnis, ust_anteil_euro
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe


@dataclass
class _TabellenKontext:
    """Was alle Monate EINER Anfrage teilen — im Orchestrator geladen, von den Phasen nur gelesen."""
    db: AsyncSession
    anlage_id: int
    tarif_cache: dict[date, dict]
    preis_messung: Any
    inv_rows: Any
    _ust_saetze: dict
    _ust_monate: set
    zaehler_stand_je_monat: dict[tuple[int, int], dict[str, float]]
    temperatur_je_monat: dict[tuple[int, int], float]


async def _finanzen_des_monats(kx: _TabellenKontext, f, netzbezug: float) -> tuple:
    """Finanz-Aggregat, Netzbezugskosten, USt-Anteil und Netto-Ertrag des Monats — Phase von `_monatszeile`."""
    # ── Finanzen dieses Monats über den SoT (N-22) ───────────────────────
    # `berechne_finanz_aggregat` über EINE Zeile: derselbe Weg, den der
    # Tages-Pfad derselben Tabelle längst geht (`tage_werte.py`).
    finanz_zeile = await baue_finanz_zeile(
        kx.db, kx.anlage_id, finanz_zeile_eingabe(f), tarif_cache=kx.tarif_cache,
        preis_messung=kx.preis_messung,
    )
    # §9.2 Geldseite (E1, Entscheid 06.09.2026): der gepflegte Erloes eines
    # Erzeugers mit eigenem Vergütungssatz bzw. eines Geräts der Kategorie
    # *Abgabe an Dritte* ist der FÜNFTE Summand des Netto-Ertrags
    # (`finanz_aggregat.py`). Cockpit → Jahr, HA-Sensor, PDF und Aussichten
    # führen ihn längst; diese Route tat es als einzige nicht — dieselbe
    # Kachel nannte deshalb in zwei Sichten zwei Zahlen (#402, rilmor-mhrs:
    # „nicht mehr in den Grafen darüber").
    # ⛔ Er geht NICHT in `einspeise_erloes_euro`: der bewertet den
    # Anlagenzähler mit dem EINEN Satz der Anlage, und ein eigener Satz ist
    # per Definition ein anderer (§8/9).
    finanz = berechne_finanz_aggregat(
        [finanz_zeile],
        erzeuger_erloes_euro=f.sonstiges.einspeise_erloes_euro,
    )
    netzbezug_kosten = berechne_netzbezug_kosten(
        netzbezug, f.tarif.netzbezug_preis_cent, f.tarif.grundpreis_euro_monat
    )
    _satz = kx._ust_saetze.get(f.jahr)
    _ust = (
        # N-588 (F4): die USt bemisst die entnommene Menge — der Eigenverbrauch ohne Wandlungsverluste.
        ust_anteil_euro(finanz.eigenverbrauch_ohne_verluste_kwh, _satz.euro_je_kwh)
        if _satz is not None and f.schluessel in kx._ust_monate else None
    )
    ust_eigenverbrauch = _ust if _ust is not None else 0.0
    # Stufe 1 der Ergebnis-Leiter — dieselbe Definition wie Cockpit, Übersicht, PDF und HA-Sensor (GLOSSAR
    # „Netto-Ertrag (PV)"), seit 03.10.2026 MIT den Sonstigen Positionen des Monats (A1, Entscheid Fable-Master).
    # Bis dahin fehlten sie hier und *Auswertungen → Finanzen* schlug sie aus der Komponenten-Zeitreihe selbst auf.
    netto_ertrag = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=finanz.einspeise_erloes_euro, ev_ersparnis=finanz.ev_ersparnis_euro,
        bkw_rest_ersparnis=finanz.bkw_ersparnis_euro, erzeuger_erloes=finanz.erzeuger_erloes_euro,
        sonstige_netto=f.sonstiges.netto_euro,
        # N-633: derselbe Posten wie Cockpit, Übersicht, PDF und HA-Sensor (Monats-Fakten).
        dienstliche_ladekosten=f.emob.dienstliche_ladekosten_euro, ust_anteil=ust_eigenverbrauch,
    )).netto_ertrag
    return finanz, netzbezug_kosten, ust_eigenverbrauch, netto_ertrag


def _arbeitszahl_des_monats(f):
    """Die Arbeitszahl des Monats mit Grund — Phase von `_monatszeile`."""
    # ADR-002/P12: Die Arbeitszahl dieses Monats — aus dem Layer, mit allen
    # R2-Sperren, die Cockpit und Hub auch ziehen.
    #
    # ⚠ `zeitraum_versetzt` gehört hier **nicht** hinein, und das ist keine
    # Lücke: Diese Route liest **eine** Quelle (die Monats-Fakten). Q und E
    # stammen damit aus demselben Zeitraum; die Vier-Quellen-Auflösung, in
    # der ein Versatz überhaupt entstehen kann, gibt es nur in
    # `api/routes/aktueller_monat.py`.
    _wp_az = arbeitszahl(
        f.wp.waerme_kwh, f.wp.strom_kwh,
        waerme_abgeleitet_kwh=f.wp.waerme_abgeleitet_kwh,
        # SOLL-§9-E7/Option A: der **Abzug**, nicht die Menge.
        strom_funktionsfremd_kwh=f.wp.modus_strom_funktionsfremd_abzug_kwh,
        abgrenzung_verletzt=abgrenzungs_grund(
            abgrenzung_stoerung=f.wp.abgrenzung_stoerung,
            bauarten_gemischt=f.wp.bauarten_gemischt,
            geraete_ohne_waerme=f.wp.waerme_deckt_nicht_alle_geraete,
            # N-441: Waerme von einem Geraet, Strom von einem anderen.
            geraete_verschieden=f.wp.geraete_verschieden,
        ),
    )
    return _wp_az


def _zeile_kopf(kx: _TabellenKontext, f, md, einspeisung: float, netzbezug: float) -> dict[str, Any]:
    """Felder der Zeile, Teil 1: Schlüssel, Zählerstand, Zählerwerte, Nenner, Wetter und Monatspreise."""
    return dict(
        # `md is None` ⇒ Monat ohne Zählerzeile (nur mit
        # `inkl_ohne_zaehlerzeile=true` in der Antwort). Die Zählerwerte
        # kommen ohnehin schon aus der Schicht (`f.zaehler`, dort 0,0), die
        # Spalten daneben existieren nicht — sie bleiben `None` statt still 0
        # zu werden.
        id=md.id if md is not None else None,
        anlage_id=md.anlage_id if md is not None else kx.anlage_id,
        jahr=f.jahr,
        monat=f.monat,
        # #377: Stand am Monatsende je Zähler-Gerät (nie summiert).
        zaehler_stand={
            k: round(v, 3)
            for k, v in kx.zaehler_stand_je_monat.get((f.jahr, f.monat), {}).items()
        } or None,
        pv_vollstaendig=f.erzeugung.pv_vollstaendig,
        einspeisung_kwh=round(einspeisung, 1),
        netzbezug_kwh=round(netzbezug, 1),
        # F-58: Nenner des spez. Ertrags je Monat. `mit_bkw=True`, weil
        # `pv_erzeugung_kwh` dieser Zeile `f.erzeugung.pv_kwh` ist — Module
        # UND Balkonkraftwerk. ⛔ Bis 03.10.2026 stand hier `mit_bkw=False`
        # mit der Begründung „die Zeile trägt die Modul-PV": falsch, und die
        # Spalte „Spez. Ertrag" lag bei 10 kWp + 0,8 kWp BKW um den
        # BKW-Anteil über Cockpit → Monat (100,0 gegen 92,6 kWh/kWp, N-612).
        # Derselbe Nenner wie `get_monatsdaten` und Cockpit → Monat; die
        # Abtretung an Modul-Kinder entscheidet `summe_erzeuger_kwp` je
        # Stichtag (N-266).
        anlagen_kwp=(
            berechne_anlagen_kwp(
                kx.inv_rows,
                date(f.jahr, f.monat, monthrange(f.jahr, f.monat)[1]),
                mit_bkw=True,
            ) or None
        ),
        globalstrahlung_kwh_m2=md.globalstrahlung_kwh_m2 if md is not None else None,
        sonnenstunden=md.sonnenstunden if md is not None else None,
        durchschnittstemperatur_c=kx.temperatur_je_monat.get((f.jahr, f.monat)),
        netzbezug_durchschnittspreis_cent=(
            md.netzbezug_durchschnittspreis_cent if md is not None else None
        ),
        einspeise_durchschnittspreis_cent=(
            md.einspeise_durchschnittspreis_cent if md is not None else None
        ),
    )


def _zeile_erzeugung(f, hat_pv_imd: bool, finanz) -> dict[str, Any]:
    """Felder der Zeile, Teil 2: PV-Achse (Module, Balkonkraftwerk), Wandlungsverluste, Sonstige, Netzpunkt-Erzeugung."""
    return dict(
        # Komponenten-Aggregate: None wenn keine aktive IMD beigetragen
        # hat, sonst tatsächlicher Wert (auch 0 ist legitim, z.B. WP im
        # Sommer 0 kWh Heizung).
        pv_erzeugung_kwh=round(f.erzeugung.pv_kwh, 1) if hat_pv_imd else None,
        pv_module_kwh=(
            round(
                f.erzeugung.pv_kwh - f.erzeugung.bkw_kwh
                - f.erzeugung.bkw_aus_anlagenwert_kwh, 1,
            ) if hat_pv_imd else None
        ),
        bkw_kwh=(
            round(f.erzeugung.bkw_kwh + f.erzeugung.bkw_aus_anlagenwert_kwh, 1)
            if hat_pv_imd else None
        ),
        bkw_aus_anlagenwert_kwh=(
            round(f.erzeugung.bkw_aus_anlagenwert_kwh, 1) if hat_pv_imd else None
        ),
        wandlungsverluste_kwh=f.erzeugung.wandlungsverluste_kwh,
        wandlungsverluste_prozent=wandlungsverluste_prozent(
            f.erzeugung.wandlungsverluste_kwh, f.erzeugung.wandlungsverluste_bezug_kwh,
        ),
        eigenverbrauch_ohne_verluste_kwh=round(finanz.eigenverbrauch_ohne_verluste_kwh, 1),
        verluste_grund=f.erzeugung.verluste_grund,
        sonstige_erzeugung_kwh=(
            round(f.erzeugung.sonstige_erzeuger_kwh, 1)
            if f.sonstiges.hat_erzeuger_zeile else None
        ),
        abgabe_dritte_kwh=(
            round(f.sonstiges.abgabe_kwh, 1) if f.sonstiges.abgabe_kwh > 0 else None
        ),
        sonstige_verbrauch_kwh=(
            round(f.sonstiges.verbrauch_kwh, 1)
            if f.sonstiges.hat_verbraucher_zeile else None
        ),
        # Dieselbe Zahl, mit der direktverbrauch/eigenverbrauch gerechnet
        # wurden — nicht neu summiert, sonst driftet die ausgelieferte Größe
        # von der intern verwendeten ab. `None`, wenn WEDER PV noch ein
        # sonstiger Erzeuger beigetragen hat.
        erzeugung_hinter_zaehler_kwh=(
            round(f.erzeugung.hinter_zaehler_kwh, 1)
            if (hat_pv_imd or f.sonstiges.hat_erzeuger_zeile) else None
        ),
    )


def _zeile_komponenten(
    f, typen, hat_speicher_imd: bool, speicher_ladung: float, speicher_entladung: float, _wp_az,
) -> dict[str, Any]:
    """Felder der Zeile, Teil 3: Speicher, Wärmepumpe, E-Auto, Wallbox."""
    # E-Mob je Quelle getrennt ausweisen (die Response trägt eauto_* und
    # wallbox_* als eigene Felder) — über denselben SoT-Leser, nicht roh aus
    # dem Dict. `emob.ladung_kwh` (der Pool) wäre hier falsch: er wählt EINE
    # Quelle für die Gesamt-Heimladung, diese Sicht zeigt aber beide Seiten.
    eauto = f.emob.eauto_summe
    wallbox = f.emob.wallbox_summe
    return dict(
        speicher_ladung_kwh=round(speicher_ladung, 1) if hat_speicher_imd else None,
        speicher_entladung_kwh=round(speicher_entladung, 1) if hat_speicher_imd else None,
        speicher_netzladung_kwh=(
            round(f.speicher.netzladung_kwh, 1) if hat_speicher_imd else None
        ),
        wp_strom_kwh=round(f.wp.strom_kwh, 1) if "waermepumpe" in typen else None,
        wp_strom_heizen_kwh=round(f.wp.strom_heizen_kwh, 1) if f.wp.hat_split else None,
        wp_strom_warmwasser_kwh=(
            round(f.wp.strom_warmwasser_kwh, 1) if f.wp.hat_split else None
        ),
        # N-673: ohne Messung der Achse „keine Angabe" statt 0 (die Fakten tragen dann `None`).
        wp_heizung_kwh=(round(f.wp.heizung_kwh, 1)
                        if "waermepumpe" in typen and f.wp.heizung_kwh is not None else None),
        wp_warmwasser_kwh=(round(f.wp.warmwasser_kwh, 1)
                           if "waermepumpe" in typen and f.wp.warmwasser_kwh is not None else None),
        wp_arbeitszahl=_wp_az.wert if "waermepumpe" in typen else None,
        wp_arbeitszahl_grund=_wp_az.grund if "waermepumpe" in typen else None,
        eauto_ladung_kwh=round(eauto.ladung_kwh, 1) if "e-auto" in typen else None,
        eauto_km=round(f.emob.km, 1) if "e-auto" in typen else None,
        wallbox_ladung_kwh=round(wallbox.ladung_kwh, 1) if "wallbox" in typen else None,
        wallbox_ladung_pv_kwh=round(wallbox.pv_kwh, 1) if "wallbox" in typen else None,
    )


def _zeile_bilanz_und_geld(
    f, finanz, *, ust_eigenverbrauch: float, netzbezug_kosten: float, netto_ertrag: float,
    hat_legacy: bool, legacy_ohne_ziel: bool, aus_tagen,
) -> dict[str, Any]:
    """Felder der Zeile, Teil 4: Bilanz-Kennzahlen, §51, die Finanz-Zeile und die Hinweis-Flags."""
    _kz = f.kennzahlen
    return dict(
        direktverbrauch_kwh=round(_kz.direktverbrauch_kwh, 1),
        eigenverbrauch_kwh=round(_kz.eigenverbrauch_kwh, 1),
        gesamtverbrauch_kwh=round(_kz.gesamtverbrauch_kwh, 1),
        autarkie_prozent=round(_kz.autarkie_prozent, 1),
        eigenverbrauchsquote_prozent=round(_kz.eigenverbrauchsquote_prozent, 1),
        # `None` heißt „nicht §51-pflichtig ODER kein Tages-Aggregat mit
        # Strompreis-Mitschrift" — eine 0 wäre dort eine Aussage, die
        # niemand belegen kann (Gate im Erlös-Service).
        einspeisung_neg_preis_kwh=(
            round(f.eeg.neg_preis_kwh, 1) if f.eeg.neg_preis_kwh is not None else None
        ),
        einspeise_erloes_euro=round(finanz.einspeise_erloes_euro, 2),
        einspeise_nicht_verguetet_euro=round(finanz.nicht_vergueteter_erloes_euro, 2),
        ev_ersparnis_euro=round(finanz.ev_ersparnis_euro, 2),
        # §9 Weg 2 / §9.2 Geldseite — der Betrag steckt seit E1 (06.09.)
        # IN `netto_ertrag_euro` (oben gereicht) und steht hier zusätzlich
        # als eigene Größe, damit die Sicht ihn BENENNEN kann („inkl. +X €
        # Abgabe an Dritte"). Ohne dieses Feld wüsste der Client nicht
        # einmal, ob es solche Erzeuger gibt.
        erzeuger_erloes_euro=round(f.sonstiges.einspeise_erloes_euro, 2),
        bkw_ersparnis_euro=round(finanz.bkw_ersparnis_euro, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2),
        dienstliche_ladekosten_euro=round(f.emob.dienstliche_ladekosten_euro, 2),
        netzbezug_kosten_euro=round(netzbezug_kosten, 2),
        netto_ertrag_euro=round(netto_ertrag, 2),
        netto_bilanz_euro=round(netto_ertrag - netzbezug_kosten, 2),
        netzbezug_preis_cent=round(f.tarif.netzbezug_preis_cent, 2),
        hat_legacy_daten=hat_legacy,
        legacy_ohne_ziel=legacy_ohne_ziel,
        aus_tageswerten=sorted(aus_tagen) or None,
    )
