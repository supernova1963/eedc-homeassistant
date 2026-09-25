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
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.core.investition_parameter import ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import (
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
    investitionen: list[Investition],
    neg_preis_kwh: Optional[float],
    tarif_cache: dict[date, dict],
    zeittarif_cache: dict,
    tages_summe: Optional[TagesMonatsSumme] = None,
    preis_cache: Optional[dict] = None,
    preis_messung: Optional[PreisMessung] = None,
    heimlade_quellen: frozenset = frozenset(),
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

    # PV nur, wenn die P7-Auflösung nichts ergab (`None` = kein Modulwert und
    # kein Anlagen-Aggregat). Ein aufgelöster Wert — auch ein teilweise
    # geschätzter — bleibt unangetastet.
    if pv_modul_summe is None and tages_summe is not None and tages_summe.pv_module_kwh > 0:
        pv_modul_summe = tages_summe.pv_module_kwh
        pv_vollstaendig = True
        tageswert_gruppen.add(TAGESWERT_PV)
    else:
        pv_vollstaendig = pv_modul_summe is not None or not pv_je_modul

    # BKW nur ohne eigene IMD-Zeile im Monat.
    bkw_erzeugung = roh.bkw_erzeugung
    if (
        "balkonkraftwerk" not in roh.typen_mit_zeile
        and tages_summe is not None
        and tages_summe.bkw_kwh > 0
    ):
        bkw_erzeugung = tages_summe.bkw_kwh
        tageswert_gruppen.add(TAGESWERT_BKW)

    pv_kwh = (pv_modul_summe or 0.0) + bkw_erzeugung
    erzeugung = ErzeugungFakten(
        pv_module_kwh=pv_modul_summe,
        bkw_kwh=bkw_erzeugung,
        sonstige_erzeuger_kwh=roh.sonstiges_erzeugung,
        pv_kwh=pv_kwh,
        # Netzpunkt-Bilanz: der sonstige Erzeuger speist hinter denselben Zähler.
        hinter_zaehler_kwh=erzeugung_hinter_zaehler_kwh(pv_kwh, roh.sonstiges_erzeugung),
        pv_je_modul=pv_je_modul,
        pv_vollstaendig=pv_vollstaendig,
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
    eauto_ladedaten, wallbox_ladedaten, anteil_abgeleitet = reichere_ladezeilen_an(
        eauto_daten=roh.eauto_ladedaten,
        wallbox_daten=roh.wallbox_ladedaten,
        quote=tages_summe.abgeleiteter_pv_anteil if tages_summe is not None else None,
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
        wallbox_in_betrieb=bool(wallbox_ladedaten) or any(
            i.typ == "wallbox" and not ist_dienstlich(i)
            and i.ist_aktiv_im_monat(jahr, monat)
            for i in investitionen
        ),
        dienstwagen_je_inv=roh.dienstlich_je_inv,
        # Nur im laufenden Monat nicht leer (Regel 1: dort zählt auch eine Quelle).
        heimlade_quellen=heimlade_quellen,
        pv_quote=tages_summe.abgeleiteter_pv_anteil if tages_summe is not None else None,
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
        eauto_ladedaten=tuple(eauto_ladedaten),
        ladedaten_je_inv={
            **dict(zip(roh.eauto_ladedaten_ids, eauto_ladedaten)),
            **dict(zip(roh.wallbox_ladedaten_ids, wallbox_ladedaten)),
        },
        wallbox_ladedaten=tuple(wallbox_ladedaten),
        eauto_summe=summiere_emob_quelle(eauto_ladedaten),
        wallbox_summe=summiere_emob_quelle(wallbox_ladedaten),
        # Ungeschätzt — nur für den Community-Payload (s. Feld-Docstring).
        eauto_summe_gemessen=summiere_emob_quelle(roh.eauto_ladedaten),
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
