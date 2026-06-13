"""
Regressionstests für die kanonische Investitionstyp-Reihenfolge
(Fundament P4 / F7, #243).

Hintergrund: Sechs Read-/Export-Sites sortierten Investitionen alphabetisch
nach `typ` (balkonkraftwerk zuerst!) statt nach `INVESTITION_TYP_ORDER`.
Sie nutzen jetzt alle `sort_investitionen_nach_typ()` als Single Source of
Truth. Dieser Test hält die Reihenfolge fest, damit sie nicht zurückdriftet.
"""

from __future__ import annotations

from backend.models.investition import Investition
from backend.utils.investition_filter import (
    INVESTITION_TYP_ORDER,
    sort_investitionen_nach_typ,
)


def test_kanon_reihenfolge_ist_fixiert():
    """Wallbox VOR E-Auto, BKW NACH Speicher (detLAN #186/#211/#214)."""
    assert INVESTITION_TYP_ORDER == [
        "wechselrichter",
        "pv-module",
        "speicher",
        "balkonkraftwerk",
        "waermepumpe",
        "wallbox",
        "e-auto",
        "sonstiges",
    ]


def test_sort_bringt_durcheinander_in_kanon():
    """Eine alphabetisch/zufällig gemischte Liste wird kanonisch sortiert."""
    # Alphabetisch wäre: balkonkraftwerk, e-auto, pv-module, speicher,
    # waermepumpe, wallbox, wechselrichter — also komplett anders.
    items = [
        Investition(id=1, typ="e-auto"),
        Investition(id=2, typ="wechselrichter"),
        Investition(id=3, typ="waermepumpe"),
        Investition(id=4, typ="balkonkraftwerk"),
        Investition(id=5, typ="pv-module"),
        Investition(id=6, typ="wallbox"),
        Investition(id=7, typ="speicher"),
        Investition(id=8, typ="sonstiges"),
    ]
    sortiert = [i.typ for i in sort_investitionen_nach_typ(items)]
    assert sortiert == INVESTITION_TYP_ORDER


def test_unbekannter_typ_landet_am_ende():
    items = [
        Investition(id=1, typ="sonstiges"),
        Investition(id=2, typ="phantasie-typ"),
        Investition(id=3, typ="speicher"),
    ]
    sortiert = [i.typ for i in sort_investitionen_nach_typ(items)]
    assert sortiert == ["speicher", "sonstiges", "phantasie-typ"]


def test_tiebreaker_id_innerhalb_eines_typs():
    """Innerhalb desselben Typs stabil nach id."""
    items = [
        Investition(id=30, typ="pv-module"),
        Investition(id=10, typ="pv-module"),
        Investition(id=20, typ="pv-module"),
    ]
    ids = [i.id for i in sort_investitionen_nach_typ(items)]
    assert ids == [10, 20, 30]
