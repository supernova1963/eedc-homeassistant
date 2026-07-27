"""η der ersetzten Altanlage — ein Resolver, eine Antwort (ADR-001).

Zwei getrennte Befunde, die dieselbe Wurzel haben:

**A — der Parameter-Pfad ließ η ganz weg.**
`berechne_waermepumpe_einsparung` (Grundlage der ROI-Seite) rechnete
``alte_kosten = wärmebedarf × preis`` und ``co2_alt = wärmebedarf × f``, während
alle gemessenen Pfade (Aussichten, HA-Export, WP-Dashboard) über
`gas_kosten_altanlage` gehen und ``wärme / η`` ansetzen. Damit nannten ROI-Seite
und Aussichten für dieselbe WP verschiedene Ersparnisse.

Dass der Eingang **abgegebene Wärme** ist (und nicht schon Brennstoff), steht in
derselben Funktion: ``wp_strom_kwh = gesamt_waermebedarf / jaz`` — die JAZ ist als
Wärme/Strom definiert. Das Formular-Label bestätigt es („Heizwärmebedarf
(kWh/Jahr) — aus Energieausweis").

**B — die η-Wahl kannte „Strom" nicht.**
Vier Stellen entschieden lokal ``OEL if traeger == "oel" else GAS``. Die im
Formular wählbare Strom-Direktheizung („Strom (Direktheizung)") bekam damit den
Gas-Kessel-Wirkungsgrad 0,90 — rund 11 % zu hohe Altkosten und damit zu hohe
WP-Ersparnis. Eine Widerstandsheizung heizt verlustfrei, η = 1,0.

B ist die Voraussetzung für A: Fixt man A ohne B, bekäme eine Stromheizung
erstmals ein η ≠ 1 verpasst — vorher war die η-freie Formel für sie zufällig
richtig.
"""

import ast
from pathlib import Path

import pytest

from backend.core.berechnungen import alter_wirkungsgrad, gas_kosten_altanlage
from backend.core.calculations import berechne_waermepumpe_einsparung
from backend.core.wirtschaftlichkeit_defaults import (
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
    WP_WIRKUNGSGRAD_STROM_DEFAULT,
)

BACKEND = Path(__file__).resolve().parents[1]


# ============================================================================
# A — Resolver-Kontrakt
# ============================================================================


@pytest.mark.parametrize(
    "traeger,erwartet",
    [
        ("gas", WP_WIRKUNGSGRAD_GAS_DEFAULT),
        ("oel", WP_WIRKUNGSGRAD_OEL_DEFAULT),
        ("strom", WP_WIRKUNGSGRAD_STROM_DEFAULT),
        (None, WP_WIRKUNGSGRAD_GAS_DEFAULT),
        ("unbekannt", WP_WIRKUNGSGRAD_GAS_DEFAULT),
    ],
)
def test_alter_wirkungsgrad_je_energietraeger(traeger, erwartet):
    assert alter_wirkungsgrad(traeger) == erwartet


def test_strom_direktheizung_ist_verlustfrei():
    """η = 1,0 — sonst rechnet eedc einer Stromheizung Kesselverluste an,
    die es physikalisch nicht gibt (Befund B)."""
    assert alter_wirkungsgrad("strom") == 1.0


# ============================================================================
# B — der Parameter-Pfad rechnet wie der gemessene
# ============================================================================


def _einsparung(traeger: str, **kwargs):
    basis = dict(
        waermebedarf_kwh=15000.0,
        jaz=3.5,
        effizienz_modus="gesamt_jaz",
        strompreis_cent=30.0,
        pv_anteil_prozent=30.0,
        alter_energietraeger=traeger,
        alter_preis_cent_kwh=12.0,
    )
    basis.update(kwargs)
    return berechne_waermepumpe_einsparung(**basis)


@pytest.mark.parametrize("traeger", ["gas", "oel", "strom"])
def test_altkosten_identisch_zum_layer_sot(traeger):
    """Kernaussage: die Altkosten des Parameter-Pfads sind exakt die des
    gemessenen Pfads. Vorher fehlte hier die η-Rückrechnung."""
    r = _einsparung(traeger)
    erwartet = gas_kosten_altanlage(15000.0, alter_wirkungsgrad(traeger), 12.0)
    assert r.alte_heizung_kosten_euro == pytest.approx(erwartet, abs=0.01)


def test_gas_altkosten_enthalten_kesselverlust():
    """15.000 kWh Wärme @ 12 ct und η=0,90 → 2.000 €, nicht 1.800 €."""
    r = _einsparung("gas")
    assert r.alte_heizung_kosten_euro == pytest.approx(2000.0, abs=0.01)


def test_stromheizung_unveraendert_gegenueber_frueher():
    """Regressions-Anker für Befund B: bei η=1,0 ist `wärme / η × preis`
    identisch zur früheren η-freien Formel — die Zahl darf sich NICHT ändern."""
    r = _einsparung("strom")
    assert r.alte_heizung_kosten_euro == pytest.approx(15000.0 * 12.0 / 100, abs=0.01)


def test_oel_teurer_als_gas():
    assert (
        _einsparung("oel").alte_heizung_kosten_euro
        > _einsparung("gas").alte_heizung_kosten_euro
    )


