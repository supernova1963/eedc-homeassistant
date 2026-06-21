/**
 * Komponenten-Analyse-Registry (IA v4 Phase A.2 — IST-getreuer Umbau).
 *
 * Manche Komponenten-Blöcke (vor allem ⑤ Vergleich, teils ④ Verlauf) tragen
 * **typ-spezifische IST-Analysen**, die sich NICHT auf generische Adapter-Daten
 * reduzieren lassen (z. B. PV-SOLL/IST pro String, WP-Saison-Toggle). Statt sie
 * generisch nachzubauen (führte zu Platzhaltern, die nur in kleinen Teilen dem
 * IST entsprachen), rendert der Hub hier die **echten IST-Komponenten** direkt
 * — „Umbau, keine Verschlechterung": alle IST-Informationen bleiben erhalten,
 * nur in die neue, einheitliche Block-Struktur eingebettet.
 *
 * Mechanik: pro Typ optionale Block-Renderer. Ist einer gesetzt, ersetzt er den
 * generischen Block (Adapter-Daten); sonst greift der generische Pfad. Die
 * geteilten IST-Analyse-Komponenten leben in `components/` (Flag-Reinheit) und
 * werden auch vom IST-Dashboard genutzt — keine zweite Kopie.
 *
 * Stand: PV als getreues Muster (Vergleich = SOLL-IST pro String). Speicher/WP/
 * E-Auto/BKW/Sonstiges ziehen nach demselben Muster nach (je IST-Analyse).
 */
import type { ReactNode } from 'react'
import { PVStringVergleich } from '../components/pv'

export interface KompAnalyse {
  /** Block ④ Verlauf — typ-eigene IST-Charts statt generischem Adapter-Verlauf. */
  verlauf?: (anlageId: number) => ReactNode
  /** Block ⑤ Vergleich — typ-eigene IST-Vergleichsanalyse (z. B. PV-String-SOLL/IST). */
  vergleich?: (anlageId: number) => ReactNode
}

export const KOMPONENTEN_ANALYSE: Record<string, KompAnalyse> = {
  // PV-Anlage: SOLL-IST-Vergleich pro String (PVGIS-Prognose vs. gemessen) —
  // wiederverwendete IST-Komponente, self-fetch über anlageId.
  'pv-module': {
    vergleich: (anlageId) => <PVStringVergleich anlageId={anlageId} embed />,
  },
}
