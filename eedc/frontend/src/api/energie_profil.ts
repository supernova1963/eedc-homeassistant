import { api } from './client'

export interface SerieInfo {
  key: string
  label: string
  typ: string       // z.B. "sonstiges", "pv-module", "virtual"
  kategorie: string // z.B. "sonstige", "pv", "netz"
  seite: string     // "quelle" | "senke" | "bidirektional"
}

export interface StundenWert {
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
  einspeisung_kw: number | null
  netzbezug_kw: number | null
  batterie_kw: number | null
  waermepumpe_kw: number | null
  wallbox_kw: number | null
  ueberschuss_kw: number | null
  defizit_kw: number | null
  temperatur_c: number | null
  globalstrahlung_wm2: number | null
  soc_prozent: number | null
  komponenten: Record<string, number> | null
  // WP-Kompressor-Starts in dieser Stunde (Summe über alle WPs der Anlage, Issue #136)
  wp_starts_anzahl: number | null
  // WP-Betriebsstunden in dieser Stunde (Summe über alle WPs der Anlage, Issue #238)
  wp_betriebsstunden: number | null
}

export interface StundenAntwort {
  stunden: StundenWert[]
  serien: SerieInfo[]
}

export interface WochenmusterPunkt {
  wochentag: number   // 0=Mo … 6=So
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
  netzbezug_kw: number | null
  einspeisung_kw: number | null
  batterie_kw: number | null
  anzahl_tage: number
}

export interface TagesZusammenfassung {
  datum: string
  ueberschuss_kwh: number | null
  defizit_kwh: number | null
  peak_pv_kw: number | null
  peak_netzbezug_kw: number | null
  peak_einspeisung_kw: number | null
  batterie_vollzyklen: number | null
  temperatur_min_c: number | null
  temperatur_max_c: number | null
  strahlung_summe_wh_m2: number | null
  performance_ratio: number | null
  stunden_verfuegbar: number
  datenquelle: string | null
  komponenten_kwh: Record<string, number> | null
  // Per-Komponente Counter pro Tag (z.B. WP-Kompressor-Starts, Issue #136)
  // Form: { wp_starts_anzahl: { "<inv_id>": <int> } }
  komponenten_starts: Record<string, Record<string, number>> | null
  // Börsenpreis / Negativpreis (§51 EEG)
  boersenpreis_avg_cent: number | null
  boersenpreis_min_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
}

/**
 * Tageszeile für die Werte/Tabelle-Embed-Sicht in Tagesgranularität
 * (IA v4 E3, Cockpit/Monat). Feldnamen sind deckungsgleich mit den
 * Registry-Keys (`lib/werte`), damit `getTagWert` direkt `row[key]` liest.
 * Backend: GET /energie-profil/{id}/tage-werte (additiv zur Monatsbilanz).
 */
export interface TagWerte {
  datum: string
  stunden_verfuegbar: number
  datenquelle: string | null
  // Energie (kWh)
  erzeugung: number
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
  gesamtverbrauch: number
  direktverbrauch: number
  // Quoten (%)
  autarkie: number | null
  evQuote: number | null
  spezErtrag: number | null
  // Speicher
  speicher_ladung: number | null
  speicher_entladung: number | null
  speicher_effizienz: number | null
  // Wärmepumpe (nur Strom je Tag)
  wp_strom: number | null
  // Finanzen (€)
  einspeise_erloes: number
  ev_ersparnis: number
  netzbezug_kosten: number
  netto_ertrag: number
  netto_bilanz: number
  // CO₂
  co2_einsparung: number
  // Tag-native Zusatzmetriken (kein Monats-Pendant)
  ueberschuss_kwh: number | null
  defizit_kwh: number | null
  peak_pv_kw: number | null
  peak_netzbezug_kw: number | null
  peak_einspeisung_kw: number | null
  performance_ratio: number | null
  batterie_vollzyklen: number | null
  temperatur_min_c: number | null
  temperatur_max_c: number | null
  strahlung_summe_wh_m2: number | null
  boersenpreis_avg_cent: number | null
  boersenpreis_min_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
}

/**
 * Tages-Detailwerte (Cockpit/Tag), die NICHT in der Tages-Bilanz stehen, aber
 * snapshot-/TEP-genau pro Tag erhebbar sind (SPEC-COCKPIT-TAG-JAHR Abschnitt F,
 * D1 „maximal erheben"). Ein Aufruf je gewähltem Tag (`getTagDetail`). Felder
 * `null` = Sensor nicht gemappt / keine Daten → Frontend lässt sie weg.
 */
