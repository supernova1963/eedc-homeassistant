"""Monats-Fakten — `_baue_fakt`: aus einem Rohmonat wird der kanonische `MonatsFakt` (P7-Auflösung, Layer-Helfer rufen,
Zeitfilter und Dienstwagen-Filter genau hier).
"""
# Reiner Umzug aus `services/monats_fakten.py` (19.09.2026, Vorlage 10 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert die Namen weiter, die
# Aufrufer und Tests bisher aus dem Modul importierten (ADR-002/P10 bleibt: die Schicht ist das Paket).

from __future__ import annotations

from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.strompreis_aggregator import PreisMessung
from backend.core.berechnungen import (
    PvModulWert,
    berechne_verbrauchs_kennzahlen,
    erzeugung_hinter_zaehler_kwh,
)
from backend.core.berechnungen.anlagen_kwp import BKW_TYP, PV_MODUL_TYP
from backend.core.berechnungen.erzeuger_traeger import abgetretene_bkw_ids
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.core.investition_parameter import ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import (
    eauto_zeile_ohne_altwert,
    entscheide_emob_heimladung,
    summiere_emob_quelle,
)
from backend.services.emob_ladeanteil import reichere_ladezeilen_an
from backend.services.energie_profil.monats_aus_tagen import TagesMonatsSumme
from backend.utils.sonstige_positionen import berechne_md_sonstige_summen
from backend.services.monats_fakten.fakten import BkwFakten, EegFakten, EmobFakten, ErzeugungFakten, MetaFakten, MonatsFakt, MonatsSchluessel, SonstigesFakten, SonstigesGeraetFakten, SpeicherFakten, TAGESWERT_BKW, TAGESWERT_EMOB_ANTEIL, TAGESWERT_PV, TAGESWERT_SPEICHER, TAGESWERT_ZAEHLER, ZaehlerFakten
from backend.services.monats_fakten.fakten_wp import WpFakten
from backend.services.monats_fakten.roh import _RohMonat, _erzeuger_aktiv
from backend.services.monats_fakten.tarif import _lade_tarif


