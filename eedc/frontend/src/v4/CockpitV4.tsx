/**
 * CockpitV4 — Dispatcher der Cockpit-Zeit-Achse.
 *
 * „Monat" ist das ausgearbeitete Referenz-Muster (→ {@link CockpitMonatV4}). Alle
 * übrigen Zeit-Sichten (Live/Tag/Jahr/Aussicht) sind noch NICHT pattern-treu
 * gebaut und zeigen einen Platzhalter, bis ihre echten Sichten nach Phase 3
 * folgen (Tag/Jahr = Varianten von Monat). Bewusst KEIN Vorab-Gerüst, das von der
 * entschiedenen Struktur driftet (vgl. IASkeleton-Pflege-Timing).
 */
import { useParams } from 'react-router-dom'
import { Card } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import CockpitMonatV4 from './CockpitMonatV4'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'

const ZEITEN: { key: string; label: string }[] = [
  { key: 'live', label: 'Live' },
  { key: 'tag', label: 'Tag' },
  { key: 'monat', label: 'Monat' },
  { key: 'jahr', label: 'Jahr/Gesamt' },
  { key: 'aussicht', label: 'Aussicht' },
]

export default function CockpitV4() {
  const { zeit = 'monat' } = useParams<{ zeit: string }>()
  const { selectedAnlageId } = useSelectedAnlage()

  // Zeit-Achse (Sub-Tabs, route-getrieben) über die geteilte IASubTabBar (SoT).
  const zeitNav = (
    <IASubTabBar items={ZEITEN.map((z) => ({ key: z.key, label: z.label, to: `/v4/cockpit/${z.key}` }))} />
  )

  const inhalt =
    zeit === 'monat' ? (
      // Einziges ausgearbeitetes Muster — Tages-Granularität, lädt selbst.
      <CockpitMonatV4 anlageId={selectedAnlageId} />
    ) : (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Die Zeit-Sicht „{ZEITEN.find((z) => z.key === zeit)?.label ?? zeit}" wird in einem späteren
            IA-v4-Slice mit echten Daten verdrahtet.
          </p>
        </Card>
      </div>
    )

  return <ViewShell bar={zeitNav}>{inhalt}</ViewShell>
}
