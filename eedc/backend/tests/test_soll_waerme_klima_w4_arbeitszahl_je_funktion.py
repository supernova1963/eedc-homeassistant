"""SOLL Wärme/Klima — **W-4**: je Funktion eine eigene Arbeitszahl (§4.1).

Schwesterdateien: ``test_soll_waerme_klima_achse2_abgrenzung.py`` (R2 — wann darf
eine Kennzahl nicht erscheinen; alle Sperren dort gelten hier weiter) und
``test_soll_waerme_klima_e4_lueften_entfeuchten.py`` (die andere Hälfte desselben
§4.1-Bauplans).

**Die Regel** (`soll-waerme-klima.md` §4.1):

    | Heizen      | Arbeitszahl Heizen      | Q_heiz / E_heiz |
    | Warmwasser  | Arbeitszahl Warmwasser  | Q_ww  / E_ww    |

⭐ **Warum das keine „genauere JAZ" ist, sondern zwei andere Zahlen.** Warmwasser
liegt bauartbedingt niedriger als Heizen (höhere Zieltemperatur). Eine Anlage mit
viel Warmwasseranteil hat deshalb eine niedrigere **Gesamt**zahl, **ohne
schlechter zu sein** — und genau das kann die Gesamtzahl nicht sagen.

## Was hier vorher stand — drei Mängel in einem Dreizeiler

Der Komponenten-Hub rechnete `cop_heizen` / `cop_warmwasser` **selbst**
(`gesamt_heizung_getrennt / gesamt_strom_heizen`) und zeigte sie als „JAZ
Heizen" / „JAZ Warmwasser". Daran war dreierlei falsch:

1. **Eigener Quotient statt Layer** — die **W-3-Klasse** (die JAZ stand einmal an
   drei Orten). Folge: **alle** R2-Sperren fehlten außer der abgeleiteten Wärme.
   Ein Heizstab auf dem Zähler sperrte die Gesamt-JAZ, diese beiden aber nicht —
   *dieselbe Anlage, zwei Aussagen.*
2. **`0` statt „keine Aussage"**, wo die Zahl gesperrt war. Eine 0 heißt
   „Arbeitszahl null", nicht „unbekannt" (ADR-002/**P4**).
3. **`cop_*` als Feldname**, obwohl das Projekt Perioden-Kennzahlen durchgängig
   als **JAZ** führt (Glossar, v3.23.4/#167). Der *Anzeige*name war längst „JAZ".

⚠ **Und sie fehlten in der Monatssicht ganz** — dieselbe Zahl, zwei Sichten, eine
davon stumm.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDSTROM,
    GRUND_STROM_NICHT_JE_FUNKTION,
    arbeitszahl,
    arbeitszahl_je_funktion,
)


def _je_funktion(**kw):
    """Vollständiger Aufruf mit den Mengen einer realen Anlage."""
    basis = dict(
        heizung_kwh=2000.0, strom_heizen_kwh=500.0,
        warmwasser_kwh=600.0, strom_warmwasser_kwh=300.0,
        hat_split=True,
    )
    basis.update(kw)
    return arbeitszahl_je_funktion(**basis)


# ── Die Zahlen selbst ──────────────────────────────────────────────────────

def test_w4_je_funktion_eine_eigene_zahl():
    """Q_heiz/E_heiz und Q_ww/E_ww — getrennt, nicht als Mittelwert."""
    r = _je_funktion()

    assert r.heizen.wert == pytest.approx(4.0)        # 2000 / 500
    assert r.warmwasser.wert == pytest.approx(2.0)    # 600 / 300


def test_w4_warmwasser_darf_niedriger_sein_ohne_hinweis_auf_einen_fehler():
    """**Die fachliche Pointe.** Die Gesamtzahl liegt zwischen beiden.

    2600 kWh Wärme auf 800 kWh Strom sind 3,25 — eine Zahl, die weder das gute
    Heizen (4,0) noch das schwächere Warmwasser (2,0) beschreibt. Erst die
    getrennten Zahlen sagen, woher der Mittelwert kommt.
    """
    r = _je_funktion()
    gesamt = arbeitszahl(2600.0, 800.0)

    assert gesamt.wert == pytest.approx(3.25)
    assert r.warmwasser.wert < gesamt.wert < r.heizen.wert


# ── Mangel 1: die R2-Sperren gelten jetzt auch hier ────────────────────────

def test_w4_abgrenzungs_stoerung_sperrt_BEIDE_zahlen():
    """Ein Heizstab auf dem WP-Zähler trifft nicht nur eine der Funktionen.

    ⭐ **Das ist der Kern von Mangel 1.** Vorher rechnete der Hub den Quotienten
    selbst und kannte diese Sperre nicht: Die Gesamt-JAZ verschwand mit Grund,
    „JAZ Heizen" stand unbeeindruckt daneben. **Dieselbe Anlage, zwei Aussagen.**
    """
    r = _je_funktion(abgrenzung_verletzt=GRUND_FREMDSTROM)

    assert r.heizen.wert is None
    assert r.warmwasser.wert is None
    assert r.heizen.grund == GRUND_FREMDSTROM
    assert r.warmwasser.grund == GRUND_FREMDSTROM


def test_w4_abgeleitete_waerme_sperrt_beide():
    """Aus `Strom × JAZ` kommt je Funktion derselbe Faktor zurück wie in der Summe."""
    r = _je_funktion(waerme_abgeleitet_kwh=1500.0)

    assert r.heizen.wert is None
    assert r.warmwasser.wert is None
    assert "gerechnet" in (r.heizen.grund or "")


# ── Mangel 2: keine Aussage statt 0 ────────────────────────────────────────

def test_w4_ohne_getrennte_strommessung_gibt_es_die_zahlen_nicht():
    """**Kein 0, sondern ein Grund** (ADR-002/P4).

    Ohne `getrennte_strommessung` liegt E je Funktion nicht vor. Die Wärme allein
    genügt nicht — Q ohne E ist kein Quotient.
    """
    r = arbeitszahl_je_funktion(
        heizung_kwh=2000.0, strom_heizen_kwh=None,
        warmwasser_kwh=600.0, strom_warmwasser_kwh=None,
        hat_split=False,
    )

    assert r.heizen.wert is None, "0 wäre die Aussage „Arbeitszahl null“"
    assert r.heizen.grund == GRUND_STROM_NICHT_JE_FUNKTION
    assert r.warmwasser.grund == GRUND_STROM_NICHT_JE_FUNKTION


def test_w4_fehlender_waermezaehler_nennt_seinen_eigenen_grund():
    """Eine Funktion kann fehlen, ohne die andere mitzunehmen.

    Wer Strom je Funktion misst, aber nur die Heizwärme zählt, bekommt die
    Heizzahl — und beim Warmwasser den Grund, warum es dort keine gibt.
    """
    r = _je_funktion(warmwasser_kwh=None)

    assert r.heizen.wert == pytest.approx(4.0)
    assert r.warmwasser.wert is None
    assert "Wärmemengenzähler" in (r.warmwasser.grund or "")


# ── Der Heizstab-Satz gilt auch je Funktion ────────────────────────────────

def test_w4_heizstab_hinweis_erscheint_auch_je_funktion():
    """W-6 hängt an der Zahl, nicht an der Sicht — dieselbe Layer-Funktion.

    Warmwasser über den Heizstab ergibt eine Arbeitszahl nahe 1. Sie ist richtig
    und bekommt ihren erklärenden Satz, statt wie ein Defekt auszusehen.
    """
    r = _je_funktion(warmwasser_kwh=310.0, strom_warmwasser_kwh=330.0)

    assert r.warmwasser.wert == pytest.approx(310 / 330)
    assert r.warmwasser.hinweis is not None
    assert "elektrisch" in r.warmwasser.hinweis
    # Die Heizzahl daneben ist unbeeinflusst — der Hinweis hängt am Wert.
    assert r.heizen.hinweis is None


# ── Abgrenzung zu E4: kein doppelter Abzug ─────────────────────────────────

def test_w4_zieht_keinen_funktionsfremden_strom_ab():
    """**Die Falle, die hier NICHT gebaut werden durfte.**

    `strom_heizen_kwh` ist bereits nur der Heizbetrieb — Kühlen, Lüften und
    Entfeuchten sind darin gar nicht enthalten. Einen `funktionsfremd`-Abzug
    hier anzuwenden zöge dieselbe Menge zweimal ab. Die Probe hält fest, dass
    die Zahl exakt Q/E ist.
    """
    r = _je_funktion(heizung_kwh=1000.0, strom_heizen_kwh=250.0)

    assert r.heizen.wert == pytest.approx(4.0), (
        "Der Nenner wurde verändert — je Funktion gibt es keinen Abzug."
    )
