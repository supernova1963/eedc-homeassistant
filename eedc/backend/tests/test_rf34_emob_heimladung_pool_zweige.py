"""RF-34 — die drei Zweige von `aktueller_monat/aggregation.py::emob_heimladung_pool`, die weder der Golden Master
`aktueller-monat` (drei DB-Kopien, jeder Monat) noch ein Test vor dem Umbau ausführte (Zeilenspur 23.10.2026, HEAD dba12861):

* die Wache «Fremdquelle»: `emob_ladung_kwh` steht als direkter Wert in `resolved`, die Monats-Fakten haben ihn nicht
  entschieden ⇒ unangetastet (Orchestrator);
* die gespeicherte **Schätzung**: ihr direkter Wert gilt nur, wenn die eine Funktion bei ihr bleibt — beide Felder werden
  ersetzt, der PV-Anteil nur mit abgeleiteter Quote (`_pool_in_resolved`);
* die **dienstliche Wallbox** in Betrieb: ihre Zeile geht an die eine Funktion, die Schätzung des Dienstwagens entfällt
  (`_geraete_des_monats`).

Charakterisierung des Verhaltens vor dem Schnitt (am HEAD und nach RF-34 gleich grün); Schwesterdateien:
`test_n555_fahrverbrauch_bleibt_fahrverbrauch.py`, `test_n555_stufe3_ladebloecke.py`, `test_wallbox_quelle_laufender_monat.py`.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.api.routes.aktueller_monat.aggregation import emob_heimladung_pool
from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.models import Investition
from backend.services.eauto_wirtschaftlichkeit import QUELLE_SCHAETZUNG

_LIVE = DatenquelleInfo(quelle="ha_statistics", konfidenz=92)
_GESPEICHERT = DatenquelleInfo(quelle="gespeichert", konfidenz=85)


def _inv(inv_id: int, typ: str, *, dienstlich: bool = False) -> Investition:
    return Investition(
        id=inv_id, anlage_id=1, typ=typ, bezeichnung=f"{typ} {inv_id}", anschaffungsdatum=date(2024, 1, 1),
        aktiv=True, parameter={"ist_dienstlich": True} if dienstlich else {},
    )


def _schaetzung(*, abgeleitet: bool) -> SimpleNamespace:
    emob = SimpleNamespace(
        quelle=QUELLE_SCHAETZUNG, ladedaten_je_inv={7: {"verbrauch_kwh": 200.0}}, dienstlich_ladedaten_je_inv={},
        heim_gesamt_ids=frozenset(), ladung_kwh=200.0, ladung_pv_kwh=50.0, ladung_anteil_abgeleitet=abgeleitet,
    )
    return SimpleNamespace(emob=emob)


def test_rf34_fremdquelle_bleibt_unangetastet():
    resolved = {"emob_ladung_kwh": (12.0, _LIVE), "inv_7_verbrauch_kwh": (99.0, _LIVE)}
    vorher = dict(resolved)
    out = emob_heimladung_pool(
        direct_fields={"emob_ladung_kwh"}, investitionen=[_inv(7, "e-auto")], jahr=2026, monat=8,
        resolved=resolved, ist_aktueller_monat=False,
    )
    assert out == {}
    assert resolved == vorher


def test_rf34_gespeicherte_schaetzung_mit_abgeleiteter_quote():
    resolved = {"emob_ladung_kwh": (999.0, _LIVE), "emob_pv_ladung_kwh": (888.0, _LIVE)}
    out = emob_heimladung_pool(
        direct_fields={"emob_ladung_kwh", "emob_pv_ladung_kwh"}, investitionen=[_inv(7, "e-auto")], jahr=2026,
        monat=8, resolved=resolved, monats_fakt=_schaetzung(abgeleitet=True), ist_aktueller_monat=False,
    )
    assert out["emob_entscheid"].quelle == QUELLE_SCHAETZUNG
    assert resolved == {"emob_pv_ladung_kwh": (50.0, _GESPEICHERT), "emob_ladung_kwh": (200.0, _GESPEICHERT)}
    assert list(resolved) == ["emob_pv_ladung_kwh", "emob_ladung_kwh"]


def test_rf34_gespeicherte_schaetzung_ohne_quote_verliert_den_pv_anteil():
    resolved = {"emob_ladung_kwh": (999.0, _LIVE), "emob_pv_ladung_kwh": (888.0, _LIVE)}
    emob_heimladung_pool(
        direct_fields={"emob_ladung_kwh", "emob_pv_ladung_kwh"}, investitionen=[_inv(7, "e-auto")], jahr=2026,
        monat=8, resolved=resolved, monats_fakt=_schaetzung(abgeleitet=False), ist_aktueller_monat=False,
    )
    assert resolved == {"emob_ladung_kwh": (200.0, _GESPEICHERT)}


def test_rf34_dienstliche_wallbox_macht_die_schaetzung_des_dienstwagens_wirkungslos():
    def entscheid(mit_wallbox: bool):
        invs = [_inv(7, "e-auto", dienstlich=True)] + ([_inv(5, "wallbox", dienstlich=True)] if mit_wallbox else [])
        resolved = {"inv_7_verbrauch_kwh": (300.0, _LIVE), "inv_7_km_gefahren": (1000.0, _LIVE)}
        return emob_heimladung_pool(
            direct_fields=set(), investitionen=invs, jahr=2026, monat=9, resolved=resolved, ist_aktueller_monat=True,
        )["emob_entscheid"]

    mit, ohne = entscheid(True), entscheid(False)
    assert mit.dienstliche_wallbox_in_betrieb is True
    assert set(mit.dienstlich_je_inv) == {5}
    assert mit.dienstwagen_ungemessen == frozenset()
    assert ohne.dienstliche_wallbox_in_betrieb is False
    assert ohne.dienstlich_je_inv[7].netz_kwh == 300.0
    assert ohne.dienstwagen_ungemessen == frozenset({7})
