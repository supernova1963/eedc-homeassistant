"""
Daten-Checker: `_check_phev_anteil_unbestimmt` — PHEV mit Kilometern, aber ohne
bestimmbaren elektrischen Fahranteil, warnt; alle Entlastungswege schweigen.

Trigger: Prüfbericht Daten-Checker 2026-08-22 (B8, Test-Lücke) — der Check war
seit seinem Bau ungetestet, D5 schließt die Lücke.

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_daten_checker_phev_anteil_unbestimmt.py
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.daten_checker import (
    CheckKategorie,
    DatenChecker,
)

_KAT = CheckKategorie.PHEV_ANTEIL_UNBESTIMMT.value


def _imd(jahr: int, monat: int, **verbrauch_daten):
    return SimpleNamespace(jahr=jahr, monat=monat, verbrauch_daten=verbrauch_daten)


def _anlage(*, parameter: dict, monate: list, typ: str = "e-auto"):
    inv = SimpleNamespace(
        id=7, typ=typ, bezeichnung="Test-PHEV",
        parameter=parameter, monatsdaten=monate,
    )
    return SimpleNamespace(id=1, investitionen=[inv])


def _run(anlage):
    svc = DatenChecker(db=None)  # der Check liest nur die geladenen Objekte
    return [e for e in svc._check_phev_anteil_unbestimmt(anlage)
            if e.kategorie == _KAT]


def test_phev_ohne_verbrauch_und_ohne_anteil_warnt():
    """Verbrenner gepflegt, ≥2 Monate mit km ohne kWh → WARNING mit investition_id."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    treffer = _run(anlage)
    assert treffer, "WARNING erwartet"
    assert treffer[0].investition_id == 7
    assert "2 Monaten" in treffer[0].details


def test_unter_mindestmonaten_schweigt():
    """Nur EIN unbestimmter Monat liegt unter PHEV_MINDEST_MONATE_OHNE_VERBRAUCH."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900, verbrauch_kwh=150)],
    )
    assert not _run(anlage)


def test_gemessener_fahrverbrauch_entlastet():
    """`verbrauch_kwh` in allen km-Monaten → der gemessene Weg, kein Befund."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5},
        monate=[_imd(2026, 5, km_gefahren=800, verbrauch_kwh=140),
                _imd(2026, 6, km_gefahren=900, verbrauch_kwh=150)],
    )
    assert not _run(anlage)


def test_geschaetzter_fahranteil_entlastet_auch_bei_null():
    """`elektrischer_fahranteil_prozent` gepflegt — 0 ist ein Wert (is not None)."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5,
                   "elektrischer_fahranteil_prozent": 0},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    assert not _run(anlage)


def test_bev_ohne_verbrenner_schweigt():
    """Kein `eigener_verbrauch_l_100km` → BEV, nichts aufzuteilen."""
    anlage = _anlage(
        parameter={},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    assert not _run(anlage)


def test_dienstwagen_schweigt():
    """Dienstwagen sind aus allen Ersparnis-Sichten gefiltert — auch hier."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5, "ist_dienstlich": True},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    assert not _run(anlage)


# ── Ein geleertes Feld ist kein gepflegter Wert (rapahl, T89667 #253) ──
#
# Seit dem Formular-Fix nimmt ein geleertes Feld den gespeicherten Wert zurück,
# indem es `""` sendet — der Weg, auf dem eine einmal getroffene Auswahl
# überhaupt erst zurücknehmbar wurde. Dieser Check las den Rohwert und fragte
# `is not None`: ein `""` hätte ihn zum Schweigen gebracht, obwohl der Anteil
# gerade NICHT gepflegt ist. Er las damit an `_fahranteil_prozent` vorbei, das
# die drei rechnenden Stellen benutzen — der Check schwieg genau dann, wenn die
# Rechnung „unbestimmt" ergibt.
#
# ⚠ Die Grenze zu `test_geschaetzter_fahranteil_entlastet_auch_bei_null`: `0`
# ist ein gepflegter Wert und entlastet weiterhin. Nur das Nicht-Gepflegte
# darf nicht entlasten.


def test_geleerter_fahranteil_entlastet_nicht():
    """`""` heißt „nicht gepflegt" — der Check muss weiter warnen."""
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5,
                   "elektrischer_fahranteil_prozent": ""},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    assert _run(anlage), "geleertes Feld darf nicht entlasten"


def test_unlesbarer_fahranteil_entlastet_nicht():
    """Auch ein unbrauchbarer Wert entlastet nicht — die Rechnung sieht ihn nie.

    Sonst schwiege der Check, während `teile_fahrleistung` mangels Zahl auf
    „100 % elektrisch" fällt: Ersparnis und CO₂ zu gut, ohne jeden Hinweis.
    """
    anlage = _anlage(
        parameter={"eigener_verbrauch_l_100km": 6.5,
                   "elektrischer_fahranteil_prozent": "keine Ahnung"},
        monate=[_imd(2026, 5, km_gefahren=800),
                _imd(2026, 6, km_gefahren=900)],
    )
    assert _run(anlage), "unlesbarer Wert darf nicht entlasten"
