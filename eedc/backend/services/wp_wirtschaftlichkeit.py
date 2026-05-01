"""WP-Wirtschaftlichkeit — Single Source of Truth für Ersparnis-Berechnung.

Anlass: 6-Sprachen-Drift bei der WP-Ersparnis-Anzeige (siehe Issue #178 +
`docs/drafts/INVENTUR-DRIFT-AUDIT.md`, Domäne A1).

Vorher: vier Render-Stellen (Cockpit-Monatsbericht, Cockpit-Übersicht,
Cockpit-WP-Detail, Auswertungen-Komponenten) rechneten unterschiedliche
Werte für dieselbe Anlage — bis zu 54€ Drift bei detLANs WP (#178).

Nachher: alle Render-Stellen rufen `berechne_wp_ersparnis(...)` auf und
bekommen denselben Wert.

Formel:
    alte_heizung_kosten = waerme / wirkungsgrad × gaspreis_cent / 100
    wp_kosten = strom × wp_strompreis_cent / 100
    ersparnis = alte_heizung_kosten − wp_kosten

Wirkungsgrad: 0.90 für Gas, 0.85 für Öl (kanon. in WP_WIRKUNGSGRAD_*_DEFAULT).
Gaspreis: monatlicher Override (Monatsdaten.gaspreis_cent_kwh) > params.alter_preis_cent_kwh > Default 12 ct.
WP-Strompreis: separater WP-Tarif > allgemeiner Tarif > Default 30 ct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.investition_parameter import (
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    GASPREIS_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
)


@dataclass
class WPErsparnisErgebnis:
    """Ergebnis der WP-Ersparnis-Berechnung."""
    ersparnis_euro: float
    alte_heizung_kosten_euro: float
    wp_kosten_euro: float
    # Diagnostik: welcher Gaspreis wurde tatsächlich verwendet?
    verwendeter_gaspreis_cent: float
    verwendeter_wirkungsgrad: float


def _wp_alter_wirkungsgrad(wp_parameter: Optional[dict]) -> float:
    """0.85 für Öl, 0.90 sonst (Gas/Default)."""
    if wp_parameter is None:
        return WP_WIRKUNGSGRAD_GAS_DEFAULT
    if wp_parameter.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]) == "oel":
        return WP_WIRKUNGSGRAD_OEL_DEFAULT
    return WP_WIRKUNGSGRAD_GAS_DEFAULT


def _wp_alter_preis_cent(wp_parameter: Optional[dict]) -> float:
    """Liest Gaspreis-Default aus WP-Parametern, sonst kanon. Default."""
    if wp_parameter is None:
        return GASPREIS_DEFAULT_CENT
    return wp_parameter.get(
        PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
        PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
    ) or GASPREIS_DEFAULT_CENT


def berechne_wp_ersparnis(
    *,
    wp_waerme_kwh: float,
    wp_strom_kwh: float,
    wp_strompreis_cent: float,
    wp_parameter: Optional[dict] = None,
    monats_gaspreis_cent: Optional[float] = None,
) -> WPErsparnisErgebnis:
    """Berechnet WP-Ersparnis vs. fossile Heizung.

    Args:
        wp_waerme_kwh: Erzeugte Wärme (Heizung + Warmwasser) in kWh
        wp_strom_kwh: WP-Stromverbrauch in kWh
        wp_strompreis_cent: WP-Strompreis in ct/kWh (separater WP-Tarif oder
            allgemeiner Tarif als Fallback)
        wp_parameter: `Investition.parameter`-Dict für die Wärmepumpe.
            Wird genutzt für Wirkungsgrad-Wahl (Gas vs. Öl) und
            Default-Gaspreis (`alter_preis_cent_kwh`).
        monats_gaspreis_cent: Optionaler monatlicher Gaspreis-Override aus
            `Monatsdaten.gaspreis_cent_kwh`. Hat Vorrang vor dem Default
            aus den WP-Parametern.

    Returns:
        WPErsparnisErgebnis mit Ersparnis, Komponenten und Diagnostik.
    """
    if wp_waerme_kwh <= 0:
        return WPErsparnisErgebnis(0.0, 0.0, 0.0, 0.0, WP_WIRKUNGSGRAD_GAS_DEFAULT)

    wirkungsgrad = _wp_alter_wirkungsgrad(wp_parameter)

    if monats_gaspreis_cent is not None:
        gaspreis_cent = monats_gaspreis_cent
    else:
        gaspreis_cent = _wp_alter_preis_cent(wp_parameter)

    alte_heizung_kosten = (wp_waerme_kwh / wirkungsgrad) * gaspreis_cent / 100
    wp_kosten = wp_strom_kwh * wp_strompreis_cent / 100
    ersparnis = alte_heizung_kosten - wp_kosten

    return WPErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        alte_heizung_kosten_euro=alte_heizung_kosten,
        wp_kosten_euro=wp_kosten,
        verwendeter_gaspreis_cent=gaspreis_cent,
        verwendeter_wirkungsgrad=wirkungsgrad,
    )
