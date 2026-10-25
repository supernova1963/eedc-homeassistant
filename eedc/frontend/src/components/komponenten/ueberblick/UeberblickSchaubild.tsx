/**
 * UeberblickSchaubild — das Panorama mit den Energiefluss-Kacheln (P-433-2 E1).
 *
 * **Das Bild zeigt immer alle Gerätearten, deine Anlage zeigen die Kacheln**
 * (B2). Kacheln nur für Werte, die ankommen; was fehlt, nennt die Zeile unter
 * dem Bild mit dem Weg zur Datenquellen-Zuordnung.
 *
 * - **Dieselbe Kachel wie im Energiefluss** (`EnergieFlussKachel`, B1), im Bild
 *   mit `k = 1312 / W` skaliert (E-P2-6) — Größe und Schrift wie dort.
 * - **Hell/dunkel:** beide Panoramen liegen gestapelt, das Thema wählt per
 *   `dark:`-Opacity-Paar — dieselbe Bauform wie `EnergieFlussBackground`
 *   (Regel B), kein Theme-Hook, kein Nachlade-Blitz.
 * - **Linien** Kachelkante → Objekt mit Saum (Bau B Regel C, `ENERGIEFLUSS_SAUM`,
 *   nur hell); keine Partikel.
 * - **Tooltip** über `data-title` an der Kachel; der Touch-Hook ist einmal in
 *   `App.tsx` montiert (Ü11) — hier kein eigener.
 * - **Gruppen (Ü6):** Tipp auf «Innengeräte (n)» öffnet den vorhandenen
 *   Innengeräte-Abschnitt (`LiveInnengeraete`) unter dem Bild, auf
 *   «Wärmepumpen (n)» oder «Weitere (n)» eine einfache Liste — nicht das
 *   Energiefluss-Overlay (es kennt nur Live-Knoten).
 */
import { useEffect, useRef, useState } from 'react'
import { ENERGIEFLUSS_SAUM, KATEGORIE_FARBEN } from '../../../lib'
import { verbergeTouchTooltip } from '../../../hooks/useTouchTitleTooltip'
import { Button } from '../../ui'
import EnergieFlussKachel from '../../live/EnergieFlussKachel'
import EnergieFlussDefs from '../../live/EnergieFlussDefs'
import LiveInnengeraete from '../../live/LiveInnengeraete'
import { formatPower, kuerzeMitSuffix, liesLiteModus, zeichenBudget } from '../../live/EnergieFluss'
import type { LiveInnengeraet } from '../../../api/liveDashboard'
import { PANORAMA_BREITE, PANORAMA_HOEHE, WAERME_PANORAMA } from './waermePanoramaAnker'
import { kachelWertText, type UeberblickKachel } from './kachelAnker'
import { layoutUeberblick, type Platz, type UeberblickLayout } from './ueberblickLayout'

/** Startbreite bis zur ersten Messung (Desktop-Spalte); jsdom misst nie. */
const START_BREITE = 900

const GRUPPEN_NAME: Record<string, string> = {
  geraete: 'Wärmepumpen',
  innengeraete: 'Innengeräte',
  weitere: 'Weitere',
}

/**
 * Wert der Gruppenkachel — wie im Energiefluss die Σ-Leistung der Mitglieder:
 * «Wärmepumpen (n)» immer, «Innengeräte (n)» nur, wenn jedes Mitglied eine
 * Leistung hat (sonst wäre die Summe zu klein), «Weitere (n)» nie (gemischte
 * Einheiten: kW, °C, kWh). Leer statt eines Ersatzworts.
 */
function gruppenWert(p: Platz<UeberblickKachel>): { text: string; kw: number | null } {
  if (p.gruppe === 'weitere') return { text: '', kw: null }
  const werte = p.mitglieder.map((m) => m.leistungKw)
  if (werte.some((w) => w == null)) return { text: '', kw: null }
  const kw = werte.reduce<number>((s, w) => s + (w ?? 0), 0)
  return { text: formatPower(kw), kw }
}

/** Was eine Gruppenkachel zeigt. */
function gruppenKachel(p: Platz<UeberblickKachel>) {
  const n = p.mitglieder.length
  const name = GRUPPEN_NAME[p.gruppe ?? 'weitere']
  const tip = [`${name} (${n})`, ...p.mitglieder.map((m) => `• ${m.label}: ${m.wertText}${m.zweiteZeile ? ` (${m.zweiteZeile.text})` : ''}`)].join('\n')
  const erste = p.mitglieder[0]
  const wert = gruppenWert(p)
  return {
    name,
    icon: p.gruppe === 'weitere' ? 'wrench' : erste.icon,
    color: p.gruppe === 'weitere' ? KATEGORIE_FARBEN.waermepumpe : erste.color,
    isActive: wert.kw != null ? wert.kw > 0 : p.mitglieder.some((m) => m.isActive),
    wertText: wert.text,
    tip,
  }
}

