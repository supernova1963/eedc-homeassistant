/**
 * Aussichten API
 *
 * Prognosen und Vorhersagen für PV-Erträge.
 */

import { api } from './client'

// =============================================================================
// Kurzfrist-Prognose Types
// =============================================================================

export interface TagesPrognose {
  datum: string
  pv_prognose_kwh: number
  globalstrahlung_kwh_m2: number | null
  sonnenstunden: number | null
  temperatur_max_c: number | null
  temperatur_min_c: number | null
  niederschlag_mm: number | null
  bewoelkung_prozent: number | null
  wetter_symbol: string
}

export interface KurzfristPrognose {
  anlage_id: number
  anlagenname: string
  anlagenleistung_kwp: number
  prognose_zeitraum: {
    von: string | null
    bis: string | null
  }
  summe_kwh: number
  durchschnitt_kwh_tag: number
  tageswerte: TagesPrognose[]
  datenquelle: string
  abgerufen_am: string
  system_losses_prozent: number
}

// =============================================================================
// Langfrist-Prognose Types
// =============================================================================

export interface MonatsPrognose {
  jahr: number
  monat: number
  monat_name: string
  pvgis_prognose_kwh: number
  trend_korrigiert_kwh: number
  konfidenz_min_kwh: number
  konfidenz_max_kwh: number
  historische_performance_ratio: number | null
}

export interface TrendAnalyse {
  durchschnittliche_performance_ratio: number
  trend_richtung: 'positiv' | 'stabil' | 'negativ'
  datenbasis_monate: number
}

export interface LangfristPrognose {
  anlage_id: number
  anlagenname: string
  anlagenleistung_kwp: number
  prognose_zeitraum: {
    von: string | null
    bis: string | null
  }
  jahresprognose_kwh: number
  monatswerte: MonatsPrognose[]
  trend_analyse: TrendAnalyse
  datenquellen: string[]
}

// =============================================================================
// Trend-Analyse Types
// =============================================================================

export interface JahresVergleich {
  jahr: number
  gesamt_kwh: number
  spezifischer_ertrag_kwh_kwp: number
  performance_ratio: number | null
  anzahl_monate: number
  ist_vollstaendig: boolean
}

export interface SaisonaleMuster {
  beste_monate: string[]
  schlechteste_monate: string[]
}

export interface Degradation {
  geschaetzt_prozent_jahr: number | null
  hinweis: string
  methode: string | null
  zuverlaessig?: boolean
}

export interface TrendAnalyseResponse {
  anlage_id: number
  anlagenname: string
  anlagenleistung_kwp: number
  analyse_zeitraum: {
    von: number
    bis: number
  }
  jahres_vergleich: JahresVergleich[]
  saisonale_muster: SaisonaleMuster
  degradation: Degradation
  datenquellen: string[]
}

// =============================================================================
// Wetter-Vorhersage Types
// =============================================================================

export interface WetterVorhersageTag {
  datum: string
  temperatur_max_c: number | null
  temperatur_min_c: number | null
  niederschlag_mm: number | null
  sonnenstunden: number | null
  bewoelkung_prozent: number | null
  wetter_symbol: string
}

export interface WetterVorhersage {
  anlage_id: number
  standort: {
    latitude: number
    longitude: number
  }
  tage: WetterVorhersageTag[]
  abgerufen_am: string
}

// =============================================================================
// Finanz-Prognose Types
// =============================================================================

export interface FinanzPrognoseMonat {
  jahr: number
  monat: number
  monat_name: string
  pv_erzeugung_kwh: number
  eigenverbrauch_kwh: number
  einspeisung_kwh: number
  einspeise_erloes_euro: number
  ev_ersparnis_euro: number
  netto_ertrag_euro: number
  // Komponenten-Details
  speicher_beitrag_kwh: number
  v2h_beitrag_kwh: number
  wp_verbrauch_kwh: number
}

export interface KomponentenBeitrag {
  typ: string
  bezeichnung: string
  beitrag_kwh_jahr: number
  beitrag_euro_jahr: number
  beschreibung: string
}

