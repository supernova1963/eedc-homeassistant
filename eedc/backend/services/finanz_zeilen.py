"""Gemeinsamer Builder für ``FinanzMonatsZeile`` (#326).

**Single Source of Truth für die Eingabe-Aufbereitung** der Finanz-Aggregation.
Der reine Aggregat-Helper ``berechne_finanz_aggregat`` (core/berechnungen) garantiert
nur dann denselben Netto-Ertrag über alle Read-Sites, wenn er auch dieselben
**Eingaben** bekommt. Genau das ist mehrfach gedriftet (#326): jede Read-Site löste
den Monatstarif selbst auf — eine nahm den neuesten Strompreis für ALLE Jahre statt
des je Monat gültigen (rilmor-mhrs, ~174 € Drift).

Dieser Builder kapselt den drift-anfälligen Teil — die **per-Monat-Tarif-Auflösung**
(``lade_tarife_fuer_anlage`` über ``gueltig_ab``/``gueltig_bis`` + Flex-Ø-Override) —
und ist die **einzige** erlaubte Stelle, an der ``FinanzMonatsZeile`` konstruiert wird
(Konformitäts-Wächter ``test_finanz_monatszeile_nur_im_builder``). Eine künftige
Read-Site kann damit nicht mehr versehentlich einen Einheitstarif verwenden — sie
MUSS durch ``baue_finanz_zeile``.

Energiemengen-Aggregation und §51-Negativpreis (``neg_preis_kwh``) bleiben beim Caller
— die unterscheiden sich legitim je Site (welche Monate/PV-Quelle/Filter). Sie fließen
über ``FinanzZeileEingabe`` herein.

DB-I/O (Tarif-Lookup) → bewusst NICHT in core/berechnungen (ADR-001 = DB-frei),
sondern hier in der Service-Schicht.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_netzbezug_preis_cent,
)
from backend.services.strompreis_aggregator import PreisMessung, aufgeloester_monatspreis
from backend.core.berechnungen import FinanzMonatsZeile
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)


@dataclass
class FinanzZeileEingabe:
    """Pro-Monat-Eingabe für den Finanz-Zeilen-Builder.

    Enthält alles AUSSER dem Tarif — den löst der Builder per Monat auf. Die
    Energiemengen + ``neg_preis_kwh`` bereitet der Caller auf (legitim
    site-spezifisch). ``monatsdaten`` dient nur dem Flex-Ø-Override
    (``netzbezug_durchschnittspreis_cent``) und darf ``None`` sein.
    """
    jahr: int
    monat: int
    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0
    pv_erzeugung_kwh: float = 0.0
    speicher_ladung_kwh: float = 0.0
    speicher_entladung_kwh: float = 0.0
    v2h_entladung_kwh: float = 0.0
    #: §9.2 — an Dritte abgegebene kWh, vom Eigenverbrauch abgezogen (Layer).
    abgabe_dritte_kwh: float = 0.0
    bkw_eigenverbrauch_kwh: float = 0.0
    neg_preis_kwh: Optional[float] = None
    monatsdaten: Any = None
    #: Der **EV-gewichtete** Slot-Preis dieses Zeitraums, wenn der Caller ihn
    #: kennt (Tagesebene seit 17.09.2026). ``None`` ⇒ die Ersparnis wird mit
    #: dem Bezugspreis bewertet, wie bisher. Begründung: SOLL Flex-Tarife
    #: **A-2** — gewichtet wird mit der Menge, die bewertet wird, und der
    #: vermiedene Bezug fällt zu anderen Zeiten an als der tatsächliche.
    ev_preis_cent: Optional[float] = None
    #: N-588: Wandlungsverluste des Zeitraums und Messpunkt-Vertrag (``ErzeugungFakten`` bzw. ``KanalTag``) — der
    #: Aggregat-Helper bewertet den Eigenverbrauch ohne sie, wenn der Vertrag hält. ``None`` ⇒ bitgleich.
    wandlungsverluste_kwh: Optional[float] = None
    verluste_grund: Optional[str] = None


async def baue_finanz_zeile(
    db: AsyncSession,
    anlage_id: int,
    eingabe: FinanzZeileEingabe,
    *,
    tarif_cache: dict[date, dict],
    preis_messung: Optional[PreisMessung] = None,
) -> FinanzMonatsZeile:
    """Baut EINE ``FinanzMonatsZeile`` mit dem je Monat gültigen Tarif.

    ``tarif_cache`` ist caller-eigen (ein Dict pro Aggregations-Lauf), damit der
    Tarif je Stichtag nur einmal aus der DB geladen wird.

    ``preis_messung`` ist dieselbe Bauform für Stufe 2 der Preis-Kaskade: Wer
    vorher ``lade_monats_fakten`` gerufen hat, reicht **dasselbe** Objekt weiter
    — sonst fragt diese Funktion die Stundenpreise des Monats ein weiteres Mal
    ab (drittes Mal je Monat, gemessen 15.09.2026).
    """
    stichtag = date(eingabe.jahr, eingabe.monat, 1)
    if stichtag not in tarif_cache:
        tarif_cache[stichtag] = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=stichtag
        )
    allgemein = tarif_cache[stichtag].get("allgemein")
    # N-267: mit Zeitfenstern (HT/NT) ist der Preis des Monats der ueber den
    # gemessenen Netzbezug gewichtete Arbeitspreis; ohne Fenster liefert der
    # Helfer die Spalte unveraendert. Ohne eigenen Cache — diese Funktion baut
    # EINE Zeile. Warum er auch nicht im `tarif_cache` mitreist, steht in
    # `monats_fakten/tarif.py` im Block ueber `_komponenten_preis`.
    # ⭐ **Die ganze Kaskade an einer Stelle** (#412, 11.09.2026): gepflegt →
    # gemessen → Zeitfenster → Stamm. Bis dahin standen hier zwei Schritte —
    # `wirksamer_arbeitspreis_cent` (Zeitfenster) und darunter der
    # `resolve_netzbezug_preis_cent`-Override (gepflegt) —, und die **Messung**
    # fehlte dazwischen ganz: Wer einen dynamischen Tarif hat, rechnete im
    # laufenden Monat und an jedem Tag mit dem Stammpreis, obwohl eedc die
    # Stundenpreise mitschreibt.
    preis = await aufgeloester_monatspreis(
        db, anlage_id, eingabe.jahr, eingabe.monat, eingabe.monatsdaten, allgemein,
        messung=preis_messung,
    )
    verg_cent = (
        allgemein.einspeiseverguetung_cent_kwh if allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
    )
    # #392: variable Einspeisevergütung — der Satz des Monats schlägt den
    # Stammwert (dieselbe Bauform wie der Flex-Ø beim Netzbezug unten).
    verg_cent = resolve_einspeise_preis_cent(eingabe.monatsdaten, verg_cent)
    return FinanzMonatsZeile(
        einspeisung_kwh=eingabe.einspeisung_kwh or 0,
        netzbezug_kwh=eingabe.netzbezug_kwh or 0,
        pv_erzeugung_kwh=eingabe.pv_erzeugung_kwh or 0,
        speicher_ladung_kwh=eingabe.speicher_ladung_kwh or 0,
        speicher_entladung_kwh=eingabe.speicher_entladung_kwh or 0,
        v2h_entladung_kwh=eingabe.v2h_entladung_kwh or 0,
        abgabe_dritte_kwh=eingabe.abgabe_dritte_kwh or 0,
        bkw_eigenverbrauch_kwh=eingabe.bkw_eigenverbrauch_kwh or 0,
        netzbezug_preis_cent=preis.cent,
        # A-2 auf JEDER Ebene (seit 18.09.2026): kennt der Aufrufer den
        # EV-gewichteten Preis (Tagesebene), gilt seiner; sonst der aus der
        # Monatsmessung — damit rechnen Cockpit → Monat/Jahr, Aussichten, PDF
        # und HA-Export dieselbe Ersparnis wie die Summe der Tage es tut. Ohne
        # Messung bleibt ``None`` und der Aggregat-Helper nimmt den Bezugspreis
        # (Prüfstein 2: bei Festpreis bewegt sich keine Zahl).
        ev_preis_cent=(
            eingabe.ev_preis_cent if eingabe.ev_preis_cent is not None else preis.ev_cent
        ),
        netzbezug_preis_herkunft=preis.herkunft,
        einspeiseverguetung_cent=verg_cent,
        neg_preis_kwh=eingabe.neg_preis_kwh,
        wandlungsverluste_kwh=eingabe.wandlungsverluste_kwh,
        verluste_grund=eingabe.verluste_grund,
    )
