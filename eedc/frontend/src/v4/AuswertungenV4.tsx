/**
 * AuswertungenV4 — Dispatcher der Auswertungen-(Wie-)Achse.
 *
 * Sub-Tabs (route-getrieben `:sub`): Finanzen · ROI · Prognose · CO₂ · Tabelle
 * (Anzeige-Reihenfolge, Default Finanzen — Gernot-Entscheid D1, SPEC-AUSWERTUNGEN
 * §0/§1). Shell = geteilte `ViewShell` + `IASubTabBar` (SoT); unbekannte Subs
 * → Redirect auf Finanzen (Default).
 *
 * R18-3 (Option B, Gernot 2026-07-10): Der Jahr-Filter lebt HIER — EINE
 * Steuerleiste unter der Sub-Tab-Bar nach dem Community-Muster (`CommunityV4`),
 * `useAuswertungBasis` wird einmal im Dispatcher gehalten und als `basis`-Prop
 * an Finanzen/Prognose/CO₂ gereicht. Die Auswahl überlebt so den Sub-Tab-Wechsel
 * (vorher: useState je Sub-Sicht, Reset bei jedem Wechsel). ROI (immer
 * Gesamt-Lebensdauer) und Tabelle (eigene `WerkbankZeitraum`-Bereichswahl)
 * blenden die Leiste aus — wie Community bei Trends/Statistiken. Blöcke, die dem
 * Filter nicht folgen können, kennzeichnen das sichtbar (`ZeitraumHinweis`).
 * KEIN globaler Achsen-Zeitraum (verworfen, s. Triage R18-3 §3).
 */
import { Navigate, useParams } from 'react-router-dom'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'
import { Select } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import AuswertungenTabelleV4 from './AuswertungenTabelleV4'
import AuswertungenCo2V4 from './AuswertungenCo2V4'
import AuswertungenFinanzenV4 from './AuswertungenFinanzenV4'
import AuswertungenPrognoseV4 from './AuswertungenPrognoseV4'
import AuswertungenRoiV4 from './AuswertungenRoiV4'

const SUBS: { key: string; label: string }[] = [
  { key: 'finanzen', label: 'Finanzen' },
  { key: 'roi', label: 'ROI' },
  { key: 'prognose', label: 'Prognose' },
  { key: 'co2', label: 'CO₂' },
  { key: 'tabelle', label: 'Tabelle' },
]
// Sub-Tabs mit Jahr-Filter (ROI = Lebensdauer, Tabelle = eigene Bereichswahl).
const FILTER_SUBS = new Set(['finanzen', 'prognose', 'co2'])

export default function AuswertungenV4() {
  const { sub = 'finanzen' } = useParams<{ sub: string }>()

  // Basis (Monatsdaten + Jahr-Filter) im Dispatcher — Community-Muster: einmal
  // laden/halten, an die Sub-Sichten reichen (Auswahl bleibt beim Tab-Wechsel).
  const { selectedAnlageId } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  // Wie-Achse (Sub-Tabs, route-getrieben) über die geteilte IASubTabBar (SoT).
  const nav = (
    <IASubTabBar items={SUBS.map((s) => ({ key: s.key, label: s.label, to: `/v4/auswertungen/${s.key}` }))} />
  )

  // Index oder unbekannter Sub → Default (Finanzen).
  if (!SUBS.some((s) => s.key === sub)) return <Navigate to="/v4/auswertungen/finanzen" replace />

  // Steuerleiste (Jahr-Filter) unter den Sub-Tabs — nur für Subs, die ihn befolgen.
  const steuerleiste = FILTER_SUBS.has(sub) ? (
    <div className="bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-3 sm:px-6">
      <div className="max-w-[1920px] mx-auto flex items-center justify-end gap-3 py-2 flex-wrap">
        {/* B15: Filter-Leisten-Kontrolle → Select-SoT in der 32-px-steuer-Variante. */}
        <Select
          steuer
          value={basis.jahr === 'alle' ? '' : String(basis.jahr)}
          onChange={(e) => basis.setJahr(e.target.value ? Number(e.target.value) : 'alle')}
          aria-label="Jahr filtern"
          options={[{ value: '', label: 'Alle Jahre' }, ...basis.jahre.map((j) => ({ value: String(j), label: String(j) }))]}
        />
      </div>
    </div>
  ) : null

  const bar = <>{nav}{steuerleiste}</>

  const inhalt =
    sub === 'finanzen' ? (
      // Finanz-Übersicht (FinanzenTab) + SOLL/HABEN-T-Konto (Monat|Jahr) + Berichte.
      <AuswertungenFinanzenV4 basis={basis} />
    ) : sub === 'tabelle' ? (
      // SoT der Wie-Achse — volle Werte-Werkbank (WerteTabelle, eigene Bereichswahl).
      // basis liefert Monatsdaten/Strompreise (Paket Q: kein Eigen-Fetch-Trio mehr).
      <AuswertungenTabelleV4 basis={basis} />
    ) : sub === 'co2' ? (
      // CO₂-Bilanz/Äquivalente/Klimapositiv (IST-Tab CO2Tab, lose eingepasst).
      <AuswertungenCo2V4 basis={basis} />
    ) : sub === 'prognose' ? (
      // SOLL/IST + Quellen-Vergleich (G5) + PV-String-SOLL/IST (D4).
      <AuswertungenPrognoseV4 basis={basis} />
    ) : (
      // ROI — Rebuild-lite (RoiAnalyse-SoT, ohne Slider, D3). Immer Lebensdauer.
      <AuswertungenRoiV4 />
    )

  return <ViewShell bar={bar}>{inhalt}</ViewShell>
}
