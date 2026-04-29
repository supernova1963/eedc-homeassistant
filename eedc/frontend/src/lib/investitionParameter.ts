/**
 * Single Source of Truth für die Schlüssel im `parameter`-JSON-Feld
 * jeder Investition.
 *
 * Hintergrund: das `parameter`-Feld auf einer Investition ist ein unstrukturiertes
 * JSON. Über mehrere Iterationen sind Schlüsselnamen zwischen Form, Wizard und
 * Backend-Lese-Code gedriftet — siehe Inventur in
 * `docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md`.
 *
 * Dieses Modul macht die Keys statisch typisiert + auffindbar:
 *   - `PARAM_<TYP>` exportiert die kanonischen Schlüsselnamen pro Investitions-Typ
 *   - `PARAM_<TYP>_DEFAULTS` exportiert die Default-Werte (gemeinsam für Frontend
 *     und Backend, damit Default-Drift wie #7 in der Inventur nicht entsteht)
 *   - `<Typ>Parameter` exportiert das passende TS-Interface
 *
 * Verwendung:
 *
 *   import { PARAM_SPEICHER, type SpeicherParameter } from '@/lib/investitionParameter'
 *
 *   const sp = inv.parameter as SpeicherParameter
 *   const kap = sp[PARAM_SPEICHER.KAPAZITAET_KWH]
 */

// ============================================================================
// E-Auto
// ============================================================================

export const PARAM_E_AUTO = {
  BATTERIE_KAPAZITAET_KWH: 'batteriekapazitaet_kwh',
  VERBRAUCH_KWH_100KM: 'verbrauch_kwh_100km',
  JAHRESFAHRLEISTUNG_KM: 'jahresfahrleistung_km',
  PV_LADEANTEIL_PROZENT: 'pv_ladeanteil_prozent',
  VERGLEICH_VERBRAUCH_L_100KM: 'vergleich_verbrauch_l_100km',
  BENZINPREIS_EURO: 'benzinpreis_euro',
  V2H_FAEHIG: 'v2h_faehig',
  V2H_ENTLADELEISTUNG_KW: 'v2h_entladeleistung_kw',
  V2H_ENTLADE_PREIS_CENT: 'v2h_entlade_preis_cent',
  V2H_ENTLADUNG_KWH_JAHR: 'v2h_entladung_kwh_jahr',
  IST_DIENSTLICH: 'ist_dienstlich',
  ALTERNATIV_KOSTEN_EURO: 'alternativ_kosten_euro',
} as const

export const PARAM_E_AUTO_DEFAULTS = {
  verbrauch_kwh_100km: 18,
  jahresfahrleistung_km: 15000,
  pv_ladeanteil_prozent: 60,
  vergleich_verbrauch_l_100km: 7.5,
  benzinpreis_euro: 1.65,
  v2h_faehig: false,
  ist_dienstlich: false,
} as const

export interface EAutoParameter {
  batteriekapazitaet_kwh?: number
  verbrauch_kwh_100km?: number
  jahresfahrleistung_km?: number
  pv_ladeanteil_prozent?: number
  vergleich_verbrauch_l_100km?: number
  benzinpreis_euro?: number
  v2h_faehig?: boolean
  v2h_entladeleistung_kw?: number
  v2h_entlade_preis_cent?: number
  v2h_entladung_kwh_jahr?: number
  ist_dienstlich?: boolean
  alternativ_kosten_euro?: number
}

// ============================================================================
// Speicher
// ============================================================================

export const PARAM_SPEICHER = {
  KAPAZITAET_KWH: 'kapazitaet_kwh',
  NUTZBARE_KAPAZITAET_KWH: 'nutzbare_kapazitaet_kwh',
  MAX_LADELEISTUNG_KW: 'max_ladeleistung_kw',
  MAX_ENTLADELEISTUNG_KW: 'max_entladeleistung_kw',
  WIRKUNGSGRAD_PROZENT: 'wirkungsgrad_prozent',
  ARBITRAGE_FAEHIG: 'arbitrage_faehig',
  LADE_DURCHSCHNITTSPREIS_CENT: 'lade_durchschnittspreis_cent',
  ENTLADE_VERMIEDENER_PREIS_CENT: 'entlade_vermiedener_preis_cent',
} as const

export const PARAM_SPEICHER_DEFAULTS = {
  wirkungsgrad_prozent: 95,
  arbitrage_faehig: false,
  lade_durchschnittspreis_cent: 12,
  entlade_vermiedener_preis_cent: 35,
} as const

