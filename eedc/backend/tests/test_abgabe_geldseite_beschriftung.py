"""Die Erlös-Zeile des T-Kontos heißt wie die Energiezeile (Bauschritt 11d).

Konzept §9.2 „Die Geldseite": *„T-Konto-Zeile ‚{Gerät} — Abgabe an Dritte'; der
Name kommt aus dem **Backend** (`erloes_label`, Bauform wie `ersparnis_label`),
nicht hart verdrahtet."*

**Warum das eine eigene Probe braucht.** Dasselbe Feld
(`einspeise_erloes_euro`) trägt bei zwei Kategorien zwei verschiedene
Ertragsarten: beim *Erzeuger* einen Einspeise-Erlös, bei der *Abgabe an Dritte*
den Erlös des dritten Wegs. Bis zum 06.09.2026 schrieb der Client über beide
„— Einspeisung" — rilmor-mhrs (#402) las damit im T-Konto ein Wort, das in der
Energiebilanz derselben Anlage nicht vorkommt. Regel 0 des Style-Guides
verlangt für die Geldzeile denselben Namen wie für die Energiezeile.

Die Client-Hälfte (`TKonto.tsx` liest das Feld, statt es zu verdrahten) hält
`components/finanzen/TKonto.test.tsx`.

Schwesterdateien: test_abgabe_geldseite_drei_sichten.py (Kapitalrechnung),
test_abgabe_an_dritte_vier_sichten.py (Bilanz), test_erzeuger_einspeise_erloes.py
(§9 Weg 2 — der Erzeuger-Fall, gegen den hier abgegrenzt wird).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import (
    ERLOES_LABEL_EINSPEISUNG,
    _baue_investition_financial,
)
from backend.core.field_definitions import SONSTIGES_ABGABE_LABEL
from backend.models import Investition

ERLOES = 209.35


def _sonstiges(kategorie: str) -> Investition:
    """Ein *Sonstiges*-Gerät mit gepflegtem Erlös — nur die Kategorie wechselt."""
    return Investition(
        id=1, anlage_id=1, typ="sonstiges", bezeichnung="Allg. Strom",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=2000.0,
        aktiv=True, parameter={"kategorie": kategorie},
    )


def _detail(inv: Investition):
    return _baue_investition_financial(
        inv,
        {"einspeise_erloes_euro": ERLOES},
        netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0,
        monats_gaspreis=None, monats_benzinpreis=None, emob_pool_attr=None,
    )


def test_abgabe_traegt_den_namen_ihrer_kategorie():
    """Kategorie `abgabe` ⇒ „Abgabe an Dritte", nicht „Einspeisung"."""
    d = _detail(_sonstiges("abgabe"))

    assert d is not None
    assert d.erloes_label == SONSTIGES_ABGABE_LABEL, (
        f"Erlös-Zeile heißt {d.erloes_label!r} statt {SONSTIGES_ABGABE_LABEL!r} — "
        "der Anwender sucht dieses Wort in der Energiebilanz vergeblich")
    assert d.erloes_euro == pytest.approx(ERLOES)


def test_erzeuger_bleibt_bei_einspeisung():
    """Die Gegenprobe — der Erzeuger speist ein und heißt weiter so.

    Ohne sie wäre die Probe darüber auch dann grün, wenn jemand das Label
    pauschal auf „Abgabe an Dritte" setzt.
    """
    d = _detail(_sonstiges("erzeuger"))

    assert d is not None
    assert d.erloes_label == ERLOES_LABEL_EINSPEISUNG
    assert SONSTIGES_ABGABE_LABEL not in (d.erloes_formel or "")


def test_die_herleitung_nennt_die_richtige_ertragsart():
    """A6: die Formel beschreibt, was der Betrag IST — je Kategorie verschieden.

    Beide Sätze sagen „von eedc nicht nachgerechnet" (der Betrag ist gepflegt),
    aber der eine nennt einen Vergütungssatz und der andere einen eigenen Satz
    für abgegebenen Strom. Ein gemeinsamer Satz behauptete für einen der beiden
    Fälle etwas Falsches.
    """
    abgabe = _detail(_sonstiges("abgabe"))
    erzeuger = _detail(_sonstiges("erzeuger"))

    assert SONSTIGES_ABGABE_LABEL in (abgabe.erloes_formel or "")
    assert "Einspeise-Erlös" in (erzeuger.erloes_formel or "")
    assert abgabe.erloes_formel != erzeuger.erloes_formel


def test_der_default_gilt_fuer_alle_uebrigen_typen():
    """Ein BKW rechnet seinen Erlös selbst — und bleibt „Einspeisung".

    Der Default sitzt an einer Stelle (`ERLOES_LABEL_EINSPEISUNG`); diese Probe
    hält fest, dass er auch die Typen erreicht, die den `sonstiges`-Zweig gar
    nicht betreten.
    """
    bkw = Investition(
        id=2, anlage_id=1, typ="balkonkraftwerk", bezeichnung="BKW",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=800.0,
        aktiv=True, parameter={},
    )
    d = _baue_investition_financial(
        bkw, {"einspeisung_kwh": 120.0, "eigenverbrauch_kwh": 300.0},
        netz_p=30.0, einsp_p=8.0, wp_p=30.0, wb_p=30.0,
        monats_gaspreis=None, monats_benzinpreis=None, emob_pool_attr=None,
    )

    assert d is not None and d.erloes_euro is not None
    assert d.erloes_label == ERLOES_LABEL_EINSPEISUNG


def test_der_posten_der_kapitalrechnung_teilt_den_namen():
    """Ein Name, zwei Zeilen — sonst driften Geld- und Energieseite getrennt.

    `BEZEICHNUNG_ABGABE` (Kapitalrechnung) ist von `SONSTIGES_ABGABE_LABEL`
    abgeleitet. Diese Probe hält die Ableitung fest: Wer den Anzeigenamen
    ändert, ändert beide Zeilen — oder er merkt es hier.
    """
    from backend.core.berechnungen.investitions_jahresertrag import (
        BEZEICHNUNG_ABGABE,
    )

    assert BEZEICHNUNG_ABGABE.endswith(SONSTIGES_ABGABE_LABEL)