async def _baue_fakt(
    db: AsyncSession,
    anlage_id: int,
    schluessel: MonatsSchluessel,
    roh: _RohMonat,
    *,
    monatsdaten: Optional[Monatsdaten],
    pv_modul_summe: Optional[float],
    pv_je_modul: dict[int, PvModulWert],
    pv_modul_teilsumme: Optional[float] = None,
    investitionen: list[Investition],
    bkw_aus_anlagenwert: Optional[dict[int, float]] = None,
    neg_preis_kwh: Optional[float],
    tarif_cache: dict[date, dict],
    zeittarif_cache: dict,
    tages_summe: Optional[TagesMonatsSumme] = None,
    preis_cache: Optional[dict] = None,
    preis_messung: Optional[PreisMessung] = None,
    heimlade_quellen: frozenset = frozenset(),
    bloecke: Optional[dict] = None,
) -> MonatsFakt:
    jahr, monat = schluessel

    # ── Lücken aus der Tagesebene füllen (N-121, nur mit `inkl_nur_tageswerte`) ──
    # Präzedenz wie bei P7: was in der DB steht, gewinnt. Die Tageswerte füllen
    # **Lücken**, sie überschreiben nichts — und zwar feldgruppen-weise, nicht
    # monatsweise: ein Monat, dessen einzige DB-Spur eine Sonstiges-Zeile ist,
    # bekommt dadurch seine PV, statt sie still als 0 zu zeichnen.
    tageswert_gruppen: set[str] = set()

    zaehler = ZaehlerFakten(
        einspeisung_kwh=(monatsdaten.einspeisung_kwh or 0.0) if monatsdaten else 0.0,
        netzbezug_kwh=(monatsdaten.netzbezug_kwh or 0.0) if monatsdaten else 0.0,
    )
    if monatsdaten is None and tages_summe is not None:
        zaehler = ZaehlerFakten(
            einspeisung_kwh=tages_summe.einspeisung_kwh,
            netzbezug_kwh=tages_summe.netzbezug_kwh,
        )
        tageswert_gruppen.add(TAGESWERT_ZAEHLER)

    # N-627 (Bauplan PV-Achse T4, Zusatz Master): die Monatsregel gilt auch im Tageswert-Rückfall.
    # Ein Balkonkraftwerk, dessen Modul-Kinder in diesem Monat aktiv sind, hat seine Erzeugung an
    # sie abgetreten (ADR-002/P11); sein Tages-Key (der E4-Rest) gehört im Monat zur Gruppe der
    # Module, nicht zur BKW-Zeile — sonst nennte derselbe Monat vor dem Abschluss BKW 90 / Module
    # 540 und danach 0 / 630. Eine Umbuchung zwischen den zwei Gruppen; die Summe bleibt.
    tages_module = tages_bkw = 0.0
    if tages_summe is not None:
        _abgetreten = abgetretene_bkw_ids([
            i for i in investitionen
            if i.typ in (PV_MODUL_TYP, BKW_TYP) and i.ist_aktiv_im_monat(jahr, monat)
        ])
        _abgetreten_tag = sum(
            v for k, v in (tages_summe.bkw_je_inv or {}).items() if k.isdigit() and int(k) in _abgetreten
        )
        tages_module = tages_summe.pv_module_kwh + _abgetreten_tag
        tages_bkw = max(0.0, tages_summe.bkw_kwh - _abgetreten_tag)

    # PV nur, wenn die P7-Auflösung nichts ergab (`None` = kein Modulwert und
    # kein Anlagen-Aggregat). Ein aufgelöster Wert — auch ein teilweise
    # geschätzter — bleibt unangetastet.
    if pv_modul_summe is None and tages_summe is not None and tages_module > 0:
        pv_modul_summe = tages_module
        pv_vollstaendig = True
        tageswert_gruppen.add(TAGESWERT_PV)
    else:
        pv_vollstaendig = pv_modul_summe is not None or not pv_je_modul
        # N-626 (Gernot 04.10.2026): fehlt einem Modul der Wert und gibt es keinen Anlagenwert, trägt es
        # nichts bei — die vorhandenen Werte bleiben in der Summe (vorher fiel die ganze Modulsumme weg:
        # 90 statt 450). Reihenfolge: vollständige Summe → Tageswert (oben) → Teilsumme. `pv_vollstaendig`
        # bleibt False — der Hinweis „unvollständig" (`pv_unvollstaendig_hinweis`) und der Daten-Checker
        # sagen es weiter; `pv_module_kwh` trägt die Teilsumme, sonst blieben Tabelle und ROI leer.
        if pv_modul_summe is None and pv_modul_teilsumme is not None:
            pv_modul_summe = pv_modul_teilsumme

    # N-621: der Anteil der Balkonkraftwerke ohne eigenen Wert am gespeicherten
    # Anlagenwert (`pv_monatswerte.lade_pv_je_monat`, `bkw_anteile`). Leer ohne
    # Anlagenwert — dann ist jede Zahl unten dieselbe wie vorher.
    bkw_anteil = dict(bkw_aus_anlagenwert or {})
    bkw_aus_anlagenwert_kwh = sum(bkw_anteil.values())

    # BKW nur ohne eigene IMD-Zeile im Monat — und nicht neben einem Anteil am
    # Anlagenwert (N-621, Tageswert-Vorrang): der gespeicherte Anlagenwert steht
    # für ALLE PV-Quellen und hat das BKW schon bedacht; der Tageswert käme
    # obendrauf (gemessen vorher: Anlagenwert 1000, Strings 550 + 380, BKW-Tag
    # 45 ⇒ mit Tagesebene 975, nach dem Bau sonst 1045).
    bkw_erzeugung = roh.bkw_erzeugung
    if (
        "balkonkraftwerk" not in roh.typen_mit_zeile
        and not bkw_anteil
        and tages_summe is not None
        and tages_bkw > 0
    ):
        bkw_erzeugung = tages_bkw
        tageswert_gruppen.add(TAGESWERT_BKW)

    pv_kwh = (pv_modul_summe or 0.0) + bkw_erzeugung + bkw_aus_anlagenwert_kwh
    erzeugung = ErzeugungFakten(
        pv_module_kwh=pv_modul_summe,
        bkw_kwh=bkw_erzeugung,
        sonstige_erzeuger_kwh=roh.sonstiges_erzeugung,
        pv_kwh=pv_kwh,
        # Netzpunkt-Bilanz: der sonstige Erzeuger speist hinter denselben Zähler.
        hinter_zaehler_kwh=erzeugung_hinter_zaehler_kwh(pv_kwh, roh.sonstiges_erzeugung),
        pv_je_modul=pv_je_modul,
        pv_vollstaendig=pv_vollstaendig,
        bkw_aus_anlagenwert_kwh=bkw_aus_anlagenwert_kwh,
    )

    # ── PV-Anteil der Heimladung: echter Wert gewinnt, sonst ableiten ──────
    # Rahmenbedingung 1 (N-141 Weg c): die Ableitung füllt NUR Lücken. Gepflegt
    # ist der Anteil, sobald irgendeine Quellzeile den Schlüssel trägt — auch
    # mit **0**. Das ist bewusst `is not None` und nicht `> 0`: eine gepflegte
    # 0 („diesen Monat nur nachts geladen") ist eine Aussage, keine Lücke, und
    # sie darf keine Schätzung auslösen (CLAUDE.md §0-Werte prüfen).
    #
    # ⚠ **Angereichert wird VOR dem Pool, nicht danach (F-16).** Bis `a7a50abc`
    # saß die Ableitung unter `pool` und traf damit nur die Felder
    # `ladung_pv_kwh`/`ladung_netz_kwh` — jede Sicht, die die mitgereichten
    # Rohdicts selbst poolt (Cockpit → Jahr, Jahresbericht-PDF) oder die IMD
    # direkt liest (Komponenten-Hub, Aussichten, HA-Export), zeigte weiter 0 %.
    # Unterhalb des Pools angesetzt gilt die Aufteilung für jeden dieser Wege.
    # N-555 Stufe 2: „Wallbox in Betrieb" kommt aus der Investitionsliste, nicht aus der
    # Existenz einer Zeile — eine Wallbox ohne Monatszeile ist trotzdem da (Regel 2).
    wallbox_in_betrieb = bool(roh.wallbox_ladedaten) or any(
        i.typ == "wallbox" and not ist_dienstlich(i)
        and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    dienstliche_wallbox_in_betrieb = bool(roh.dienstliche_wallbox_ids) or any(
        i.typ == "wallbox" and ist_dienstlich(i)
        and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    eauto_ladedaten, wallbox_ladedaten, anteil_abgeleitet = reichere_ladezeilen_an(
        eauto_daten=roh.eauto_ladedaten,
        wallbox_daten=roh.wallbox_ladedaten,
        quote=tages_summe.abgeleiteter_pv_anteil if tages_summe is not None else None,
        wallbox_in_betrieb=wallbox_in_betrieb,
    )
    if anteil_abgeleitet:
        tageswert_gruppen.add(TAGESWERT_EMOB_ANTEIL)

    # ── N-555 Stufe 1: die EINE Funktion entscheidet (Regel 1, 2-Ü, 6) ──────
    # Abgeschlossene Monate entscheiden nur nach dem gespeicherten Wert; nur für
    # den laufenden Monat reicht `laden.py` die Heimlade-Quellen herein. „Wallbox in Betrieb" kommt aus der
    # Investitionsliste, nicht aus der Existenz einer Zeile: eine Wallbox ohne
    # Monatszeile ist trotzdem da (Regel 2-Ü Schritt 2, alter Gesamtwert am Auto).
    # Die Tages-Quote gilt auch für die Schätzung — dieselbe Zahl wie vor N-555,
    # als die Anreicherung sie über den Fahrverbrauch der Zeile legte.
    entscheid = entscheide_emob_heimladung(
        eauto_je_inv=dict(zip(roh.eauto_ladedaten_ids, eauto_ladedaten)),
        wallbox_zeilen=wallbox_ladedaten,
        wallbox_in_betrieb=wallbox_in_betrieb,
        # N-555 Stufe 2 (Regel 3): Dienstwagen und dienstliche Wallboxen getrennt — eine
        # gemessene dienstliche Ladung fehlt im Rest der privaten Wallbox, eine dienstliche
        # Wallbox in Betrieb macht Felder und Schätzung der Dienstwagen wirkungslos.
        dienstwagen_je_inv={
            i: z for i, z in roh.dienstlich_je_inv.items()
            if i not in roh.dienstliche_wallbox_ids
        },
        dienstliche_wallbox_je_inv={
            i: z for i, z in roh.dienstlich_je_inv.items()
            if i in roh.dienstliche_wallbox_ids
        },
        dienstliche_wallbox_in_betrieb=dienstliche_wallbox_in_betrieb,
        # Nur im laufenden Monat nicht leer (Regel 1: dort zählt auch eine Quelle).
        heimlade_quellen=heimlade_quellen,
        pv_quote=tages_summe.abgeleiteter_pv_anteil if tages_summe is not None else None,
        # Regel 8 (E5): welches `ladung_kwh` „Heim: gesamt" ist — nach Herkunft.
        heim_gesamt=roh.heim_gesamt_ids,
        # Wessen Quelle ist eine Wallbox-Quelle? (Die Quellen tragen seit Stufe 2 auch
        # Dienstwagen — eine Quelle am Dienstwagen sagt nichts über die private Wallbox.)
        wallbox_ids={
            i.id for i in investitionen
            if i.typ == "wallbox" and not ist_dienstlich(i)
            and i.ist_aktiv_im_monat(jahr, monat)
        },
        # Regel 2 Schritt 3: Empfänger des Rests sind alle privaten Autos in Betrieb, auch
        # die ohne Monatszeile (0 km, E6) — sonst fiele der Rest eines Monats, in dem nur
        # die Wallbox erfasst ist, aus dem Topf.
        eauto_in_betrieb=[
            i.id for i in investitionen
            if i.typ == "e-auto" and not ist_dienstlich(i)
            and i.ist_aktiv_im_monat(jahr, monat)
        ],
        # W-1 (Konzept Regel 2 Schritt 3): „nur eine Wallbox" nur ohne Dienstwagen in Betrieb.
        dienstwagen_in_betrieb=[
            i.id for i in investitionen
            if i.typ == "e-auto" and ist_dienstlich(i)
            and i.ist_aktiv_im_monat(jahr, monat)
        ],
        # N-555 Stufe 3 (Regel 9 Punkt 3): hat ein Auto im Monat geltende Ladeblöcke, sind
        # sie seine Messung (Menge und Anteil), nicht der gespeicherte „Heim: gesamt".
        bloecke=bloecke,
        # N-569-Ergänzung: „davon aus dem Speicher" — nur Ausweis je Auto.
        speicher_quote=(
            tages_summe.abgeleiteter_speicher_anteil if tages_summe is not None else None
        ),
    )
    pool = entscheid.pool
    if entscheid.anteil_abgeleitet:
        anteil_abgeleitet = True
        tageswert_gruppen.add(TAGESWERT_EMOB_ANTEIL)

    emob = EmobFakten(
        ladung_kwh=pool.ladung_kwh,
        ladung_pv_kwh=pool.pv_kwh,
        ladung_netz_kwh=pool.netz_kwh,
        ladung_anteil_abgeleitet=anteil_abgeleitet,
        extern_kwh=pool.extern_kwh,
        extern_euro=pool.extern_euro,
        ladevorgaenge=pool.ladevorgaenge,
        quelle=pool.quelle,
        km=roh.eauto_km,
        fahrverbrauch_kwh=roh.eauto_fahrverbrauch,
        v2h_entladung_kwh=roh.eauto_v2h,
        km_je_fahrzeug=dict(roh.eauto_km_je_fahrzeug),
        fahrverbrauch_je_fahrzeug=dict(roh.eauto_fahrverbrauch_je_fahrzeug),
        dienstlich_ladung_pv_kwh=entscheid.dienstlich_pv_kwh,
        dienstlich_ladung_netz_kwh=entscheid.dienstlich_netz_kwh,
        dienstlich_geschaetzt=any(
            not d.gemessen for d in entscheid.dienstlich_je_inv.values()
            if d.pv_kwh + d.netz_kwh > 0
        ),
        # N-555 Stufe 2: die Ausgabe je Auto (Regel 2/3); ihre Summe ist der Topf oben.
        je_auto=dict(entscheid.je_auto),
        rest_pv_kwh=entscheid.rest_pv_kwh,
        rest_netz_kwh=entscheid.rest_netz_kwh,
        rest_zugeordnet=entscheid.rest_zugeordnet,
        wallbox_hat_wert=entscheid.wallbox_hat_wert,
        wallbox_in_betrieb=entscheid.wallbox_in_betrieb,
        dienstlich_gemessen_pv_kwh=sum(
            entscheid.dienstlich_je_inv[i].pv_kwh for i in entscheid.dienstwagen_gemessen
        ),
        dienstlich_gemessen_netz_kwh=sum(
            entscheid.dienstlich_je_inv[i].netz_kwh for i in entscheid.dienstwagen_gemessen
        ),
        dienstwagen_ungemessen=entscheid.dienstwagen_ungemessen,
        dienstwagen_gemessen=entscheid.dienstwagen_gemessen,
        dienstliche_wallbox_in_betrieb=entscheid.dienstliche_wallbox_in_betrieb,
        dienstwagen_in_betrieb=any(
            i.typ == "e-auto" and ist_dienstlich(i) and i.ist_aktiv_im_monat(jahr, monat)
            for i in investitionen
        ),
        heim_gesamt_ids=frozenset(roh.heim_gesamt_ids),
        dienstlich_ladedaten_je_inv=dict(roh.dienstlich_je_inv),
        eauto_ladedaten=tuple(eauto_ladedaten),
        ladedaten_je_inv={
            **dict(zip(roh.eauto_ladedaten_ids, eauto_ladedaten)),
            **dict(zip(roh.wallbox_ladedaten_ids, wallbox_ladedaten)),
        },
        wallbox_ladedaten=tuple(wallbox_ladedaten),
        eauto_summe=summiere_emob_quelle(eauto_ladedaten),
        wallbox_summe=summiere_emob_quelle(wallbox_ladedaten),
        # Ungeschätzt — nur für den Community-Payload (s. Feld-Docstring).
        # N-555 Stufe 2 (F2 der Nachmessung, Regel 8): die E-Auto-Seite liest die Zeilen wie
        # die eine Funktion — ein alter Gesamtwert `ladung_kwh` (Herkunft `legacy:unknown`
        # oder ohne) zählt neben einer privaten Wallbox in Betrieb nicht, auch nicht als
        # Messwert an die Community; „Heim: gesamt" mit Herkunft und ohne Wallbox der
        # Altwert (Steckerlader) schon.
        eauto_summe_gemessen=summiere_emob_quelle(
            eauto_zeile_ohne_altwert(
                z, wallbox_in_betrieb=wallbox_in_betrieb,
                heim_gesamt=i in roh.heim_gesamt_ids,
            )
            for i, z in zip(roh.eauto_ladedaten_ids, roh.eauto_ladedaten)
        ),
        wallbox_summe_gemessen=summiere_emob_quelle(roh.wallbox_ladedaten),
    )

    md_summen = berechne_md_sonstige_summen(monatsdaten) if monatsdaten else None
    ertraege = roh.ertraege_euro + (md_summen["ertraege_euro"] if md_summen else 0.0)
    ausgaben = roh.ausgaben_euro + (md_summen["ausgaben_euro"] if md_summen else 0.0)

    tarif = await _lade_tarif(
        db, anlage_id, schluessel, monatsdaten, tarif_cache, zeittarif_cache,
        preis_cache=preis_cache, preis_messung=preis_messung,
    )

    speicher = SpeicherFakten(
        ladung_kwh=roh.speicher_ladung,
        entladung_kwh=roh.speicher_entladung,
        netzladung_kwh=roh.speicher_netzladung,
        netzladung_preis_summe_cent_kwh=roh.speicher_preis_summe,
        netzladung_gewicht_kwh=roh.speicher_preis_gewicht,
    )
    # Speicher nur ohne eigene IMD-Zeile im Monat. Die Netzladung (Arbitrage)
    # bleibt dabei ungefüllt: sie ist eine **Preis**-Aussage, und die trägt die
    # Tagesebene nicht — eine 0 daneben wäre keine Messung, sondern eine
    # Behauptung über einen nie gepflegten Wert.
    if (
        "speicher" not in roh.typen_mit_zeile
        and tages_summe is not None
        and (tages_summe.speicher_ladung_kwh > 0 or tages_summe.speicher_entladung_kwh > 0)
    ):
        speicher = SpeicherFakten(
            ladung_kwh=tages_summe.speicher_ladung_kwh,
            entladung_kwh=tages_summe.speicher_entladung_kwh,
        )
        tageswert_gruppen.add(TAGESWERT_SPEICHER)

    return MonatsFakt(
        jahr=jahr,
        monat=monat,
        zaehler=zaehler,
        erzeugung=erzeugung,
        bkw=BkwFakten(
            erzeugung_kwh=bkw_erzeugung,
            eigenverbrauch_gemessen_kwh=roh.bkw_eigenverbrauch,
            rest_eigenverbrauch_kwh=roh.bkw_rest_eigenverbrauch,
            speicher_ladung_kwh=roh.bkw_speicher_ladung,
            speicher_entladung_kwh=roh.bkw_speicher_entladung,
            # Leer lassen, sobald die Zahl von der Tagesebene kommt: dort ist sie
            # anlagenweit, eine Aufteilung wäre erfunden (s. Feld-Docstring).
            erzeugung_je_investition=(
                {} if TAGESWERT_BKW in tageswert_gruppen
                else dict(roh.bkw_je_investition)
            ),
        ),
        speicher=speicher,
        emob=emob,
        wp=WpFakten(
            strom_kwh=roh.wp_strom,
            strom_mit_ersatz_kwh=roh.wp_strom_mit_ersatz,
            waerme_mit_ersatz_kwh=roh.wp_waerme_mit_ersatz,
            waerme_kwh=roh.wp_waerme,
            heizung_kwh=roh.wp_heizung,
            warmwasser_kwh=roh.wp_warmwasser,
            strom_heizen_kwh=roh.wp_strom_heizen,
            strom_warmwasser_kwh=roh.wp_strom_warmwasser,
            heizung_gemessen=roh.wp_heizung_gemessen,
            warmwasser_gemessen=roh.wp_warmwasser_gemessen,
            strom_heizen_gemessen=roh.wp_strom_heizen_gemessen,
            strom_warmwasser_gemessen=roh.wp_strom_warmwasser_gemessen,
            hat_split=roh.wp_hat_split,
            waerme_ist_gesamt=roh.wp_waerme_ist_gesamt,
            modus_strom_heizen_kwh=roh.wp_modus_strom_heizen,
            modus_strom_kuehlen_kwh=roh.wp_modus_strom_kuehlen,
            modus_strom_warmwasser_kwh=roh.wp_modus_strom_warmwasser,
            modus_strom_lueften_kwh=roh.wp_modus_strom_lueften,
            modus_strom_entfeuchten_kwh=roh.wp_modus_strom_entfeuchten,
            modus_strom_funktionsfremd_abzug_kwh=(
                roh.wp_modus_strom_funktionsfremd_abzug
            ),
            nutzenergie_kuehlen_kwh=roh.wp_nutzenergie_kuehlen,
            nutzenergie_lueften_kwh=roh.wp_nutzenergie_lueften,
            nutzenergie_entfeuchten_kwh=roh.wp_nutzenergie_entfeuchten,
            modus_abdeckung_h=roh.wp_modus_abdeckung_h,
            modus_gemessen=roh.wp_modus_gemessen,
            modus_strom_bezug_kwh=roh.wp_modus_strom_bezug,
            strom_nicht_aufgeteilt_kwh=roh.wp_strom_nicht_aufgeteilt,
            waerme_abgeleitet_kwh=roh.wp_waerme_abgeleitet,
            # `WpFakten` ist `frozen=True` — die Mengen frieren beim Übergang
            # mit ein, damit ein Leser sie nicht versehentlich fortschreibt.
            geraete_mit_strom=frozenset(roh.wp_geraete_mit_strom),
            geraete_mit_waerme=frozenset(roh.wp_geraete_mit_waerme),
            geraete_e_heizen=frozenset(roh.wp_geraete_e_heizen),
            geraete_q_heizen=frozenset(roh.wp_geraete_q_heizen),
            geraete_e_warmwasser=frozenset(roh.wp_geraete_e_warmwasser),
            geraete_q_warmwasser=frozenset(roh.wp_geraete_q_warmwasser),
            geraete_e_kuehlen=frozenset(roh.wp_geraete_e_kuehlen),
            geraete_q_kuehlen=frozenset(roh.wp_geraete_q_kuehlen),
            geraete_luft_luft=roh.wp_geraete_luft_luft,
            geraete_luft_wasser=roh.wp_geraete_luft_wasser,
            abgrenzung_stoerung=roh.wp_abgrenzung,
        ),
        sonstiges=SonstigesFakten(
            erzeugung_kwh=roh.sonstiges_erzeugung,
            abgabe_kwh=roh.sonstiges_abgabe,
            verbrauch_kwh=roh.sonstiges_verbrauch,
            eigenverbrauch_kwh=roh.sonstiges_eigenverbrauch,
            einspeisung_kwh=roh.sonstiges_einspeisung,
            bezug_pv_kwh=roh.sonstiges_bezug_pv,
            bezug_netz_kwh=roh.sonstiges_bezug_netz,
            einspeise_erloes_euro=roh.sonstiges_einspeise_erloes_euro,
            je_geraet={
                inv_id: SonstigesGeraetFakten(
                    erzeugung_kwh=g["erzeugung"],
                    verbrauch_kwh=g["verbrauch"],
                    eigenverbrauch_kwh=g["eigenverbrauch"],
                    einspeisung_kwh=g["einspeisung"],
                    bezug_pv_kwh=g["bezug_pv"],
                    bezug_netz_kwh=g["bezug_netz"],
                    einspeise_erloes_euro=g.get("einspeise_erloes_euro", 0.0),
                    hat_einspeise_erloes=bool(g.get("hat_einspeise_erloes")),
                    abgabe_kwh=g.get("abgabe", 0.0),
                )
                for inv_id, g in roh.sonstiges_je_geraet.items()
            },
            ertraege_euro=round(ertraege, 2),
            ausgaben_euro=round(ausgaben, 2),
            netto_euro=round(ertraege - ausgaben, 2),
            anlage_ertraege_euro=round(md_summen["ertraege_euro"], 2) if md_summen else 0.0,
            anlage_ausgaben_euro=round(md_summen["ausgaben_euro"], 2) if md_summen else 0.0,
            hat_erzeuger_zeile=roh.hat_sonstigen_erzeuger,
            hat_verbraucher_zeile=roh.hat_sonstigen_verbraucher,
        ),
        tarif=tarif,
        eeg=EegFakten(neg_preis_kwh=neg_preis_kwh),
        kennzahlen=berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=erzeugung.hinter_zaehler_kwh,
            einspeisung_kwh=zaehler.einspeisung_kwh,
            netzbezug_kwh=zaehler.netzbezug_kwh,
            speicher_ladung_kwh=speicher.ladung_kwh,
            speicher_entladung_kwh=speicher.entladung_kwh,
            v2h_entladung_kwh=emob.v2h_entladung_kwh,
            abgabe_dritte_kwh=roh.sonstiges_abgabe,
        ),
        meta=MetaFakten(
            monatsdaten=monatsdaten,
            hat_zaehlerzeile=monatsdaten is not None,
            erzeuger_aktiv=_erzeuger_aktiv(investitionen, jahr, monat),
            pv_vollstaendig=erzeugung.pv_vollstaendig,
            aktive_investitionen=tuple(
                i.id for i in investitionen if i.ist_aktiv_im_monat(jahr, monat)
            ),
            typen_mit_zeile=frozenset(roh.typen_mit_zeile),
            tageswert_gruppen=frozenset(tageswert_gruppen),
        ),
    )