export interface TagDetail {
  datum: string
  wp_strom_heizen_kwh: number | null
  wp_strom_warmwasser_kwh: number | null
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  speicher_ladung_netz_kwh: number | null
  speicher_effektiver_ladepreis_cent: number | null
  speicher_effektiver_ladepreis_quelle: string | null
  emob_ladung_pv_kwh: number | null
  emob_ladung_netz_kwh: number | null
  soll_pv_kwh: number | null
  einspeise_preis_cent: number | null
  netzbezug_preis_cent: number | null
}

export interface HeatmapZelle {
  tag: number          // 1..31
  stunde: number       // 0..23
  pv_kw: number | null
  verbrauch_kw: number | null
  netzbezug_kw: number | null
  einspeisung_kw: number | null
  ueberschuss_kw: number | null
}

export interface PeakStunde {
  datum: string
  stunde: number
  wert_kw: number
}

export interface TagesprofilStunde {
  stunde: number
  pv_kw: number | null
  verbrauch_kw: number | null
}

export interface KomponentenEintrag {
  key: string
  label: string
  kategorie: string
  typ: string
  seite: string
  kwh: number
  anteil_prozent: number | null
}

export interface KategorieSumme {
  kategorie: string
  kwh: number
  anteil_prozent: number | null
}

export interface MonatsAuswertung {
  jahr: number
  monat: number
  tage_im_monat: number
  tage_mit_daten: number
  pv_kwh: number
  verbrauch_kwh: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  ueberschuss_kwh: number
  defizit_kwh: number
  autarkie_prozent: number | null
  eigenverbrauch_prozent: number | null
  performance_ratio_avg: number | null
  batterie_vollzyklen_summe: number | null
  grundbedarf_kw: number | null
  batterie_ladung_kwh: number | null
  batterie_entladung_kwh: number | null
  batterie_wirkungsgrad: number | null
  direkt_eigenverbrauch_kwh: number | null
  pv_tag_best_kwh: number | null
  pv_tag_schnitt_kwh: number | null
  pv_tag_schlecht_kwh: number | null
  typisches_tagesprofil: TagesprofilStunde[]
  kategorien: KategorieSumme[]
  komponenten: KomponentenEintrag[]
  peak_netzbezug: PeakStunde[]
  peak_einspeisung: PeakStunde[]
  peak_pv: PeakStunde | null
  heatmap: HeatmapZelle[]
  // Börsenpreis / Negativpreis (§51 EEG)
  boersenpreis_avg_cent: number | null
  negative_preis_stunden: number | null
  einspeisung_neg_preis_kwh: number | null
}

export interface VollbackfillResult {
  verarbeitet: number
  geschrieben: number
  // #190 Bug B: Skip-Transparenz — Tage ohne HA-Daten bzw. bereits vorhanden
  uebersprungen_keine_daten?: number
  uebersprungen_existiert?: number
  von: string
  bis: string
}

export interface KraftstoffpreisStatus {
  tages_offen: number
  monats_offen: number
  land: string
}

export interface KraftstoffpreisBackfillResult {
  aktualisiert: number
  land: string
  hinweis?: string
  fehler?: string
}

export interface ProfildatenLoeschResult {
  geloescht_stundenwerte: number
  geloescht_tagessummen: number
}

export interface VerfuegbarerMonat {
  jahr: number
  monat: number
  tage: number
}

export interface AnlageStats {
  stundenwerte: number
  tageszusammenfassungen: number
  monatswerte: number
  zeitraum: {
    von: string
    bis: string
    tage_mit_daten: number
    tage_gesamt: number
    abdeckung_prozent: number
  } | null
  wachstum_pro_monat: number
}

export interface StundenPrognose {
  stunde: number
  pv_kw: number
  verbrauch_kw: number
  netto_kw: number
  netzbezug_kw: number
  einspeisung_kw: number
  soc_prozent: number | null
}

export interface TagesPrognose {
  datum: string
  stunden: StundenPrognose[]
  pv_summe_kwh: number
  verbrauch_summe_kwh: number
  netzbezug_summe_kwh: number
  einspeisung_summe_kwh: number
  eigenverbrauch_kwh: number
  autarkie_prozent: number
  speicher_kapazitaet_kwh: number | null
  speicher_voll_um: string | null
  speicher_leer_um: string | null
  verbrauch_basis: string
  pv_quelle: string
  daten_tage: number
}

export interface ReaggregatePreviewBoundary {
  sensor_key: string
  kategorie: string | null
  zeitpunkt: string
  alt_kwh: number | null
  neu_kwh: number | null
}