def test_co2_alt_nutzt_denselben_wirkungsgrad_wie_die_kosten():
    """CO₂ und € dürfen nicht auseinanderlaufen: verbrannt wird der Brennstoff
    (`wärme / η`), nicht die Nutzwärme. Prüfung über das Verhältnis zweier
    Energieträger mit gleichem CO₂-Faktor-Verhältnis wäre indirekt — daher
    direkt gegen die erwartete Größenordnung des Kesselverlusts."""
    ohne_zusatz = _einsparung("gas", alternativ_zusatzkosten_jahr=0.0)
    # WP-Strom = 15000/3,5 = 4285,7 kWh, davon 70 % Netz.
    wp_strom_netz = 15000.0 / 3.5 * 0.7
    from backend.core.calculations import (
        CO2_FAKTOR_GAS_KG_KWH,
        CO2_FAKTOR_STROM_KG_KWH,
    )

    erwartet = (
        15000.0 / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH
        - wp_strom_netz * CO2_FAKTOR_STROM_KG_KWH
    )
    assert ohne_zusatz.co2_einsparung_kg == pytest.approx(erwartet, abs=0.1)


def test_zusatzkosten_gehen_ungeteilt_ein():
    """Fixe Jahreskosten der Altanlage (Schornsteinfeger, Grundpreis) sind
    keine Energie — sie dürfen NICHT durch η geteilt werden."""
    ohne = _einsparung("gas", alternativ_zusatzkosten_jahr=0.0)
    mit = _einsparung("gas", alternativ_zusatzkosten_jahr=200.0)
    assert mit.alte_heizung_kosten_euro - ohne.alte_heizung_kosten_euro == pytest.approx(
        200.0, abs=0.01
    )


# ============================================================================
# C — Wächter: die η-Wahl bleibt an einer Stelle
# ============================================================================

# Erlaubt: die Konstanten-Heimat und der Resolver selbst.
_ETA_ERLAUBT = {
    "core/wirtschaftlichkeit_defaults.py",
    "core/berechnungen/alternativkosten.py",
}


def _py_dateien():
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", "venv/", "alembic/")) or "__pycache__" in rel:
            continue
        yield path, rel


def test_oel_und_strom_konstante_nur_im_resolver():
    """**Wächter** (baumweit): die Entscheidung „welches η gilt für diesen
    Energieträger" gehört ausschließlich in `alter_wirkungsgrad`.

    Sie stand vorher 4× im Baum (`_wp_aggregate`, `wp_wirtschaftlichkeit`,
    `aussichten`, `ha_export`) — und alle vier kannten „strom" nicht.

    Deckung, offen benannt: der Wächter greift über die **Konstanten**
    `WP_WIRKUNGSGRAD_OEL/STROM_DEFAULT`. Er fängt damit jede Trägerwahl, die
    die kanonischen Werte benutzt — ein- wie mehrzeilig, im Gegensatz zu einer
    zeilenweisen Regex auf `== "oel"`, die drei der vier Altfälle durchgelassen
    hätte (die nannten `WIRKUNGSGRAD` erst in der Folgezeile). Eine Kopie, die
    **0.85 hartkodiert** statt die Konstante zu importieren, fängt er nicht;
    das ist die bekannte Restlücke. Der Gas-Default bleibt referenzierbar — wer
    nur ihn nennt, trifft keine Trägerwahl (Nullfall-Diagnostik in
    `wp_wirtschaftlichkeit`, gemessener Gas-Pfad in `co2_wp_ersparnis_kg`).
    """
    verstoesse: list[str] = []
    for path, rel in _py_dateien():
        if rel in _ETA_ERLAUBT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "WP_WIRKUNGSGRAD_OEL_DEFAULT" in line or "WP_WIRKUNGSGRAD_STROM_DEFAULT" in line:
                verstoesse.append(f"  {rel}:{line_no}  {line.strip()}")
    assert not verstoesse, (
        "Öl-/Strom-Wirkungsgrad außerhalb des Resolvers referenziert "
        "(ADR-001):\n" + "\n".join(verstoesse)
    )


def test_keine_eta_freie_altkosten_formel():
    """`wärmebedarf × preis / 100` ohne η ist die Formel, die Befund A war.

    Sie ist per AST schwer zu fassen; hier reicht die Kontrolle, dass
    `berechne_waermepumpe_einsparung` den Layer-Helper überhaupt aufruft —
    ein Rückbau auf die Inline-Multiplikation fällt damit auf.
    """
    quelle = (BACKEND / "core" / "calculations.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    funktion = next(
        n for n in ast.walk(baum)
        if isinstance(n, ast.FunctionDef) and n.name == "berechne_waermepumpe_einsparung"
    )
    aufrufe = {
        n.func.id for n in ast.walk(funktion)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "gas_kosten_altanlage" in aufrufe, (
        "berechne_waermepumpe_einsparung muss die Altkosten über den Layer-SoT "
        "`gas_kosten_altanlage` bilden (ADR-001) — sonst driftet die ROI-Seite "
        "wieder gegen Aussichten/HA-Export."
    )
    assert "alter_wirkungsgrad" in aufrufe, (
        "…und das η über `alter_wirkungsgrad`, damit der Strom-Fall stimmt."
    )
