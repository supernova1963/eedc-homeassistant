/**
 * waermeTemperaturen — das Temperatur-Diagramm je Wärmepumpe in *Cockpit → Tag* als reine Funktion
 * (P-433-3 S3, #432; Bauplan S3-6, B9/B10, E-P3-12).
 *
 * Getrennt von der Zeichnung wie `waermeVerlauf.ts` (Recharts zeichnet in jsdom nichts). Die Zeichnung ist die Hülle
 * {@link WaermeVerlaufChart} — keine zweite Chart-Komponente: Vorlauf und Rücklauf als Linien, dazwischen die
 * Spreizung als Fläche, die Warmwasser-Temperatur als dritte Linie, alles auf der °C-Achse. Die Außentemperatur
 * bleibt im Verlauf darüber (E-P3-2 entfällt).
 *
 * ⛔ **Der Client rechnet nichts.** Stundenmittel, Spreizung je Stunde und der Kopf (Ø Vorlauf, Ø Spreizung über die
 * Betriebsstunden) kommen fertig aus dem Backend (`waerme-temperaturen-stunden`, Layer `temperatur.py` /
 * `temperatur_tagesmittel.py`). Hier wird nur benannt, gereiht und formatiert.
 */
import { CHART_COLORS, fmtZahl } from '../lib'
import { stundenBereich, type StundenRaster } from '../lib/stundenBereich'
import type { WaermeTemperaturGeraet, WaermeTemperaturStunden } from '../api/energie_profil'
import type { VerlaufFlaeche, VerlaufLinie, WaermeVerlaufRow } from './WaermeVerlaufChart'

export interface TemperaturDiagramm {
  rows: WaermeVerlaufRow[]
  linien: VerlaufLinie[]
  flaechen: VerlaufFlaeche[]
  /** «Ø Vorlauf 34,1 °C · Ø Spreizung 5,0 K (9 Betriebsstunden)» — `null` ohne erkennbare Betriebsstunde. */
  kopf: string | null
  /** `{Label: Wert der letzten Stunde}` für die Legende. */
  legendeZusatz: Record<string, string>
}

const LABEL = { vorlauf: 'Vorlauf', ruecklauf: 'Rücklauf', warmwasser: 'Warmwasser', spreizung: 'Spreizung' } as const

/** Die Geräte, für die es das Diagramm gibt: mindestens eine Temperatur-Stunde (B10: ohne Werte kein Diagramm). */
export function geraeteMitTemperaturen(t: WaermeTemperaturStunden | null | undefined): WaermeTemperaturGeraet[] {
  return (t?.geraete ?? []).filter((g) => g.abdeckung_h > 0)
}

const grad = (v: number | null | undefined) => (v == null ? null : `${fmtZahl(v, 1)} °C`)

/** Der letzte Wert einer Reihe (die letzte Stunde mit Messung) — für die Legende. */
function letzter(g: WaermeTemperaturGeraet, feld: 'vorlauf_c' | 'ruecklauf_c' | 'warmwasser_c' | 'spreizung_k') {
  for (let i = g.stunden.length - 1; i >= 0; i--) {
    const v = g.stunden[i][feld]
    if (v != null) return v
  }
  return null
}

export function baueTemperaturDiagramm(g: WaermeTemperaturGeraet, raster: StundenRaster = 'ende'): TemperaturDiagramm {
  const hat = (feld: 'vorlauf_c' | 'ruecklauf_c' | 'warmwasser_c') => g.stunden.some((s) => s[feld] != null)
  const hatVorlauf = hat('vorlauf_c')
  const hatRuecklauf = hat('ruecklauf_c')
  const hatWarmwasser = hat('warmwasser_c')
  const hatSpreizung = g.stunden.some((s) => s.spreizung_k != null)

  const rows: WaermeVerlaufRow[] = g.stunden.map((s) => {
    const row: WaermeVerlaufRow = { name: stundenBereich(s.stunde, raster) }
    if (hatVorlauf) row.vorlauf = s.vorlauf_c ?? null
    if (hatRuecklauf) row.ruecklauf = s.ruecklauf_c ?? null
    if (hatWarmwasser) row.warmwasser = s.warmwasser_c ?? null
    // Die Fläche nur, wo beide Werte gemessen sind — eine Lücke bleibt eine Lücke.
    if (hatSpreizung) row.spreizung = s.vorlauf_c != null && s.ruecklauf_c != null ? [s.ruecklauf_c, s.vorlauf_c] : null
    return row
  })

  const linien: VerlaufLinie[] = [
    ...(hatVorlauf ? [{ key: 'vorlauf', label: LABEL.vorlauf, farbe: CHART_COLORS.vorlauf, dezimalen: 1 }] : []),
    ...(hatRuecklauf ? [{ key: 'ruecklauf', label: LABEL.ruecklauf, farbe: CHART_COLORS.ruecklauf, dezimalen: 1 }] : []),
    ...(hatWarmwasser
      ? [{ key: 'warmwasser', label: LABEL.warmwasser, farbe: CHART_COLORS.wpWarmwasser, dezimalen: 1 }]
      : []),
  ]
  const flaechen: VerlaufFlaeche[] = hatSpreizung
    ? [{ key: 'spreizung', label: LABEL.spreizung, farbe: CHART_COLORS.spreizung }]
    : []

  const legendeZusatz: Record<string, string> = {}
  const setze = (label: string, text: string | null) => { if (text) legendeZusatz[label] = text }
  setze(LABEL.vorlauf, grad(letzter(g, 'vorlauf_c')))
  setze(LABEL.ruecklauf, grad(letzter(g, 'ruecklauf_c')))
  setze(LABEL.warmwasser, grad(letzter(g, 'warmwasser_c')))
  const sp = letzter(g, 'spreizung_k')
  setze(LABEL.spreizung, sp != null ? `${fmtZahl(sp, 1)} K` : null)

  return { rows, linien, flaechen, kopf: temperaturKopf(g), legendeZusatz }
}

/** Der Kopf des Diagramms aus dem Layer — ohne Ø Vorlauf kein Kopf (B10). */
export function temperaturKopf(g: WaermeTemperaturGeraet): string | null {
  if (g.vorlauf_mittel_c == null) return null
  const teile = [`Ø Vorlauf ${fmtZahl(g.vorlauf_mittel_c, 1)} °C`]
  if (g.spreizung_mittel_k != null) teile.push(`Ø Spreizung ${fmtZahl(g.spreizung_mittel_k, 1)} K`)
  const stunden = g.betriebsstunden === 1 ? '1 Betriebsstunde' : `${g.betriebsstunden} Betriebsstunden`
  return `${teile.join(' · ')} (${stunden})`
}

/** Die Zeile unter dem Diagramm für Geräte mit zugeordnetem Temperatur-Sensor ohne Stundenmittel (B10, §5). */
export function ohneKanalZeilen(t: WaermeTemperaturStunden | null | undefined): { label: string; wert: string }[] {
  return (t?.ohne_kanal ?? []).map((o) => ({
    label: o.bezeichnung,
    wert: 'keine Stundenwerte — Sensor ohne Langzeitstatistik in Home Assistant',
  }))
}
