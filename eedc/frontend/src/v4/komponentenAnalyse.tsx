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
import { ExternalLink } from 'lucide-react'
import { PVStringVergleich } from '../components/pv'
import { SpeicherVerlaufIST, SpeicherVergleichIST } from './SpeicherVerlaufIST'
import { WaermepumpeVerlaufIST, WaermepumpeVergleichIST, WaermepumpeWirtschaftlichkeitIST } from './WaermepumpeHubBloecke'
import { EAutoVerlaufIST, EAutoVergleichIST, EAutoWirtschaftlichkeitIST } from './EAutoHubBloecke'
import { BkwVerlaufIST, BkwVergleichIST } from './BkwHubBloecke'
import { WallboxWirtschaftlichkeitIST } from './WallboxHubBloecke'
import type { Investition } from '../types'

export interface KompAnalyse {
  /** Block ④ Verlauf — typ-eigene IST-Charts statt generischem Adapter-Verlauf.
   *  `inv` = das im Hub aktive Gerät (Mehrgeräte-Selektor); für Single-Aggregate
   *  (PV) irrelevant, für Speicher/WP/… die Geräte-Auswahl. */
  verlauf?: (anlageId: number, inv?: Investition) => ReactNode
  /** Block ⑤ Vergleich — typ-eigene IST-Vergleichsanalyse (z. B. PV-String-SOLL/IST). */
  vergleich?: (anlageId: number, inv?: Investition) => ReactNode
  /** Block „Wirtschaftlichkeit" — Kostenvergleich/ROI/Amortisation (eigene Heimat
   *  im Hub statt Parken in Auswertungen; WP=vs Gas, Wallbox=ROI, E-Auto=vs Benzin). */
  wirtschaftlichkeit?: (anlageId: number, inv?: Investition) => ReactNode
}

export const KOMPONENTEN_ANALYSE: Record<string, KompAnalyse> = {
  // PV-Anlage: SOLL-IST-Vergleich pro String (PVGIS-Prognose vs. gemessen) —
  // wiederverwendete IST-Komponente, self-fetch über anlageId.
  'pv-module': {
    // D4 „beides": scoped SOLL/IST pro String hier (Embed) + Cross-Link auf die
    // volle Prognose-Analyse (Quellen-Vergleich/MAE-MAPE) in Auswertungen/Prognose.
    vergleich: (anlageId) => (
      <div className="space-y-3">
        <PVStringVergleich anlageId={anlageId} embed />
        <a href="#/v4/auswertungen/prognose" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          <ExternalLink className="h-4 w-4" /> Volle Prognose-Analyse (Quellen-Vergleich, MAE/MAPE) →
        </a>
      </div>
    ),
  },
  // Speicher: IST-Zeitreihen (η-12M-Degradation, Vollzyklen, Arbitrage-Stapel)
  // im Verlauf; ⑤ = Jahres-Energiebilanz (Ladung-Herkunft ⟷ Entladung+Verlust).
  speicher: {
    verlauf: (anlageId, inv) => <SpeicherVerlaufIST anlageId={anlageId} inv={inv} />,
    vergleich: (anlageId, inv) => <SpeicherVergleichIST anlageId={anlageId} inv={inv} />,
  },
  // Wärmepumpe: ④ Wärme/Monat+Tabelle · ⑤ Monats-/Saisonvergleich (JAZ⇄Strom) ·
  // Wirtschaftlichkeit = Kostenvergleich vs. Gas/Öl.
  waermepumpe: {
    verlauf: (anlageId, inv) => <WaermepumpeVerlaufIST anlageId={anlageId} inv={inv} />,
    vergleich: (anlageId, inv) => <WaermepumpeVergleichIST anlageId={anlageId} inv={inv} />,
    wirtschaftlichkeit: (anlageId, inv) => <WaermepumpeWirtschaftlichkeitIST anlageId={anlageId} inv={inv} />,
  },
  // E-Auto: ④ km/Monat + Ladung/Monat (PV/Netz/Extern) + Tabelle · ⑤ Ladung
  // nach Quelle/Jahr (PV-Anteil-Entwicklung) · Wirtschaftlichkeit = vs. Benzin.
  'e-auto': {
    verlauf: (anlageId, inv) => <EAutoVerlaufIST anlageId={anlageId} inv={inv} />,
    vergleich: (anlageId, inv) => <EAutoVergleichIST anlageId={anlageId} inv={inv} />,
    wirtschaftlichkeit: (anlageId, inv) => <EAutoWirtschaftlichkeitIST anlageId={anlageId} inv={inv} />,
  },
  // Balkonkraftwerk: ④ Erzeugung/Monat + integ. Speicher + Tabelle · ⑤ Verwendung/Jahr
  // (EV-Quoten-Entwicklung). Entgangener Erlös/Spez. Ertrag = ① Kennzahlen (Adapter).
  balkonkraftwerk: {
    verlauf: (anlageId, inv) => <BkwVerlaufIST anlageId={anlageId} inv={inv} />,
    vergleich: (anlageId, inv) => <BkwVergleichIST anlageId={anlageId} inv={inv} />,
  },
  // Wallbox: ④/⑤ generisch (Heimladung/Monat bzw. /Jahr — IMD trägt nur die
  // Summe); Wirtschaftlichkeit = Kostenvergleich Heim vs. extern + ROI + Amortisation.
  wallbox: {
    wirtschaftlichkeit: (anlageId, inv) => <WallboxWirtschaftlichkeitIST anlageId={anlageId} inv={inv} />,
  },
}
