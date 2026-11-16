"""Befund «Leistung (kW) fehlt» am Wechselrichter fragt den Kennwert der Rechnung (Päckchen «Kleineres» 16.11.2026, N4).

`get_wr_grenze_kw` (die AC-Grenze, mit der die Prognose kappt) fällt auf die Spalte `leistung_kwp` zurück — Setup-Wizard
und Import schreiben sie. Der Befund `geraet_leistung_kw_fehlt` las nur die Parameter und meldete «fehlt», während eedc mit
einem Wert rechnete. Jetzt eine Formel, ein Ort (`core/investition_kennwerte.py`).

Schwesterdateien: test_daten_checker_bkw_wr_grenze_347.py, test_wechselrichter_kein_pv_erzeuger.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.models.investition import Investition
from backend.services.daten_checker import DatenChecker


@pytest.mark.parametrize("parameter, spalte, befund", [
    ({}, 7.0, False),                       # nur die Spalte (Wizard/Import) ⇒ eedc rechnet damit ⇒ kein Befund
    ({"max_leistung_kw": 8.0}, None, False),
    ({"leistung_ac_kw": 8.0}, None, False),  # Alt-Name
    ({}, None, True),                        # beides leer ⇒ Befund
    ({"max_leistung_kw": 0}, 0.0, True),     # 0 ist keine Grenze (`get_wr_grenze_kw` ⇒ None)
])
def test_wr_leistung_fehlt_folgt_dem_kennwert(parameter, spalte, befund):
    inv = Investition(id=1, typ="wechselrichter", bezeichnung="WR", parameter=parameter, leistung_kwp=spalte)
    erg = DatenChecker(None)._check_typ_wechselrichter("stammdaten", inv, "WR", parameter,
                                                       SimpleNamespace(sensor_mapping={}))
    assert ("geraet_leistung_kw_fehlt" in [e.code for e in erg]) is befund
