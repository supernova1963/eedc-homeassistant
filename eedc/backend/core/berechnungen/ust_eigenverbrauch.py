"""USt auf den Eigenverbrauch (unentgeltliche Wertabgabe, § 3 Abs. 1b UStG).

Single Source of Truth für **zwei** Größen, die bis 2026-08-04 in je eigener
Handschrift an sechs Read-Sites standen:

1. **Die Bemessungsgrundlage** — welche Anschaffungskosten in die Selbstkosten
   je kWh eingehen. Im Baum lagen dafür *vier* Formen nebeneinander
   (Fund **N-129**): vier Sichten setzten die **Vollkosten** ein
   (`Σ anschaffungskosten_gesamt`, also inkl. des vollen Kaufpreises eines
   E-Autos), das Cockpit eine ad-hoc zusammengesetzte Summe aus
   `PV-System + WP-Mehrkosten + eAuto-Mehrkosten + Sonstiges` — die dabei
   **nicht** das gepflegte Feld `anschaffungskosten_alternativ` las, sondern die
   Parameter-Defaults 35.000/8.000 €. Dieselbe Anlage bekam je Sicht eine andere
   USt. Kanon seit 04.08. (Entscheid Gernot): **Mehrkosten** =
   `Σ max(0, gesamt − alternativ)` — das, was die Cockpit-Summe gemeint hat, nur
   mit dem Feld, das der Anwender pflegt.

2. **Der Zeitraum** — die Selbstkosten je kWh sind eine **Jahres**-Größe
   (Jahres-AfA + Jahres-Betriebskosten ÷ Jahres-Erzeugung). Vier Sichten
   übergaben als „Jahres-Erzeugung" die Erzeugung ihres **gewählten Zeitraums**;
   bei Filter „alle Jahre" stand im Nenner eine mehrjährige Menge, im Zähler eine
   Ein-Jahres-Abschreibung ⇒ die USt fiel um den Faktor der Jahresanzahl zu
   niedrig aus (Fund **N-130**, am Demo-Bestand gemessen: 646 € statt 2.447 €
   über 34 Monate, Faktor 3,79). Diese Funktion rechnet deshalb **je
   Kalenderjahr** und summiert.

**Angeschnittene Jahre zählen anteilig** (Entscheid Gernot 04.08.): AfA und
Betriebskosten werden mit `monate / 12` gewichtet. Sonst trägt ein Jahr mit
sieben Betriebsmonaten zwölf Monate Abschreibung gegen sieben Monate Ertrag und
die Selbstkosten je kWh steigen künstlich. Dieselbe Gewichtung wenden
Jahresbericht und Aussichten für die Betriebskosten des Zeitraums längst an
(`betriebskosten_jahr * anzahl_monate / 12`) — hier ist es dieselbe Regel an der
einen Stelle.

**Was diese Funktion NICHT vereinheitlicht:** welche Menge als „Eigenverbrauch"
eingeht. Cockpit und HA-Export übergeben den **Netzpunkt**-Eigenverbrauch (inkl.
Brennstoff-Erzeuger), Jahresbericht, Aussichten und die Monatszeile den
**Finanz**-Eigenverbrauch (PV allein). Das ist die vorbestehende Asymmetrie aus
Fund **N-131**; sie hier still zu glätten wäre eine fünfte Lesart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from backend.core.berechnungen.investitionskosten import (
    relevante_kosten_aus_investitionen,
)


@dataclass(frozen=True)
class UstJahresanteil:
    """Ein Kalenderjahr des ausgewerteten Zeitraums.

    ``monate`` ist die Zahl der Monate **dieses Jahres**, die im ausgewerteten
    Zeitraum liegen (1–12) — der Gewichtungsfaktor für AfA und Betriebskosten.
    Für eine hochgerechnete Jahresprognose ist er 12.
    """

    jahr: int
    eigenverbrauch_kwh: float
    pv_kwh: float
    monate: int = 12


# Lineare AfA über 20 Jahre — die steuerliche Nutzungsdauer einer PV-Anlage.
AFA_JAHRE = 20


def bemessungsgrundlage_aus_investitionen(investitionen: Iterable) -> float:
    """Kanonische USt-Bemessungsgrundlage: Σ max(0, gesamt − alternativ).

    **Identisch mit den relevanten Kosten der Wirtschaftlichkeitsrechnung** —
    seit N-137 steht die Definition deshalb nur noch einmal, in
    `investitionskosten.relevante_kosten_aus_investitionen`. Zwei Namen für
    denselben Wert, weil das Steuerrecht ihn anders nennt als die
    Amortisationsrechnung; **eine** Formel, damit USt, Amortisations-Fortschritt
    und Amortisationsdauer nicht wieder auseinanderlaufen.
    """
    return relevante_kosten_aus_investitionen(investitionen)


def berechne_ust_eigenverbrauch(
    jahresanteile: Sequence[UstJahresanteil],
    *,
    bemessungsgrundlage_euro: float,
    betriebskosten_jahr_euro: float,
    ust_satz_prozent: float = 19.0,
) -> float:
    """USt auf den Eigenverbrauch über einen beliebig langen Zeitraum.

    Je Kalenderjahr:

        selbstkosten_kwh = (AfA_jahr + Betriebskosten_jahr) × monate/12 ÷ PV_jahr
        ust_jahr         = Eigenverbrauch_jahr × selbstkosten_kwh × Satz/100

    Ein Jahr ohne PV-Erzeugung oder ohne Eigenverbrauch trägt 0 bei — nicht
    ``None`` und keinen Fehler: die Sichten liefern auch Monate, in denen noch
    kein Erzeuger lief.

    Returns:
        USt-Betrag in Euro (positiv = Kosten für den Betreiber), der vom
        Netto-Ertrag ABZUZIEHEN ist.
    """
    if ust_satz_prozent <= 0:
        return 0.0

    jahreskosten = bemessungsgrundlage_euro / AFA_JAHRE + betriebskosten_jahr_euro
    if jahreskosten <= 0:
        return 0.0

    summe = 0.0
    for anteil in jahresanteile:
        if anteil.pv_kwh <= 0 or anteil.eigenverbrauch_kwh <= 0:
            continue
        anteilige_kosten = jahreskosten * min(anteil.monate, 12) / 12
        selbstkosten_pro_kwh = anteilige_kosten / anteil.pv_kwh
        summe += anteil.eigenverbrauch_kwh * selbstkosten_pro_kwh * ust_satz_prozent / 100
    return summe


def ust_eigenverbrauch_fuer_anlage(
    anlage,
    *,
    jahresanteile: Sequence[UstJahresanteil],
    bemessungsgrundlage_euro: float,
    betriebskosten_jahr_euro: float,
) -> float:
    """USt inkl. der Steuerregime-Vorprüfung.

    Single Source der drei Zeilen, die vor der Formel stehen müssen: nur bei
    ``steuerliche_behandlung == "regelbesteuerung"``, sonst ``0.0``; fehlender
    ``ust_satz_prozent`` → 19 %. Genau diese Vorprüfung stand doppelt im Baum
    (Cockpit + Aussichten) und **fehlte** im Jahresbericht-PDF und im HA-Export —
    dort lag der Netto-Ertrag bei Regelbesteuerung um den USt-Betrag über dem
    Cockpit (#326-Inventur, Dimension 2).

    ``anlage`` wird nur per ``getattr`` gelesen — kein ORM-Import.
    """
    if (getattr(anlage, "steuerliche_behandlung", None) or "keine_ust") != "regelbesteuerung":
        return 0.0
    satz = getattr(anlage, "ust_satz_prozent", None)
    return berechne_ust_eigenverbrauch(
        jahresanteile,
        bemessungsgrundlage_euro=bemessungsgrundlage_euro,
        betriebskosten_jahr_euro=betriebskosten_jahr_euro,
        ust_satz_prozent=satz if satz is not None else 19.0,
    )
