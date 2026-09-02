"""ADR-002/**P12** — dieselbe Arbeitszahl auf jedem Weg (Melder dietmar1968).

Der Wächter `test_wurzelmuster_konformitaet.py::test_p12_arbeitszahl_nur_im_layer`
hält die *Bauform* frei: niemand außer dem Layer dividiert Wärme durch Strom.
Er sagt nichts über den **Wert** — eine Stelle könnte den Layer rufen und ihm
die falschen Argumente geben.

Diese Datei prüft deshalb die Argumente, und zwar an den Zahlen aus dem
Melder-Screenshot (T89667 #290, August 2026):

    WP-Wärme (Heizung + Warmwasser)   210 kWh
    Strom über BEIDE Geräte           316 kWh   ⇒ gezeigt wurde 0,7
    Strom der Wärmepumpe allein        97 kWh   ⇒ ihre Zahl ist 2,2

**0,7 beschreibt kein Gerät seiner Anlage.** Sie entsteht, weil im Nenner der
Strom von zwei Geräten steht und im Zähler die Wärme von einem — und sie
bewegt sich mit dem Betrieb der Klimaanlage statt mit Effizienz.
"""
import pytest

from backend.core.berechnungen.waermepumpe_kennzahl import (
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_GERAETE_OHNE_WAERME,
    abgrenzungs_grund,
    arbeitszahl,
)

#: Die Zahlen des Melders, auf zwei Nachkommastellen nachgerechnet.
WAERME_KWH = 210.0
STROM_BEIDE_KWH = 316.0
STROM_NUR_WP_KWH = 97.0


def test_melderfall_ohne_sperre_waere_die_zahl_0_7():
    """Die Ausgangslage — ohne Abgrenzungs-Grund kommt genau seine 0,7 heraus.

    Das ist **kein** Soll, sondern der Beleg, dass die Testzahlen den gemeldeten
    Fall treffen. Wäre diese Probe grün und die nächste auch, ohne dass sich
    etwas unterscheidet, prüfte die nächste nichts.
    """
    az = arbeitszahl(WAERME_KWH, STROM_BEIDE_KWH)
    assert az.wert is not None
    assert round(az.wert, 1) == 0.7


def test_bauartmischung_sperrt_die_zahl_mit_grund():
    """Wärmepumpe + Split-Klimaanlage ⇒ keine Kennzahl, sondern der Grund."""
    az = arbeitszahl(
        WAERME_KWH, STROM_BEIDE_KWH,
        abgrenzung_verletzt=abgrenzungs_grund(bauarten_gemischt=True),
    )
    assert az.wert is None, "Ein Quotient über zwei Bauarten ist keine Kennzahl."
    assert az.grund == GRUND_BAUARTEN_GEMISCHT
    assert az.grund, "S3: nicht „—“, sondern der Grund."


def test_geraet_ohne_waermemeldung_sperrt_ebenfalls():
    """Gleiche Bauart, aber eines der Geräte meldet keine Wärme (§4.2 Fall 1)."""
    az = arbeitszahl(
        WAERME_KWH, STROM_BEIDE_KWH,
        abgrenzung_verletzt=abgrenzungs_grund(geraete_ohne_waerme=True),
    )
    assert az.wert is None
    assert az.grund == GRUND_GERAETE_OHNE_WAERME


def test_das_geraet_allein_hat_sehr_wohl_eine_zahl():
    """Die Wärmepumpe für sich genommen: 2,2 — genau das, was E1 zusagt.

    **Mengen bleiben summiert, Kennzahlen werden getrennt.** Der Melder verliert
    seine Zahl nicht, er bekommt sie je Gerät — im Komponenten-Hub, der die
    Arbeitszahl je Investition bildet.
    """
    az = arbeitszahl(WAERME_KWH, STROM_NUR_WP_KWH)
    assert az.wert is not None
    assert round(az.wert, 1) == 2.2
    assert az.grund is None


def test_die_gemischte_zahl_faellt_mit_fremdem_betrieb_ohne_dass_sich_die_wp_aendert():
    """Der Kern: 0,7 misst nicht Effizienz, sondern Fremdbetrieb.

    Dieselbe Wärmepumpe (210 kWh Wärme aus 97 kWh Strom, Arbeitszahl 2,2), nur
    läuft die Klimaanlage einmal wenig und einmal viel. **An der Wärmepumpe
    ändert sich nichts**, die gemeinsame Zahl halbiert sich trotzdem — deshalb
    ist sie keine schlechtere Kennzahl, sondern eine andere Größe.
    """
    wenig = arbeitszahl(WAERME_KWH, STROM_NUR_WP_KWH + 50).wert
    viel = arbeitszahl(WAERME_KWH, STROM_NUR_WP_KWH + 400).wert
    allein = arbeitszahl(WAERME_KWH, STROM_NUR_WP_KWH).wert

    assert allein is not None and wenig is not None and viel is not None
    assert round(allein, 1) == 2.2
    assert wenig > viel, "Mehr Fremdstrom ⇒ kleinere Zahl, bei gleicher WP."
    assert viel < 1.0 < wenig, (
        "Die gemeinsame Zahl wandert allein durch den Fremdbetrieb über die "
        "Schwelle 1 — genau die Zahl, die der Melder als unmöglich erkannt hat."
    )


def test_reihenfolge_der_gruende_konkreter_schlaegt_allgemeiner():
    """Bauart vor „Gerät ohne Wärme“ — beide treffen zu, einer hilft weiter.

    Eine Split-Klimaanlage ist genau eines der Geräte, die keine Wärme melden.
    Der allgemeinere Satz riete zu einer Zuordnung, die es dort **bauartbedingt
    nie geben kann** (kein Wasserkreis, deshalb kein Wärmemengenzähler); der
    konkretere ist die bessere Auskunft.
    """
    grund = abgrenzungs_grund(bauarten_gemischt=True, geraete_ohne_waerme=True)
    assert grund == GRUND_BAUARTEN_GEMISCHT


@pytest.mark.parametrize("funktionsfremd_kwh, erwartet", [(0.0, 0.66), (100.0, 0.97)])
def test_funktionsfremder_strom_gehoert_nicht_in_den_nenner(funktionsfremd_kwh, erwartet):
    """W-14/E4 — Kühlen, Lüften und Entfeuchten drücken die Zahl sonst.

    Der HA-Sensor „COP Durchschnitt“ und das Jahresbericht-PDF haben bis zum
    2026-09-02 **ohne** diesen Abzug gerechnet: eine kühlende Anlage stand
    systematisch schlechter da als eine, die es nicht tut.
    """
    az = arbeitszahl(
        WAERME_KWH, STROM_BEIDE_KWH,
        strom_funktionsfremd_kwh=funktionsfremd_kwh,
    )
    assert az.wert is not None
    assert round(az.wert, 2) == erwartet
