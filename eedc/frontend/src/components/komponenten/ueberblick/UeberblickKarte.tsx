/**
 * UeberblickKarte — «Auf einen Blick» neben dem Schaubild (P-433-2 E2,
 * Gegenentwurf W7/W8).
 *
 * Eine Karte für das **gewählte** Gerät (E-P2-2): Kopf mit Name und Modus-Chip,
 * darunter nur Zeilen, die einen Wert haben (`!= null` — keine Zeile ohne Wert,
 * keine 0 für „nicht gemessen"), und der Anlagen-Ring.
 *
 * - **Heute** kommt aus zwei Quellen: Strom aus `heute_kwh_pro_komponente` der
 *   Live-Antwort (derselbe Tageswert wie der Energiefluss-Tooltip), Wärme und
 *   Arbeitszahl je Gerät aus dem Tag-Detail (`wp_geraete`, Rechenstelle des
 *   Wärme/Klima-Blocks). **Benannte Grenze:** ein Gerät ohne Strom-Beitrag heute
 *   hat dort keine Zeile — dann fehlen Wärme und AZ heute.
 * - **Anlagen-Ring = Gauge `eigenverbrauch`** (B9, E-P2-8): die EV-Quote der
 *   Anlage inklusive Speicher-Entladung — dieselbe Zahl wie im Cockpit, kein
 *   Wert je Gerät. Nur wenn die Live-Antwort sie liefert (Erzeugung > 0).
 * - **Gestrichen (W7):** Zusatzheizung, Betriebsstunden, Kompressor-Starts —
 *   dafür gibt es kein Feld; der Heizstab kommt mit P-433-3. Keine Kosten-,
 *   CO₂- oder Ersparniszahl (sie stehen in den Blöcken darunter).
 */
import type { ReactNode } from 'react'
import RingGauge from '../../charts/RingGauge'
import { CHART_COLORS, fmtZahl } from '../../../lib'
import { formatPower } from '../../live/EnergieFluss'
import ModusChip from '../../ui/ModusChip'
import type { LiveDashboardResponse, LiveWetterResponse } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { istPassivGekuehlt, stromHeute, wpKnoten } from './kachelAnker'

export interface UeberblickKarteProps {
  inv: Investition
  live: LiveDashboardResponse | null
  wetter: LiveWetterResponse | null
  tag: TagDetail | null
  /** Hat die Anlage mehr als eine Wärmepumpe? Dann zählt nur der exakte Tages-Key. */
  mehrereGeraete: boolean
}

function Zeile({ label, children, data }: { label: string; children: ReactNode; data: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-sm" data-zeile={data}>
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-semibold text-gray-900 dark:text-white whitespace-nowrap">{children}</span>
    </div>
  )
}

export default function UeberblickKarte({ inv, live, wetter, tag, mehrereGeraete }: UeberblickKarteProps) {
  const k = wpKnoten(live, inv.id)
  const leistungKw = k ? Math.max(k.erzeugung_kw ?? 0, k.verbrauch_kw ?? 0) : null
  const ww = live?.warmwasser_temperatur_c ?? null
  const aussen = wetter?.aktuell?.temperatur_c ?? null
  const strom = stromHeute(live, inv.id, mehrereGeraete)
  const zeile = tag?.wp_geraete?.find((z) => z.investition_id === inv.id) ?? null
  const azJe = zeile
    ? ([['Heizen', zeile.jaz_heizen], ['Warmwasser', zeile.jaz_warmwasser], ['Kühlen', zeile.jaz_kuehlen]] as const)
        .filter(([, v]) => v != null) as [string, number][]
    : []
  const ev = live?.gauges?.find((g) => g.key === 'eigenverbrauch') ?? null
  const hatHeute = strom != null || zeile?.waerme_kwh != null || zeile?.jaz != null || azJe.length > 0

  return (
    <div className="space-y-3" data-ueberblick-karte>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-gray-900 dark:text-white truncate min-w-0">{inv.bezeichnung}</span>
        {k?.betriebsmodus && k.betriebsmodus_label && (
          <ModusChip modus={k.betriebsmodus} label={k.betriebsmodus_label} passiv={istPassivGekuehlt(k, inv)} />
        )}
      </div>

      <div className="space-y-1">
        {leistungKw != null && <Zeile label="Leistung jetzt" data="leistung">{formatPower(leistungKw)}</Zeile>}
        {ww != null && <Zeile label="Warmwasser" data="warmwasser">{fmtZahl(ww, 1)} °C</Zeile>}
        {aussen != null && <Zeile label="Außentemperatur" data="aussen">{fmtZahl(aussen, 1)} °C</Zeile>}
      </div>

      {hatHeute && (
        <div className="space-y-1">
          <div className="text-xs font-semibold text-gray-500 dark:text-gray-400">Heute</div>
          {strom != null && <Zeile label="Strom" data="strom-heute">{fmtZahl(strom, 1)} kWh</Zeile>}
          {zeile?.waerme_kwh != null && <Zeile label="Wärme" data="waerme-heute">{fmtZahl(zeile.waerme_kwh, 1)} kWh</Zeile>}
          {zeile?.jaz != null && <Zeile label="Arbeitszahl" data="az-heute">{fmtZahl(zeile.jaz, 2)}</Zeile>}
          {azJe.map(([name, v]) => (
            <Zeile key={name} label={`Arbeitszahl ${name}`} data={`az-${name.toLowerCase()}`}>{fmtZahl(v, 2)}</Zeile>
          ))}
        </div>
      )}

      {ev && (
        <div className="flex items-center gap-3 pt-1" data-anlagen-ring>
          <RingGauge value={ev.wert} color={CHART_COLORS.eigenverbrauch} size={56} label={`${fmtZahl(ev.wert, 0)}`} />
          <span className="text-sm text-gray-600 dark:text-gray-400">
            Eigenverbrauch jetzt {fmtZahl(ev.wert, 0)} % (Anlage)
          </span>
        </div>
      )}
    </div>
  )
}
