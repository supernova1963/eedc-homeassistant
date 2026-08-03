/**
 * Monatsdaten API Client
 */

import { api } from './client'
import type { Monatsdaten, MonatsKennzahlen, SonstigePosition } from '../types'
import type { BehalteneAbweichung } from './monatsabschluss'

export interface MonatsdatenCreate {
  anlage_id: number
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  pv_erzeugung_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  batterie_ladung_netz_kwh?: number
  batterie_ladepreis_cent?: number
  netzbezug_durchschnittspreis_cent?: number
  kraftstoffpreis_euro?: number
  gaspreis_cent_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  datenquelle?: string
  notizen?: string
  // G19-1: Anlage-Ebene Sonstige Erträge & Ausgaben ([] = bewusst geleert)
  sonstige_positionen?: SonstigePosition[]
  // PN 90128: bewusst behaltene Sensor-Abweichungen je Basis-Feld
  // ({feld: {sensor, wert}}); `{}` nimmt frühere Bestätigungen zurück.
  geprueft_gegen?: Record<string, BehalteneAbweichung>
}

export interface MonatsdatenUpdate {
  einspeisung_kwh?: number
  netzbezug_kwh?: number
  pv_erzeugung_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  batterie_ladung_netz_kwh?: number
  batterie_ladepreis_cent?: number
  netzbezug_durchschnittspreis_cent?: number
  kraftstoffpreis_euro?: number
  gaspreis_cent_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  notizen?: string
  // G19-1: Anlage-Ebene Sonstige Erträge & Ausgaben ([] = bewusst geleert)
  sonstige_positionen?: SonstigePosition[]
  // PN 90128: siehe MonatsdatenCreate
  geprueft_gegen?: Record<string, BehalteneAbweichung>
}

export interface MonatsdatenMitKennzahlen extends Monatsdaten {
  kennzahlen?: MonatsKennzahlen
}

/**
 * Aggregierte Monatsdaten mit Werten aus InvestitionMonatsdaten
 */
export interface AggregierteMonatsdaten {
  // null = Monat OHNE Zählerzeile (kein Monatsabschluss) — kommt nur mit
  // `inklOhneZaehlerzeile`. Die Zeile trägt IMD-Mengen, aber keinen Datensatz:
  // wer sie bearbeiten/löschen/verlinken will, muss auf null prüfen.
  id: number | null
  anlage_id: number
  jahr: number
  monat: number
  // Zählerwerte (aus Monatsdaten)
  einspeisung_kwh: number
  netzbezug_kwh: number
  globalstrahlung_kwh_m2: number | null
  sonnenstunden: number | null
  // Dynamischer Monats-Ø-Netzbezugspreis (Flex-Tarif). null = kein Flex-Wert
  // → Fallback auf statischen Tarif, gleiche Quelle wie Cockpit (#326).
  netzbezug_durchschnittspreis_cent?: number | null
  // Komponenten-Aggregate: null = "in dem Monat keine aktive Komponente
  // dieses Typs" (vor Anschaffung / nach Stilllegung / Anlage hat den Typ
  // nicht). 0 = "Komponente aktiv, IMD vorhanden, Wert echt 0" (z.B.
  // WP-Heizung im Sommer). UI muss die Unterscheidung respektieren —
  // null als "—" rendern, nicht als "0 kWh" (#236).
  // ⚠️ Zwei Bedeutungen, ein Name: DIESES Feld ist Module + BKW. Die
  // DB-Spalte `Monatsdaten.pv_erzeugung_kwh` heißt gleich, meint aber das
  // manuell gepflegte Gesamt-Aggregat der Module (Legacy). Nicht umbenannt,
  // weil der Identifier MQTT-Topic, CSV-Spalte und Backup-Feld ist.
  pv_erzeugung_kwh: number | null
  // R17/Verlauf-Vergleich: Module vs. BKW getrennt (Σ == pv_erzeugung_kwh) +
  // Netzladung-Anteil + §51-Abzug-Volumen (nur wenn Anlage §51 unterliegt).
  // Hieß bis A17 `pv_anlage_kwh` — „PV-Anlage" ist im Produkt überall die
  // GANZE Anlage (inkl. BKW), das Feld meint aber Module OHNE BKW.
  pv_module_kwh: number | null
  bkw_kwh: number | null
  // Sonstige Erzeuger (typ `sonstiges` + Kategorie `erzeuger`, z. B. BHKW).
  // NICHT in pv_erzeugung_kwh (die bleibt rein PV), aber Teil der
  // Netzpunkt-Bilanz, aus der direktverbrauch/eigenverbrauch gerechnet sind.
  sonstige_erzeugung_kwh: number | null
  // Netzpunkt-Größe: alles hinter dem Hauszähler Erzeugte
  // (`pv_module_kwh + bkw_kwh + sonstige_erzeugung_kwh`) — genau die Zahl, mit
  // der das Backend direktverbrauch/eigenverbrauch gerechnet hat. NIE als
  // Zähler einer PV-Kennzahl verwenden (spez. Ertrag/PR bleiben rein PV).
  erzeugung_hinter_zaehler_kwh: number | null
  speicher_ladung_kwh: number | null
  speicher_entladung_kwh: number | null
  speicher_netzladung_kwh: number | null
  wp_strom_kwh: number | null
  wp_strom_heizen_kwh: number | null  // #191: nur befüllt wenn getrennte_strommessung
  wp_strom_warmwasser_kwh: number | null  // #191: nur befüllt wenn getrennte_strommessung
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  eauto_ladung_kwh: number | null
  eauto_km: number | null
  wallbox_ladung_kwh: number | null
  wallbox_ladung_pv_kwh: number | null
  // Berechnet
  direktverbrauch_kwh: number
  eigenverbrauch_kwh: number
  gesamtverbrauch_kwh: number
  autarkie_prozent: number
  eigenverbrauchsquote_prozent: number
  // §51-Abzug-Volumen (kWh bei neg. Börsenpreis eingespeist); null = Anlage
  // unterliegt nicht §51 (R17/Verlauf).
  einspeisung_neg_preis_kwh: number | null
  // Legacy-Marker
  hat_legacy_daten: boolean
}

