"""SOLL Wärme/Klima — **W-5**: eine Kennzahl für den Kühlbetrieb (§4.1).

Schwesterdateien: ``test_soll_waerme_klima_w4_arbeitszahl_je_funktion.py`` (die
andere Hälfte desselben §4.1-Bauplans) und
``test_soll_waerme_klima_achse2_abgrenzung.py`` (R2 — gilt hier unverändert).

**Der Befund, den das schließt:** Die Kältemenge
(``betriebsart_nutzenergie_kuehlen_kwh``) war seit v4.0.24 erfassbar, die
Layer-Funktion ``betriebsart_nutzenergie_kwh`` gab es — und **kein einziger
Aufrufer** las sie. Baumweiter Grep am 26.08.: null Treffer im Backend außerhalb
ihrer eigenen Datei, null im Frontend. Wer seine Kältemenge pflegte, sah sie an
**keiner** Stelle. Die P-6-Falle: ein Angebot, das niemand einlösen kann.

⛔ **Die Zahl heißt NICHT „SEER" — Empfehlung 26.08., von Gernot angenommen.**
SEER ist eine **genormte** Größe: saisonal gewichtet, unter definierten
Prüfstandsbedingungen ermittelt. Was eedc bilden kann, ist der schlichte
Quotient zweier Zähler über einen Zeitraum. Ihn „SEER" zu nennen behauptete
Vergleichbarkeit mit Datenblatt-Werten, die er nicht hat — dieselbe Klasse wie
ein Feldname, der etwas anderes trägt als er verspricht (**#120**, die Warnung
steht wörtlich an ``BETRIEBSART_NUTZENERGIE_FELD``). Sie heißt **„Arbeitszahl
Kühlen"**, parallel zu W-4 und ehrlich über das, was sie ist.

⚠ **Der Modul-Kopf des Konzepts nannte sie in einem Kommentar** (``modus_split``:
*„K-1 (SEER) braucht die Kühl-kWh"*) — genau die Sorte Versprechen, die dieses
Paket einlöst und dabei umbenennt.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_FREMDSTROM,
    GRUND_KEINE_KAELTEMENGE,
    arbeitszahl_kuehlen,
)


def test_w5_kaeltemenge_durch_kuehlstrom():
    """Der Normalfall: beide Zähler da, die Zahl entsteht."""
    r = arbeitszahl_kuehlen(900.0, 300.0)

    assert r.wert == pytest.approx(3.0)
    assert r.grund is None


def test_w5_ohne_kaeltemengenzaehler_steht_der_grund_da():
    """**Der häufigste Fall** — Kältemengenzähler sind selten.

    Wichtig ist, was **nicht** passiert: keine Schätzung. Eine Kältemenge lässt
    sich nicht ableiten; aus einem angenommenen Wirkungsgrad käme genau der
    Faktor zurück, mit dem man gerechnet hat (dieselbe Begründung wie bei der
    abgeleiteten Heizwärme, Konzept §3.5).
    """
    r = arbeitszahl_kuehlen(None, 300.0)

    assert r.wert is None
    assert r.grund == GRUND_KEINE_KAELTEMENGE
    assert "Kältemengenzähler" in r.grund


def test_w5_ohne_kuehlbetrieb_ist_der_grund_ein_anderer():
    """„Nicht gekühlt" und „Kälte nicht gemessen" sind verschiedene Auskünfte.

    Ohne diese Trennung bekäme jede Heizungs-Wärmepumpe im Winter den Hinweis,
    ihr fehle ein Kältemengenzähler — ein Ratschlag, der auf ihren Fall nicht
    passt.
    """
    r = arbeitszahl_kuehlen(None, 0.0)

    assert r.wert is None
    assert r.grund == "kein Kühlbetrieb in diesem Zeitraum"
    assert r.grund != GRUND_KEINE_KAELTEMENGE


def test_w5_r2_gilt_auch_hier():
    """Ein Fremdanteil auf dem Zähler macht auch diese Zahl unbrauchbar."""
    r = arbeitszahl_kuehlen(900.0, 300.0, abgrenzung_verletzt=GRUND_FREMDSTROM)

    assert r.wert is None
    assert r.grund == GRUND_FREMDSTROM


def test_w5_traegt_keinen_heizstab_hinweis():
    """**Bewusst kein übernommener Satz.**

    ``HEIZSTAB_HINWEIS`` erklärt eine Arbeitszahl nahe 1 mit direkter
    Elektroheizung. Im Kühlbetrieb gibt es dafür keine Entsprechung — eine
    niedrige Kälte-Arbeitszahl hat andere Ursachen (hohe Außentemperatur,
    kleiner Temperaturhub). Einen Satz zu übernehmen, weil die Bauform passt,
    wäre eine Erklärung, die nichts erklärt.
    """
    r = arbeitszahl_kuehlen(280.0, 300.0)   # 0,93 — unter der Heizstab-Schwelle

    assert r.wert == pytest.approx(280 / 300)
    assert r.hinweis is None


def test_w5_die_kaeltemenge_erreicht_die_fakten_aus_der_ZEILE():
    """Der Negativbeweis von gestern, positiv gewendet — **über die echte Kette**.

    Bis zum 26.08.2026 gab es **keinen Aufrufer** für die Kältemenge: erfassbar,
    nirgends lesbar. Diese Probe geht den Weg, den ein echter Wert nimmt —
    ``verbrauch_daten`` → ``imd_typ_beitrag`` → Kennzahl.

    ⛔ **Ihr erster Entwurf tat genau das nicht.** Er baute ein ``WpFakten``
    direkt mit ``nutzenergie_kuehlen_kwh=900`` und prüfte damit nur, dass das
    **Feld existiert** — nicht, dass die Kette es **befüllt**. Die Gegenprobe
    (Resolver-Zeile entfernt) blieb grün. *Eine Probe, die sich ihren Zustand
    selbst herstellt, schützt am Ende die Falschaussage.*
    """
    from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
    from backend.core.betriebsmodus import (
        BETRIEBSART_NUTZENERGIE_FELD,
        BETRIEBSART_STROM_FELD,
        KUEHLEN,
    )

    inv = SimpleNamespace(typ="waermepumpe", parameter={"wp_art": "luft_luft"})
    beitrag = imd_typ_beitrag(inv, {
        "stromverbrauch_kwh": 1000.0,
        BETRIEBSART_STROM_FELD[KUEHLEN]: 300.0,
        BETRIEBSART_NUTZENERGIE_FELD[KUEHLEN]: 900.0,
    })

    assert beitrag.wp_nutzenergie_kuehlen == pytest.approx(900.0), (
        "Die gemessene Kältemenge erreicht den Zeilen-Resolver nicht — "
        "sie ist damit an keiner Sicht auswertbar."
    )
    assert arbeitszahl_kuehlen(
        beitrag.wp_nutzenergie_kuehlen, beitrag.wp_modus_strom_kuehlen,
    ).wert == pytest.approx(3.0)


def test_w5_ohne_kaeltezaehler_bleibt_die_zeile_bei_null():
    """Gegenprobe zur Kette: kein Feld, kein Wert — und keine erfundene Menge."""
    from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
    from backend.core.betriebsmodus import BETRIEBSART_STROM_FELD, KUEHLEN

    inv = SimpleNamespace(typ="waermepumpe", parameter={"wp_art": "luft_luft"})
    beitrag = imd_typ_beitrag(inv, {
        "stromverbrauch_kwh": 1000.0,
        BETRIEBSART_STROM_FELD[KUEHLEN]: 300.0,
    })

    assert beitrag.wp_nutzenergie_kuehlen == 0.0
    assert arbeitszahl_kuehlen(
        beitrag.wp_nutzenergie_kuehlen, beitrag.wp_modus_strom_kuehlen,
    ).grund == GRUND_KEINE_KAELTEMENGE
