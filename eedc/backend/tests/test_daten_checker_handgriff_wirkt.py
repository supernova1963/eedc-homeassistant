"""W-11 Kein Knopf ohne Wirkung (Etappe E3, Bauplan §4; Konzept §3.1 R3/R7; Gegenprüfung Sprengsatz S2).

**Regel.** Ein Aktion-Knopf steht nur dort, wo ein Test beweist, dass der Befund nach dem Lauf verschwindet oder sich
ändert — über die eine Mechanik (``plan`` → ``execute``) mit den Parametern, die der Befund trägt. An Kanal-Tagen liefert
der Erzeuger kein ``REAGGREGATE_*`` (die Neu-Aggregation schreibt dort keine Mengen): mit HA-Spiegel «Aus Home Assistant
neu übernehmen», ohne Spiegel kein Knopf (Kanal-Lage-Weiche R7).

**Abdeckung je Operation × Lage** (``WIRKUNG``): jede Operation, die ein Erzeuger unter ``services/daten_checker/``
als Aktion setzt (AST), hat mindestens einen Wirkungs-Beleg; jeder Beleg ist ein Test, der existiert. Eine Operation ohne
Beleg ist rot. Die Lagen: Bestandstag (der Tag liest Tages-/Stundenzeilen) · Kanal-Tag mit Spiegel · Kanal-Tag ohne
Spiegel · «Monat» (Operationen auf Monatszeilen, ohne Tageslage).

Schwesterdateien: ``test_repair_operationen_checker.py``, ``test_n790_drift_handgriff.py``,
``test_n791_reparatur_zaehler_ohne_leistungskurve.py``, ``test_daten_checker_texte.py`` (W-4).
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from backend.services.daten_checker.kategorien import AKTION_SPIEGEL_ABGLEICH_TAG
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    execute,
    plan,
)

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"

#: Operation → [(Lage, Beleg «datei::test»)]. Ein Beleg führt den Knopf über plan → execute aus und prüft den Befund danach.
WIRKUNG: dict[str, list[tuple[str, str]]] = {
    "reaggregate_day": [
        ("Bestandstag", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_a_lk_reparatur_schreibt_zaehlerwerte_und_laesst_den_leistungsverlauf"),
        ("Kanal-Tag mit Spiegel (S2: Abgleich statt Tag)", "test_n790_drift_handgriff.py::test_a_komponenten_achse_mit_spiegel_traegt_den_handgriff"),
    ],
    "reaggregate_range": [
        ("Bestandstag", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_w11_bereich_ueber_plan_und_ausfuehren_behebt_die_drift"),
        ("Kanal-Tag mit Spiegel", "test_daten_checker_handgriff_wirkt.py::test_s2_kanal_tag_mit_spiegel_bekommt_den_abgleich"),
        ("Kanal-Tag ohne Spiegel", "test_daten_checker_handgriff_wirkt.py::test_s2_kanal_tag_ohne_spiegel_ohne_knopf"),
        ("Bestand + Kanal gemischt", "test_daten_checker_handgriff_wirkt.py::test_s2_bereich_nur_ueber_bestandstage"),
    ],
    AKTION_SPIEGEL_ABGLEICH_TAG: [
        ("Kanal-Tag mit Spiegel", "test_n790_drift_handgriff.py::test_c_kette_ueber_plan_und_ausfuehren"),
        ("Bestandstag mit Spiegel", "test_n791_reparatur_zaehler_ohne_leistungskurve.py::test_w11_aus_home_assistant_neu_uebernehmen_ueber_plan_und_ausfuehren"),
    ],
    "kraftstoffpreis_backfill": [
        ("Monat", "test_daten_checker_vergleichspreis_fehlt.py::test_w11_benzinpreise_nachtragen_ueber_plan_und_ausfuehren"),
    ],
    "wetter_backfill": [
        ("Monat", "test_wetter_nachzug_und_checker.py::test_w11_wetterreihe_nachziehen_ueber_plan_und_ausfuehren"),
    ],
    "temperatur_aus_messung": [
        ("Monat", "test_daten_checker_handgriff_wirkt.py::test_temperatur_aus_messung_wirkt"),
    ],
    "feldwert_entfernen": [
        ("Monat", "test_daten_checker_handgriff_wirkt.py::test_wert_entfernen_wirkt"),
    ],
}


def _aktionen_der_erzeuger() -> set[str]:
    """Jede Operation, die ein Erzeuger als ``Aktion("<op>", …)`` setzt, und die Spiegel-Aktion (``aktion_spiegel_…``)."""
    ops: set[str] = set()
    for p in (BACKEND / "services" / "daten_checker").rglob("*.py"):
        baum = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name == "Aktion" and n.args and isinstance(n.args[0], ast.Constant):
                ops.add(n.args[0].value)
            if name == "aktion_spiegel_abgleich_tag":
                ops.add(AKTION_SPIEGEL_ABGLEICH_TAG)
    return ops


def _testfunktionen(datei: str) -> set[str]:
    baum = ast.parse((TESTS / datei).read_text(encoding="utf-8"))
    return {n.name for n in baum.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_jede_aktion_hat_einen_wirkungs_beleg():
    ops = _aktionen_der_erzeuger()
    assert ops, "keine Aktion gefunden — AST-Suche kaputt?"
    fehlt = sorted(ops - set(WIRKUNG))
    assert not fehlt, f"Aktion ohne Wirkungs-Beleg (W-11, Halt H-10): {fehlt}"
    assert not set(WIRKUNG) - ops, f"verwaiste Einträge: {sorted(set(WIRKUNG) - ops)}"
    for op, belege in WIRKUNG.items():
        assert belege, op
        for _lage, beleg in belege:
            datei, funktion = beleg.split("::")
            assert funktion in _testfunktionen(datei), f"{op}: Beleg {beleg} fehlt"


def test_jede_aktion_ist_eine_operation_des_orchestrators():
    werte = {o.value for o in RepairOperationType}
    assert _aktionen_der_erzeuger() <= werte


def test_der_waechter_hat_zaehne(monkeypatch):
    """Sprengsatz: eine Operation ohne Beleg ⇒ rot."""
    monkeypatch.delitem(WIRKUNG, "wetter_backfill")
    with pytest.raises(AssertionError, match="ohne Wirkungs-Beleg"):
        test_jede_aktion_hat_einen_wirkungs_beleg()


# ── S2: Kanal-Lage-Weiche (Nr 63 «Einspeisung über Erzeugung»; Muster für alle Bereichs-Zeilen) ────────────────────

TAGE = [date(2026, 6, d) for d in (8, 9, 10)]


async def _weiche(monkeypatch, *, kanal: set, spiegel: int):
    from backend.services.daten_checker import DatenChecker

    async def _kanal(self, _anlage, tage):
        return {d: object() for d in tage if d in kanal}

    async def _spiegel(_db, _aid):
        return spiegel

    monkeypatch.setattr(DatenChecker, "_bilanz_kanal_tage", _kanal)
    monkeypatch.setattr("backend.services.kanal.konsistenz.spiegel_quellen_anzahl", _spiegel)

    class _A:
        id = 7

    return await DatenChecker(None)._weiche_bereich(_A(), TAGE)


async def test_s2_bestandstage_bekommen_tage_neu_aufbauen(monkeypatch):
    a = await _weiche(monkeypatch, kanal=set(), spiegel=3)
    assert (a.operation, a.params) == ("reaggregate_range", {"von": "2026-06-08", "bis": "2026-06-10"})


async def test_s2_bereich_nur_ueber_bestandstage(monkeypatch):
    a = await _weiche(monkeypatch, kanal={date(2026, 6, 10)}, spiegel=3)
    assert (a.operation, a.params) == ("reaggregate_range", {"von": "2026-06-08", "bis": "2026-06-09"})


async def test_s2_kanal_tag_mit_spiegel_bekommt_den_abgleich(monkeypatch):
    a = await _weiche(monkeypatch, kanal=set(TAGE), spiegel=3)
    assert (a.operation, a.params) == (AKTION_SPIEGEL_ABGLEICH_TAG, {"datum": "2026-06-10"})
    assert not a.operation.startswith("reaggregate")


async def test_s2_kanal_tag_ohne_spiegel_ohne_knopf(monkeypatch):
    assert await _weiche(monkeypatch, kanal=set(TAGE), spiegel=0) is None


# ── Monats-Operationen: der Befund verschwindet nach dem Lauf ─────────────────────────────────────────────────────

@pytest.fixture
def _leer():
    _reset_state_for_tests()


async def _ausfuehren(db, anlage_id: int, e) -> None:
    p = await plan(RepairOperationRequest(anlage_id=anlage_id, operation=RepairOperationType(e.action_kind),
                                          params=e.action_params), db)
    assert "nichts_zu_tun" not in p.operation_preview, p.operation_preview
    await execute(p.plan_id, db)


async def test_temperatur_aus_messung_wirkt(db, _leer):
    from backend.tests.test_n426_temperatur_historie import _anlage, _befunde

    a = await _anlage(db, monate={1: None, 2: None}, messreihe={1: 2.0, 2: 3.5})
    (e,) = await _befunde(db, a.id)
    assert e.action_kind == "temperatur_aus_messung"
    await _ausfuehren(db, a.id, e)
    assert [(x.schwere, x.code) for x in await _befunde(db, a.id)] == [("ok", "temperatur_ok")]


async def test_wert_entfernen_wirkt(db, _leer):
    from backend.tests.test_n393_wert_in_nicht_gefuehrtem_feld import _anlage_mit, _befunde

    a, klima = await _anlage_mit(db, typ="waermepumpe", parameter={"wp_art": "luft_luft"},
                                 monate={5: {"warmwasser_kwh": 10.0}, 6: {"warmwasser_kwh": 889.0}})
    (e,) = _befunde(db, klima)
    assert e.action_kind == "feldwert_entfernen"
    await _ausfuehren(db, a.id, e)
    _, nachher = await _anlage_mit_neu_geladen(db, klima.id)
    assert _befunde(db, nachher) == []


async def _anlage_mit_neu_geladen(db, inv_id: int):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from backend.models import Investition

    db.expire_all()
    inv = (await db.execute(select(Investition).options(selectinload(Investition.monatsdaten))
                            .where(Investition.id == inv_id))).scalar_one()
    return None, inv
