"""
Daten-Checker: der Heiz-/Kühlstrom-Widerspruchs-Befund (#263 K-2, Entscheid E-H)
läuft an der Wärmepumpe — nicht an Gerätetypen, die nie Modus-Felder tragen.

Trigger: F-59 (Prüfbericht Daten-Checker 2026-08-22). Der Block stand seit
`f0b8db90` in `_check_investition_monatsdaten`, deren Aufrufer nur
BKW/Speicher/E-Auto/Wallbox sind — der Befund konnte für sein Zielgerät nie
erscheinen (CHANGELOG-Zusage v4.0.21 ungedeckt). Zusätzlich las Zeile 820
`param`, das dort nicht gebunden war: ein Modus-Wert > 0 hätte die gesamte
Checker-Antwort in einen NameError laufen lassen (die N84/P5-Klasse).

Vor dem Fix ist dieser Test zweifach rot: `test_wp_modus_widerspruch_warnt`
findet keine Meldung (Block unerreichbar), `test_alte_stelle_wirft_keinen_
nameerror_mehr` stirbt am NameError.

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_daten_checker_wp_modus_widerspruch.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.models import Anlage, Investition, Monatsdaten  # noqa: E402
from backend.models.investition import InvestitionMonatsdaten  # noqa: E402
from backend.services.daten_checker import (  # noqa: E402
    CheckSeverity,
    DatenChecker,
)

WIDERSPRUCH_TEXT = "Heiz- und Kühlstrom zusammen größer"


def _wp_mit_daten(
    *, typ: str = "waermepumpe", param: dict | None = None, verbrauch_daten: dict,
) -> tuple[Investition, list[Monatsdaten]]:
    """Eine Investition mit einem IMD-Monat (06/2026) + passende Monatsdaten-Zeile."""
    inv = Investition(
        id=42,
        anlage_id=1,
        typ=typ,
        bezeichnung="Test-Gerät",
        aktiv=True,
        anschaffungsdatum=date(2026, 1, 15),
        parameter=param or {},
    )
    inv.monatsdaten = [
        InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=6,
            verbrauch_daten=dict(verbrauch_daten),
        )
    ]
    monatsdaten = [Monatsdaten(anlage_id=1, jahr=2026, monat=6)]
    return inv, monatsdaten


def _widersprueche(ergebnisse) -> list:
    return [
        e for e in ergebnisse
        if e.schwere == CheckSeverity.WARNING and WIDERSPRUCH_TEXT in e.meldung
    ]


def test_wp_modus_widerspruch_warnt():
    """WP: Modus-Teilmengen (80+30) > Gesamt (100) + 0.5 → WARNING mit Monat + investition_id."""
    inv, monatsdaten = _wp_mit_daten(verbrauch_daten={
        "stromverbrauch_kwh": 100,
        "modus_strom_heizen_kwh": 80,
        "modus_strom_kuehlen_kwh": 30,
    })
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_wp_monatsdaten(inv, "Test-WP", inv.parameter, monatsdaten)
    treffer = _widersprueche(ergebnisse)
    assert treffer, (
        f"Widerspruchs-WARNING erwartet. Meldungen: {[e.meldung for e in ergebnisse]}"
    )
    assert "06/2026" in treffer[0].meldung
    assert treffer[0].investition_id == 42


def test_wp_modus_teilmenge_bleibt_still():
    """WP: Teilmengen (60+30) <= Gesamt (100) → kein Widerspruchs-Befund."""
    inv, monatsdaten = _wp_mit_daten(verbrauch_daten={
        "stromverbrauch_kwh": 100,
        "modus_strom_heizen_kwh": 60,
        "modus_strom_kuehlen_kwh": 30,
    })
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_wp_monatsdaten(inv, "Test-WP", inv.parameter, monatsdaten)
    assert not _widersprueche(ergebnisse)


def test_getrennte_strommessung_rechnet_gegen_die_split_summe():
    """`param` wird wirklich gelesen: Gesamt = strom_heizen + strom_warmwasser (110),
    Modus-Summe 120 → WARNING. Genau der Pfad, der vorher am ungebundenen
    `param` gestorben wäre."""
    inv, monatsdaten = _wp_mit_daten(
        param={"getrennte_strommessung": True},
        verbrauch_daten={
            "strom_heizen_kwh": 50,
            "strom_warmwasser_kwh": 60,
            "modus_strom_heizen_kwh": 80,
            "modus_strom_kuehlen_kwh": 40,
        },
    )
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_wp_monatsdaten(inv, "Test-WP", inv.parameter, monatsdaten)
    assert _widersprueche(ergebnisse), (
        f"WARNING gegen die Split-Summe erwartet. Meldungen: {[e.meldung for e in ergebnisse]}"
    )


def test_alte_stelle_wirft_keinen_nameerror_mehr():
    """`_check_investition_monatsdaten` läuft mit Modus-Feldern in der Zeile
    durch, ohne zu sterben — und meldet den Widerspruch dort NICHT mehr
    (der Block ist umgezogen, nicht dupliziert)."""
    inv, monatsdaten = _wp_mit_daten(typ="speicher", verbrauch_daten={
        "speicher_ladung_kwh": 10,
        "modus_strom_heizen_kwh": 80,
        "modus_strom_kuehlen_kwh": 30,
    })
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_investition_monatsdaten(
        inv, "Test-Speicher",
        pflicht_feld="speicher_ladung_kwh", feld_label="Ladung",
        schwere=CheckSeverity.WARNING, monatsdaten=monatsdaten,
    )
    assert not _widersprueche(ergebnisse)
