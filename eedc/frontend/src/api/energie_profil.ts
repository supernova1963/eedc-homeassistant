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
}

export interface VollbackfillResult {
  verarbeitet: number
  geschrieben: number
  von: string
  bis: string
}

export const energieProfilApi = {
  getStunden: (anlageId: number, datum: string): Promise<StundenAntwort> =>
    api.get(`/energie-profil/${anlageId}/stunden?datum=${datum}`),

  getWochenmuster: (anlageId: number, von: string, bis: string): Promise<WochenmusterPunkt[]> =>
    api.get(`/energie-profil/${anlageId}/wochenmuster?von=${von}&bis=${bis}`),

  getTage: (anlageId: number, von: string, bis: string): Promise<TagesZusammenfassung[]> =>
    api.get(`/energie-profil/${anlageId}/tage?von=${von}&bis=${bis}`),

  getMonat: (anlageId: number, jahr: number, monat: number): Promise<MonatsAuswertung> =>
    api.get(`/energie-profil/${anlageId}/monat?jahr=${jahr}&monat=${monat}`),

  vollbackfill: (anlageId: number): Promise<VollbackfillResult> =>
    api.post(`/energie-profil/${anlageId}/vollbackfill`),
}
