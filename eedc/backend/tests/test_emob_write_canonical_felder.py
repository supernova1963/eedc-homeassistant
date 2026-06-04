"""Phase 2a Etappe 3 — Write-Side-Kanonisierung der manuellen Erfassung.

Existiert eine Wallbox-Investition, ist sie die kanonische Quelle der
Heimladung. Die manuelle Monatsabschluss-Erfassung blendet die E-Auto-
Heim-Lade-Felder (`ladung_pv_kwh`/`ladung_netz_kwh`) dann aus, damit die
Heimladung nicht zusätzlich am E-Auto erfasst wird (sonst Dual-Daten →
Doppelzählung; siehe docs/KONZEPT-WALLBOX-EAUTO.md). Km, Verbrauch und die
Extern-Ladung (fahrzeugspezifisch) bleiben am E-Auto.

Die strukturierten Import-Pfade (`data_import.py`, evcc-Parser) routen die
Heimladung bereits auf die Wallbox-Investition — hier nur die Form-Felder.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.field_definitions import get_felder_fuer_investition


def _felder(typ: str, anlage_typen: list[str]) -> set[str]:
    invs = [SimpleNamespace(typ=t) for t in anlage_typen]
    return {f["feld"] for f in get_felder_fuer_investition(typ, {}, anlage_investitionen=invs)}


def test_eauto_ohne_wallbox_zeigt_heim_ladefelder():
    """Steckerlader/Schuko (keine Wallbox) → E-Auto trägt die Heimladung selbst."""
    felder = _felder("e-auto", ["e-auto"])
    assert "ladung_pv_kwh" in felder
    assert "ladung_netz_kwh" in felder
    assert "km_gefahren" in felder
    assert "ladung_extern_kwh" in felder


def test_eauto_mit_wallbox_blendet_heim_ladefelder_aus():
    """Wallbox vorhanden → Heim-Lade-Felder am E-Auto verschwinden; Fahrzeug-
    und Extern-Felder bleiben."""
    felder = _felder("e-auto", ["e-auto", "wallbox"])
    assert "ladung_pv_kwh" not in felder
    assert "ladung_netz_kwh" not in felder
    assert "km_gefahren" in felder
    assert "verbrauch_kwh" in felder
    assert "ladung_extern_kwh" in felder
    assert "ladung_extern_euro" in felder


def test_wallbox_felder_unveraendert():
    """Die Wallbox-Form behält ihre Heimladungs-Felder (= kanonische Quelle)."""
    felder = _felder("wallbox", ["e-auto", "wallbox"])
    assert "ladung_kwh" in felder
    assert "ladung_pv_kwh" in felder
    assert "ladevorgaenge" in felder


def test_ohne_anlage_kontext_alle_felder_sichtbar():
    """`anlage_investitionen=None` → bedingung_anlage wird nicht ausgewertet
    (z. B. Import-Kontext) → E-Auto-Heim-Felder bleiben sichtbar."""
    felder = {f["feld"] for f in get_felder_fuer_investition("e-auto", {})}
    assert "ladung_pv_kwh" in felder
    assert "ladung_netz_kwh" in felder
