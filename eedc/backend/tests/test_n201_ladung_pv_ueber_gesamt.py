"""N-201, erste Hälfte: eine Monatszeile, in der die PV-Ladung größer ist als
die Gesamtladung, wird gemeldet.

**Der Befund.** ``ladung_pv_kwh`` ist ein *Teil* von ``ladung_kwh``. An Anlage 1
stand für 06/2026 real **100,5 kWh PV bei 86,0 kWh Gesamt**. Kein Pfad im Baum
hat das je gemeldet: baumweiter Grep über ``daten_checker/`` fand das Feld
dreimal und **null** Vergleiche.

**Warum es trotzdem keine falsche Zahl erzeugt — und warum das der Grund für
die Meldung ist.** Die Rechenkette fängt den Widerspruch strukturell ab
(``summiere_emob_quelle`` bildet ``ladung_kwh`` als ``pv + netz``,
``get_emob_pv_netz_kwh`` klemmt ``netz`` mit ``max(0, total − pv)``; #262,
gewächtert in ``test_n314_pv_ladeanteil_spanne.py``). Genau dabei wird der
gepflegte Wert 86,0 **verworfen**: Der Anwender sieht eine Gesamtladung, die er
nie eingetragen hat, und erfährt nie, dass einer seiner beiden Werte falsch
ist. ``monats_fakten.pv_ladeanteil_prozent`` hält diese Lücke im Docstring
ausdrücklich als N-201 fest.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.services.daten_checker import DatenChecker, CheckKategorie

_KAT = CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value


def _imd(jahr, monat, **felder):
    return SimpleNamespace(jahr=jahr, monat=monat, verbrauch_daten=dict(felder))


def _inv(inv_id, typ, bezeichnung, monatsdaten):
    return SimpleNamespace(
        id=inv_id, typ=typ, bezeichnung=bezeichnung, parameter={},
        monatsdaten=monatsdaten,
    )


def _anlage(investitionen):
    return SimpleNamespace(id=1, investitionen=investitionen)


def _run(anlage):
    return DatenChecker(MagicMock())._check_emob_pv_ueber_gesamt(anlage)


def test_der_gemessene_anlassfall_wird_gemeldet():
    """100,5 kWh PV bei 86,0 kWh Gesamt — der reale Fall von Anlage 1, 06/2026."""
    inv = _inv(7, "wallbox", "Wallbox Garage", [
        _imd(2026, 6, ladung_kwh=86.0, ladung_pv_kwh=100.5),
    ])
    treffer = [e for e in _run(_anlage([inv])) if e.schwere == "warning"]

    assert len(treffer) == 1, f"Erwartet 1 Warnung, bekommen {treffer}"
    e = treffer[0]
    assert e.kategorie == _KAT
    assert "Wallbox Garage" in e.meldung
    assert "06/2026" in e.meldung
    assert "100.5" in e.meldung.replace(",", ".")
    assert "86.0" in e.meldung.replace(",", ".")
    assert e.investition_id == 7, "Der Befund gehört an sein Gerät (Komponenten-Hub)."
    assert e.link == "/einstellungen/daten?erfassen=2026-06"
    # Kein Reparatur-Knopf: eedc kann nicht wissen, welcher Wert stimmt.
    assert e.action_kind is None


def test_stimmige_zeile_schweigt():
    """Gegenrichtung: PV ≤ Gesamt ist der Normalfall und darf nie melden."""
    inv = _inv(7, "wallbox", "Wallbox Garage", [
        _imd(2026, 6, ladung_kwh=120.0, ladung_pv_kwh=100.5),
        _imd(2026, 7, ladung_kwh=100.0, ladung_pv_kwh=100.0),  # Gleichstand
    ])
    assert _run(_anlage([inv])) == []


def test_rundung_ist_kein_widerspruch():
    """0,05 kWh Überhang ist Rundung, kein Befund — sonst nörgelt die Prüfung."""
    inv = _inv(7, "e-auto", "ID.3", [
        _imd(2026, 6, ladung_kwh=86.0, ladung_pv_kwh=86.05),
    ])
    assert _run(_anlage([inv])) == []


def test_fehlende_gesamtladung_ist_kein_widerspruch():
    """Ohne `ladung_kwh` ist die Zeile unvollständig, nicht widersprüchlich.

    Das ist die Frage der Vollständigkeits-Prüfungen — hier kein zweiter Turm.
    """
    inv = _inv(7, "e-auto", "ID.3", [_imd(2026, 6, ladung_pv_kwh=100.5)])
    assert _run(_anlage([inv])) == []


def test_andere_geraetetypen_bleiben_aussen_vor():
    """Ein Speicher hat kein `ladung_pv_kwh` im Sinne dieser Regel."""
    inv = _inv(9, "speicher", "Hausakku", [
        _imd(2026, 6, ladung_kwh=86.0, ladung_pv_kwh=100.5),
    ])
    assert _run(_anlage([inv])) == []


def test_viele_monate_werden_gedeckelt():
    """12 widersprüchliche Monate → 10 Einzelmeldungen plus ein Rest-Hinweis."""
    inv = _inv(7, "wallbox", "Wallbox Garage", [
        _imd(2026, m, ladung_kwh=10.0, ladung_pv_kwh=30.0) for m in range(1, 13)
    ])
    ergebnisse = _run(_anlage([inv]))
    warnungen = [e for e in ergebnisse if e.schwere == "warning"]
    rest = [e for e in ergebnisse if e.schwere == "info"]
    assert len(warnungen) == 10, f"Erwartet 10, bekommen {len(warnungen)}"
    assert len(rest) == 1 and "2 weitere" in rest[0].meldung
    # Neueste zuerst (Regel 0a: Datums-Listen absteigend).
    assert "12/2026" in warnungen[0].meldung
