/**
 * Wirtschaftlichkeits-Defaults — zentrale Konstanten für Berechnungen.
 *
 * Single Source of Truth für hartcodierte Werte, die bisher an mehreren Stellen
 * dupliziert waren (siehe `docs/archive/INVENTUR-DRIFT-AUDIT.md`, Domäne B).
 *
 * Pendant im Backend: `eedc/backend/core/wirtschaftlichkeit_defaults.py`
 * — bei Änderungen dort spiegeln.
 */

// Wärmepumpen-Wirkungsgrade (alter Energieträger).
// Die Auswahl je Energieträger trifft ausschließlich das Backend
// (`core/berechnungen/alternativkosten.py::alter_wirkungsgrad`) — hier stehen
// nur die Werte als Spiegel. Strom-Direktheizung heizt verlustfrei: 1,0.
export const WP_WIRKUNGSGRAD_GAS_DEFAULT = 0.90
export const WP_WIRKUNGSGRAD_OEL_DEFAULT = 0.85
export const WP_WIRKUNGSGRAD_STROM_DEFAULT = 1.0

// Energiepreise (Defaults wenn nichts gepflegt)
export const GASPREIS_DEFAULT_CENT = 12.0
export const EINSPEISEVERGUETUNG_DEFAULT_CENT = 8.2
export const NETZBEZUG_DEFAULT_CENT = 30.0
export const EXTERNE_LADUNG_DEFAULT_EURO_KWH = 0.50

// E-Auto Vergleichswerte (kanonisch in PARAM_E_AUTO_DEFAULTS)
export const BENZIN_VERBRAUCH_DEFAULT_L_100KM = 7.5
export const BENZIN_PREIS_DEFAULT_EURO_L = 1.65

// WP-PV-Anteil: Annahme wenn keine Detail-Daten vorliegen
export const WP_PV_ANTEIL_DEFAULT = 0.5
