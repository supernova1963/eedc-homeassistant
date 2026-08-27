"""SOLL Wärme/Klima — **E4**: Lüften und Entfeuchten erfassen, nicht bewerten.

Schwesterdateien: ``test_soll_waerme_klima_achse1_erfassung.py`` (R1/K3 — welche
Größe darf welche entwerten), ``test_soll_waerme_klima_achse2_abgrenzung.py``
(R2 — wann darf eine Kennzahl nicht erscheinen) und
``test_263_innengeraete_varianten.py`` (Variante ``V8_nur_lueften_entfeuchten``,
dieselbe Regel über vier Flächen gemessen).

**Die Regel** (Konzept ``soll-waerme-klima.md`` §2.3, Entscheid Gernot 26.08.):

    Lüften und Entfeuchten sind **erfassbar, aber keine bewertete Funktion** —
    sie erscheinen in der Aufteilung, bekommen aber keine Kennzahl und keinen
    Vergleich. Wer sie nicht erfasst, sieht sie nicht.

**Was bis zum 26.08.2026 fehlte, war die erste Hälfte.** Die Registry bot die
vier Felder an, der Anwender konnte Zähler zuordnen — und ihre Kilowattstunden
erschienen **nirgends**. ``modus_strom_zeile`` las im gemessenen Zweig nur
Heizen und Kühlen; alles Übrige fiel stumm unter „nicht aufgeteilt". Das ist die
P-6-Falle: ein Angebot, das niemand einlösen kann.

⛔ **Ein früherer Entscheid stand dem entgegen und ist abgelöst.** In
``energie_profil/views.py`` stand wörtlich: *„Lüften/Entfeuchten haben eigene
Zähler, aber kein eigenes Segment — sie fallen wie im Monat unter ‚nicht
aufgeteilt' (Entscheid Gernot 2026-08-25: erst differenzieren, wenn Anwender es
verlangen)."* Das war eine Umfangs-Abwägung **ohne Konzept**; seit dem 26.08.
gibt es eines, und es beantwortet dieselbe Frage anders. Drei Proben hielten den
alten Zustand fest und sind umgestellt, nicht gelöscht — sie hatten recht,
solange die Regel galt.

⭐ **Die zweite Hälfte — „nicht bewertet" — ist der Grund, warum diese Datei
existiert.** Sichtbar machen allein wäre ein halber Bau: Stünde ihr Strom weiter
im Nenner der Arbeitszahl, drückte er sie aus demselben Grund wie der Kühlstrom
vor **W-14**. Lüften erzeugt keine Wärme, die in einem Wärmemengenzähler landet.
*Ein Kategorienfehler, kein Messfehler.*
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile
from backend.core.berechnungen.waermepumpe_kennzahl import arbeitszahl
from backend.core.betriebsmodus import (
    BETRIEBSART_STROM_FELD,
    ENTFEUCHTEN,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    MODUS_ABDECKUNG_FELD,
    MODUS_STROM_FELD,
)
from backend.services.monats_fakten import WpFakten


# ── Hälfte 1: erfassen — die Zeile trägt alle vier Betriebsarten ────────────

def test_e4_gemessene_zeile_traegt_alle_vier_betriebsarten():
    """Ein zugeordneter Lüftungs-Zähler landet in der Zeile, nicht im Nirgendwo."""
    zeile = modus_strom_zeile({
        BETRIEBSART_STROM_FELD[HEIZEN]: 40.0,
        BETRIEBSART_STROM_FELD[KUEHLEN]: 30.0,
        BETRIEBSART_STROM_FELD[LUEFTEN]: 5.0,
        BETRIEBSART_STROM_FELD[ENTFEUCHTEN]: 7.0,
    })

    assert zeile.gemessen is True
    assert zeile.lueften_kwh == 5.0, (
        "Der gemessene Lüftungs-Zähler erreicht die Zeile nicht — sein Wert "
        "fällt still unter „nicht aufgeteilt“ (P-6-Falle)."
    )
    assert zeile.entfeuchten_kwh == 7.0


def test_e4_abgeleiteter_split_kennt_sie_nicht_und_das_ist_die_aussage():
    """**Die Gegenrichtung, und sie ist keine Lücke.**

    Der aus dem Betriebsmodus abgeleitete Split kann nur Heizen und Kühlen
    (``AUFGETEILTE_MODI``, #263 D11) — ein Modus-Signal gibt nicht mehr her.
    Dort bleiben die beiden bei 0, statt eine Zahl zu erfinden.

    Ohne diese Probe wäre nicht unterscheidbar, ob der abgeleitete Zweig sie
    *nicht kann* oder ob jemand vergessen hat, sie zu füllen.
    """
    zeile = modus_strom_zeile({
        MODUS_STROM_FELD[HEIZEN]: 40.0,
        MODUS_STROM_FELD[KUEHLEN]: 30.0,
        MODUS_ABDECKUNG_FELD: 500.0,
    })

    assert zeile.gemessen is False
    assert zeile.lueften_kwh == 0.0
    assert zeile.entfeuchten_kwh == 0.0
    assert zeile.heizen_kwh == 40.0


# ── Hälfte 2: nicht bewerten — sie fallen aus dem Nenner ────────────────────

def test_e4_lueften_und_entfeuchten_fallen_aus_dem_nenner():
    """Der Kern der Regel: sichtbar ja, bewertet nein.

    Ohne den Abzug bekäme eine Anlage, die viel lüftet, eine gedrückte
    Arbeitszahl — obwohl der Lüftungsstrom nie Wärme erzeugen sollte.
    """
    fakten = WpFakten(
        strom_kwh=100.0, waerme_kwh=240.0,
        modus_strom_heizen_kwh=60.0,
        modus_strom_kuehlen_kwh=20.0,
        modus_strom_lueften_kwh=15.0,
        modus_strom_entfeuchten_kwh=5.0,
        modus_strom_bezug_kwh=100.0,
        geraete_mit_strom=1, geraete_mit_waerme=1,
    )

    assert fakten.modus_strom_funktionsfremd_kwh == pytest.approx(40.0), (
        "Kühlen + Lüften + Entfeuchten sind der Nenner-Abzug (W-14 + E4)."
    )

    az = arbeitszahl(
        fakten.waerme_kwh, fakten.strom_kwh,
        strom_funktionsfremd_kwh=fakten.modus_strom_funktionsfremd_kwh,
    )
    # 240 / (100 − 40) = 4,0 — nicht 240/100 = 2,4.
    assert az.wert == pytest.approx(4.0), (
        f"Der funktionsfremde Strom steht noch im Nenner: {az.wert}"
    )


def test_e4_ohne_lueftungszaehler_aendert_sich_nichts():
    """**Gegenprobe.** Wer nicht lüftet (oder es nicht misst), rechnet wie zuvor.

    Ohne sie wäre eine zu breite Regel grün — etwa eine, die pauschal einen
    Anteil abzieht.
    """
    fakten = WpFakten(
        strom_kwh=100.0, waerme_kwh=240.0,
        modus_strom_heizen_kwh=80.0,
        modus_strom_kuehlen_kwh=20.0,
        modus_strom_bezug_kwh=100.0,
        geraete_mit_strom=1, geraete_mit_waerme=1,
    )

    assert fakten.modus_strom_funktionsfremd_kwh == pytest.approx(20.0)
    az = arbeitszahl(
        fakten.waerme_kwh, fakten.strom_kwh,
        strom_funktionsfremd_kwh=fakten.modus_strom_funktionsfremd_kwh,
    )
    assert az.wert == pytest.approx(3.0)  # 240 / 80


# ── Die Invariante: keine Menge steht zweimal ───────────────────────────────

def test_e4_restmenge_zieht_die_neuen_segmente_ab():
    """Σ Teilmengen + Rest == Bezug — sonst stünde dieselbe Menge zweimal.

    Das ist die Doppelzählungs-Klasse, die das Projekt beim BKW, beim Speicher
    und beim Wallbox/E-Auto-Pool je einmal getroffen hat.
    """
    fakten = WpFakten(
        strom_kwh=100.0,
        modus_strom_heizen_kwh=60.0,
        modus_strom_kuehlen_kwh=20.0,
        modus_strom_lueften_kwh=5.0,
        modus_strom_entfeuchten_kwh=7.0,
        modus_strom_bezug_kwh=100.0,
    )

    assert fakten.modus_nicht_aufgeteilt_kwh == pytest.approx(8.0)

    summe = (
        fakten.modus_strom_heizen_kwh + fakten.modus_strom_kuehlen_kwh
        + fakten.modus_strom_lueften_kwh + fakten.modus_strom_entfeuchten_kwh
        + fakten.modus_nicht_aufgeteilt_kwh
    )
    assert summe == pytest.approx(fakten.modus_strom_bezug_kwh)


def test_e4_wer_nicht_misst_findet_sie_weiterhin_im_rest():
    """**Die andere Hälfte des SOLL-Satzes:** *„Wer sie nicht erfasst, sieht sie nicht."*

    Ohne Zähler bleibt der Lüftungsstrom in der Restmenge — genau dort, wo er
    vorher stand. Die Regel nimmt niemandem etwas weg; sie gibt nur dem etwas,
    der misst.
    """
    fakten = WpFakten(
        strom_kwh=100.0,
        modus_strom_heizen_kwh=60.0,
        modus_strom_kuehlen_kwh=20.0,
        modus_strom_bezug_kwh=100.0,
    )

    assert fakten.modus_nicht_aufgeteilt_kwh == pytest.approx(20.0)


# ═══ N-336 — Warmwasser ist NICHT funktionsfremd ═══════════════════════════
#
# ⛔ **Die Falle beim Bau von N-336, und sie ist verführerisch.** In der
# Aufteilung steht Warmwasser neben Kühlen, Lüften und Entfeuchten und sieht
# aus wie sie: eine Betriebsart, die nicht Heizen ist. Der Unterschied ist
# nicht die Betriebsart, sondern die **Nutzenergie** — Warmwasser hat eine,
# und sie steht im Zähler desselben Quotienten (`waerme_gesamt_kwh`).
#
# ⚠ **Zwei Objekte tragen dieselbe Regel** und müssen beide geprüft werden:
# `ModusStromZeile.funktionsfremd_kwh` (je Zeile, für den Tagespfad) und
# `WpFakten.modus_strom_funktionsfremd_kwh` (anlagenweit). Beim ersten
# Gegenprobe-Versuch wurde nur das erste entschärft — und der
# Simulationstest blieb grün, weil die Route über das zweite geht. *Ein
# Sprengsatz beweist nur etwas, wenn er am Objekt sitzt, das der Prüfer liest.*

def test_n336_warmwasser_faellt_nicht_aus_dem_nenner_je_zeile():
    """`ModusStromZeile` — die Zeilen-Ebene (Tagespfad)."""
    from backend.core.berechnungen.betriebsart_gemessen import ModusStromZeile

    zeile = ModusStromZeile(
        heizen_kwh=600.0, kuehlen_kwh=100.0, gemessen=False,
        abdeckung_h=700.0, warmwasser_kwh=250.0,
    )

    assert zeile.funktionsfremd_kwh == pytest.approx(100.0), (
        "nur der Kühlstrom — Warmwasser erzeugt eine bewertete Nutzenergie "
        "und gehört deshalb in den Nenner"
    )


def test_n336_warmwasser_faellt_nicht_aus_dem_nenner_anlagenweit():
    """`WpFakten` — die anlagenweite Ebene, die die Routen lesen."""
    from backend.services.monats_fakten import WpFakten

    fakten = WpFakten(
        strom_kwh=1000.0,
        modus_strom_heizen_kwh=600.0,
        modus_strom_warmwasser_kwh=250.0,
        modus_strom_kuehlen_kwh=100.0,
        modus_abdeckung_h=700.0,
        modus_strom_bezug_kwh=1000.0,
    )

    assert fakten.modus_strom_funktionsfremd_kwh == pytest.approx(100.0)
    # Und die Restmenge zieht es sehr wohl ab — sonst stünde dieselbe Menge
    # zweimal im Balken.
    assert fakten.modus_nicht_aufgeteilt_kwh == pytest.approx(50.0)
