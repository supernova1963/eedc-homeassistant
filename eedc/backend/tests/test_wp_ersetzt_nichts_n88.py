"""N-88/F2b: „nichts ersetzt" schlägt in JEDEM Alternativkosten-Pfad durch.

`alter_energietraeger` kannte bis 2026-08-16 nur `gas` / `oel` / `strom`, Default
`gas` — es gab **keine** Möglichkeit zu sagen, dass gar keine Heizung ersetzt
wurde. Damit bekam jede Wärmepumpe im **Neubau** eine Gaskessel-Ersparnis
angerechnet, die es nie gab. Der bisherige Ausweg war ein **Typ**-Sonderweg
(`wp_art == luft_luft` ⇒ gar nicht bewerten) — und der beruhte seinerseits auf
einer falschen Annahme: Eine Luft-Luft-Wärmepumpe **kann** sehr wohl eine
Gasheizung ersetzen (Gernot, 16.08.).

Diese Datei prüft die **Rechen**-Ebene; die Anzeige-Ebene der ROI-Route liegt in
`test_roi_klimaanlage_nicht_bewertet.py`. Getrennt, weil die ROI-Zeile eine
**Prognose aus gepflegten Parametern** ist (Bedarf × JAZ/COP), während Cockpit,
Aussichten, WP-Dashboard, Jahresbericht-PDF und der HA-Sensor mit der
**gemessenen** Wärme rechnen. Zwei verschiedene Größen — und genau deshalb hat
ein Filter an einer der beiden Stellen die andere nie mit erledigt.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    ERSETZT_NICHTS,
    ersetzt_keine_heizung,
)
from backend.core.berechnungen.alternativkosten import (
    berechne_wp_alternativkosten_ersparnis,
)
from backend.core.calculations import (
    berechne_waermepumpe_einsparung,
    co2_wp_ersparnis_kg,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis


GAS = {"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12}
NICHTS = {"alter_energietraeger": ERSETZT_NICHTS, "alter_preis_cent_kwh": 12}


class _WP:
    """Minimal-Stub — die Layer-Funktionen lesen nur `.id` und `.parameter`."""

    def __init__(self, wp_id: int, parameter: dict):
        self.id = wp_id
        self.parameter = parameter


# ============================================================================
# Das Prädikat selbst
# ============================================================================


def test_praedikat_trennt_nichts_von_ungepflegt():
    """Ein ungesetztes Feld heißt NICHT „nichts".

    Bestandsgeräte tragen den alten Default `gas`; eine fehlende Angabe darf
    eine bisher ausgewiesene Ersparnis nicht stillschweigend abschalten. Ohne
    diesen Test wäre der Wächter nicht von einem „schaltet immer ab" zu
    unterscheiden.
    """
    assert ersetzt_keine_heizung(ERSETZT_NICHTS) is True
    assert ersetzt_keine_heizung("gas") is False
    assert ersetzt_keine_heizung("oel") is False
    assert ersetzt_keine_heizung(None) is False


# ⛔ Hier stand bis 2026-08-29 `test_aggregat_praedikat_ist_streng`: „Anlagenweit
# gilt ‚alle oder keine' — eine gemischte Anlage rechnet weiter." Er hat das
# Prädikat `alle_ersetzen_nichts` geprüft, und beide sind mit N-256 ENTFALLEN,
# nicht zurückgedreht: Die Regel „alle oder keine" war die bewusste Näherung von
# damals (ihr eigener Docstring nannte die saubere Trennung „ein eigenes Paket").
# Dieses Paket ist gebaut — die anlagenweiten Sichten rechnen jetzt mit den
# Teilmengen `WpFakten.waerme_mit_ersatz_kwh`/`strom_mit_ersatz_kwh`, und ein
# Prädikat, das die gemischte Anlage durchwinkt, hat keinen Gegenstand mehr.
# Was an seine Stelle tritt: `test_wp_ersparnis_grundmenge_n279.py` (Kosten) und
# `test_co2_grundmenge_mit_ersatz_n256.py` (CO₂) — beide messen die WIRKUNG statt
# des Prädikats.


# ============================================================================
# Gemessener Pfad — Cockpit, Cockpit-Monat, Komponenten-Zeitreihe, WP-Dashboard
# ============================================================================


def test_gemessene_ersparnis_entfaellt_ohne_ersetzte_heizung():
    """`berechne_wp_ersparnis` ist der Pfad hinter fünf Anzeige-Stellen."""
    mit = berechne_wp_ersparnis(
        wp_waerme_kwh=2400.0, wp_strom_kwh=800.0,
        wp_strompreis_cent=28.0, wp_parameter=GAS,
    )
    ohne = berechne_wp_ersparnis(
        wp_waerme_kwh=2400.0, wp_strom_kwh=800.0,
        wp_strompreis_cent=28.0, wp_parameter=NICHTS,
    )

    assert mit.ersparnis_euro > 0          # Negativprobe: der Pfad rechnet sonst
    assert ohne.ersparnis_euro == 0
    # Auch die Kosten der Altanlage sind 0 — es gibt keine.
    assert ohne.alte_heizung_kosten_euro == 0


def test_gemessene_co2_ersparnis_entfaellt_ohne_ersetzte_heizung():
    """`co2_wp_ersparnis_kg` ist die einzige erlaubte Konstruktions-Stelle (DI-1).

    Der Filter sitzt deshalb HIER und nicht in den zwei Aufrufern (WP-Dashboard,
    Jahresbericht-PDF) — genau die Duplizierung hat DI-1 abgeschafft.
    """
    assert co2_wp_ersparnis_kg(2400.0, 800.0, "gas") > 0
    assert co2_wp_ersparnis_kg(2400.0, 800.0, ERSETZT_NICHTS) == 0.0
    # Alt-Aufrufer ohne den neuen Parameter verhalten sich unverändert.
    assert co2_wp_ersparnis_kg(2400.0, 800.0) == co2_wp_ersparnis_kg(2400.0, 800.0, "gas")


# ============================================================================
# Historien-Pfad — HA-Export und Aussichten-Historie
# ============================================================================


def _historie(inv_id: int) -> dict:
    return {(inv_id, 2025, 1): {"heizenergie_kwh": 1200, "stromverbrauch_kwh": 400}}


def test_historische_ersparnis_ueberspringt_die_wp_samt_zusatzkosten():
    """Der `continue` steht VOR den Zusatzkosten — sonst zahlte der Anwender den
    Schornsteinfeger einer Anlage, die es nie gab."""
    gas_mit_zusatz = {**GAS, "alternativ_zusatzkosten_jahr": 240}
    nichts_mit_zusatz = {**NICHTS, "alternativ_zusatzkosten_jahr": 240}

    mit = berechne_wp_alternativkosten_ersparnis(
        [_WP(1, gas_mit_zusatz)], _historie(1), {(2025, 1): 12.0}, {(2025, 1): 28.0}, 28.0,
    )
    ohne = berechne_wp_alternativkosten_ersparnis(
        [_WP(1, nichts_mit_zusatz)], _historie(1), {(2025, 1): 12.0}, {(2025, 1): 28.0}, 28.0,
    )

    assert mit > 0
    assert ohne == 0.0


def test_gemischte_anlage_verliert_die_andere_wp_nicht():
    """Zwei WPs, eine ersetzt Gas, eine nichts — die erste rechnet unverändert.

    Der per-Gerät-Pfad war hier schon immer exakt; seit N-256 gilt dasselbe für
    die anlagenweiten Aggregate (Teilmengen in `WpFakten`). Ohne diesen Test wäre
    der `continue` nicht von einem „bricht die Schleife ab" zu unterscheiden.
    """
    nur_gas = berechne_wp_alternativkosten_ersparnis(
        [_WP(1, GAS)], _historie(1), {(2025, 1): 12.0}, {(2025, 1): 28.0}, 28.0,
    )
    gemischt = berechne_wp_alternativkosten_ersparnis(
        [_WP(1, GAS), _WP(2, NICHTS)],
        {**_historie(1), **_historie(2)},
        {(2025, 1): 12.0}, {(2025, 1): 28.0}, 28.0,
    )

    assert gemischt == pytest.approx(nur_gas)


# ============================================================================
# Prognose-Pfad — die ROI-Zeile
# ============================================================================


def test_prognose_ohne_ersetzte_heizung_hat_keine_altanlage():
    """Kosten UND CO₂ der Altanlage entfallen — nicht nur die Kosten.

    Die Jahres-Einsparung wird dadurch negativ: Die Anlage kostet Strom und
    spart nichts ein. Das ist bei einem Neubau ohne Vorgängerheizung die wahre
    Aussage, und die ROI-Route zeigt sie gar nicht erst an („nicht bewertet").
    """
    ohne = berechne_waermepumpe_einsparung(
        waermebedarf_kwh=9000, jaz=3.5, effizienz_modus="gesamt_jaz",
        strompreis_cent=28.0, pv_anteil_prozent=30,
        alter_energietraeger=ERSETZT_NICHTS, alter_preis_cent_kwh=12,
        alternativ_zusatzkosten_jahr=240,
    )
    mit = berechne_waermepumpe_einsparung(
        waermebedarf_kwh=9000, jaz=3.5, effizienz_modus="gesamt_jaz",
        strompreis_cent=28.0, pv_anteil_prozent=30,
        alter_energietraeger="gas", alter_preis_cent_kwh=12,
        alternativ_zusatzkosten_jahr=240,
    )

    assert ohne.alte_heizung_kosten_euro == 0
    assert ohne.co2_einsparung_kg < 0     # nur noch der eigene Stromverbrauch
    assert ohne.jahres_einsparung_euro < 0
    assert mit.alte_heizung_kosten_euro > 0
    assert mit.co2_einsparung_kg > 0
