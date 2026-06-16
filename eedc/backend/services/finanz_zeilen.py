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
    resolve_netzbezug_preis_cent,
)
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
    bkw_eigenverbrauch_kwh: float = 0.0
    neg_preis_kwh: Optional[float] = None
    monatsdaten: Any = None


async def baue_finanz_zeile(
    db: AsyncSession,
    anlage_id: int,
    eingabe: FinanzZeileEingabe,
    *,
    tarif_cache: dict[date, dict],
) -> FinanzMonatsZeile:
    """Baut EINE ``FinanzMonatsZeile`` mit dem je Monat gültigen Tarif.

    ``tarif_cache`` ist caller-eigen (ein Dict pro Aggregations-Lauf), damit der
    Tarif je Stichtag nur einmal aus der DB geladen wird.
    """
    stichtag = date(eingabe.jahr, eingabe.monat, 1)
    if stichtag not in tarif_cache:
        tarif_cache[stichtag] = await lade_tarife_fuer_anlage(
            db, anlage_id, target_date=stichtag
        )
    allgemein = tarif_cache[stichtag].get("allgemein")
    netz_cent = (
        allgemein.netzbezug_arbeitspreis_cent_kwh if allgemein else NETZBEZUG_DEFAULT_CENT
    )
    verg_cent = (
        allgemein.einspeiseverguetung_cent_kwh if allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
    )
    return FinanzMonatsZeile(
        einspeisung_kwh=eingabe.einspeisung_kwh or 0,
        netzbezug_kwh=eingabe.netzbezug_kwh or 0,
        pv_erzeugung_kwh=eingabe.pv_erzeugung_kwh or 0,
        speicher_ladung_kwh=eingabe.speicher_ladung_kwh or 0,
        speicher_entladung_kwh=eingabe.speicher_entladung_kwh or 0,
        v2h_entladung_kwh=eingabe.v2h_entladung_kwh or 0,
        bkw_eigenverbrauch_kwh=eingabe.bkw_eigenverbrauch_kwh or 0,
        # Flex-Ø-Override (dynamischer Tarif) vor dem Monatstarif.
        netzbezug_preis_cent=resolve_netzbezug_preis_cent(eingabe.monatsdaten, netz_cent),
        einspeiseverguetung_cent=verg_cent,
        neg_preis_kwh=eingabe.neg_preis_kwh,
    )
