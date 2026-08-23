"""
Akzeptanztests für `get_inv_value` und seine Anwendung in den
Verteilungs-Helpern (#229 JanKgh).

Geprüft:
  1. Helper liest Spalte vor parameter-JSON (#229 Hauptbefund)
  2. Helper fällt auf parameter zurück, wenn Spalte None
  3. _distribute_by_param verteilt 12/5/3 kWp korrekt anteilig, wenn kWp
     in der Tabellen-Spalte gepflegt ist (typischer SolarEdge-Multi-
     String-Fall) — vor dem Fix: 1/3 je Modul.
"""

from __future__ import annotations

from backend.models import Investition
from backend.utils.investition_value import get_inv_value


def test_get_inv_value_spalte_vor_parameter():
    """Wenn beide gepflegt sind: Spalte gewinnt."""
    inv = Investition(typ="pv-module", leistung_kwp=10.0, parameter={"leistung_kwp": 99.0})
    assert get_inv_value(inv, "leistung_kwp") == 10.0


def test_get_inv_value_fallback_parameter():
    """Wenn Spalte None, parameter wird gelesen."""
    inv = Investition(typ="pv-module", leistung_kwp=None, parameter={"leistung_kwp": 7.5})
    assert get_inv_value(inv, "leistung_kwp") == 7.5


def test_get_inv_value_parameter_only_key():
    """Keys ohne Spalten-Mapping (z.B. kapazitaet_kwh) lesen aus parameter."""
    inv = Investition(typ="speicher", parameter={"kapazitaet_kwh": 5.0})
    assert get_inv_value(inv, "kapazitaet_kwh") == 5.0


def test_get_inv_value_default_wenn_nichts_da():
    inv = Investition(typ="pv-module", leistung_kwp=None, parameter={})
    assert get_inv_value(inv, "leistung_kwp") == 0.0
    assert get_inv_value(inv, "leistung_kwp", default=99.0) == 99.0


def test_distribute_by_param_solaredge_multi_string():
    """#229 JanKgh-Hauptbefund: bei 3 PV-Modulen mit kWp 12/5/3 (Spalte
    gepflegt, parameter leer) muss `_distribute_by_param` 20 kWh
    proportional auf 12/5/3 verteilen — nicht 1/3 je Modul.
    """
    from backend.api.routes.connector import _distribute_by_param

    investitionen = [
        Investition(id=1, typ="pv-module", leistung_kwp=12.0, parameter={}),
        Investition(id=2, typ="pv-module", leistung_kwp=5.0, parameter={}),
        Investition(id=3, typ="pv-module", leistung_kwp=3.0, parameter={}),
    ]
    result = _distribute_by_param(investitionen, total=20.0, param_key="leistung_kwp")
    anteil_by_id = {inv.id: anteil for inv, anteil in result}

    # 20 × 12/20 = 12, 20 × 5/20 = 5, 20 × 3/20 = 3
    assert anteil_by_id[1] == 12.0, f"Modul 1 (12 kWp) sollte 12.0 bekommen, war {anteil_by_id[1]}"
    assert anteil_by_id[2] == 5.0, f"Modul 2 (5 kWp) sollte 5.0 bekommen, war {anteil_by_id[2]}"
    assert anteil_by_id[3] == 3.0, f"Modul 3 (3 kWp) sollte 3.0 bekommen, war {anteil_by_id[3]}"


def test_distribute_by_param_parameter_fallback():
    """Wenn kWp nur im parameter steht (alter Datenstand), funktioniert die
    Verteilung weiterhin korrekt — Fallback auf parameter-Lesung."""
    from backend.api.routes.connector import _distribute_by_param

    investitionen = [
        Investition(id=1, typ="pv-module", leistung_kwp=None, parameter={"leistung_kwp": 8.0}),
        Investition(id=2, typ="pv-module", leistung_kwp=None, parameter={"leistung_kwp": 2.0}),
    ]
    result = _distribute_by_param(investitionen, total=10.0, param_key="leistung_kwp")
    anteil_by_id = {inv.id: anteil for inv, anteil in result}

    assert anteil_by_id[1] == 8.0
    assert anteil_by_id[2] == 2.0
