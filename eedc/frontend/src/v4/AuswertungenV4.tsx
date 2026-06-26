/**
 * AuswertungenV4 — Dispatcher der Auswertungen-(Wie-)Achse.
 *
 * Sub-Tabs (route-getrieben `:sub`): Finanzen · ROI · Prognose · CO₂ · Tabelle
 * (Anzeige-Reihenfolge, Default Finanzen — Gernot-Entscheid D1, SPEC-AUSWERTUNGEN
 * §0/§1). Bau-Reihenfolge startete bei Tabelle (SoT-Abhängigkeit). Shell = geteilte
 * `ViewShell` + `IASubTabBar` (SoT). Alle fünf Sub-Sichten gebaut; unbekannte Subs
 * → Redirect auf Finanzen (Default).
 */
import { Navigate, useParams } from 'react-router-dom'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'
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

export default function AuswertungenV4() {
  const { sub = 'finanzen' } = useParams<{ sub: string }>()

  // Wie-Achse (Sub-Tabs, route-getrieben) über die geteilte IASubTabBar (SoT).
  const nav = (
    <IASubTabBar items={SUBS.map((s) => ({ key: s.key, label: s.label, to: `/v4/auswertungen/${s.key}` }))} />
  )

  // Index oder unbekannter Sub → Default (Finanzen).
  if (!SUBS.some((s) => s.key === sub)) return <Navigate to="/v4/auswertungen/finanzen" replace />

  const inhalt =
    sub === 'finanzen' ? (
      // Finanz-Übersicht (FinanzenTab) + SOLL/HABEN-T-Konto (Monat|Jahr) + Berichte.
      <AuswertungenFinanzenV4 />
    ) : sub === 'tabelle' ? (
      // SoT der Wie-Achse — volle Werte-Werkbank (WerteTabelle).
      <AuswertungenTabelleV4 />
    ) : sub === 'co2' ? (
      // CO₂-Bilanz/Äquivalente/Klimapositiv (IST-Tab CO2Tab, lose eingepasst).
      <AuswertungenCo2V4 />
    ) : sub === 'prognose' ? (
      // SOLL/IST + Quellen-Vergleich (G5) + PV-String-SOLL/IST (D4).
      <AuswertungenPrognoseV4 />
    ) : (
      // ROI — Rebuild-lite (RoiAnalyse-SoT, ohne Slider, D3). Einziger Rest-Sub.
      <AuswertungenRoiV4 />
    )

  return <ViewShell bar={nav}>{inhalt}</ViewShell>
}
