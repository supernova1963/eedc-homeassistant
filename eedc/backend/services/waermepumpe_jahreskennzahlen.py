"""Die Wärmepumpen-Kennzahlen eines Zeitraums aus den Monats-Fakten — EINE Stelle.

B6/Y-2 (05.09.2026): Bis hierher rechnete `cockpit/uebersicht.py` (Cockpit → Jahr,
B4) den ganzen Kennzahl-Satz aus den Fakten — Arbeitszahl mit Grund und Hinweis,
je Funktion, Kühlen, Herkunft, Vorbehalt, Betriebsarten — und der PDF-Jahresbericht
rechnete daneben eine **eigene** Arbeitszahl und warf ihren Grund weg: „–" ohne
Grund im gedruckten Bericht (SOLL §3.3 S3), keine Kennzahl je Funktion, keine
Kühl-Arbeitszahl, keine Herkunft der Wärme, kein Vorbehalt (gemessen an F2b · F7 ·
F8 · F11 · F12). Zwei Jahres-Rechnungen für dieselbe Frage sind die Klasse, an
der die Drift-Inventur 2026-07-31 entstanden ist (ADR-001, SOLL §3.3 S1).

Hier steht die Faltung über die Monate genau einmal; Cockpit → Jahr und der
Jahresbericht lesen dasselbe Ergebnis. Die Regeln, die sie trägt:

* **R2 — Q und E derselben Abgrenzung:** getrennte Ströme und Wärmen nur aus
  Monaten MIT getrennter Messung (`hat_split`), sonst teilte man die Wärme aller
  Monate durch den Strom einiger.
* **Ein** Monat mit verletzter Abgrenzung (Fremdanteil, gemischte Bauarten,
  Geräte ohne Wärmezähler) macht die Jahreszahl zum Mischquotienten — deshalb
  `any(...)`, nicht „überwiegend".
* Die Restmenge der Betriebsarten ist die **Σ der monatlichen Layer-Reste** (E4:
  Lüften und Entfeuchten sind Mengen, keine Kennzahl), nicht eine eigene Differenz.
* Der Herkunfts-Faktor (Strom × JAZ) ist nur bei **einer** Wärmepumpe benennbar.

Die Formeln selbst stehen im Layer (`core/berechnungen/waermepumpe_kennzahl.py`);
dieses Modul faltet nur die Fakten und ruft sie.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from backend.core.berechnungen.modus_split import heiz_effizienz_gepflegt
from backend.core.berechnungen.waermepumpe_kennzahl import (
    Arbeitszahl,
    ArbeitszahlJeFunktion,
    abgrenzungs_grund,
    arbeitszahl,
    arbeitszahl_je_funktion,
    arbeitszahl_kuehlen,
    ersparnis_vorbehalt,
    waerme_herkunft,
)


@dataclass(frozen=True)
class WpBetriebsarten:
    """Σ der Betriebsart-Ströme über den Zeitraum — Teilmengen des WP-Stroms."""
    heizen_kwh: float
    kuehlen_kwh: float
    warmwasser_kwh: float
    lueften_kwh: float
    entfeuchten_kwh: float
    nicht_aufgeteilt_kwh: float
    abdeckung_h: float
    bezug_kwh: float
    gemessen: bool


@dataclass(frozen=True)
class WpJahreskennzahlen:
    """Der Kennzahl-Satz eines Zeitraums, mit Gründen — nie nur die Zahlen."""
    waerme_kwh: float
    strom_kwh: float
    heizung_kwh: float
    warmwasser_kwh: float
    waerme_abgeleitet_kwh: float
    abgrenzung: Optional[str]
    abgrenzung_stoerung: Optional[str]
    arbeitszahl: Arbeitszahl
    hat_split: bool
    strom_heizen_kwh: float
    strom_warmwasser_kwh: float
    je_funktion: ArbeitszahlJeFunktion
    kaelte_kwh: float
    kuehlen: Arbeitszahl
    hat_modus: bool
    betriebsarten: WpBetriebsarten
    abgeleitet: bool
    herkunft: str
    vorbehalt: Optional[str]


def waermepumpe_jahreskennzahlen(
    fakten: Sequence, wp_invs: Iterable,
) -> WpJahreskennzahlen:
    """Faltet die Monats-Fakten eines Zeitraums zu den WP-Kennzahlen.

    ``fakten``: die Monats-Fakten der Anlage (ADR-002/P10). ``wp_invs``: die
    Wärmepumpen-Investitionen, die für den Zeitraum zählen — nur ihre Anzahl und
    (bei genau einer) ihre Parameter werden gelesen (Herkunfts-Faktor).
    """
    wp_invs = list(wp_invs)
    waerme = sum(f.wp.waerme_kwh for f in fakten)
    strom = sum(f.wp.strom_kwh for f in fakten)
    heizung = sum(f.wp.heizung_kwh for f in fakten)
    warmwasser = sum(f.wp.warmwasser_kwh for f in fakten)
    waerme_abgeleitet = sum(f.wp.waerme_abgeleitet_kwh for f in fakten)
    stoerung = next(
        (f.wp.abgrenzung_stoerung for f in fakten if f.wp.abgrenzung_stoerung), None,
    )
    abgrenzung = abgrenzungs_grund(
        abgrenzung_stoerung=stoerung,
        bauarten_gemischt=any(f.wp.bauarten_gemischt for f in fakten),
        geraete_ohne_waerme=any(f.wp.waerme_deckt_nicht_alle_geraete for f in fakten),
    )
    az = arbeitszahl(
        waerme, strom,
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        strom_funktionsfremd_kwh=sum(f.wp.modus_strom_funktionsfremd_kwh for f in fakten),
        abgrenzung_verletzt=abgrenzung,
    )
    hat_split = any(f.wp.hat_split for f in fakten)
    strom_heizen = sum(f.wp.strom_heizen_kwh for f in fakten if f.wp.hat_split)
    strom_ww = sum(f.wp.strom_warmwasser_kwh for f in fakten if f.wp.hat_split)
    je_funktion = arbeitszahl_je_funktion(
        heizung_kwh=sum(f.wp.heizung_kwh for f in fakten if f.wp.hat_split),
        strom_heizen_kwh=strom_heizen,
        warmwasser_kwh=sum(f.wp.warmwasser_kwh for f in fakten if f.wp.hat_split),
        strom_warmwasser_kwh=strom_ww,
        hat_split=hat_split,
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        abgrenzung_verletzt=abgrenzung,
    )
    kaelte = sum(f.wp.nutzenergie_kuehlen_kwh for f in fakten)
    modus_kuehlen = sum(f.wp.modus_strom_kuehlen_kwh for f in fakten)
    kuehlen = arbeitszahl_kuehlen(kaelte, modus_kuehlen, abgrenzung_verletzt=abgrenzung)
    betriebsarten = WpBetriebsarten(
        heizen_kwh=sum(f.wp.modus_strom_heizen_kwh for f in fakten),
        kuehlen_kwh=modus_kuehlen,
        warmwasser_kwh=sum(f.wp.modus_strom_warmwasser_kwh for f in fakten),
        lueften_kwh=sum(f.wp.modus_strom_lueften_kwh for f in fakten),
        entfeuchten_kwh=sum(f.wp.modus_strom_entfeuchten_kwh for f in fakten),
        nicht_aufgeteilt_kwh=sum(f.wp.modus_nicht_aufgeteilt_kwh for f in fakten),
        abdeckung_h=sum(f.wp.modus_abdeckung_h for f in fakten),
        bezug_kwh=sum(f.wp.modus_strom_bezug_kwh for f in fakten),
        gemessen=any(f.wp.modus_gemessen for f in fakten),
    )
    abgeleitet = waerme_abgeleitet > 0
    ref_param = wp_invs[0].parameter if len(wp_invs) == 1 else None
    herkunft = waerme_herkunft(
        abgeleitet,
        heiz_effizienz_gepflegt(ref_param) if (abgeleitet and ref_param) else None,
    )
    return WpJahreskennzahlen(
        waerme_kwh=waerme,
        strom_kwh=strom,
        heizung_kwh=heizung,
        warmwasser_kwh=warmwasser,
        waerme_abgeleitet_kwh=waerme_abgeleitet,
        abgrenzung=abgrenzung,
        abgrenzung_stoerung=stoerung,
        arbeitszahl=az,
        hat_split=hat_split,
        strom_heizen_kwh=strom_heizen,
        strom_warmwasser_kwh=strom_ww,
        je_funktion=je_funktion,
        kaelte_kwh=kaelte,
        kuehlen=kuehlen,
        hat_modus=any(f.wp.hat_modus_split for f in fakten),
        betriebsarten=betriebsarten,
        abgeleitet=abgeleitet,
        herkunft=herkunft,
        vorbehalt=ersparnis_vorbehalt(waerme_abgeleitet=abgeleitet, abgrenzung=stoerung),
    )
