"""E6.B N5 (E5 ⚑6, Master-Entscheid Option b): die Anzeige-Grenze gilt **je Gerät**, nicht je Kategorie.

Bis E5 kappten `_check_emob_pv_ueber_gesamt` (10) und `_check_wp_arbeitszahl_unplausibel` (6) die Treffer **aller** Geräte
gemeinsam; die Gruppenzeile trennt aber je Gerät (`handgriffe.GRUPPEN`, `je=("investition_id",)`). Ein Gerät, dessen
Monate alle hinter den Monaten eines anderen lagen, hatte damit kein Glied und verschwand samt seiner Zahl
(Nachmessung E6 §3 Fall 2: Gerät A 10 Monate 2026, Gerät B 2 Monate 2025 ⇒ B unsichtbar, 10 von 12 Treffern sichtbar).
Seit E6.B kappt `gruppen.je_geraet_begrenzt` je Gerät: jedes Gerät mit Treffern hat mindestens ein Glied und sein eigenes
`werte.weitere`; je Gerät gilt Glieder + weitere = alle Treffer des Geräts. Ein Gerät allein ⇒ unverändert
(`test_n201_ladung_pv_ueber_gesamt.py`, 12 Monate ⇒ 10 + 2).

Schwesterdateien: `test_n201_ladung_pv_ueber_gesamt.py` (E-Mob, ein Gerät), `test_daten_checker_wp_arbeitszahl.py` (WP).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.gruppen import gruppen_bilden, je_geraet_begrenzt
from backend.services.daten_checker.waermepumpe import WaermepumpeChecks

_A, _B = 7, 8


def _monate(jahr: int, anzahl: int) -> list[tuple[int, int]]:
    return [(jahr, m) for m in range(1, anzahl + 1)]


def _inv(inv_id: int, typ: str, name: str, monate: list[tuple[int, int]], daten: dict):
    return SimpleNamespace(
        id=inv_id, typ=typ, bezeichnung=name, parameter={},
        monatsdaten=[SimpleNamespace(jahr=j, monat=m, verbrauch_daten=dict(daten)) for j, m in monate],
    )


def _je_geraet(ergebnisse) -> dict[int, tuple[int, int, str]]:
    """investition_id ⇒ (Glieder, weitere, Gruppentitel) nach dem Gruppenbau des Prüflaufs."""
    gruppen_bilden(ergebnisse)
    aus: dict[int, tuple[int, int, str]] = {}
    for inv_id in sorted({e.investition_id for e in ergebnisse}):
        glieder = [e for e in ergebnisse if e.investition_id == inv_id]
        weitere = {int((e.werte or {}).get("weitere") or 0) for e in glieder}
        assert len(weitere) == 1, f"ein `weitere` je Gerät, nicht {weitere}"
        titel = {e.gruppe.titel if e.gruppe else e.meldung for e in glieder}
        assert len(titel) == 1
        aus[inv_id] = (len(glieder), weitere.pop(), titel.pop())
    return aus


# ─── E-Mobilität: PV-Ladung größer als Gesamtladung (Grenze 10) ─────────────

_EMOB_WIDERSPRUCH = {"ladung_kwh": 50.0, "ladung_pv_kwh": 60.0}


def _emob(monate_a, monate_b):
    anlage = SimpleNamespace(id=1, investitionen=[
        _inv(_A, "wallbox", "Wallbox A", monate_a, _EMOB_WIDERSPRUCH),
        _inv(_B, "e-auto", "Auto B", monate_b, _EMOB_WIDERSPRUCH),
    ])
    return DatenChecker(MagicMock())._check_emob_pv_ueber_gesamt(anlage)


def test_emob_nachstellung_der_nachmessung_beide_geraete_sichtbar():
    """Gerät A 10 Monate 2026, Gerät B 2 Monate 2025: 12 Treffer = 10 (A) + 2 (B), beide mit eigenem Glied."""
    ergebnisse = _emob(_monate(2026, 10), _monate(2025, 2))
    assert len(ergebnisse) == 12
    je = _je_geraet(ergebnisse)
    assert je[_A] == (10, 0, "10 Monate: PV-Ladung größer als Gesamtladung")
    assert je[_B] == (2, 0, "2 Monate: PV-Ladung größer als Gesamtladung")


def test_emob_grenze_je_geraet_mit_weiteren():
    """A 12 Monate 2026 ⇒ 10 Glieder + 2 weitere = 12; B 2 Monate 2025 ⇒ 2 + 0 = 2 (früher: B verschwand)."""
    je = _je_geraet(_emob(_monate(2026, 12), _monate(2025, 2)))
    assert je[_A] == (10, 2, "12 Monate: PV-Ladung größer als Gesamtladung")
    assert je[_B] == (2, 0, "2 Monate: PV-Ladung größer als Gesamtladung")


# ─── Wärmepumpe: Arbeitszahl zu hoch (Grenze 6) ─────────────────────────────

_WP_AZ_9 = {"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 900.0}


def _wp(monate_a, monate_b):
    anlage = SimpleNamespace(investitionen=[
        _inv(_A, "waermepumpe", "WP A", monate_a, _WP_AZ_9),
        _inv(_B, "waermepumpe", "WP B", monate_b, _WP_AZ_9),
    ])
    return WaermepumpeChecks()._check_wp_arbeitszahl_unplausibel(anlage)


def test_wp_nachstellung_beide_geraete_sichtbar():
    """A 10 Monate 2026 ⇒ 6 Glieder + 4 weitere = 10; B 2 Monate 2025 ⇒ 2 + 0 = 2 (früher: B verschwand)."""
    ergebnisse = _wp(_monate(2026, 10), _monate(2025, 2))
    assert len(ergebnisse) == 8
    je = _je_geraet(ergebnisse)
    assert je[_A] == (6, 4, "10 Monate mit unplausibel hoher Arbeitszahl")
    assert je[_B] == (2, 0, "2 Monate mit unplausibel hoher Arbeitszahl")


def test_wp_ein_geraet_unveraendert():
    """Ein Gerät: die Grenze je Gerät ist die alte Grenze (6 Glieder + Rest)."""
    je = _je_geraet(_wp(_monate(2026, 9), []))
    assert je == {_A: (6, 3, "9 Monate mit unplausibel hoher Arbeitszahl")}


# ─── der Helfer selbst ──────────────────────────────────────────────────────

def test_je_geraet_begrenzt_haelt_reihenfolge_und_zaehlt_je_geraet():
    treffer = [(1, "a"), (2, "b"), (1, "c"), (1, "d"), (2, "e"), (3, "f")]
    auswahl, weitere = je_geraet_begrenzt(treffer, 2)
    assert auswahl == [(1, "a"), (2, "b"), (1, "c"), (2, "e"), (3, "f")]
    assert dict(weitere) == {1: 1}
    for geraet in (1, 2, 3):
        assert sum(1 for t in auswahl if t[0] == geraet) + weitere[geraet] == sum(1 for t in treffer if t[0] == geraet)
