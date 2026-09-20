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


# ─── 3. Tagesebene: Stufe 2 vor dem Anlagen-Aggregat ────────────────────────

def _tag(komponenten: dict[str, float], kinder: int = 2):
    from backend.services.snapshot.komponenten_beitraege import loese_pv_tageswerte_auf

    bkw, module = _anlage_mit_bkw(kinder)
    invs = {str(i.id): i for i in [bkw, *module]}
    return loese_pv_tageswerte_auf(komponenten, invs, date(2026, 9, 19))


def _summe(out: dict) -> float:
    from backend.core.berechnungen.energie import summe_pv_bkw_kwh

    return summe_pv_bkw_kwh(out)


def test_tag_kai2_zaehlt_die_energie_einmal():
    out, _ = _tag({"bkw_2": 0.52, "pv_21": 0.28, "pv_22": 0.24})
    assert _summe(out) == pytest.approx(0.52)
    assert out["bkw_2"] == 0.0, "abgetretene Null, nicht gelöscht (#350 zeigt Erzeuger je Gerät)"


def test_tag_findet_das_bkw_auch_im_live_keyspace():
    """Derselbe Tag kann vom Boundary-Pfad (`bkw_<id>`) oder vom Live-Pfad
    (`pv_<id>` für jeden Erzeuger) geschrieben sein — der Mismatch war der
    BKW-Doppelzählungs-Bug vom 2026-05-19."""
    out, _ = _tag({"pv_2": 0.52, "pv_21": 0.28, "pv_22": 0.24})
    assert _summe(out) == pytest.approx(0.52)
    assert out["pv_2"] == 0.0


def test_tag_verteilt_den_rest_kwp_gewichtet_und_kennzeichnet_ihn():
    """Nur das BKW misst → seine Kinder bekommen den kWp-Anteil, als Zerlegung
    markiert. Auf der TAGESEBENE ist die kWp-Gewichtung zulässig (über einen Tag
    mittelt sich Ost/West aus) — auf der Stundenebene nicht."""
    from backend.services.provenance import ABGELEITET_KWP_ANTEIL

    out, marken = _tag({"bkw_2": 0.52})
    assert _summe(out) == pytest.approx(0.52)
    assert out["pv_21"] == pytest.approx(0.26)
    assert out["pv_22"] == pytest.approx(0.26)
    assert marken == {"pv_21": ABGELEITET_KWP_ANTEIL, "pv_22": ABGELEITET_KWP_ANTEIL}


def test_tag_teil_deckung_laesst_die_messung_stehen():
    out, marken = _tag({"bkw_2": 0.52, "pv_21": 0.28})
    assert out["pv_21"] == pytest.approx(0.28), "gemessene Module behalten ihren Wert (P7)"
    assert out["pv_22"] == pytest.approx(0.24)
    assert set(marken) == {"pv_22"}


def test_tag_bkw_ohne_kinder_bleibt_unveraendert():
    out, marken = _tag({"bkw_2": 0.52}, kinder=0)
    assert out == {"bkw_2": 0.52}
    assert marken == {}


# ─── 4. Stundenebene: Deckung auf Träger-Ebene, Rest unverteilt ─────────────

def test_stunde_deckung_steigt_auf_die_traeger_ebene():
    """Ohne diese Ergänzung fiele eine Anlage mit BKW-Zähler und Kindern ohne
    eigene Zähler dauerhaft auf das Anlagen-Aggregat zurück."""
    from backend.core.berechnungen.erzeuger_traeger import ergaenze_kinder_deckung

    bkw, module = _anlage_mit_bkw()
    invs = [bkw, *module]
    assert ergaenze_kinder_deckung({"2"}, invs) == {"2", "21", "22"}
    # Ergänzt nur, streicht nie:
    assert ergaenze_kinder_deckung({"21"}, invs) == {"21"}


def test_stunde_summe_zaehlt_die_energie_einmal_und_verteilt_nicht():
    """Die Stundensumme kürzt das BKW auf den Rest — aber sie legt ihn NICHT
    kWp-gewichtet auf die Kinder (`komponenten_beitraege`: der kWp-Schlüssel ist
    eine Tages-Aussage, über eine Stunde mittelt sich Ost/West nicht aus)."""
    bkw, module = _anlage_mit_bkw()
    invs = [bkw, *module]

    einzel = {"2": 0.052, "21": 0.028, "22": 0.024}
    einzel.update(bkw_restwerte(invs, einzel))
    assert sum(einzel.values()) == pytest.approx(0.052)

    teil = {"2": 0.052, "21": 0.028}
    teil.update(bkw_restwerte(invs, teil))
    assert sum(teil.values()) == pytest.approx(0.052)
    assert teil["2"] == pytest.approx(0.024), "der Rest bleibt beim Gerät, unverteilt"


def test_beide_stundenpfade_haengen_die_kuerzung_wirklich_ein():
    """⚠ Diese Probe schließt eine gemessene Lücke der Probe darüber.

    `test_stunde_summe_…` ruft `bkw_restwerte` selbst auf und prüft damit die
    **Formel**, nicht ihre **Einhängung**: Bei der Gegenprobe am 20.09.2026 blieb
    sie grün, während der Aufruf in `snapshot/aggregator.py` entschärft war. Der
    Stundenpfad ist ohne Snapshots und DB nicht in einer Werte-Probe erreichbar —
    also hält ihn ein Quelltext-Wächter, so wie die Wurzelmuster-Prüfer es für
    dieselbe Frage tun.

    Der P11-Wächter allein genügt hier nicht: ihm reicht **ein** Selektor-Aufruf
    je Funktion, und `ergaenze_kinder_deckung` (die Deckungs-Hälfte) würde die
    Funktion freikaufen, auch wenn die Kürzung der Summe verschwunden ist.
    """
    from pathlib import Path

    basis = Path(__file__).resolve().parents[1]
    for rel in ("services/snapshot/aggregator.py", "services/snapshot/lts_aggregator.py"):
        quelle = (basis / rel).read_text(encoding="utf-8")
        assert "bkw_restwerte(_alle_invs, einzel)" in quelle, (
            f"{rel}: die Summe des Einzel-Zweigs kürzt das abtretende "
            f"Balkonkraftwerk nicht mehr — N-536 wäre dort wieder offen."
        )
        assert "ergaenze_kinder_deckung(" in quelle, (
            f"{rel}: die Deckungsfrage steht nicht mehr auf der Träger-Ebene — "
            f"eine Anlage mit BKW-Zähler und Kindern ohne eigenen Zähler fiele "
            f"wieder auf das Anlagen-Aggregat oder eine Teilsumme zurück."
        )
