/**
 * KomponentenV4 — Dispatcher der Komponenten-(Was-)Achse.
 *
 * Sub-Tabs pro Komponententyp, **nur wenn die Anlage den Typ hat** (K-B2),
 * Reihenfolge via `compareTyp` (K-B3). `/v4/komponenten` (ohne Typ) leitet auf
 * den ersten verfügbaren Typ; `:typ` rendert {@link KomponentenTypV4}. Label/Icon
 * aus dem Identitäts-SoT `KOMPONENTEN_IDENTITAET`.
 */
import { useEffect, useMemo, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { Card, LoadingSpinner } from '../components/ui'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { useSelectedAnlage } from '../hooks'
import { compareTyp } from '../lib/constants'
import { KOMPONENTEN_IDENTITAET } from '../lib/komponentenStyle'
import { investitionenApi } from '../api/investitionen'
import { ViewShell } from './ViewShell'
import KomponentenTypV4 from './KomponentenTypV4'

/** Hub-Tabs: key (URL) → Investitionstyp. PV-Anlage = Aggregat aus
 *  pv-module/wechselrichter; BKW eigener Tab. Sortiert über compareTyp. */
const HUB_TABS: { key: string; typ: string }[] = [
  { key: 'pv-anlage', typ: 'pv-module' },
  { key: 'speicher', typ: 'speicher' },
  { key: 'bkw', typ: 'balkonkraftwerk' },
  { key: 'waermepumpe', typ: 'waermepumpe' },
  { key: 'wallbox', typ: 'wallbox' },
  { key: 'e-auto', typ: 'e-auto' },
  { key: 'sonstiges', typ: 'sonstiges' },
].sort(compareTyp)

export default function KomponentenV4() {
  const { typ: routeKey } = useParams<{ typ: string }>()
  const { selectedAnlageId } = useSelectedAnlage()
  const [vorhandeneTypen, setVorhandeneTypen] = useState<Set<string> | null>(null)

  // Aktive Investitionen → welche Typen hat die Anlage (Tab-Sichtbarkeit, K-B2).
  useEffect(() => {
    if (!selectedAnlageId) { setVorhandeneTypen(new Set()); return }
    let ab = false
    investitionenApi.list(selectedAnlageId, undefined, true)
      .then((invs) => { if (!ab) setVorhandeneTypen(new Set(invs.map((i) => i.typ))) })
      .catch(() => { if (!ab) setVorhandeneTypen(new Set()) })
    return () => { ab = true }
  }, [selectedAnlageId])

  // PV-Tab erscheint auch bei reinem Wechselrichter-Bestand (UI-Aggregat).
  const verfuegbar = useMemo(() => {
    if (!vorhandeneTypen) return []
    return HUB_TABS.filter((t) =>
      t.typ === 'pv-module'
        ? vorhandeneTypen.has('pv-module') || vorhandeneTypen.has('wechselrichter')
        : vorhandeneTypen.has(t.typ))
  }, [vorhandeneTypen])

  const nav = (
    <IASubTabBar items={verfuegbar.map((t) => ({
      key: t.key, label: KOMPONENTEN_IDENTITAET[t.typ].label, to: `/v4/komponenten/${t.key}`,
    }))} />
  )

  if (vorhandeneTypen === null) {
    return <ViewShell><div className="p-3 sm:p-6"><LoadingSpinner text="Lade Komponenten…" /></div></ViewShell>
  }
  if (verfuegbar.length === 0) {
    return (
      <ViewShell>
        <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
          <Card><p className="text-sm text-gray-500 dark:text-gray-400">
            Diese Anlage hat noch keine erfassten Komponenten.
          </p></Card>
        </div>
      </ViewShell>
    )
  }

  // Index oder unbekannter Typ → erster verfügbarer Typ.
  const aktiv = verfuegbar.find((t) => t.key === routeKey)
  if (!aktiv) return <Navigate to={`/v4/komponenten/${verfuegbar[0].key}`} replace />

  return (
    <ViewShell bar={nav}>
      <KomponentenTypV4 typ={aktiv.typ} anlageId={selectedAnlageId} />
    </ViewShell>
  )
}
