"""Päckchen R, Nachlauf N1: das Feld-Label **an der Investition** (`core/field_definitions/auswahl.py::feld_label_fuer_investition`).

`FELD_LABELS` ist flach über alle Typen, der letzte Eintrag gewinnt — gemessen am HEAD e3623eef5: `ladung_kwh` → «Ladung gesamt»
(falsch am Speicher), `netzbezug_eigener_tarif_kwh` → «Netzbezug zum Wallbox-Tarif» (falsch an der WP). Der Helfer nimmt das Label
der Registry für den Typ der Investition (dieselbe Quelle wie die Datenquellen-Fläche) und fällt sonst auf das flache zurück.
Benutzt von den Daten-Checker-Meldungen (Langzeitstatistik, Einheit, Rücksprung) und der Werkbank «Verwerfen vor Quellbeginn».
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.core.field_definitions import FELD_LABELS, feld_label_fuer_investition


def _inv(typ, parameter=None):
    return SimpleNamespace(typ=typ, parameter=parameter)


def test_flaches_dict_ist_mehrdeutig():
    """Der Anlass: das flache Dict trägt je Feld genau ein Label — am Speicher und an der WP das falsche."""
    assert FELD_LABELS["ladung_kwh"] == "Ladung gesamt"
    assert FELD_LABELS["netzbezug_eigener_tarif_kwh"] == "Netzbezug zum Wallbox-Tarif"


def test_label_je_typ():
    assert feld_label_fuer_investition(_inv("speicher"), "ladung_kwh") == "Ladung"
    assert feld_label_fuer_investition(_inv("wallbox"), "ladung_kwh") == "Ladung gesamt"
    assert feld_label_fuer_investition(_inv("waermepumpe"), "netzbezug_eigener_tarif_kwh") == "Netzbezug zum WP-Tarif"
    assert feld_label_fuer_investition(_inv("wallbox"), "netzbezug_eigener_tarif_kwh") == "Netzbezug zum Wallbox-Tarif"
    assert feld_label_fuer_investition(_inv("pv-module"), "pv_erzeugung_kwh") == "PV-Erzeugung"


def test_label_wenn_wird_aufgeloest():
    """Speicher mit Netzladung: dasselbe Label wie auf der Datenquellen-Fläche."""
    assert feld_label_fuer_investition(_inv("speicher", {"laedt_aus_netz": True}), "ladung_kwh") == "Ladung (gesamt, inkl. Netz)"


def test_rueckfall_ohne_investition_und_fuer_fremde_felder():
    assert feld_label_fuer_investition(None, "ladung_kwh") == FELD_LABELS["ladung_kwh"]
    assert feld_label_fuer_investition(_inv("waermepumpe"), "leistung_w") == FELD_LABELS.get("leistung_w", "leistung_w")
    assert feld_label_fuer_investition(_inv("speicher"), "gibt_es_nicht_kwh") == "gibt_es_nicht_kwh"


def test_innengeraete_kopie_heisst_wie_ihr_basisfeld():
    assert (feld_label_fuer_investition(_inv("waermepumpe"), "netzbezug_eigener_tarif_kwh-3")
            == feld_label_fuer_investition(_inv("waermepumpe"), "netzbezug_eigener_tarif_kwh"))
