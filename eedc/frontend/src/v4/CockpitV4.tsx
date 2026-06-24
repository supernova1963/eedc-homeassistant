/**
 * CockpitV4 — Dispatcher der Cockpit-Zeit-Achse.
 *
 * „Monat" (Referenz-Muster, → {@link CockpitMonatV4}), „Live" (→ {@link
 * CockpitLiveV4}, A.3), „Aussicht" (→ {@link CockpitAussichtV4}, A.4), „Tag"
 * (→ {@link CockpitTagV4}) und „Jahr" (→ {@link CockpitJahrV4}) sind als Monat-
 * Varianten pattern-treu gebaut.
 */
import { useParams } from 'react-router-dom'
import { Card } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import CockpitMonatV4 from './CockpitMonatV4'
import CockpitLiveV4 from './CockpitLiveV4'
import CockpitAussichtV4 from './CockpitAussichtV4'
import CockpitTagV4 from './CockpitTagV4'
import CockpitJahrV4 from './CockpitJahrV4'
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
      // Referenz-Muster — Tages-Granularität, lädt selbst.
      <CockpitMonatV4 anlageId={selectedAnlageId} />
    ) : zeit === 'live' ? (
      // A.3 — Echtzeit-Sicht (reiches IST-Layout, lose ins Skelett eingepasst).
      <CockpitLiveV4 anlageId={selectedAnlageId} />
    ) : zeit === 'aussicht' ? (
      // A.4 — Projektions-Sicht (Vorwärts-Teleskop, Horizont-Selektor).
      <CockpitAussichtV4 anlageId={selectedAnlageId} />
    ) : zeit === 'tag' ? (
      // Monat-Variante auf Tages-/Stunden-Granularität.
      <CockpitTagV4 anlageId={selectedAnlageId} />
    ) : zeit === 'jahr' ? (
      // Monat-Variante auf Jahres-/Monats-Granularität (Σ der 12 Monate).
      <CockpitJahrV4 anlageId={selectedAnlageId} />
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