export interface SpeicherParameter {
  kapazitaet_kwh?: number
  nutzbare_kapazitaet_kwh?: number
  max_ladeleistung_kw?: number
  max_entladeleistung_kw?: number
  wirkungsgrad_prozent?: number
  arbitrage_faehig?: boolean
  lade_durchschnittspreis_cent?: number
  entlade_vermiedener_preis_cent?: number
}

// ============================================================================
// Wärmepumpe
// ============================================================================

export const PARAM_WAERMEPUMPE = {
  LEISTUNG_KW: 'leistung_kw',
  WP_ART: 'wp_art',
  EFFIZIENZ_MODUS: 'effizienz_modus',
  JAZ: 'jaz',
  SCOP_HEIZUNG: 'scop_heizung',
  SCOP_WARMWASSER: 'scop_warmwasser',
  VORLAUFTEMPERATUR: 'vorlauftemperatur',
  COP_HEIZUNG: 'cop_heizung',
  COP_WARMWASSER: 'cop_warmwasser',
  GETRENNTE_STROMMESSUNG: 'getrennte_strommessung',
  HEIZWAERMEBEDARF_KWH: 'heizwaermebedarf_kwh',
  WARMWASSERBEDARF_KWH: 'warmwasserbedarf_kwh',
  WAERMEBEDARF_KWH: 'waermebedarf_kwh',
  PV_ANTEIL_PROZENT: 'pv_anteil_prozent',
  ALTER_ENERGIETRAEGER: 'alter_energietraeger',
  ALTER_PREIS_CENT_KWH: 'alter_preis_cent_kwh',
  ALTERNATIV_ZUSATZKOSTEN_JAHR: 'alternativ_zusatzkosten_jahr',
  ALTERNATIV_KOSTEN_EURO: 'alternativ_kosten_euro',
  SG_READY: 'sg_ready',
} as const

export const PARAM_WAERMEPUMPE_DEFAULTS = {
  wp_art: 'luft_wasser' as const,
  effizienz_modus: 'gesamt_jaz' as const,
  jaz: 3.5,
  scop_heizung: 4.5,
  scop_warmwasser: 3.2,
  vorlauftemperatur: '35' as const,
  cop_heizung: 3.9,
  cop_warmwasser: 3.0,
  getrennte_strommessung: false,
  heizwaermebedarf_kwh: 12000,
  warmwasserbedarf_kwh: 3000,
  pv_anteil_prozent: 30,
  alter_energietraeger: 'gas' as const,
  // Inventur Bug #7: in aussichten.py + ha_export.py:241 stand 10.0,
  // andernorts 12.0. Vereinheitlicht auf 12.0 — typisch Gas-Endkundenpreis.
  alter_preis_cent_kwh: 12,
  alternativ_zusatzkosten_jahr: 0,
  sg_ready: false,
} as const

export type WPEffizienzModus = 'gesamt_jaz' | 'scop' | 'getrennte_cops'
export type WPArt = 'luft_wasser' | 'sole_wasser' | 'grundwasser' | 'luft_luft'
export type WPVorlauftemperatur = '35' | '55'
export type WPAlterEnergietraeger = 'gas' | 'oel' | 'strom'

export interface WaermepumpeParameter {
  leistung_kw?: number
  wp_art?: WPArt
  effizienz_modus?: WPEffizienzModus
  jaz?: number
  scop_heizung?: number
  scop_warmwasser?: number
  vorlauftemperatur?: WPVorlauftemperatur
  cop_heizung?: number
  cop_warmwasser?: number
  // Inventur Bug #8: Form speicherte als String 'true'/'false' — JS-Truthy
  // verfälscht das. Ab v3.25.0 echter Boolean.
  getrennte_strommessung?: boolean
  heizwaermebedarf_kwh?: number
  warmwasserbedarf_kwh?: number
  waermebedarf_kwh?: number
  pv_anteil_prozent?: number
  alter_energietraeger?: WPAlterEnergietraeger
  alter_preis_cent_kwh?: number
  alternativ_zusatzkosten_jahr?: number
  alternativ_kosten_euro?: number
  sg_ready?: boolean
}

// ============================================================================
// Wallbox
// ============================================================================

export const PARAM_WALLBOX = {
  MAX_LADELEISTUNG_KW: 'max_ladeleistung_kw',
  BIDIREKTIONAL: 'bidirektional',
  PV_OPTIMIERT: 'pv_optimiert',
  IST_DIENSTLICH: 'ist_dienstlich',
} as const

