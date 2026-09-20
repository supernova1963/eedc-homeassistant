"""N-536 — Ein Balkonkraftwerk mit Modul-Kindern zählt nie neben ihnen.

**Der Anlass.** Kai2 (Forum T89667 #354) folgte unserer Empfehlung aus #346 und
legte die beiden Module seiner Balkonkraftwerke als eigene Investitionen mit
`parent_investition_id` an — samt eigener Sensoren. Der Energiefluss zeigte
danach „Solarleistung 167 W", obwohl BKW-Summe (32+52) und Modulsumme
(17+15+28+24) dieselben 84 W sind: derselbe Strom, zweimal gezählt.

**Die Regel.** Ein abtretendes BKW (N-266) ist Träger wie ein Wechselrichter.
Ohne Lücke bei den Kindern trägt es nichts mehr; mit Lücke genau das, was sie
nicht messen. Der Rest wird auf Live- und Stundenebene **nicht verteilt** — die
kWp-Gewichtung ist eine Tages-Aussage (`snapshot/komponenten_beitraege`).

⚠ **Die Gegenprobe ist der wichtigere Teil dieser Datei.** Der Selektor blind
anzuwenden wäre falsch gewesen: bei den meisten Anlagen ist der Wechselrichter
des Balkonkraftwerks die EINZIGE Live-Quelle, und seine Kinder haben gar keinen
eigenen Sensor. Dort darf sich nichts ändern — das halten
`test_nur_bkw_gemappt_*` und `test_ohne_abtretendes_bkw_*` fest.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.erzeuger_traeger import (
    bkw_kinder_decken_vollstaendig,
    bkw_restwerte,
    kuerze_bkw_in_werte_map,
)
from backend.models import Anlage, Investition
from backend.services.live_komponenten_builder import build_komponenten


def _anlage_mit_bkw(kinder: int = 2):
    """BKW 1,10 kWp mit `kinder` Modul-Kindern à 0,55 kWp (Kai2s Konstellation)."""
    bkw = Investition(id=2, typ="balkonkraftwerk", bezeichnung="BKW 2",
                      leistung_kwp=1.10, anschaffungsdatum=date(2024, 9, 2))
    module = [
        Investition(id=20 + i + 1, typ="pv-module", bezeichnung=f"Modul {i + 1}",
                    leistung_kwp=0.55, parent_investition_id=2,
                    anschaffungsdatum=date(2024, 9, 2))
        for i in range(kinder)
    ]
    return bkw, module


# ─── 1. Die Formel ──────────────────────────────────────────────────────────

def test_rest_ist_null_wenn_alle_kinder_messen():
    bkw, module = _anlage_mit_bkw()
    reste = bkw_restwerte([bkw, *module], {"2": 52.0, "21": 28.0, "22": 24.0})
    assert reste == {"2": 0.0}


def test_rest_traegt_das_ungemessene_kind():
    """Teil-Deckung: das BKW trägt genau die Lücke, nicht mehr und nicht weniger."""
    bkw, module = _anlage_mit_bkw()
    reste = bkw_restwerte([bkw, *module], {"2": 52.0, "21": 28.0})
    assert reste == {"2": 24.0}


def test_rest_wird_bei_ueberschuss_auf_null_geklemmt():
    """Verschiedene Abtastzeitpunkte: Σ Kinder > BKW. Negativ wird der Rest nie —
    dieselbe Klemmung wie `pv_verteilung.resolve_pv_je_modul`."""
    bkw, module = _anlage_mit_bkw()
    reste = bkw_restwerte([bkw, *module], {"2": 50.0, "21": 28.0, "22": 24.0})
    assert reste == {"2": 0.0}


def test_bkw_ohne_eigenen_wert_steht_nicht_im_ergebnis():
    """`0.0` wäre eine Aussage über eine Messung, die es nicht gibt."""
    bkw, module = _anlage_mit_bkw()
    assert bkw_restwerte([bkw, *module], {"21": 28.0, "22": 24.0}) == {}


def test_bkw_ohne_kinder_tritt_nichts_ab():
    bkw, _ = _anlage_mit_bkw(kinder=0)
    assert bkw_restwerte([bkw], {"2": 52.0}) == {}


def test_werte_map_kuerzt_beide_keyspaces():
    """Der Live-Keyspace führt ALLE Erzeuger unter `pv_<id>`, der Boundary-Keyspace
    unterscheidet `pv_<id>`/`bkw_<id>` — der Mismatch war der BKW-Bug 2026-05-19."""
    bkw, module = _anlage_mit_bkw()
    invs = [bkw, *module]
    live = kuerze_bkw_in_werte_map({"pv_2": 52.0, "pv_21": 28.0, "pv_22": 24.0}, invs)
    assert live == {"pv_21": 28.0, "pv_22": 24.0}
    boundary = kuerze_bkw_in_werte_map({"bkw_2": 52.0, "pv_21": 28.0, "pv_22": 24.0}, invs)
    assert boundary == {"pv_21": 28.0, "pv_22": 24.0}


def test_werte_map_laesst_das_anlagen_aggregat_unberuehrt():
    """`pv_gesamt` benennt keine Investition — die Wahl zwischen Aggregat und
    Einzelwerten trifft eine andere Schicht."""
    bkw, module = _anlage_mit_bkw()
    out = kuerze_bkw_in_werte_map(
        {"pv_gesamt": 99.0, "pv_2": 52.0, "pv_21": 28.0, "pv_22": 24.0},
        [bkw, *module],
    )
    assert out["pv_gesamt"] == 99.0


def test_vollstaendige_deckung_nur_wenn_jedes_kind_misst():
    bkw, module = _anlage_mit_bkw()
    invs = [bkw, *module]
    beide = bkw_kinder_decken_vollstaendig(invs, lambda i: i in {"21", "22"})
    assert beide == frozenset({"2"})
    eines = bkw_kinder_decken_vollstaendig(invs, lambda i: i == "21")
    assert eines == frozenset()


# ─── 2. Live-Energiefluss ───────────────────────────────────────────────────

def _live(werte: dict[str, float], kinder: int = 2) -> dict:
    anlage = Anlage(anlagenname="K", standort_land="DE", leistung_kwp=1.10)
    bkw, module = _anlage_mit_bkw(kinder)
    invs = {str(i.id): i for i in [bkw, *module]}
    return build_komponenten(
        anlage,
        {"netzbezug_w": 400.0},
        {k: {"leistung_w": v} for k, v in werte.items()},
        invs,
        {k: {"leistung_w": f"s.{k}"} for k in werte},
    )


def test_live_kai2_zaehlt_die_energie_einmal():
    """Der Melder-Fall: BKW und beide Module gemappt."""
    res = _live({"2": 52.0, "21": 28.0, "22": 24.0})
    assert res["pv_total_w"] == pytest.approx(52.0)
    keys = {k["key"] for k in res["komponenten"]}
    assert "pv_2" not in keys, "das abtretende BKW darf keinen eigenen Knoten haben"
    assert {"pv_21", "pv_22"} <= keys


def test_live_teil_deckung_zeigt_das_bkw_mit_dem_rest():
    res = _live({"2": 52.0, "21": 28.0})
    assert res["pv_total_w"] == pytest.approx(52.0)
    bkw_knoten = next(k for k in res["komponenten"] if k["key"] == "pv_2")
    assert bkw_knoten["erzeugung_kw"] == pytest.approx(0.024)


def test_nur_bkw_gemappt_bleibt_unveraendert():
    """⚠ Die Gegenprobe: der Normalfall darf seine einzige Live-Quelle behalten."""
    res = _live({"2": 52.0})
    assert res["pv_total_w"] == pytest.approx(52.0)
    assert [k["key"] for k in res["komponenten"] if k["key"].startswith("pv_")] == ["pv_2"]


def test_ohne_abtretendes_bkw_bleibt_alles_wie_bisher():
    """Ein BKW ohne Modul-Kinder ist selbst Erzeuger — nichts wird gekürzt."""
    res = _live({"2": 52.0}, kinder=0)
    assert res["pv_total_w"] == pytest.approx(52.0)


def test_live_auslastung_nimmt_zaehler_und_nenner_aus_derselben_menge():
    """Vor N-536 lief der Nenner durch den Selektor (1,10 kWp) und der Zähler
    nicht (104 W) — 9 % statt 5 %, in derselben Formel drei Zeilen auseinander."""
    res = _live({"2": 52.0, "21": 28.0, "22": 24.0})
    gauge = next(g for g in res["gauges"] if g["key"] == "pv_leistung")
    assert gauge["wert"] == pytest.approx(5.0, abs=0.5)
