"""RF-39 — benannte Probe für die Zweige von ``services/kanal/bilanz_adapter.py::_tag_wie_ha`` (Fassung (b) «wie HA»),
die kein Bestandstest erreicht.

Gemessen im Komplexitäts-Paket, Sitzung C (23.10.2026, Bedingungs-Abdeckung per Import-Hook über die 44 Kanal-Testdateien,
879 Tests): 70 von 86 Bedingungs-Seiten. Offen waren u. a. «kein Eintrag mit Δ», zwei Anlagenzähler-Einträge, die
Stundenwahl ohne Stunden-Slots (Quelle liefert keine Reihe ⇒ ``QUELLE_KEINE``), Einzelzähler-Stunden ohne Aggregat-Slot,
das Aggregat ohne Stundenreihe in der Auflösung, ein Einzelzähler ohne Reihe in der Auflösung, ein Tag ohne PV und ein Tag
nur mit Erzeugern hinter dem Zähler. Diese Probe treibt ``_tag_wie_ha`` direkt (reine Funktion: Einträge, Δ je Kanal,
eine Quelle mit ``get_hourly_slots_for_day``) und hält die heutige Antwort fest — Sinn ist der Umzug RF-39, keine neue Regel.

Nicht erreichbar (benannt, ohne Probe): ``praefix is None`` wahr in der Aggregat-Auflösung — ``loese_aggregat_tag_auf``
liefert nur Werte für PV-Module und Balkonkraftwerke, beide stehen in ``_TYP_KEY_PREFIX``.
Keine Uhr, keine DB, kein Netz.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.models.investition import Investition
from backend.services.kanal import bilanz_adapter as BA
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.snapshot.keys import PV_AGGREGAT_BASIS_FELD
from backend.services.snapshot.tages_tabelle import TabellenEintrag

TAG = date(2026, 6, 4)
AGG = f"basis:{PV_AGGREGAT_BASIS_FELD}"


def _inv(i: int, kwp: float = 5.0, typ: str = "pv-module") -> Investition:
    return Investition(id=i, anlage_id=1, typ=typ, bezeichnung=f"I{i}", leistung_kwp=kwp, aktiv=True,
                       anschaffungsdatum=date(2024, 1, 1))


def _e(schluessel: str, kategorie: str, sensor_key: str, target: str, vz: int = 1) -> TabellenEintrag:
    return TabellenEintrag(schluessel=schluessel, kategorie=kategorie, gruppe=None, sensor_key=sensor_key,
                           target_key=target, vorzeichen=vz)


def _agg(schluessel: str = "k_agg", target: str = PV_AGGREGAT_BASIS_FELD) -> TabellenEintrag:
    return _e(schluessel, "pv", AGG, target)


def _einzel(inv_id: int) -> TabellenEintrag:
    return _e(f"k_inv{inv_id}", "pv", f"inv:{inv_id}:pv_erzeugung_kwh", f"pv_{inv_id}")


class _Quelle:
    """Stunden-Slots je Kanal-Schlüssel: ``{key: {h: (delta, n)}}``; ein fehlender Schlüssel hat keine Reihe."""

    def __init__(self, reihen: dict[str, dict[int, tuple[float, int]]] | None = None):
        self.reihen = reihen or {}

    def get_hourly_slots_for_day(self, keys, datum):
        assert datum == TAG
        return {k: SimpleNamespace(slots={h: SimpleNamespace(delta=d, n=n) for h, (d, n) in r.items()})
                for k, r in self.reihen.items() if k in keys}


def _tag(invs, eintraege, deltas, quelle=None):
    return BA._tag_wie_ha(None, {str(i.id): i for i in invs}, TAG, eintraege, deltas, quelle or _Quelle())


def test_ohne_einen_eintrag_mit_delta_kein_tag():
    assert _tag([_inv(1)], [_einzel(1), _e("k_ein", "einspeisung", "basis:einspeisung", "einspeisung")],
                {"k_inv1": None}) is None


def test_tag_ohne_pv_nur_netz():
    t = _tag([_inv(1)], [_e("k_ein", "einspeisung", "basis:einspeisung", "einspeisung"),
                         _e("k_bez", "netzbezug", "basis:netzbezug", "netzbezug")], {"k_ein": 2.5, "k_bez": 4.25})
    assert t.komponenten_kwh == {"einspeisung": 2.5, "netzbezug": 4.25} and t.pv_marken == {} and t.verworfen == {}
    assert t.bilanz.erzeugung_kwh == 0.0 and t.bilanz.einspeisung_kwh == 2.5 and t.bilanz.netzbezug_kwh == 4.25


def test_tag_nur_mit_erzeuger_hinter_dem_zaehler():
    t = _tag([], [_e("k_sonst", "erzeugung_sonstiges", "inv:9:erzeugung_kwh", "sonstige_9")], {"k_sonst": 3.0})
    assert t.komponenten_kwh == {"sonstige_9": 3.0} and t.bilanz.erzeugung_kwh == 3.0


def test_zwei_anlagenzaehler_eintraege_ohne_reihe_werden_summiert_und_nach_kwp_verteilt():
    t = _tag([_inv(1, 6.0), _inv(2, 4.0)], [_agg("k_agg_a"), _agg("k_agg_b")], {"k_agg_a": 6.0, "k_agg_b": 4.0})
    assert t.komponenten_kwh == {"pv_1": 6.0, "pv_2": 4.0}, "Σ 10 kWh nach kWp 6 : 4"
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}
    assert t.bilanz.erzeugung_kwh == pytest.approx(10.0)


def test_aggregat_und_einzel_ohne_stunden_slots_ergeben_keine_pv_quelle():
    """Beide liefern ein Tages-Δ, aber die Quelle hat für keinen der Kanäle eine Stundenreihe ⇒ die Stundenwahl sieht
    nichts (``QUELLE_KEINE``) und der Tag trägt keine PV — die heutige Antwort, festgehalten."""
    t = _tag([_inv(1), _inv(2)], [_agg(), _einzel(1)], {"k_agg": 9.0, "k_inv1": 4.0})
    assert t.komponenten_kwh == {} and t.pv_marken == {} and t.bilanz.erzeugung_kwh == 0.0


def test_einzel_deckt_alle_stunden_ohne_aggregat_reihe():
    q = _Quelle({"k_inv1": {10: (1.0, 1), 11: (2.0, 1)}})
    t = _tag([_inv(1)], [_agg(), _einzel(1)], {"k_agg": 9.0, "k_inv1": 3.0}, q)
    assert t.komponenten_kwh == {"pv_1": 3.0} and t.pv_marken == {}


def test_einzelstunde_ohne_aggregat_slot_und_luecke_waehlt_das_aggregat():
    q = _Quelle({AGG: {10: (3.0, 1), 11: (3.0, 1)}, "k_inv1": {10: (1.0, 1), 11: (1.0, 1), 12: (0.5, 1)}})
    t = _tag([_inv(1, 5.0), _inv(2, 5.0)], [_agg(AGG), _einzel(1)], {AGG: 6.0, "k_inv1": 2.5}, q)
    assert set(t.komponenten_kwh) == {"pv_1", "pv_2"}
    assert sum(t.komponenten_kwh.values()) == pytest.approx(6.0), "Σ Keys == Anlagenzähler (Regel 4)"
    assert t.komponenten_kwh["pv_1"] == pytest.approx(2.5) and t.pv_marken == {"pv_2": ABGELEITET_KWP_ANTEIL}


def test_einzel_ohne_reihe_in_der_aggregat_aufloesung():
    q = _Quelle({AGG: {9: (2.0, 1), 10: (4.0, 2)}})
    t = _tag([_inv(1, 5.0), _inv(2, 5.0)], [_agg(AGG), _einzel(1)], {AGG: 6.0, "k_inv1": 2.0}, q)
    assert set(t.komponenten_kwh) == {"pv_1", "pv_2"}
    assert sum(t.komponenten_kwh.values()) == pytest.approx(6.0)
    assert t.komponenten_kwh == {"pv_1": 3.0, "pv_2": 3.0}, "ohne eigene Stunden ist inv 1 nicht gemessen ⇒ kWp-Anteil"
    assert t.pv_marken == {"pv_1": ABGELEITET_KWP_ANTEIL, "pv_2": ABGELEITET_KWP_ANTEIL}


def test_aggregat_mit_fremdem_ziel_key_bleibt_unaufgeloest():
    """Künstlich (im Bestand trägt der Anlagenzähler-Eintrag den Ziel-Key ``PV_AGGREGAT_BASIS_FELD``): ein anderer
    Ziel-Key nimmt den Auflösungs-Zweig nicht und bleibt als Komponente stehen."""
    t = _tag([_inv(1)], [_agg(target="pv_anders")], {"k_agg": 5.0})
    assert t.komponenten_kwh == {"pv_anders": 5.0} and t.pv_marken == {}