export interface ReaggregatePreviewSlot {
  stunde: number
  kategorie: string
  alt_kwh: number | null
  neu_kwh: number | null
}

export interface ReaggregatePreviewCounterTagesdelta {
  feld: string
  alt: number | null
  neu: number | null
}

export interface ReaggregatePreviewResponse {
  datum: string
  boundaries: ReaggregatePreviewBoundary[]
  slot_deltas: ReaggregatePreviewSlot[]
  tagesumme_alt: Record<string, number | null>
  tagesumme_neu: Record<string, number | null>
  ha_verfuegbar: boolean
  counter_tagesdelta: ReaggregatePreviewCounterTagesdelta[]
}

export const energieProfilApi = {
  getStunden: (anlageId: number, datum: string): Promise<StundenAntwort> =>
    api.get(`/energie-profil/${anlageId}/stunden?datum=${datum}`),

  getWochenmuster: (anlageId: number, von: string, bis: string): Promise<WochenmusterPunkt[]> =>
    api.get(`/energie-profil/${anlageId}/wochenmuster?von=${von}&bis=${bis}`),

  getTage: (anlageId: number, von: string, bis: string): Promise<TagesZusammenfassung[]> =>
    api.get(`/energie-profil/${anlageId}/tage?von=${von}&bis=${bis}`),

  getTageWerte: (anlageId: number, von: string, bis: string): Promise<TagWerte[]> =>
    api.get(`/energie-profil/${anlageId}/tage-werte?von=${von}&bis=${bis}`),

  getTagDetail: (anlageId: number, datum: string): Promise<TagDetail> =>
    api.get(`/energie-profil/${anlageId}/tag-detail?datum=${datum}`),

  getKomponentenSerien: (anlageId: number, von: string, bis: string): Promise<SerieInfo[]> =>
    api.get(`/energie-profil/${anlageId}/komponenten-serien?von=${von}&bis=${bis}`),

  getMonat: (anlageId: number, jahr: number, monat: number): Promise<MonatsAuswertung> =>
    api.get(`/energie-profil/${anlageId}/monat?jahr=${jahr}&monat=${monat}`),

  vollbackfill: (anlageId: number): Promise<VollbackfillResult> =>
    api.post(`/energie-profil/${anlageId}/vollbackfill`),

  reaggregateTag: (anlageId: number, datum: string, mitResnap: boolean = true, signal?: AbortSignal): Promise<{ status: string; datum: string; stunden_verfuegbar: number; stunden_mit_messdaten: number; pv_kwh_alt: number | null; pv_kwh_neu: number | null }> =>
    api.post(`/energie-profil/${anlageId}/reaggregate-tag?datum=${datum}&mit_resnap=${mitResnap}`, undefined, { signal }),

  reaggregateTagPreview: (anlageId: number, datum: string, signal?: AbortSignal): Promise<ReaggregatePreviewResponse> =>
    api.get(`/energie-profil/${anlageId}/reaggregate-tag/preview?datum=${datum}`, { signal }),

  getTagesprognose: (anlageId: number, datum?: string): Promise<TagesPrognose> =>
    api.get(`/energie-profil/${anlageId}/tagesprognose${datum ? `?datum=${datum}` : ''}`),

  getKraftstoffpreisStatus: (anlageId: number): Promise<KraftstoffpreisStatus> =>
    api.get(`/energie-profil/${anlageId}/kraftstoffpreis-status`),

  kraftstoffpreisBackfillTages: (anlageId: number): Promise<KraftstoffpreisBackfillResult> =>
    api.post(`/energie-profil/${anlageId}/kraftstoffpreis-backfill/tages`),

  kraftstoffpreisBackfillMonats: (anlageId: number): Promise<KraftstoffpreisBackfillResult> =>
    api.post(`/energie-profil/${anlageId}/kraftstoffpreis-backfill/monats`),

  deleteRohdaten: (): Promise<ProfildatenLoeschResult> =>
    api.delete(`/energie-profil/rohdaten`),

  getAnlageStats: (anlageId: number): Promise<AnlageStats> =>
    api.get(`/energie-profil/${anlageId}/stats`),

  getVerfuegbareMonate: (anlageId: number): Promise<VerfuegbarerMonat[]> =>
    api.get(`/energie-profil/${anlageId}/verfuegbare-monate`),

  deleteRohdatenAnlage: (anlageId: number): Promise<ProfildatenLoeschResult> =>
    api.delete(`/energie-profil/${anlageId}/rohdaten`),
}
