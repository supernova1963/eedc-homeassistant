"""Import-Wizard „Zuordnung": Anteile nach Nennleistung, nicht 100/N (N59).

Befund-Sweep §3.3/§4.2/§7: `api/routes/data_import.py` las
`parameter["leistung_kwp"]` — einen Schlüssel, den **keines der drei Regime**
kennt (die kWp ist eine Spalte, der Legacy-JSON-Key des PV-Helpers heißt `kwp`).
Der falsche Schlüssel lieferte still `0`, und `0` sieht aus wie „keine Daten":
der Wizard zeigte **kein kWp** und schlug **immer Gleichverteilung** vor. Bei
12/3 kWp also 50/50 statt 80/20 — wer den Vorschlag übernahm, schrieb falsche
Monatswerte in die InvestitionMonatsdaten. Das ist zugleich der #229-Bug
(Spalte gegen JSON) und der N38-Mechanismus (Literal-Key ohne SoT).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.data_import import get_zuordnung_info
from backend.models import Anlage, Investition


async def _anlage(db, module: list[tuple], speicher: list[tuple] | None = None) -> int:
    """module/speicher = [(bezeichnung, spalten_wert, parameter_dict)]."""
    anlage = Anlage(anlagenname="Zuordnung", leistung_kwp=15.0)
    db.add(anlage)
    await db.flush()
    for bez, spalte, params in module:
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=bez,
            anschaffungsdatum=date(2024, 1, 1),
            leistung_kwp=spalte, parameter=params,
        ))
    for bez, _spalte, params in (speicher or []):
        db.add(Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung=bez,
            anschaffungsdatum=date(2024, 1, 1), parameter=params,
        ))
    await db.commit()
    return anlage.id


async def test_anteile_nach_kwp_aus_der_spalte(db):
    """12/3 kWp in der Spalte → 80/20, nicht 50/50; die kWp-Spalte ist gefüllt."""
    anlage_id = await _anlage(db, [
        ("Süddach", 12.0, {}),
        ("Garage", 3.0, {}),
    ])

    info = await get_zuordnung_info(anlage_id=anlage_id, db=db)

    anteile = {m.bezeichnung: m.default_anteil for m in info.pv_module}
    assert anteile == {"Süddach": 80.0, "Garage": 20.0}
    assert {m.bezeichnung: m.kwp for m in info.pv_module} == {"Süddach": 12.0, "Garage": 3.0}
    assert all(not m.anteil_geschaetzt for m in info.pv_module)


@pytest.mark.parametrize("key", ["kwp", "leistung_kwp"])
async def test_anteile_nach_kwp_aus_dem_parameter_json(db, key):
    """Beide Legacy-JSON-Konventionen werden gefunden — `kwp` (Helper
    `get_pv_kwp`) und `leistung_kwp` (Helper `get_inv_value`). Vorher lieferte
    die Stelle für BEIDE Pflege-Formen Gleichverteilung, weil sie roh auf
    `parameter["leistung_kwp"]` las und die Spalte gar nicht ansah."""
    anlage_id = await _anlage(db, [
        ("Süddach", None, {key: 12.0}),
        ("Garage", None, {key: 3.0}),
    ])

    info = await get_zuordnung_info(anlage_id=anlage_id, db=db)

    anteile = {m.bezeichnung: m.default_anteil for m in info.pv_module}
    assert anteile == {"Süddach": 80.0, "Garage": 20.0}
    assert all(not m.anteil_geschaetzt for m in info.pv_module)


async def test_ohne_kwp_gleichverteilung_aber_gekennzeichnet(db):
    """Ist die Nennleistung WIRKLICH nirgends gepflegt, bleibt 100/N — aber die
    Antwort sagt es (`anteil_geschaetzt`), statt eine gleichmäßige Aufteilung
    als errechneten Vorschlag auszugeben (P4)."""
    anlage_id = await _anlage(db, [
        ("Dach A", None, {}),
        ("Dach B", None, {}),
    ])

    info = await get_zuordnung_info(anlage_id=anlage_id, db=db)

    assert {m.default_anteil for m in info.pv_module} == {50.0}
    assert all(m.anteil_geschaetzt for m in info.pv_module)
    assert all(m.kwp is None for m in info.pv_module)


async def test_speicher_anteile_nach_kapazitaet(db):
    """Dieselbe Regel für Speicher — Bezugsgröße ist `kapazitaet_kwh`."""
    anlage_id = await _anlage(db, [("Dach", 10.0, {})], speicher=[
        ("Speicher groß", None, {"kapazitaet_kwh": 15.0}),
        ("Speicher klein", None, {"kapazitaet_kwh": 5.0}),
    ])

    info = await get_zuordnung_info(anlage_id=anlage_id, db=db)

    anteile = {s.bezeichnung: s.default_anteil for s in info.speicher}
    assert anteile == {"Speicher groß": 75.0, "Speicher klein": 25.0}
    assert all(not s.anteil_geschaetzt for s in info.speicher)