export const PARAM_WALLBOX_DEFAULTS = {
  max_ladeleistung_kw: 11,
  bidirektional: false,
  pv_optimiert: true,
  ist_dienstlich: false,
} as const

export interface WallboxParameter {
  max_ladeleistung_kw?: number
  bidirektional?: boolean
  pv_optimiert?: boolean
  ist_dienstlich?: boolean
}

// ============================================================================
// Wechselrichter
// ============================================================================

export const PARAM_WECHSELRICHTER = {
  MAX_LEISTUNG_KW: 'max_leistung_kw',
  WIRKUNGSGRAD_PROZENT: 'wirkungsgrad_prozent',
  HYBRID: 'hybrid',
} as const

export const PARAM_WECHSELRICHTER_DEFAULTS = {
  wirkungsgrad_prozent: 97,
  hybrid: false,
} as const

export interface WechselrichterParameter {
  max_leistung_kw?: number
  wirkungsgrad_prozent?: number
  hybrid?: boolean
}

// ============================================================================
// PV-Module
// ============================================================================

export const PARAM_PV_MODULE = {
  ANZAHL_MODULE: 'anzahl_module',
  MODUL_LEISTUNG_WP: 'modul_leistung_wp',
  MODUL_TYP: 'modul_typ',
  AUSRICHTUNG_GRAD: 'ausrichtung_grad',
} as const

export interface PvModuleParameter {
  anzahl_module?: number
  modul_leistung_wp?: number
  modul_typ?: string
  ausrichtung_grad?: number
}

// ============================================================================
// Balkonkraftwerk
// ============================================================================

export const PARAM_BALKONKRAFTWERK = {
  LEISTUNG_WP: 'leistung_wp',
  ANZAHL: 'anzahl',
  AUSRICHTUNG: 'ausrichtung',
  NEIGUNG_GRAD: 'neigung_grad',
  HAT_SPEICHER: 'hat_speicher',
  SPEICHER_KAPAZITAET_WH: 'speicher_kapazitaet_wh',
} as const

export const PARAM_BALKONKRAFTWERK_DEFAULTS = {
  anzahl: 2,
  ausrichtung: 'Süd' as const,
  neigung_grad: 30,
  hat_speicher: false,
} as const

export interface BalkonkraftwerkParameter {
  leistung_wp?: number
  anzahl?: number
  ausrichtung?: string
  neigung_grad?: number
  hat_speicher?: boolean
  speicher_kapazitaet_wh?: number
}

// ============================================================================
// Sonstiges
// ============================================================================

export const PARAM_SONSTIGES = {
  KATEGORIE: 'kategorie',
  BESCHREIBUNG: 'beschreibung',
} as const

export const PARAM_SONSTIGES_DEFAULTS = {
  kategorie: 'erzeuger' as const,
} as const

export type SonstigesKategorie = 'erzeuger' | 'verbraucher' | 'speicher'

export interface SonstigesParameter {
  kategorie?: SonstigesKategorie
  beschreibung?: string
}

// ============================================================================
// Helper: typisierte Parameter-Reads
// ============================================================================

/**
 * Liefert das `parameter`-Objekt einer Investition typisiert für den jeweiligen Typ.
 * Reine Type-Coercion — keine Laufzeit-Validierung.
 */
export function eAutoParameter(parameter: unknown): EAutoParameter {
  return (parameter || {}) as EAutoParameter
}

export function speicherParameter(parameter: unknown): SpeicherParameter {
  return (parameter || {}) as SpeicherParameter
}

export function waermepumpeParameter(parameter: unknown): WaermepumpeParameter {
  return (parameter || {}) as WaermepumpeParameter
}

export function wallboxParameter(parameter: unknown): WallboxParameter {
  return (parameter || {}) as WallboxParameter
}

export function wechselrichterParameter(parameter: unknown): WechselrichterParameter {
  return (parameter || {}) as WechselrichterParameter
}

export function pvModuleParameter(parameter: unknown): PvModuleParameter {
  return (parameter || {}) as PvModuleParameter
}

export function balkonkraftwerkParameter(parameter: unknown): BalkonkraftwerkParameter {
  return (parameter || {}) as BalkonkraftwerkParameter
}

export function sonstigesParameter(parameter: unknown): SonstigesParameter {
  return (parameter || {}) as SonstigesParameter
}
