"""
Daten-Checker: zwei Tarife derselben Verwendung mit IDENTISCHEM Gültig-ab sind
ein stummer Münzwurf (B6/#392-Rest) — und NUR dieser Gleichstand warnt; die
normale offene Tarif-Folge bleibt still (P-6-Grenze, gemessen 2026-08-22:
kein Auto-Schließen beim Anlegen, der Lader lässt das jüngste Gültig-ab
deterministisch gewinnen).

Dazu das P8-Prädikat `Strompreis.gilt_am` (D5): eine Stelle für die
Stichtags-Regel, deckungsgleich mit der WHERE-Klausel des Laders.

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_daten_checker_strompreis_gleichstand.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.models.strompreis import Strompreis  # noqa: E402
from backend.services.daten_checker import (  # noqa: E402
    CheckSeverity,
    DatenChecker,
)

GLEICHSTAND_TEXT = "beginnen am selben Tag"


def _tarif(ab: date, bis: date | None = None, verwendung: str = "allgemein",
           name: str | None = None) -> Strompreis:
    return Strompreis(
        anlage_id=1, gueltig_ab=ab, gueltig_bis=bis, verwendung=verwendung,
        tarifname=name, netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=8.0,
    )


def _check(strompreise: list) -> list:
    anlage = SimpleNamespace(
        strompreise=strompreise, investitionen=[], installationsdatum=None,
    )
    svc = DatenChecker(db=None)
    return svc._check_strompreise(anlage, monatsdaten=[])


def _gleichstand(ergebnisse) -> list:
    return [e for e in ergebnisse
            if e.schwere == CheckSeverity.WARNING and GLEICHSTAND_TEXT in e.meldung]


def test_gleiches_gueltig_ab_warnt_mit_beiden_namen():
    treffer = _gleichstand(_check([
        _tarif(date(2026, 1, 1), name="Alt"),
        _tarif(date(2026, 1, 1), name="Neu"),
    ]))
    assert treffer, "WARNING bei identischem Gültig-ab erwartet"
    assert "Alt" in treffer[0].details and "Neu" in treffer[0].details


def test_offene_tarif_folge_bleibt_still():
    """Der gestützte Normalfall: neuer Satz beginnt, der alte bleibt offen —
    der Lader entscheidet deterministisch, keine Meldung."""
    assert not _gleichstand(_check([
        _tarif(date(2025, 1, 1)),           # offen
        _tarif(date(2026, 1, 1)),           # jüngerer gewinnt ab 01/2026
    ]))


def test_verschiedene_verwendungen_am_selben_tag_sind_kein_gleichstand():
    """Allgemein- und WP-Tarif ab demselben Tag überlagern sich nicht —
    der Lader hält sie je Verwendung getrennt."""
    assert not _gleichstand(_check([
        _tarif(date(2026, 1, 1), verwendung="allgemein"),
        _tarif(date(2026, 1, 1), verwendung="waermepumpe"),
    ]))


def test_gilt_am_deckt_die_lader_klausel():
    """Grenzfälle des P8-Prädikats — exakt die WHERE-Klausel des Laders."""
    t = _tarif(date(2026, 3, 1), bis=date(2026, 6, 30))
    assert t.gilt_am(date(2026, 3, 1))       # Beginn einschließlich
    assert t.gilt_am(date(2026, 6, 30))      # Ende einschließlich
    assert not t.gilt_am(date(2026, 2, 28))  # davor
    assert not t.gilt_am(date(2026, 7, 1))   # danach
    offen = _tarif(date(2026, 3, 1))
    assert offen.gilt_am(date(2030, 1, 1))   # offenes Ende gilt weiter
