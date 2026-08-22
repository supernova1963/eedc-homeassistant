/**
 * Monatsabschluss API Client
 *
 * Endpoints für den Monatsabschluss-Wizard.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface Vorschlag {
  // ha_statistics + mqtt_inbound werden vom View-Endpoint zusätzlich eingefügt
  // (views.py insert(0, …)) — hier gespiegelt, sonst Typ-Lücke (SoT VorschlagQuelle).
  wert: number
  quelle: 'ha_sensor' | 'ha_statistics' | 'cron_snapshot' | 'local_connector' | 'mqtt_inbound' | 'portal_import' | 'vormonat' | 'vorjahr' | 'berechnung' | 'durchschnitt' | 'parameter'
  konfidenz: number
  beschreibung: string
  details?: Record<string, unknown>
  /** #352: gesetzt, wenn der Wert die **Zerlegung** eines Anlagen-Gesamtwerts
   *  ist (`kwp_anteil` / `kapazitaet_anteil`) und keine Gerätemessung. Wer den
   *  Vorschlag übernimmt, schickt die Marke beim Speichern zurück — sonst
   *  gilt der gerechnete Wert in der Provenance als gemessen und die
   *  String-Sichten ranken ihn gegen echte Messungen. */
  abgeleitet?: string | null
}

export interface Warnung {
  typ: 'negativ' | 'zu_hoch' | 'zu_niedrig' | 'sensor_unavailable'
  schwere: 'error' | 'warning' | 'info'
  meldung: string
  details?: Record<string, unknown>
}

export interface FeldStatus {
  feld: string
  label: string
  einheit: string
  aktueller_wert: number | null
  aktueller_text: string | null  // Für Textfelder
  quelle: 'ha_sensor' | 'snapshot' | 'manuell' | 'berechnet' | 'portal_import' | 'cloud_import' | 'local_connector' | 'csv' | 'ha_import' | 'cron_snapshot' | null
  vorschlaege: Vorschlag[]
  warnungen: Warnung[]
  strategie: string | null
  sensor_id: string | null
  typ: 'number' | 'text'  // Feldtyp
  gruppe: string | null  // zaehler, wetter, preise
  /** PN 90128: die vom Nutzer bewusst behaltene Situation dieses Feldes —
   *  `sensor` = Vorschlagswert zum Zeitpunkt der Bestätigung, `wert` = der
   *  behaltene gespeicherte Wert. Gilt nur, solange beide noch stimmen. */
  geprueft_gegen?: BehalteneAbweichung | null
}

/** Bewusst behaltene Sensor-Abweichung (PN 90128) — Situation, nicht Häkchen. */
export interface BehalteneAbweichung {
  sensor: number
  wert: number
}

// SoT-Kanon in types/index.ts (G19-1) — hier nur Re-Export für Bestand
import type { SonstigePosition } from '../types'
export type { SonstigePosition }

export interface InvestitionStatus {
  id: number
  typ: string
  bezeichnung: string
  felder: FeldStatus[]
  kategorie?: string             // Für Typ "sonstiges": erzeuger/verbraucher/speicher
  sonstige_positionen: SonstigePosition[]
}

export interface MonatsabschlussResponse {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  ist_abgeschlossen: boolean
  ha_mapping_konfiguriert: boolean
  connector_konfiguriert: boolean
  cloud_import_konfiguriert: boolean
  mqtt_inbound_konfiguriert: boolean
  portal_import_vorhanden: boolean
  datenquelle: string | null
  basis_felder: FeldStatus[]
  optionale_felder: FeldStatus[]  // Sonderkosten, Notizen
  investitionen: InvestitionStatus[]
}

export interface FeldWert {
  feld: string
  wert: number
  /** #352: Marke des übernommenen, zerlegten Vorschlags (siehe `Vorschlag`). */
  abgeleitet?: string | null
}

export interface InvestitionWerte {
  investition_id: number
  felder: FeldWert[]
  sonstige_positionen?: SonstigePosition[] | null
}

export interface MonatsabschlussInput {
  // Basis-Felder (aus field_definitions.py — alle number-Felder generisch)
  einspeisung_kwh?: number | null
  netzbezug_kwh?: number | null
  globalstrahlung_kwh_m2?: number | null
  sonnenstunden?: number | null
  durchschnittstemperatur?: number | null
  // Bedingte Basis-Felder
  netzbezug_durchschnittspreis_cent?: number | null
  kraftstoffpreis_euro?: number | null
  gaspreis_cent_kwh?: number | null
  // Optionale manuelle Felder
  sonderkosten_euro?: number | null
  sonderkosten_beschreibung?: string | null
  notizen?: string | null
  investitionen: InvestitionWerte[]
  datenquelle?: string | null
  // Index-Signatur für generischen Zugriff (Phase D)
  [key: string]: unknown
}

export interface MonatsabschlussResult {
  success: boolean
  message: string
  monatsdaten_id: number | null
  investition_monatsdaten_ids: number[]
  warnungen: Warnung[]
}

export interface NaechsterMonat {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  monat_name: string
  ha_mapping_konfiguriert: boolean
}

export interface MonatHistorie {
  id: number
  jahr: number
  monat: number
  monat_name: string
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  direktverbrauch_kwh: number | null
}

// =============================================================================
// API Client
// =============================================================================

export const monatsabschlussApi = {
  /**
   * Status für einen Monat abrufen
   */
  async getStatus(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<MonatsabschlussResponse> {
    return api.get<MonatsabschlussResponse>(`/monatsabschluss/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Monatsdaten speichern
   */
  async save(
    anlageId: number,
    jahr: number,
    monat: number,
    daten: MonatsabschlussInput
  ): Promise<MonatsabschlussResult> {
    return api.post<MonatsabschlussResult>(`/monatsabschluss/${anlageId}/${jahr}/${monat}`, daten)
  },

  /**
   * Nächsten unvollständigen Monat ermitteln
   */
  async getNaechsterMonat(anlageId: number): Promise<NaechsterMonat | null> {
    try {
      return await api.get<NaechsterMonat>(`/monatsabschluss/naechster/${anlageId}`)
    } catch {
      return null
    }
  },

  /**
   * Historie der letzten Monate
   */
  async getHistorie(anlageId: number, limit = 12): Promise<MonatHistorie[]> {
    return api.get<MonatHistorie[]>(`/monatsabschluss/historie/${anlageId}?limit=${limit}`)
  },
}
