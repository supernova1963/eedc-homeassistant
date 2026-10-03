"""Cockpit → Jahr: welche Monate gehören dazu, und ihre zwölf Antworten — Aufbereitung für die Jahresroute.

Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026, Vorlage B3, Entscheid E3). Bis dahin lud der Browser die
Monatsantworten eines Jahres (6er-Pool) und faltete sie selbst (``v4/JahrAggregat.tsx``). D3 („kein neuer Endpoint",
24.06.2026) ist damit zurückgenommen — mit derselben Begründung, die D3 trug: „ein Jahr ist die Summe seiner Monate,
kein zweiter Code-Pfad". Der Browser-Fold WAR der zweite Code-Pfad, außerhalb jedes Backend-Wächters (ADR-001-Nachtrag).

Hier steht die **Aufbereitung** (welche Monate, in welcher Reihenfolge geladen); die Faltung selbst ist Layer
(``core/berechnungen/ergebnis.py::falte_zeitraum``). Die Monatsauswahl ist 1:1 die des Clients:

* ``zu_ladende_monate`` — Intervall vom ersten Datenmonat der Anlage bis zum laufenden Monat bzw. Dezember, plus jede
  erfasste Zeile (N-65: ein Monat ohne Abschluss fehlte sonst ganz in der Jahreszahl).
* ``monat_hat_daten`` — nur Monate mit gemessenen MENGEN; ein Monat vor der Inbetriebnahme antwortet mit Stammdaten
  (SOLL, Tarif) und darf das SOLL nicht aufblähen.
* ``abgeschlossene_monate`` — die Grundgesamtheit des Vergleichs: ohne den laufenden Monat (N-37, P-12).

``heute`` ist ``date.today()`` in der **Prozesszone** — kein Zonen-Pin (Entscheid Gernot 24.08.2026, CLAUDE.md).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.ergebnis import falte_zeitraum, jahr_vergleich_aus, mittel_jahre

logger = logging.getLogger(__name__)

#: Die gemessenen Mengen einer Monatsantwort — wie ``MENGEN_FELDER`` im Client bis 03.10.2026.
MENGEN_FELDER: tuple[str, ...] = (
    "pv_erzeugung_kwh", "einspeisung_kwh", "netzbezug_kwh", "eigenverbrauch_kwh",
    "direktverbrauch_kwh", "gesamtverbrauch_kwh",
    "speicher_ladung_kwh", "speicher_entladung_kwh",
    "wp_strom_kwh", "wp_waerme_kwh",
    "emob_ladung_kwh", "emob_km",
    "bkw_erzeugung_kwh", "sonstiges_erzeugung_kwh", "sonstiges_verbrauch_kwh", "abgabe_dritte_kwh",
)


def monat_hat_daten(m: Mapping[str, Any]) -> bool:
    return any(m.get(k) is not None for k in MENGEN_FELDER)


def zu_ladende_monate(zeilen: Sequence[Mapping[str, Any]], jahr: int, heute: date) -> list[int]:
    menge = {r["monat"] for r in zeilen if r["jahr"] == jahr}
    if zeilen and jahr <= heute.year:
        erstes_jahr = min(r["jahr"] for r in zeilen)
        if jahr >= erstes_jahr:
            von = (
                min(r["monat"] for r in zeilen if r["jahr"] == erstes_jahr)
                if jahr == erstes_jahr else 1
            )
            bis = heute.month if jahr == heute.year else 12
            menge.update(range(von, bis + 1))
    return sorted(menge)


def abgeschlossene_monate(monate: Iterable[int], jahr: int, heute: date) -> list[int]:
    monate = list(monate)
    if jahr != heute.year:
        return monate
    return [m for m in monate if m < heute.month]


async def baue_jahr(db: AsyncSession, anlage_id: int, jahr: int, *, heute: Optional[date] = None) -> dict[str, Any]:
    """Die Jahresantwort: zwölf Monatsantworten (in derselben Sitzung, sequenziell), Kopf, Vergleich, Vorjahr, Ø-Jahr."""
    from backend.api.routes.aktueller_monat import _berechne_monat
    from backend.api.routes.aktueller_monat.kontext import lade_monats_kontext
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
    from backend.core.exceptions import not_found
    from backend.models.anlage import Anlage

    heute = heute or date.today()
    anlage = (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage_id)
    )).scalar_one_or_none()
    if anlage is None:
        raise not_found("Anlage")

    zeilen = [
        z.model_dump() for z in await list_monatsdaten_aggregiert(
            anlage_id, jahr=None, inkl_ohne_zaehlerzeile=True, inkl_nur_tageswerte=True, db=db,
        )
    ]
    kontext = await lade_monats_kontext(db, anlage, jahr)
    antworten: list[dict[str, Any]] = []
    for m in zu_ladende_monate(zeilen, jahr, heute):
        try:
            antwort = await _berechne_monat(anlage_id, jahr, m, db, kontext=kontext)
        except Exception:  # pragma: no cover - ein Monat kippt das Jahr nicht (wie der Client)
            logger.exception("Jahresroute: Monat %s/%s nicht berechenbar", m, jahr)
            continue
        d = antwort.model_dump()
        if monat_hat_daten(d):
            antworten.append(d)
    try:
        kennzahlen = (await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=jahr, db=db)).model_dump()
    except Exception:  # pragma: no cover - ohne Kennzahlen bleibt der Zustand vor B4 (wie der Client)
        logger.exception("Jahresroute: Übersicht %s nicht ladbar", jahr)
        kennzahlen = None

    monate_nr = [d["monat"] for d in antworten]
    vergleichs_monate = abgeschlossene_monate(monate_nr, jahr, heute)
    kopf = falte_zeitraum(antworten, jahr, kennzahlen)
    vergleich = (
        None if vergleichs_monate == monate_nr
        else falte_zeitraum([d for d in antworten if d["monat"] in vergleichs_monate], jahr)
    )
    vj = jahr_vergleich_aus(zeilen, jahr - 1, vergleichs_monate)
    andere = sorted({z["jahr"] for z in zeilen} - {jahr})
    oe = mittel_jahre([jahr_vergleich_aus(zeilen, j, vergleichs_monate) for j in andere], vergleichs_monate)
    return {
        "jahr": jahr,
        "monate": antworten,
        "kopf": kopf,
        "vergleich": vergleich,
        "monate_nr": monate_nr,
        "vergleichs_monate": vergleichs_monate,
        "vorjahr": vj if vj["monate"] else None,
        "oe_jahr": oe,
    }
