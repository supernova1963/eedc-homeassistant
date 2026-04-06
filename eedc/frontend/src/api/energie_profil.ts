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

export const energieProfilApi = {
  getStunden: (anlageId: number, datum: string): Promise<StundenAntwort> =>
    api.get(`/energie-profil/${anlageId}/stunden?datum=${datum}`),

  getWochenmuster: (anlageId: number, von: string, bis: string): Promise<WochenmusterPunkt[]> =>
    api.get(`/energie-profil/${anlageId}/wochenmuster?von=${von}&bis=${bis}`),

  getTage: (anlageId: number, von: string, bis: string): Promise<TagesZusammenfassung[]> =>
    api.get(`/energie-profil/${anlageId}/tage?von=${von}&bis=${bis}`),
}