export interface FinanzPrognose {
  anlage_id: number
  anlagenname: string
  prognose_zeitraum: {
    von: string | null
    bis: string | null
  }

  // Strompreise
  einspeiseverguetung_cent_kwh: number
  netzbezug_preis_cent_kwh: number
  grundpreis_euro_monat: number

  // Jahresprognose
  jahres_erzeugung_kwh: number
  jahres_eigenverbrauch_kwh: number
  jahres_einspeisung_kwh: number
  eigenverbrauchsquote_prozent: number

  // Finanzen
  jahres_einspeise_erloes_euro: number
  jahres_ev_ersparnis_euro: number
  jahres_netto_ertrag_euro: number

  // Komponenten-Beiträge
  komponenten_beitraege: KomponentenBeitrag[]

  // Speicher-spezifisch
  speicher_ev_erhoehung_kwh: number
  speicher_ev_erhoehung_euro: number

  // E-Auto/V2H-spezifisch
  v2h_rueckspeisung_kwh: number
  v2h_ersparnis_euro: number
  eauto_ladung_pv_kwh: number
  eauto_ersparnis_euro: number

  // Wärmepumpe-spezifisch
  wp_stromverbrauch_kwh: number
  wp_pv_anteil_kwh: number
  wp_pv_ersparnis_euro: number

  // Alternativkosten-Einsparungen
  wp_alternativ_ersparnis_euro: number  // vs. Gas/Öl
  eauto_alternativ_ersparnis_euro: number  // vs. Benzin

  // Investitionen (mit Alternativkosten-Berechnung)
  investition_pv_system_euro: number  // PV, Speicher, Wallbox (volle Kosten)
  investition_wp_mehrkosten_euro: number  // WP minus Gasheizung
  investition_eauto_mehrkosten_euro: number  // E-Auto minus Verbrenner
  investition_sonstige_euro: number  // Andere Investitionen
  investition_gesamt_euro: number  // Relevante Kosten (inkl. Mehrkosten-Ansatz)
  bisherige_ertraege_euro: number  // Kumulierte Erträge seit Inbetriebnahme
  amortisations_fortschritt_prozent: number  // Wie viel % bereits amortisiert (kumuliert)
  amortisation_erreicht: boolean
  amortisation_prognose_jahr: number | null
  restlaufzeit_bis_amortisation_monate: number | null

  // Monatswerte
  monatswerte: FinanzPrognoseMonat[]

  datenquellen: string[]
}

// =============================================================================
// Prognosen-Vergleich Types
// =============================================================================

export interface StundenProfilEintrag {
  stunde: number
  kw: number
  p10_kw: number | null
  p90_kw: number | null
}

export interface SolcastTag {
  datum: string
  kwh: number
  p10: number
  p90: number
}

export interface Tageshaelfte {
  vormittag_kwh: number
  nachmittag_kwh: number
}

export interface PrognosenVergleich {
  // OpenMeteo (roh)
  openmeteo_heute_kwh: number | null
  openmeteo_morgen_kwh: number | null
  openmeteo_uebermorgen_kwh: number | null
  openmeteo_tage: TagesPrognose[]
  openmeteo_tageshaelften: (Tageshaelfte | null)[]  // [heute, morgen, übermorgen]

  // EEDC (OpenMeteo × Lernfaktor)
  eedc_heute_kwh: number | null
  eedc_morgen_kwh: number | null
  eedc_uebermorgen_kwh: number | null
  eedc_stundenprofil: StundenProfilEintrag[]
  eedc_lernfaktor: number | null
  eedc_lernfaktor_stufe: string | null
  eedc_prognose_basis: string  // "openmeteo" | "solcast"
  eedc_tageshaelften: (Tageshaelfte | null)[]

