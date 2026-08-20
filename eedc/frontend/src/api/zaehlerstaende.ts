/**
 * Zählerstände unter *Sonstiges* (#377) — Client für die eine Backend-Route.
 *
 * Vier Anzeigen fragen dieselbe Auskunft: *Live/Auf einen Blick*,
 * *Cockpit Tag/Monat/Jahr*, *Komponenten/Sonstiges* und die Tabellen. Sie holen
 * sie hier, nicht jede für sich.
 *
 * ⚠ **Ein Zählerstand ist eine Bestandsgröße.** Er summiert sich über nichts —
 * weder über Geräte noch über die Zeit. Alles, was sich addieren lässt, ist die
 * `differenz`, und die ist eine andere Größe. Deshalb gibt es hier bewusst
 * keine Summenfunktion.
 */

import { api } from './client'

export interface ZaehlerVerlaufPunkt {
  zeitpunkt: string
  stand: number
}

export interface ZaehlerStand {
  investition_id: number
  name: string
  /** Medium-Art (`gas` · `wasser` · …) — nur Label und Symbol. */
  art: string
  /** Die Einheit, die neben der Zahl steht. eedc rechnet nie um. */
  einheit: string
  stand_anfang: number | null
  stand_ende: number | null
  /** `null`, wenn ein Stand fehlt — **nicht** 0 (ADR-002/P4). */
  differenz: number | null
  /**
   * `false` = die Aufzeichnung beginnt **innerhalb** des Fensters, `differenz`
   * deckt also nur einen Teil davon ab. Die Anzeige muss das ansagen, statt
   * eine zu kleine Zahl kommentarlos hinzustellen.
   */
  anfang_vollstaendig: boolean
  verlauf: ZaehlerVerlaufPunkt[]
}

export type ZaehlerZeitraum = 'tag' | 'monat' | 'jahr' | 'gesamt'

export interface ZaehlerstaendeParams {
  zeitraum: ZaehlerZeitraum
  /** Nur bei `zeitraum: 'tag'` — ISO-Datum. */
  datum?: string
  jahr?: number
  monat?: number
  mitVerlauf?: boolean
}

export const zaehlerstaendeApi = {
  /** Stände für ein Fenster — je Gerät, nie summiert. */
  async get(anlageId: number, params: ZaehlerstaendeParams): Promise<ZaehlerStand[]> {
    const query = new URLSearchParams({ zeitraum: params.zeitraum })
    if (params.datum) query.set('datum', params.datum)
    if (params.jahr !== undefined) query.set('jahr', String(params.jahr))
    if (params.monat !== undefined) query.set('monat', String(params.monat))
    if (params.mitVerlauf === false) query.set('mit_verlauf', 'false')
    return api.get<ZaehlerStand[]>(`/zaehlerstaende/${anlageId}?${query.toString()}`)
  },

  /** *Live / Auf einen Blick*: aktueller Stand + Veränderung heute. */
  async heute(anlageId: number): Promise<ZaehlerStand[]> {
    return api.get<ZaehlerStand[]>(`/zaehlerstaende/${anlageId}/heute`)
  },
}
