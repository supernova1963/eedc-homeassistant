"""Unit-Tests für den extrahierten T-Konto-Builder _baue_investition_financial.

Spur A des Backend-Refactoring-Plans: der per-Investition-Typ-Switch aus
get_aktueller_monat wurde in den modul-internen Helfer
`_baue_investition_financial` herausgelöst (verhaltensneutral). Diese Tests
prüfen ihn isoliert (transiente Investition-Objekte, kein DB) — die
End-to-End-Abdeckung der sechs Typ-Pfade bleibt in
test_aktueller_monat_tkonto.py.

Der Helfer bleibt bewusst im Route-Modul (nicht core/berechnungen): er erzeugt
deutsche Anzeige-Strings (label/formel/berechnung) + das Pydantic-Response-
Modell = Präsentations-Finanzlogik, kein Aggregat-Σ.
"""

from __future__ import annotations

from backend.api.routes.aktueller_monat import _baue_investition_financial
from backend.models import Investition
from backend.services.eauto_wirtschaftlichkeit import compute_emob_pool_attribution

# Default-Pool ohne evcc (use_wb_pool=False) — für Nicht-emob-Pfade irrelevant.
_POOL = compute_emob_pool_attribution(eauto_imd_data=[], wallbox_imd_data=[])

_PREISE = dict(netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0,
               monats_gaspreis=None, monats_benzinpreis=None, emob_pool_attr=_POOL)


def _inv(typ, **kw):
    """Transientes Investition-Objekt (kein Flush → id/aktiv explizit setzen)."""
    kw.setdefault("id", 1)
    kw.setdefault("aktiv", True)
    kw.setdefault("bezeichnung", f"{typ}-Test")
    return Investition(typ=typ, **kw)


def test_inaktive_investition_gibt_none():
    inv = _inv("balkonkraftwerk", aktiv=False)
    assert _baue_investition_financial(inv, {"eigenverbrauch_kwh": 100.0}, **_PREISE) is None


def test_inclusion_guard_pv_ohne_werte_gibt_none():
    inv = _inv("pv-module")  # kein T-Konto-Zweig
    assert _baue_investition_financial(inv, {"pv_erzeugung_kwh": 500.0}, **_PREISE) is None


def test_bkw_ersparnis_und_erloes():
    inv = _inv("balkonkraftwerk")
    d = _baue_investition_financial(
        inv, {"eigenverbrauch_kwh": 100.0, "einspeisung_kwh": 50.0}, **_PREISE)
    assert d is not None
    assert d.ersparnis_euro == 30.0   # 100 × 30 ct
    assert d.ersparnis_label == "Eigenverbrauch-Ersparnis"
    assert d.erloes_euro == 4.0        # 50 × 8 ct


def test_speicher_betriebskosten_durchgereicht():
    inv = _inv("speicher", betriebskosten_jahr=120.0)
    d = _baue_investition_financial(inv, {"entladung_kwh": 80.0}, **_PREISE)
    assert d is not None
    assert d.ersparnis_euro == 24.0
    assert d.betriebskosten_monat_euro == 10.0  # 120 / 12


def test_dienstwagen_zweig_uebersprungen_sonstige_bleiben():
    inv = _inv("e-auto", parameter={"ist_dienstlich": True})
    d = _baue_investition_financial(
        inv,
        {"km_gefahren": 1000.0, "ladung_kwh": 200.0,
         "sonstige_positionen": [
             {"bezeichnung": "AG-Vergütung", "betrag": 50.0, "typ": "ertrag"}]},
        **_PREISE)
    assert d is not None
    assert d.ersparnis_euro is None
    assert d.sonstige_ertraege_euro == 50.0