export const monatsdatenApi = {
  /**
   * Monatsdaten abrufen (optional gefiltert)
   */
  async list(anlageId?: number, jahr?: number): Promise<Monatsdaten[]> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (jahr) params.append('jahr', jahr.toString())
    const query = params.toString()
    return api.get<Monatsdaten[]>(`/monatsdaten/${query ? '?' + query : ''}`)
  },

  /**
   * Einzelne Monatsdaten mit Kennzahlen abrufen
   */
  async get(id: number): Promise<MonatsdatenMitKennzahlen> {
    return api.get<MonatsdatenMitKennzahlen>(`/monatsdaten/${id}`)
  },

  /**
   * Neue Monatsdaten erstellen
   */
  async create(data: MonatsdatenCreate): Promise<Monatsdaten> {
    return api.post<Monatsdaten>('/monatsdaten/', data)
  },

  /**
   * Monatsdaten aktualisieren
   */
  async update(id: number, data: MonatsdatenUpdate): Promise<Monatsdaten> {
    return api.put<Monatsdaten>(`/monatsdaten/${id}`, data)
  },

  /**
   * Monatsdaten löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/monatsdaten/${id}`)
  },

  /**
   * Aggregierte Monatsdaten abrufen
   * PV-Erzeugung und Speicher-Daten werden aus InvestitionMonatsdaten summiert
   *
   * `inklOhneZaehlerzeile` nimmt Monate mit auf, die zwar Mengen tragen, aber
   * noch keinen Monatsabschluss haben (`id: null`). Für **Zeitreihen** gedacht
   * (Cockpit → Jahr, Fund N-68) — nicht für Datensatz-Listen wie
   * *Auswertungen → Tabelle*, wo eine nicht bearbeitbare Zeile stünde.
   */
  async listAggregiert(
    anlageId: number,
    jahr?: number,
    opts?: { inklOhneZaehlerzeile?: boolean },
  ): Promise<AggregierteMonatsdaten[]> {
    const params = new URLSearchParams()
    if (jahr) params.append('jahr', jahr.toString())
    if (opts?.inklOhneZaehlerzeile) params.append('inkl_ohne_zaehlerzeile', 'true')
    const query = params.toString()
    return api.get<AggregierteMonatsdaten[]>(`/monatsdaten/aggregiert/${anlageId}${query ? '?' + query : ''}`)
  },
}
