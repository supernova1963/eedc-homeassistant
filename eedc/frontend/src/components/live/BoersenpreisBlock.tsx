/**
 * BoersenpreisBlock — Kennzahlen + Zwei-Tage-Chart der Day-Ahead-Preise (#335).
 *
 * Der Block beantwortet die Frage, die hinter dem Community-Wunsch steht: „Wann
 * ist der Strom heute und morgen billig?" Die drei Kennzahlen darüber sind
 * dieselben, die seit v4.0.10 auch die HA-Sensoren melden (`eedc_preis_aktuell_cent`,
 * `…_optimierter_durchschnitt_cent`, die Schwelle als Attribut) — wer den Block
 * gegen seine Automation hält, sieht dieselben Zahlen.
 *
 * **Leitprinzip Trigger ≠ Strategie:** Der Block zeigt Preise. Er empfiehlt kein
 * Ladefenster, rechnet keine Ladeleistung und schlägt nichts vor — das bleibt
 * Sache des Nutzers in Home Assistant.
 */

import { useMemo } from 'react'
import type { BoersenpreisResponse } from '../../api/liveDashboard'
import { KpiStrip, type KpiStripItem } from '../blocks/KpiStrip'
import { BOERSENPREIS_KPI } from '../../lib/komponentenStyle'
import { fmtZahl } from '../../lib'
import BoersenpreisChart from './BoersenpreisChart'

/** Kennzahlen des Blocks — heute, sofern heute dabei ist. */
export function baueKennzahlen(daten: BoersenpreisResponse): KpiStripItem[] {
  const heute = daten.tage.find((t) => t.datum === daten.heute)
  if (!heute) return []

  const jetzt = daten.aktuelle_stunde != null
    ? heute.stunden.find((s) => s.stunde === daten.aktuelle_stunde)
    : undefined
  const guenstigeStunden = heute.stunden.filter((s) => s.unter_schwelle).length

  const kpis: KpiStripItem[] = []
  if (jetzt) {
    kpis.push({
      ...BOERSENPREIS_KPI.aktuell,
      value: fmtZahl(jetzt.preis_cent, 2),
      unit: 'ct/kWh',
      subtitle: jetzt.unter_schwelle ? 'unter der Günstig-Schwelle' : 'über der Günstig-Schwelle',
    })
  }
  if (heute.optimierter_durchschnitt_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.durchschnitt,
      value: fmtZahl(heute.optimierter_durchschnitt_cent, 2),
      unit: 'ct/kWh',
      subtitle: 'Tagesmittel ohne die 3 teuersten Stunden',
    })
  }
  if (heute.schwelle_cent != null) {
    kpis.push({
      ...BOERSENPREIS_KPI.schwelle,
      value: fmtZahl(heute.schwelle_cent, 2),
      unit: 'ct/kWh',
      // Die Zahl daneben ist die UNGEKAPPTE Zählung (N-103) — sie kann größer
      // als fünf sein, anders als der Rang in den älteren Sensoren.
      subtitle: `${guenstigeStunden} ${guenstigeStunden === 1 ? 'Stunde liegt' : 'Stunden liegen'} heute darunter`,
    })
  }
  return kpis
}

export default function BoersenpreisBlock({ daten }: { daten: BoersenpreisResponse }) {
  const kpis = useMemo(() => baueKennzahlen(daten), [daten])

  return (
    <div className="space-y-3">
      {kpis.length > 0 && <KpiStrip kpis={kpis} />}
      {daten.tage.length > 0 && <BoersenpreisChart daten={daten} />}
      {/* Fehlt ein Tag, sagt der Block warum — statt die halbe Achse leer zu
          lassen und Vollständigkeit zu suggerieren (ADR-002/P4). */}
      {daten.hinweis && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{daten.hinweis}</p>
      )}
      <p className="text-[10px] text-gray-400 dark:text-gray-500">
        Börsenpreise der Day-Ahead-Auktion ({daten.markt === 'AT' ? 'EPEX Österreich' : 'EPEX Deutschland'}),
        netto — ohne Steuern, Abgaben und Netzentgelte. Dein Lieferant rechnet
        andere Beträge ab; für die Frage, welche Stunde die günstige ist, zählt der Verlauf.
      </p>
    </div>
  )
}