  // Solcast
  solcast_verfuegbar: boolean
  solcast_status: string | null  // "ok"|"nicht_konfiguriert"|"tageslimit"|"auth_fehler"|"ha_nicht_erreichbar"|"fehler"
  solcast_hinweis: string | null
  solcast_quelle: string | null
  solcast_heute_kwh: number | null
  solcast_p10_kwh: number | null
  solcast_p90_kwh: number | null
  solcast_morgen_kwh: number | null
  solcast_morgen_p10_kwh: number | null
  solcast_morgen_p90_kwh: number | null
  solcast_uebermorgen_kwh: number | null
  solcast_stundenprofil: StundenProfilEintrag[]
  solcast_tage: SolcastTag[]
  solcast_tageshaelften: (Tageshaelfte | null)[]

  // IST-Ertrag heute
  ist_heute_kwh: number | null
  ist_stundenprofil: StundenProfilEintrag[]
  ist_tageshaelfte: Tageshaelfte | null

  // Verbleibend (IST + Prognose Rest)
  verbleibend_kwh: number | null
  verbleibend_om_kwh: number | null
  verbleibend_eedc_kwh: number | null
  verbleibend_solcast_kwh: number | null

  // OpenMeteo Stundenprofil (GTI-basiert)
  openmeteo_stundenprofil: StundenProfilEintrag[]

  // Meta
  solcast_letzter_abruf: string | null
  openmeteo_modell: string | null
  aktuelle_stunde: number | null
}

export interface GenauigkeitsEintrag {
  datum: string
  openmeteo_kwh: number | null
  solcast_kwh: number | null
  ist_kwh: number | null
}

export interface GenauigkeitsResponse {
  tage: GenauigkeitsEintrag[]
  openmeteo_mae_prozent: number | null
  solcast_mae_prozent: number | null
  anzahl_tage: number
}

// =============================================================================
// API Functions
// =============================================================================

export const aussichtenApi = {
  /**
   * Holt die Kurzfrist-PV-Prognose (7-16 Tage).
   */
  async getKurzfristPrognose(anlageId: number, tage: number = 14): Promise<KurzfristPrognose> {
    return api.get<KurzfristPrognose>(`/aussichten/kurzfristig/${anlageId}?tage=${tage}`)
  },

  /**
   * Holt die Langfrist-PV-Prognose (Monate).
   */
  async getLangfristPrognose(anlageId: number, monate: number = 12): Promise<LangfristPrognose> {
    return api.get<LangfristPrognose>(`/aussichten/langfristig/${anlageId}?monate=${monate}`)
  },

  /**
   * Holt die Trend-Analyse basierend auf historischen Daten.
   */
  async getTrendAnalyse(anlageId: number, jahre: number = 3): Promise<TrendAnalyseResponse> {
    return api.get<TrendAnalyseResponse>(`/aussichten/trend/${anlageId}?jahre=${jahre}`)
  },

  /**
   * Holt die reine Wettervorhersage ohne PV-Berechnung.
   */
  async getWetterVorhersage(anlageId: number, tage: number = 7): Promise<WetterVorhersage> {
    return api.get<WetterVorhersage>(`/aussichten/wetter/${anlageId}?tage=${tage}`)
  },

  /**
   * Holt die Finanzprognose mit ROI und Amortisation.
   */
  async getFinanzPrognose(anlageId: number, monate: number = 12): Promise<FinanzPrognose> {
    return api.get<FinanzPrognose>(`/aussichten/finanzen/${anlageId}?monate=${monate}`)
  },

  /**
   * Holt den Prognosen-Vergleich (OpenMeteo + Solcast + SFML).
   */
  async getPrognosenVergleich(anlageId: number): Promise<PrognosenVergleich> {
    return api.get<PrognosenVergleich>(`/aussichten/prognosen/${anlageId}`)
  },

  /**
   * Holt das Genauigkeits-Tracking (Prognose vs. IST).
   */
  async getPrognosenGenauigkeit(anlageId: number, tage: number = 30): Promise<GenauigkeitsResponse> {
    return api.get<GenauigkeitsResponse>(`/aussichten/prognosen/${anlageId}/genauigkeit?tage=${tage}`)
  },
}
