"""E-Auto/Wallbox-Wirtschaftlichkeit — Single Source of Truth.

Anlass: Drift-Audit Domäne A2 (`docs/drafts/INVENTUR-DRIFT-AUDIT.md`).
Cockpit/Monatsbericht hatten 7 L/100km und 1,80 €/L hartcodiert, ignorierten
User-gepflegte Werte — User sahen 7-9% falsche Ersparnis vs. Aussichten/PDF.

Vorher: vier Code-Pfade, zwei verschiedene Defaults (7 vs. 7,5 L; 1,80 vs.
1,65 €/L). Nachher: ein Helper mit kanonischen Defaults aus
`PARAM_E_AUTO_DEFAULTS`.

Formel:
    benzin_kosten = (km / 100) × verbrauch_l_100km × benzinpreis_euro
    strom_kosten = ladung_netz_kwh × wallbox_strompreis_cent / 100 + ladung_extern_euro
    ersparnis = benzin_kosten - strom_kosten

Verbrauch: aus `params.vergleich_verbrauch_l_100km`, Default 7,5 L/100km.
Benzinpreis: monatlicher Override (Monatsdaten.kraftstoffpreis_euro) >
             params.benzinpreis_euro > Default 1,65 €/L.
Strompreis: separater Wallbox-Tarif > allgemeiner Tarif.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import (
    BENZIN_PREIS_DEFAULT_EURO_L,
    BENZIN_VERBRAUCH_DEFAULT_L_100KM,
)


@dataclass
class EAutoErsparnisErgebnis:
    """Ergebnis der E-Auto-Ersparnis-Berechnung vs. Verbrenner."""
    ersparnis_euro: float
    benzin_kosten_euro: float
    strom_kosten_euro: float
    # Diagnostik: welche Werte wurden tatsächlich verwendet?
    verwendeter_verbrauch_l_100km: float
    verwendeter_benzinpreis_euro: float


def _vergleich_verbrauch(eauto_parameter: Optional[dict]) -> float:
    """Liest Benzin-Vergleichsverbrauch aus params, sonst kanon. Default 7,5."""
    if eauto_parameter is None:
        return BENZIN_VERBRAUCH_DEFAULT_L_100KM
    return eauto_parameter.get(
        PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"],
        PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"],
    ) or BENZIN_VERBRAUCH_DEFAULT_L_100KM


def _benzinpreis_default(eauto_parameter: Optional[dict]) -> float:
    """Liest Benzinpreis-Default aus params, sonst kanon. 1,65 €/L."""
    if eauto_parameter is None:
        return BENZIN_PREIS_DEFAULT_EURO_L
    return eauto_parameter.get(
        PARAM_E_AUTO["BENZINPREIS_EURO"],
        PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"],
    ) or BENZIN_PREIS_DEFAULT_EURO_L


def berechne_eauto_ersparnis(
    *,
    km_gefahren: float,
    ladung_netz_kwh: float,
    ladung_extern_euro: float,
    wallbox_strompreis_cent: float,
    eauto_parameter: Optional[dict] = None,
    monats_benzinpreis_euro: Optional[float] = None,
) -> EAutoErsparnisErgebnis:
    """Berechnet E-Auto-Ersparnis vs. Verbrenner.

    Args:
        km_gefahren: Kilometer im Zeitraum
        ladung_netz_kwh: Heim-Netzladung in kWh (PV-Ladung ist kostenlos und
            wird hier ignoriert; wer das anders modelliert, übergibt die
            Gesamtladung als netz-Anteil)
        ladung_extern_euro: tatsächliche Kosten externer Ladevorgänge in €
        wallbox_strompreis_cent: Strompreis für Heim-Netzladung in ct/kWh
            (separater Wallbox-Tarif oder allgemeiner Tarif als Fallback)
        eauto_parameter: `Investition.parameter`-Dict für das E-Auto.
            Wird genutzt für Vergleichsverbrauch und Default-Benzinpreis.
        monats_benzinpreis_euro: Optionaler monatlicher Benzinpreis-Override
            aus `Monatsdaten.kraftstoffpreis_euro`. Hat Vorrang vor Param-Default.

    Returns:
        EAutoErsparnisErgebnis mit Ersparnis, Komponenten und Diagnostik.
    """
    if km_gefahren <= 0:
        return EAutoErsparnisErgebnis(
            0.0, 0.0, 0.0,
            BENZIN_VERBRAUCH_DEFAULT_L_100KM,
            BENZIN_PREIS_DEFAULT_EURO_L,
        )

    verbrauch_l_100km = _vergleich_verbrauch(eauto_parameter)

    if monats_benzinpreis_euro is not None:
        benzinpreis_euro = monats_benzinpreis_euro
    else:
        benzinpreis_euro = _benzinpreis_default(eauto_parameter)

    benzin_kosten = (km_gefahren / 100) * verbrauch_l_100km * benzinpreis_euro
    strom_kosten = max(0.0, ladung_netz_kwh) * wallbox_strompreis_cent / 100 + ladung_extern_euro
    ersparnis = benzin_kosten - strom_kosten

    return EAutoErsparnisErgebnis(
        ersparnis_euro=ersparnis,
        benzin_kosten_euro=benzin_kosten,
        strom_kosten_euro=strom_kosten,
        verwendeter_verbrauch_l_100km=verbrauch_l_100km,
        verwendeter_benzinpreis_euro=benzinpreis_euro,
    )
