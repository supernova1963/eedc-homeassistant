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
  // ── Finanzen je Monat (N-22) ────────────────────────────────────────────
  // Fertig gerechnet aus dem Backend-SoT (`baue_finanz_zeile` +
  // `berechne_finanz_aggregat`) — derselbe Weg, den die Tages-Granularität
  // derselben Tabelle längst geht. Der Client rechnet hier nichts nach;
  // `createMonatsZeitreihe` tat es bis 2026-08-04 und wich dabei ab.
  einspeise_erloes_euro: number
  // §51-Diagnose: entgangener Erlös. Der Erlös oben ist bereits gekürzt.
  einspeise_nicht_verguetet_euro: number
  ev_ersparnis_euro: number
  // Nur für BKW-Monate ohne erfasste Erzeugung besetzt (Datenlücke, ADR-002/P9).
  bkw_ersparnis_euro: number
  // Bereits in `netto_ertrag_euro` abgezogen; 0 außerhalb der Regelbesteuerung.
  ust_eigenverbrauch_euro: number
  // Arbeitspreis × kWh + Grundpreis des Monats.
  netzbezug_kosten_euro: number
  // Erlös + EV- + BKW-Ersparnis − USt. OHNE „Sonstige Erträge & Ausgaben".
  netto_ertrag_euro: number
  netto_bilanz_euro: number
  // Effektiver Arbeitspreis des Monats (Flex-Ø vor Stammdaten-Tarif, P8).
  netzbezug_preis_cent: number
  // Legacy-Marker
  hat_legacy_daten: boolean
  // Feldgruppen, die nicht aus der Datenbank stammen, sondern aus der lokalen
  // Tagesebene (`inklNurTageswerte`, N-121) — z. B. `['pv', 'zaehler']`.
  // null/undefined = alles steht so in der Datenbank.
  aus_tageswerten?: string[] | null
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
   * Monatsdaten löschen — **immer vollständig**, inklusive der Messwerte je
   * Komponente desselben Monats.
   *
   * ⚠ Bis zum 2026-08-12 war das teilbar (`mitGeraetewerten`, Vorgabe `false`).
   * Das war als Schonung gemeint und hat den Zustand aus #349 erzeugt: einen
   * Monat, der in keiner Liste steht und trotzdem jeden Import abweist.
   * Einspeisung und Netzbezug sind Pflichtfelder — eine Hälfte zu löschen
   * ergibt keinen darstellbaren Zustand.
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/monatsdaten/${id}`)
  },

  /**
   * Was hängt an diesem Monat außer der Zählerzeile? (#349)
   * Grundlage für den Lösch-Dialog — er soll benennen, was verschwindet.
   */
  async getGeraetewerte(id: number): Promise<{
    jahr: number
    monat: number
    anzahl: number
    komponenten: { investition_id: number; bezeichnung: string; typ: string | null; felder: string[] }[]
  }> {
    return api.get(`/monatsdaten/${id}/geraetewerte`)
  },

  /**
   * Messwerte eines Monats OHNE Zählerzeile entfernen (#349).
   * Nur für den Daten-Checker-Weg: existiert die Zeile noch, antwortet das
   * Backend mit 409 und verweist auf den Lösch-Dialog.
   */
  async deleteVerwaisteGeraetewerte(anlageId: number, jahr: number, monat: number): Promise<{
    jahr: number
    monat: number
    geloescht: number
    komponenten: string[]
  }> {
    return api.delete(`/monatsdaten/geraetewerte/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Aggregierte Monatsdaten abrufen
   * PV-Erzeugung und Speicher-Daten werden aus InvestitionMonatsdaten summiert
   *
   * `inklOhneZaehlerzeile` nimmt Monate mit auf, die zwar Mengen tragen, aber
   * noch keinen Monatsabschluss haben (`id: null`). Für **Zeitreihen** gedacht
   * (Cockpit → Jahr, Fund N-68) — nicht für Datensatz-Listen wie
   * *Auswertungen → Tabelle*, wo eine nicht bearbeitbare Zeile stünde.
   *
   * `inklNurTageswerte` geht einen Schritt weiter und nimmt Monate mit, die
   * **auch** keine Komponenten-Zeile haben und nur in der lokalen Tagesebene
   * existieren (Fund N-121). Das betrifft immer den **laufenden** Monat — einen
   * automatischen Monatsabschluss gibt es nicht. Die betroffenen Größen sind in
   * `aus_tageswerten` benannt.
   */
  async listAggregiert(
    anlageId: number,
    jahr?: number,
    opts?: { inklOhneZaehlerzeile?: boolean; inklNurTageswerte?: boolean },
  ): Promise<AggregierteMonatsdaten[]> {
    const params = new URLSearchParams()
    if (jahr) params.append('jahr', jahr.toString())
    if (opts?.inklOhneZaehlerzeile) params.append('inkl_ohne_zaehlerzeile', 'true')
    if (opts?.inklNurTageswerte) params.append('inkl_nur_tageswerte', 'true')
    const query = params.toString()
    return api.get<AggregierteMonatsdaten[]>(`/monatsdaten/aggregiert/${anlageId}${query ? '?' + query : ''}`)
  },
}
