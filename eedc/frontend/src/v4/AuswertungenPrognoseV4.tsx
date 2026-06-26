/**
 * AuswertungenPrognoseV4 — Prognose-vs-IST-Auswertung (A.5).
 *
 * Drei Blöcke (Muster, BlockShell) — alle drei IST-Komponenten unverändert
 * wiederverwendet (eine Code-Wahrheit, Feld-Sperren bleiben damit gewahrt:
 * SFML NICHT im Genauigkeits-Ranking, Solcast-Spalte erhalten):
 *  ① „SOLL/IST (PVGIS)" — `PrognoseVsIst` (Jahres-SOLL/IST/Abweichung, MAE/MAPE,
 *     gespeicherte vs. live-Prognose, Monats-Chart, „Prognose speichern").
 *  ② „Quellen-Vergleich" (G5) — `PrognoseVergleichTab` (OM/eedc/Solcast, MAE/MBE
 *     stratifiziert + 24h-Profil); in A.4 bewusst aus Cockpit/Aussicht entfernt →
 *     gehört hierher.
 *  ③ „PV-Anlage SOLL/IST pro String" (D4) — `PVAnlageTab`, volle Sicht hier
 *     (Teaser + Cross-Link bleibt zusätzlich in Komponenten/PV).
 */
import { Target, GitCompareArrows, Sun } from 'lucide-react'
import { LoadingSpinner, Card } from '../components/ui'
import { BlockShell } from '../components/blocks/BlockShell'
import type { Block } from '../components/blocks/types'
import PrognoseVsIst from '../pages/PrognoseVsIst'
import PrognoseVergleichTab from '../pages/aussichten/PrognoseVergleichTab'
import { PVAnlageTab } from '../pages/auswertung/PVAnlageTab'
import { useSelectedAnlage } from '../hooks'
import { useAuswertungBasis } from './useAuswertungBasis'
import { AuswertungKopf } from './AuswertungKopf'

export default function AuswertungenPrognoseV4() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const basis = useAuswertungBasis(selectedAnlageId)

  if (anlagenLoading || basis.loading) return <LoadingSpinner text="Lade Prognose-Daten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  // Header-Jahrfilter steuert den PV-String-Block; selbst-gescopte Blöcke (①/②)
  // tragen ihre eigenen Zeit-Controls.
  const selectedYear: number | 'all' = basis.jahr === 'alle' ? 'all' : basis.jahr

  const bloecke: Block[] = [
    {
      id: 'sollist', title: 'SOLL/IST (PVGIS)', icon: Target, defaultOpen: true,
      summary: 'Jahres-SOLL/IST + Genauigkeit (MAE/MAPE), gespeicherte vs. live-Prognose',
      render: () => <PrognoseVsIst />,
    },
    ...(selectedAnlageId
      ? [
          {
            id: 'quellen', title: 'Quellen-Vergleich (OM · eedc · Solcast)', icon: GitCompareArrows, defaultOpen: false,
            summary: 'Multi-Quellen-Genauigkeit (MAE/MBE), wetter-stratifiziert',
            render: () => <PrognoseVergleichTab anlageId={selectedAnlageId} />,
          } as Block,
          {
            id: 'pvstrings', title: 'PV-Anlage — SOLL/IST pro String', icon: Sun, defaultOpen: false,
            summary: 'String-Performance gegen PVGIS-Prognose',
            render: () => (
              <PVAnlageTab
                anlageId={selectedAnlageId}
                selectedYear={selectedYear}
                verfuegbareJahre={basis.jahre}
                zeitraumLabel={basis.zeitraumLabel}
              />
            ),
          } as Block,
        ]
      : []),
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Prognose vs. IST" jahr={basis.jahr} setJahr={basis.setJahr} jahre={basis.jahre} />
      <BlockShell bloecke={bloecke} persistKey="v4-auswertungen-prognose" />
    </div>
  )
}
