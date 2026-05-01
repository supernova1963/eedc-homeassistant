"""Wirtschaftlichkeits-Defaults — zentrale Konstanten für Berechnungen.

Single Source of Truth für hartcodierte Werte, die bisher an mehreren Stellen
dupliziert waren (siehe `docs/drafts/INVENTUR-DRIFT-AUDIT.md`, Domäne B).

Pendant im Frontend: `eedc/frontend/src/lib/wirtschaftlichkeitDefaults.ts`
— bei Änderungen dort spiegeln.
"""

from typing import Final


# Wärmepumpen-Wirkungsgrade (alter Energieträger)
# Quelle: Übliche Annahmen für Brennwert-/Niedertemperatur-Heizungen.
WP_WIRKUNGSGRAD_GAS_DEFAULT: Final[float] = 0.90
WP_WIRKUNGSGRAD_OEL_DEFAULT: Final[float] = 0.85

# Energiepreise (Defaults wenn nichts gepflegt)
# Gaspreis: typischer Endkundenpreis 2025/2026 (kanonisch in PARAM_WAERMEPUMPE_DEFAULTS).
GASPREIS_DEFAULT_CENT: Final[float] = 12.0
EINSPEISEVERGUETUNG_DEFAULT_CENT: Final[float] = 8.2
NETZBEZUG_DEFAULT_CENT: Final[float] = 30.0
EXTERNE_LADUNG_DEFAULT_EURO_KWH: Final[float] = 0.50

# E-Auto Vergleichswerte (kanonisch in PARAM_E_AUTO_DEFAULTS).
BENZIN_VERBRAUCH_DEFAULT_L_100KM: Final[float] = 7.5
BENZIN_PREIS_DEFAULT_EURO_L: Final[float] = 1.65

# WP-PV-Anteil: Annahme wenn keine Detail-Daten vorliegen
# Konservative 50/50-Annahme — sollte langfristig durch tatsächlichen Anteil
# aus InvestitionMonatsdaten ersetzt werden.
WP_PV_ANTEIL_DEFAULT: Final[float] = 0.5
