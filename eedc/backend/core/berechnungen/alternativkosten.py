"""Alternativkosten-Ersparnis: historische Komponenten-Ersparnis vs. Altanlage.

Single Source of Truth für die **historische** (bisherige) Alternativkosten-
Ersparnis, die im HA-Export und in der Aussichten-Finanzprognose in die
Jahresersparnis / ROI / Amortisation einfließt:

- **Wärmepumpe vs. Gas/Öl** — pro erfasstem Monat die hypothetischen
  Brennstoffkosten der Altanlage minus die tatsächlichen WP-Netz-Stromkosten,
  plus anteilige fixe Zusatzkosten (Schornsteinfeger, Wartung, Grundpreis).
- **Balkonkraftwerk** — der BKW-Eigenverbrauch zum Netzbezugspreis bewertet.

Die Formeln waren an mehreren Read-Sites dupliziert (`ha_export.py`,
`aussichten.py`) und sind eine bekannte Drift-Quelle: bei Multi-Komponenten-
Haushalten mit unterschiedlichen Parametern (zwei WPs Gas+Öl, zwei E-Autos)
rechnete der last-write-wins-Pfad falsch. Dieser Layer rechnet **per
Komponente und per Monat** und ist DB-/Service-frei (ADR-001): der Caller
übergibt bereits geladene und auf Laufzeit/Aktivität gefilterte IMD-Dicts
(``historische_inv_daten``) sowie den aufgelösten Monats-Gaspreis.

Der **E-Auto-Pfad** liegt bewusst NICHT hier: er braucht die km-anteilige
Wallbox-Pool-Attribution (`services.eauto_wirtschaftlichkeit`), die core nicht
importieren darf (Layer-Regel). Er wird im Caller resolved.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.field_definitions import get_wp_strom_kwh
from backend.core.investition_parameter import (
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    WP_PV_ANTEIL_DEFAULT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
    WP_WIRKUNGSGRAD_OEL_DEFAULT,
)


def gas_kosten_altanlage(
    waerme_kwh: float, wirkungsgrad: float, gaspreis_cent: float,
) -> float:
    """Hypothetische Brennstoffkosten der fossilen Altanlage in €.

    Single Source of der drift-anfälligen Formel ``(Wärme / Wirkungsgrad) ×
    Gaspreis / 100`` — die Energiekosten, die die ersetzte Gas-/Öl-Heizung für
    eine gegebene thermische Wärmemenge verursacht hätte. Genutzt von der
    per-Monat-Aggregat-Ersparnis (hier), der per-WP-Service-Ersparnis
    (`services.wp_wirtschaftlichkeit`) sowie den HA-Export- und Prognose-Sichten.
    """
    return (waerme_kwh / wirkungsgrad) * gaspreis_cent / 100


def _wp_aggregate(parameter: Optional[dict]) -> dict:
    """Per-WP-Kennwerte (alter Preis, Wirkungsgrad, fixe Zusatzkosten/Jahr) aus
    den Investitions-Parametern — vereinheitlicht über die Defaults.

    Per-WP statt last-write-wins: bei zwei WPs mit verschiedenen Energieträgern
    (Gas + Öl) wurde sonst der Wirkungsgrad der letzten auf beide angewandt.
    """
    params = parameter or {}
    return {
        "alter_preis_cent": (
            params.get(
                PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"],
                PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"],
            ) or PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"]
        ),
        "alter_wirkungsgrad": (
            WP_WIRKUNGSGRAD_OEL_DEFAULT
            if params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"]) == "oel"
            else WP_WIRKUNGSGRAD_GAS_DEFAULT
        ),
        "zusatzkosten_jahr": params.get(
            PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0,
        ) or 0,
    }


def berechne_wp_alternativkosten_ersparnis(
    waermepumpen: Iterable,
    historische_inv_daten: dict[tuple[int, int, int], dict],
    gaspreis_by_periode: dict[tuple[int, int], Optional[float]],
    netzbezug_preis_cent: float,
) -> float:
    """Bisherige WP-Ersparnis vs. Gas/Öl über alle erfassten Monate.

    Args:
        waermepumpen: Investitionen vom Typ ``waermepumpe`` (gelesen: ``.id``,
            ``.parameter``).
        historische_inv_daten: bereits auf Aktivität/Laufzeit gefilterte IMD,
            ``{(inv_id, jahr, monat): verbrauch_daten}``.
        gaspreis_by_periode: aufgelöster Monats-Gaspreis (ct/kWh) je
            ``(jahr, monat)``; ``None``/fehlend → WP-Parameter-Default.
        netzbezug_preis_cent: Netzbezugs-Arbeitspreis (ct/kWh).

    Returns:
        Σ über alle WPs/Monate ``(gas_kosten − wp_stromkosten_netz)`` plus die
        anteiligen fixen Zusatzkosten ``Σ zusatzkosten_jahr × erfasste_Monate / 12``.
        Der PV-Anteil am WP-Strom (``WP_PV_ANTEIL_DEFAULT``) wird nicht zum
        Netztarif belastet.
    """
    ersparnis = 0.0
    zusatzkosten_jahr_gesamt = 0.0
    monate_gezaehlt: set[tuple[int, int]] = set()
    for wp in waermepumpen:
        wp_agg = _wp_aggregate(wp.parameter)
        zusatzkosten_jahr_gesamt += wp_agg["zusatzkosten_jahr"]
        for (inv_id, jahr, monat), daten in historische_inv_daten.items():
            if inv_id != wp.id:
                continue
            thermisch = (daten.get("heizenergie_kwh", 0) or 0) + (
                daten.get("warmwasser_kwh", 0) or 0
            )
            strom = get_wp_strom_kwh(daten, wp.parameter)
            g = gaspreis_by_periode.get((jahr, monat))
            monats_gaspreis = g if g is not None else wp_agg["alter_preis_cent"]
            gas_kosten = gas_kosten_altanlage(
                thermisch, wp_agg["alter_wirkungsgrad"], monats_gaspreis
            )
            wp_stromkosten_netz = (
                strom * (1.0 - WP_PV_ANTEIL_DEFAULT) * netzbezug_preis_cent / 100
            )
            ersparnis += gas_kosten - wp_stromkosten_netz
            monate_gezaehlt.add((jahr, monat))
    ersparnis += zusatzkosten_jahr_gesamt * len(monate_gezaehlt) / 12
    return ersparnis


def berechne_bkw_alternativkosten_ersparnis(
    balkonkraftwerke: Iterable,
    historische_inv_daten: dict[tuple[int, int, int], dict],
    netzbezug_preis_cent: float,
) -> float:
    """Bisherige BKW-Ersparnis: Eigenverbrauch zum Netzbezugspreis bewertet.

    Args:
        balkonkraftwerke: Investitionen vom Typ ``balkonkraftwerk`` (gelesen: ``.id``).
        historische_inv_daten: gefilterte IMD ``{(inv_id, jahr, monat): daten}``.
        netzbezug_preis_cent: Netzbezugs-Arbeitspreis (ct/kWh).

    Returns:
        Σ über alle BKW/Monate ``eigenverbrauch_kwh × netzbezug_preis_cent / 100``.
    """
    ersparnis = 0.0
    for bkw in balkonkraftwerke:
        for (inv_id, _jahr, _monat), daten in historische_inv_daten.items():
            if inv_id == bkw.id:
                bkw_ev = daten.get("eigenverbrauch_kwh", 0) or 0
                ersparnis += bkw_ev * netzbezug_preis_cent / 100
    return ersparnis