function Linien({ layout }: { layout: UeberblickLayout<UeberblickKachel> }) {
  const k = layout.k
  return (
    <g pointerEvents="none">
      {[...layout.oben, ...layout.unten].map((p) => p.linie && (
        <g key={`linie-${p.key}`} data-linie={p.key}>
          <path
            data-saum
            d={`M ${p.linie.x1} ${p.linie.y1} L ${p.linie.x2} ${p.linie.y2}`}
            fill="none" stroke={ENERGIEFLUSS_SAUM} strokeWidth={3.5 * k} strokeOpacity={0.4}
            strokeLinecap="round" className="dark:opacity-0"
          />
          <path
            d={`M ${p.linie.x1} ${p.linie.y1} L ${p.linie.x2} ${p.linie.y2}`}
            fill="none" stroke={p.gruppe === 'weitere' ? KATEGORIE_FARBEN.waermepumpe : p.mitglieder[0].color}
            strokeWidth={1.5 * k} strokeOpacity={0.85} strokeLinecap="round"
          />
          <circle cx={p.linie.x2} cy={p.linie.y2} r={3 * k} fill={p.mitglieder[0].color} fillOpacity={0.85} />
        </g>
      ))}
    </g>
  )
}

function GruppenListe({ platz, onSchliessen }: { platz: Platz<UeberblickKachel>; onSchliessen: () => void }) {
  const titel = `${GRUPPEN_NAME[platz.gruppe ?? 'weitere']} (${platz.mitglieder.length})`
  const innen = platz.gruppe === 'innengeraete'
    ? platz.mitglieder.map((m) => m.innengeraet).filter((g): g is LiveInnengeraet => g != null)
    : null
  return (
    <div className="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 p-2" data-gruppen-liste={platz.key}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">{titel}</span>
        <Button type="button" variant="ghost" size="sm" onClick={onSchliessen}>schließen</Button>
      </div>
      {innen ? <LiveInnengeraete geraete={innen} /> : (
        <ul className="text-sm space-y-0.5">
          {platz.mitglieder.map((m) => (
            <li key={m.id} className="flex justify-between gap-2">
              <span className="text-gray-600 dark:text-gray-400 truncate min-w-0">{m.label}</span>
              <span className="text-gray-900 dark:text-white font-medium whitespace-nowrap">
                {m.wertText}{m.zweiteZeile ? ` · ${m.zweiteZeile.text}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export interface UeberblickSchaubildProps {
  kacheln: UeberblickKachel[]
  ohneSensor: string[]
}

export default function UeberblickSchaubild({ kacheln, ohneSensor }: UeberblickSchaubildProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [breite, setBreite] = useState(START_BREITE)
  const [lite] = useState(liesLiteModus)
  const [offen, setOffen] = useState<string | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((eintraege) => {
      for (const e of eintraege) if (e.contentRect.width > 0) setBreite(e.contentRect.width)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const layout = layoutUeberblick(kacheln, breite)
  const { dims, k } = layout
  const plaetze = [...layout.oben, ...layout.unten]
  const offenerPlatz = offen != null ? plaetze.find((p) => p.key === offen) ?? null : null

  return (
    <div ref={ref} className="w-full" data-ueberblick-schaubild>
      <svg viewBox={`0 0 ${PANORAMA_BREITE} ${PANORAMA_HOEHE}`} className="w-full h-auto block rounded-lg" role="img" aria-label="Schaubild Wärme/Klima">
        <defs><EnergieFlussDefs lite={lite} /></defs>
        <image
          data-panorama="tag" href={WAERME_PANORAMA.tag}
          x="0" y="0" width={PANORAMA_BREITE} height={PANORAMA_HOEHE}
          className="opacity-100 dark:opacity-0"
        />
        <image
          data-panorama="nacht" href={WAERME_PANORAMA.nacht}
          x="0" y="0" width={PANORAMA_BREITE} height={PANORAMA_HOEHE}
          className="opacity-0 dark:opacity-100"
        />
        <Linien layout={layout} />
        {plaetze.map((p) => {
          const einzeln = p.gruppe == null ? p.mitglieder[0] : null
          const g = einzeln ? null : gruppenKachel(p)
          const maxC = dims.labelMaxChars
          const label = einzeln
            ? (einzeln.label.length > maxC ? einzeln.label.slice(0, maxC - 2) + '…' : einzeln.label)
            : kuerzeMitSuffix(g!.name, ` (${p.mitglieder.length})`, zeichenBudget(dims.nodeW, dims.labelFontSize))
          const knopf = g ? {
            key: p.key,
            ariaLabel: `${g.name} (${p.mitglieder.length}): Liste öffnen`,
            onOeffnen: () => { verbergeTouchTooltip(); setOffen((o) => (o === p.key ? null : p.key)) },
          } : null
          return (
            <g key={p.key} transform={`translate(${p.x} ${p.y}) scale(${k})`} data-platz={p.key}>
              <EnergieFlussKachel
                x={0} y={0} dims={dims}
                label={label}
                icon={einzeln?.icon ?? g!.icon}
                color={einzeln?.color ?? g!.color}
                isActive={einzeln?.isActive ?? g!.isActive}
                wertText={einzeln ? kachelWertText(einzeln, dims) : g!.wertText}
                zweiteZeile={einzeln?.zweiteZeile ?? null}
                tip={einzeln?.tip ?? g!.tip}
                mitglieder={g ? p.mitglieder.length : undefined}
                knopf={knopf}
                lite={lite} bgVariant="haus"
              />
            </g>
          )
        })}
      </svg>
      {offenerPlatz && <GruppenListe platz={offenerPlatz} onSchliessen={() => setOffen(null)} />}
      {ohneSensor.length > 0 && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400" data-ohne-sensor>
          Ohne Sensor, deshalb ohne Kachel: {ohneSensor.join(' · ')} →{' '}
          <a href="#/einstellungen/datenquellen" className="text-primary-700 dark:text-primary-300 hover:underline">
            Datenquellen zuordnen
          </a>
        </p>
      )}
    </div>
  )
}
