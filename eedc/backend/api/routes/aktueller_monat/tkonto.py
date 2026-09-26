"""Die T-Konto-Zeile EINER Investition (`_baue_investition_financial`).

Laut Docstring der Funktion bewusst in der Routen-Schicht (Anzeige-Strings und Response-Modell,
kein Aggregat) — deshalb ein Modul dieses Pakets, nicht `core/berechnungen`.
"""
# Reiner Umzug aus `api/routes/aktueller_monat.py` (18.09.2026, Vorlage 1 des Refactorings
# grosser Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# exportiert alle Namen weiter, die Tests und Aufrufer bisher aus dem Modul importierten.

from typing import Optional
from backend.core.berechnungen.waermepumpe_kennzahl import heizwaerme_kwh, waerme_gesamt_kwh
from backend.core.berechnungen import berechne_speicher_ersparnis
from backend.services.wp_wirtschaftlichkeit import (
    WP_ERSPARNIS_FORMEL,
    berechne_wp_ersparnis,
    wp_ersparnis_berechnung,
)
from backend.services.eauto_wirtschaftlichkeit import (
    QUELLE_WALLBOX,
    attribute_emob_pool_by_km,
    berechne_eauto_ersparnis,
    entscheide_emob_heimladung,
    heimladung_des_autos,
    waehle_extern_paar,
)
from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.field_definitions import (
    SONSTIGES_ABGABE_LABEL,
    get_eauto_ladung_kwh,
    get_emob_pv_netz_kwh,
    get_speicher_netzladung_kwh,
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
    ist_abgabe_kategorie,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.zahlenformat import fmt_euro, fmt_zahl
from backend.core.investition_parameter import ist_dienstlich
from backend.api.routes.aktueller_monat.schemas import ERLOES_LABEL_EINSPEISUNG, InvestitionFinancialDetail


def _baue_investition_financial(
    inv,
    data: dict,
    *,
    netz_p: float,
    einsp_p: float,
    wp_p: float,
    wb_p: float,
    monats_gaspreis: Optional[float],
    monats_benzinpreis: Optional[float],
    emob_pool_attr,
    emob_entscheid=None,
) -> Optional[InvestitionFinancialDetail]:
    """Baut das T-Konto-Detail (InvestitionFinancialDetail) EINER Investition.

    Extrahiert aus get_aktueller_monat (Spur A, Refactoring-Plan). Bewusst IM
    Route-Modul statt core/berechnungen: erzeugt deutsche Anzeige-Strings
    (label/formel/berechnung) und das Pydantic-Response-Modell — Präsentations-
    Finanzlogik, kein Aggregat-Σ. Verhaltensneutral 1:1 übernommen.

    Gibt None zurück, wenn die Investition inaktiv ist ODER keinerlei finanzielle
    Relevanz hat (Inclusion-Guard: weder Betriebskosten noch Ersparnis/Erlös/
    sonstige Positionen). Preis-/Pool-Kontext wird vom Aufrufer einmal aufgelöst
    und übergeben.
    """
    if not inv.aktiv:
        return None
    bk_monat = round((inv.betriebskosten_jahr or 0) / 12, 2)
    # Sonstige Erträge/Ausgaben (z.B. AG-Vergütung Dienstwagen, THG-Quote)
    # für JEDE Investition evaluieren — typ-unabhängig, auch wenn der
    # Wirtschaftlichkeits-Zweig unten übersprungen wird (z.B. ist_dienstlich).
    inv_sonstige = berechne_sonstige_summen(data)
    inv_sonstige_ertraege = round(inv_sonstige["ertraege_euro"], 2)
    inv_sonstige_ausgaben = round(inv_sonstige["ausgaben_euro"], 2)
    inv_erloes: Optional[float] = None
    inv_erloes_formel: Optional[str] = None
    inv_erloes_berechnung: Optional[str] = None
    #: Default „Einspeisung" — die Abgabe-Kategorie überschreibt ihn unten.
    inv_erloes_label = ERLOES_LABEL_EINSPEISUNG

    inv_ersparnis: Optional[float] = None
    inv_label = ""
    inv_formel: Optional[str] = None
    inv_berechnung: Optional[str] = None

    if inv.typ == "balkonkraftwerk":
        ev_kwh = data.get("eigenverbrauch_kwh") or data.get("pv_erzeugung_kwh")
        einsp_kwh = data.get("einspeisung_kwh")
        if ev_kwh:
            inv_ersparnis = round(ev_kwh * netz_p / 100, 2)
            inv_label = "Eigenverbrauch-Ersparnis"
            inv_formel = "BKW-Eigenverbrauch × Netzbezugspreis"
            inv_berechnung = f"{fmt_zahl(ev_kwh, 1)} kWh × {fmt_zahl(netz_p, 2)} ct/kWh"
        if einsp_kwh and einsp_kwh > 0:
            inv_erloes = round(einsp_kwh * einsp_p / 100, 2)
            # A6: Formel und eingesetzte Werte in GETRENNTE Felder — beides in
            # einem Satz stand unter der Überschrift „Formel", während jede
            # andere Kachel „Berechnung" daneben führt. Kein Wert ändert sich.
            inv_erloes_formel = "Einspeisung × Einspeisevergütung"
            inv_erloes_berechnung = (
                f"{fmt_zahl(einsp_kwh, 1)} kWh × {fmt_zahl(einsp_p, 2)} ct/kWh"
            )

    elif inv.typ == "speicher":
        entl_kwh = data.get("entladung_kwh")
        if entl_kwh and entl_kwh > 0:
            # SPREAD, nicht Voll-Netzbezugspreis (Entscheid Gernot 2026-08-04,
            # #358 — er bestätigt den Drift-Audit-Entscheid A3, der seit
            # `core/berechnungen/speicher_wirtschaftlichkeit.py` im Docstring
            # steht und den ROI und Aussichten längst befolgen). Bis hierher
            # rechnete das T-Konto `Entladung × Netzbezug` und damit bei 30/8 ct
            # 36 % über der Zahl, die dieselbe Anlage in der ROI-Sicht trug.
            #
            # Begründung: die entladene kWh hätte sonst eingespeist werden
            # können — die entgangene Vergütung ist eine reale Gegenposition.
            # Netzgeladene Energie ist davon ausgenommen (sie hätte nie
            # eingespeist werden können); diese Trennung macht der Layer, nicht
            # dieser Aufrufer.
            netzladung = get_speicher_netzladung_kwh(data)
            lad_kwh = data.get("ladung_kwh") or 0
            # Gemessener Monats-η, sonst der Layer-Default. Er wirkt nur auf die
            # Aufteilung der Entladung nach Herkunft, nicht auf den PV-Spread.
            eta = (entl_kwh / lad_kwh * 100) if lad_kwh > 0 else None
            erg = berechne_speicher_ersparnis(
                entladung_kwh=entl_kwh,
                bezug_preis_cent=netz_p,
                einspeise_verg_cent=einsp_p,
                ladung_netz_kwh=netzladung,
                **({"wirkungsgrad_prozent": eta} if eta is not None else {}),
                lade_preis_cent=data.get("speicher_ladepreis_cent"),
            )
            inv_ersparnis = round(erg.ersparnis_euro, 2)
            inv_label = "Entladung-Ersparnis"
            if netzladung > 0:
                inv_formel = "PV-Anteil × (Netzbezug − Einspeisung) + Netz-Anteil × (Netzbezug − Ladepreis)"
                inv_berechnung = (
                    f"{fmt_zahl(erg.pv_anteil_entladung_kwh, 1)} kWh × {fmt_zahl(erg.spread_cent_kwh, 2)} ct/kWh"
                    f" + {fmt_zahl(erg.netz_anteil_entladung_kwh, 1)} kWh Netz-Anteil"
                )
            else:
                inv_formel = "Speicher-Entladung × (Netzbezugspreis − Einspeisevergütung)"
                inv_berechnung = f"{fmt_zahl(entl_kwh, 1)} kWh × {fmt_zahl(erg.spread_cent_kwh, 2)} ct/kWh"

    elif inv.typ == "waermepumpe":
        # N-398: dieselbe Weiche wie im Layer — Geraetefeld, sonst die gemessene
        # Nutzenergie Heizbetrieb. Ohne sie blieb die Zeile „Ersparnis vs.
        # Alternative" an einer Split-Klimaanlage leer, die ihre Waerme je
        # Innengeraet misst.
        waerme = heizwaerme_kwh(data)
        # N-379: die eine Lesetuer — an einem Geraet ohne Warmwasserkreis ist 0.
        ww = get_wp_warmwasser_kwh(data, inv.parameter)
        strom = get_wp_strom_kwh(data, inv.parameter) or None
        # ⛔ **N-391/D1 (14.09.2026): Gesamtwert vor Summanden, je Geraet.**
        # Hier stand bis dahin `(waerme or 0) + (ww or 0)`. Traegt der Monat
        # dieses Geraets EINEN Waermemengenzaehler (`waerme_kwh`), war die
        # Summe **0** — und die Zeile „Ersparnis vs. Alternative" entstand
        # wegen der Bedingung darunter **gar nicht**, waehrend der
        # Komponenten-Hub fuer dieselbe Anlage seit WK-14b eine Ersparnis
        # nennt. Zwei Sichten, zwei Auskuenfte (SOLL §3.3 S1). Gemessen ueber
        # die echte Route (`get_aktueller_monat`): Lage B **0** WP-Zeilen,
        # Lage D eine Zeile mit **33,33 EUR**.
        waerme_total = waerme_gesamt_kwh(data.get("waerme_kwh"), waerme, ww)
        if waerme_total > 0 and strom is not None:
            wp_result = berechne_wp_ersparnis(
                wp_waerme_kwh=waerme_total,
                wp_strom_kwh=strom,
                wp_strompreis_cent=wp_p,
                wp_parameter=inv.parameter,
                monats_gaspreis_cent=monats_gaspreis,
                # E-B: Kühlen ersetzt keine Heizung (#263 K-2).
                # B5/X-5c: über den SoT der Betriebsart-Weiche (F-56) — das
                # Rohfeld kennt nur den abgeleiteten Split; bei gemessenen
                # Betriebsart-Zählern stand hier 0 und der Kühlstrom blieb im
                # Vergleich (dieselbe Klasse wie im Hub am 26.08.).
                strom_kuehlen_kwh=modus_strom_zeile(data).kuehlen_kwh,
            )
            inv_ersparnis = round(wp_result.ersparnis_euro, 2)
            # #411: Der ersetzte Energietraeger ist gepflegt (Gas · Oel ·
            # Strom-Direktheizung) und wird korrekt verrechnet — die
            # Beschriftung nannte trotzdem unbedingt Gas. Der Block fasst
            # ausserdem mehrere Waermepumpen zusammen, die verschiedene
            # Traeger ersetzt haben koennen: ein Aggregat kann keinem
            # einzelnen folgen. Deshalb die allgemeine Form.
            inv_label = "Ersparnis vs. Alternative"
            # B6/Y-3: Formel und Rechnung beschreiben, was der Layer rechnet —
            # mit Zusatzkosten der Altheizung und ohne den Kühlstrom (E-B). Bis
            # hierher stand ein Text, der bei F8 10 € ergab, neben dem Wert 100 €.
            inv_formel = WP_ERSPARNIS_FORMEL
            inv_berechnung = wp_ersparnis_berechnung(
                wp_result, waerme_total, strom, wp_p, inv.parameter,
            )

    elif inv.typ in ("e-auto", "wallbox") and not ist_dienstlich(inv):
        km = data.get("km_gefahren") or 0
        ladung = get_eauto_ladung_kwh(data) or None
        # #262: SoT-Helper konsolidiert den vorherigen Inline-Fallback
        # (netz = ladung_netz ?? total − pv) — gleiche Semantik, gleiche
        # Drift-Quelle wie in den anderen Read-Sites.
        ladung_pv, netz_kwh = get_emob_pv_netz_kwh(data, total_kwh=ladung or 0)
        ladung_pv = ladung_pv or None
        heim_des_autos = 0.0
        if inv.typ == "e-auto":
            # N-555 (Konzept Regel 2): die Heimladung DIESES Autos kommt aus dem
            # Entscheid des Monats (`je_auto`) — seine eigene Messung, sein Anteil am
            # Rest der Wallbox (nach km, bei 0 km zusammen gleich verteilt, E6), die
            # Schätzung aus dem Fahrverbrauch oder 0. Ohne übergebenen Entscheid
            # (Einzelaufruf) entscheidet die Funktion aus dieser Zeile und dem
            # Wallbox-Topf des Aufrufers.
            entscheid = emob_entscheid or entscheide_emob_heimladung(
                eauto_je_inv={inv.id: data},
                wallbox_zeilen=[{
                    "ladung_kwh": emob_pool_attr.wb_pool_pv + emob_pool_attr.wb_pool_netz,
                    "ladung_pv_kwh": emob_pool_attr.wb_pool_pv,
                }] if emob_pool_attr.use_wb_pool else [],
            )
            pv_a, netz_a = heimladung_des_autos(entscheid, inv.id)
            ladung_pv = pv_a or None
            netz_kwh = netz_a
            heim_des_autos = pv_a + netz_a
        # ⭐ N-555 Stufe 2: das `km > 0`-Tor gilt nicht mehr für ein E-Auto, das geladen
        # hat (Konzept Regel 2, E6): hier stand `if km and km > 0` — ein Auto, das im
        # Monat geladen hat, aber nicht gefahren ist, verlor still seine Stromrechnung.
        if (km and km > 0) or heim_des_autos > 0:
            extern_euro = data.get("ladung_extern_euro", 0) or 0
            if inv.typ == "e-auto" and entscheid.quelle == QUELLE_WALLBOX:
                share = attribute_emob_pool_by_km(emob_pool_attr, km)
                if share.netz_kwh + share.pv_kwh > 0:
                    # N-555 F-5: Extern nach der Topf-Regel (höhere Kosten), nicht
                    # blind der Wallbox-Anteil — sonst fiel das Extern des Autos weg.
                    _, extern_euro = waehle_extern_paar(
                        share.extern_kwh, share.extern_euro,
                        data.get("ladung_extern_kwh", 0) or 0, extern_euro,
                    )
            eauto_result = berechne_eauto_ersparnis(
                km_gefahren=km,
                ladung_netz_kwh=max(0, netz_kwh),
                ladung_extern_euro=extern_euro,
                wallbox_strompreis_cent=wb_p,
                eauto_parameter=inv.parameter,
                monats_benzinpreis_euro=monats_benzinpreis,
                # #331: der EXPLIZITE Fahrverbrauch, nicht `ladung` von oben —
                # `get_eauto_ladung_kwh` fällt auf dasselbe Feld zurück und
                # läse eine Heimladung als Fahrleistung.
                fahrverbrauch_kwh=data.get("verbrauch_kwh"),
            )
            inv_ersparnis = round(eauto_result.ersparnis_euro, 2)
            inv_label = "Ersparnis vs. Verbrenner"
            inv_formel = "(km × Verbrauch × Benzinpreis) − Netzladung × Strompreis"
            inv_berechnung = (
                # N-555 (§11): deutsche Schreibweise über den Backend-SoT
                # `core/zahlenformat.py` (Style-Guide 0a) — hier stand
                # „1500 km × 7.5 L/100km × 1.65 €" mit Dezimalpunkt.
                f"{fmt_zahl(km, 0)} km × "
                f"{fmt_zahl(eauto_result.verwendeter_verbrauch_l_100km, 1)} L/100 km × "
                f"{fmt_euro(eauto_result.verwendeter_benzinpreis_euro)}"
            )
        elif inv.typ == "wallbox" and ladung_pv and ladung_pv > 0:
            inv_ersparnis = round(ladung_pv * wb_p / 100, 2)
            inv_label = "PV-Ladung-Ersparnis"
            inv_formel = "PV-Ladung × Netzbezugspreis"
            inv_berechnung = f"{fmt_zahl(ladung_pv, 1)} kWh × {fmt_zahl(wb_p, 2)} ct/kWh"

    elif inv.typ == "sonstiges":
        # ⛔ KEINE Eigenverbrauchs-Bewertung je Gerät (N-131, Entscheid Gernot
        # 2026-09-01: „Für einen sonstigen Erzeuger rechnet eedc den Nutzen
        # bewusst nicht selbst; er wird am Gerät als ‚Ertrag/Jahr' gepflegt").
        #
        # Bis 2026-09-02 stand hier `eigenverbrauch_kwh × netz_p` — und das war
        # eine **gemessene Doppelzählung**, keine zweite Meinung: Die Bilanz
        # führt den sonstigen Erzeuger über `erzeugung_hinter_zaehler_kwh` in
        # `eigenverbrauch_kwh` (ein Netzanschluss, ein Zähler), und
        # `ev_ersparnis_euro` bewertet **diese** Menge. Dieselben kWh standen
        # damit zweimal im Σ HABEN. Gegen eine Probe-Anlage erhoben: 430 kWh
        # Bilanz-Eigenverbrauch (129,00 €) enthielten die 50 kWh des BHKW, die
        # daneben noch einmal mit 15,00 € auftraten.
        #
        # ⚠ Die PV-Zeile sagt das seit N-131 sogar selbst („Eigenverbrauch aus
        # Sonstiges ist hier nicht bewertet") — der Satz war unwahr, solange
        # diese Zeile daneben stand. Jetzt stimmt er.
        #
        # ⚑ Der Erlös bleibt, aber nur als **gepflegter** Betrag: Konzept §9
        # Weg 2 (`einspeise_erloes_euro`, Layer-SoT
        # `finanz_aggregat.erzeuger_erloes_euro` = „Σ der gepflegten Erlöse").
        # Ein aus `einspeisung_kwh × Anlagen-Vergütung` gerechneter Betrag wäre
        # die zweite Doppelzählung: diese kWh stehen im Hauszähler und sind in
        # `einspeise_erloes_euro` eine Zeile höher bereits bewertet. Wer einen
        # eigenen Vergütungssatz hat, hat einen eigenen Zähler — und pflegt
        # deshalb den Betrag (Begründung Maintainer 2026-08-10, §9).
        #
        # ⚑ §9.2 Geldseite (06.09.): Dasselbe Feld trägt bei der Kategorie
        # *Abgabe an Dritte* eine **andere Ertragsart** — den Erlös des dritten
        # Wegs statt eines Einspeise-Erlöses. Der Betrag wird gleich behandelt
        # (gepflegt, nicht nachgerechnet), nur benannt wird er anders: Regel 0
        # verlangt für die Geldzeile denselben Namen wie für die Energiezeile.
        # Vorher stand über beiden „— Einspeisung", und rilmor-mhrs (#402) hat
        # im T-Konto ein Wort gelesen, das seine Bilanz gar nicht kennt.
        erloes_gepflegt = data.get("einspeise_erloes_euro")
        if erloes_gepflegt:
            inv_erloes = round(float(erloes_gepflegt), 2)
            if ist_abgabe_kategorie((inv.parameter or {}).get("kategorie")):
                inv_erloes_label = SONSTIGES_ABGABE_LABEL
                inv_erloes_formel = (
                    f"Am Gerät gepflegter Erlös aus {SONSTIGES_ABGABE_LABEL} "
                    "(eigener Satz) — von eedc nicht nachgerechnet"
                )
            else:
                inv_erloes_formel = (
                    "Am Gerät gepflegter Einspeise-Erlös (eigener Vergütungssatz) "
                    "— von eedc nicht nachgerechnet"
                )

    if (
        bk_monat > 0
        or inv_ersparnis is not None
        or inv_erloes is not None
        or inv_sonstige_ertraege > 0
        or inv_sonstige_ausgaben > 0
    ):
        return InvestitionFinancialDetail(
            investition_id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            betriebskosten_monat_euro=bk_monat,
            betriebskosten_jahr_euro=round(float(inv.betriebskosten_jahr or 0), 2),
            erloes_euro=inv_erloes,
            erloes_formel=inv_erloes_formel,
            erloes_berechnung=inv_erloes_berechnung,
            erloes_label=inv_erloes_label,
            ersparnis_euro=inv_ersparnis,
            ersparnis_label=inv_label,
            formel=inv_formel,
            berechnung=inv_berechnung,
            sonstige_ertraege_euro=inv_sonstige_ertraege,
            sonstige_ausgaben_euro=inv_sonstige_ausgaben,
        )
    return None
