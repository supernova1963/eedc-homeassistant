/**
 * EnergieFlussKachel — die EINE Kachel des Energieflusses (SoT seit P-433-2 E0).
 *
 * Herausgelöst aus `EnergieFluss.tsx` (24.10.2026), **bitgleich**: der
 * Live-Energiefluss zeichnet seine Knoten damit, der Hub-Block «Überblick»
 * (Konzept #433 Stufe 2, B1: dieselbe Komponente, keine Kopie) legt sie auf das
 * Panorama. Gewächtert von `EnergieFluss.kachel-sot.test.tsx` (18-Zellen-Matrix,
 * Snapshot `test/energiefluss-kacheln.snapshot.json`) und — für den Klickpfad,
 * den die Serialisierung nicht sieht — `EnergieFluss.gruppen.test.tsx`.
 *
 * **Was die Kachel weiß und was nicht:** sie zeichnet, was der Aufrufer ihr
 * gibt (Wert, zweite Zeile, Pegel, Tooltip, gekürzter Name). Tooltip-Text,
 * Label-Kürzung und die Frage „SoC, Modus oder Auto?" bleiben beim Aufrufer —
 * sie hängen an der Live-Antwort, nicht am Bild. Die zweite Zeile ist der EINE
 * Ort für den späteren Leerlauf-Chip (B10, P-433-1).
 *
 * Koordinaten in Einheiten der Zeichenfläche des Aufrufers; `x`/`y` ist die
 * Kachelmitte. Ein Aufrufer mit anderem Maßstab (Panorama 1312 breit) skaliert
 * die Kachel als Ganzes (`transform`), nie ihre Maße einzeln.
 */
import type React from 'react'
import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug, Heater, Droplets, Snowflake, Fan, Waves, Thermometer } from 'lucide-react'
import { useChartTheme } from '../../context/ThemeContext'
import type { LayoutDims } from './energieFlussLayout'
import type { BgVariant } from './EnergieFluss'

/** Versatz der hinteren Stapel-Rechtecke einer Gruppenkachel (Muster `stack: 7`, detLAN #138). */
export const STAPEL_VERSATZ = 7

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun, zap: Zap, battery: Battery, car: Car, plug: Plug,
  flame: Flame, wrench: Wrench, home: Home, heater: Heater, droplets: Droplets,
  // #398 Stufe 3: das Symbol wechselt mit dem Betriebsmodus — und AUSSCHLIESSLICH
  // hier. Der Energiefluss ist die einzige Fläche, die ohnehin „jetzt" meint;
  // `lib/komponentenStyle.ts` bleibt unberührt (Entscheid Maintainer 27.08.:
  // in Listen, Kacheln und Auswertungen behauptete ein wechselndes Symbol eine
  // Momentaktualität, die die Zahl daneben nicht hat).
  // Die Namen kommen aus dem Backend-Kanon `BETRIEBSMODUS_ICON`.
  snowflake: Snowflake, fan: Fan, waves: Waves,
  // P-433-2: die Wert-Kachel „Außentemperatur" im Hub-Überblick — kein
  // Backend-Name, der Live-Builder liefert dieses Symbol nie.
  thermometer: Thermometer,
}

/** Render Lucide Icon als React-Element */
export function IconElement({ name, size, color, className }: { name: string; size: number; color?: string; className?: string }) {
  const Icon = ICON_MAP[name]
  if (!Icon) return null
  return <Icon width={size} height={size} color={color} className={className} />
}

/** Gruppenkachel als Knopf (§A5): Key für `data-gruppe`, Beschriftung, Aktion. */
export interface KachelKnopf {
  key: string
  ariaLabel: string
  onOeffnen: () => void
}

export interface EnergieFlussKachelProps {
  /** Kachelmitte. */
  x: number
  y: number
  dims: LayoutDims
  /** Der angezeigte (schon gekürzte) Name. */
  label: string
  icon: string
  /** Rollenfarbe; inaktiv zeichnet die Kachel in der Referenzfarbe des Themas. */
  color: string
  isActive: boolean
  wertText: string
  /** SoC · Betriebsmodus · Auto-Zeile — `fill: null` ⇒ graue Klasse statt Farbe. */
  zweiteZeile?: { text: string; fill: string | null } | null
  /** Füllung von unten (SoC oder PV-Auslastung — nie beide an einem Gerät). */
  pegel?: { prozent: number; fill: string; opacity: number } | null
  tip: string
  /** Anzahl der Mitglieder einer Gruppe — gesetzt ⇒ Stapel-Optik. */
  mitglieder?: number
  /** Nur Gruppen mit Handler sind Knöpfe (kein Knopf ohne Wirkung). */
  knopf?: KachelKnopf | null
  lite: boolean
  bgVariant: BgVariant
}

export default function EnergieFlussKachel({
  x, y, dims, label, icon, color, isActive, wertText, zweiteZeile, pegel, tip, mitglieder, knopf, lite, bgVariant,
}: EnergieFlussKachelProps) {
  const achsen = useChartTheme()
  const { nodeW: NODE_W, nodeH: NODE_H, nodeR: NODE_R } = dims
  const nx = x - NODE_W / 2
  const ny = y - NODE_H / 2
  const oeffnen = knopf?.onOeffnen ?? null
  const knopfProps = knopf ? {
    role: 'button',
    tabIndex: 0,
    'aria-label': knopf.ariaLabel,
    'data-gruppe': knopf.key,
    onClick: knopf.onOeffnen,
    onKeyDown: (e: React.KeyboardEvent<SVGGElement>) => {
      if (e.key !== 'Enter' && e.key !== ' ') return
      e.preventDefault()
      knopf.onOeffnen()
    },
  } : {}

  return (
    <g
      className={oeffnen ? 'group cursor-pointer outline-none' : 'cursor-default'}
      data-title={tip}
      {...knopfProps}
    >
      <title>{tip}</title>

      {/* Tastatur-Fokus der Gruppenkachel: ein Rahmen, nur bei :focus-visible. */}
      {oeffnen && (
        <rect
          data-fokusrahmen
          x={nx - 3} y={ny - STAPEL_VERSATZ - 3}
          width={NODE_W + STAPEL_VERSATZ + 6} height={NODE_H + STAPEL_VERSATZ + 6}
          rx={NODE_R + 2}
          fill="none"
          strokeWidth={1.5}
          className="stroke-emerald-500 opacity-0 group-focus-visible:opacity-100"
        />
      )}

      {/* Stapel-Optik der Gruppe (detLAN #138, Muster `stack: 7`): zwei
          versetzte Rahmen hinter der Kachel — „hier liegen mehrere". */}
      {mitglieder ? [STAPEL_VERSATZ, STAPEL_VERSATZ / 2].map((v, i) => (
        <rect
          key={`stapel-${v}`}
          data-stapel={i + 1}
          x={nx + v} y={ny - v}
          width={NODE_W} height={NODE_H}
          rx={NODE_R}
          className="fill-white dark:fill-gray-800"
          fillOpacity={bgVariant === 'sunset' ? 0.5 : 0.33}
          stroke={isActive ? color : achsen.referenz}
          strokeWidth={isActive ? 0.8 : 0.5}
          strokeOpacity={i === 0 ? 0.35 : 0.5}
        />
      )) : null}

      {/* Knoten-Hintergrund (halbtransparent, Gitter scheint durch).
          Filter-Attribut im Lite-Modus weglassen, damit Safari pro Knoten
          keinen separaten Compositing-Layer für den (No-Op-)Filter erstellt. */}
      <rect
        x={nx} y={ny}
        width={NODE_W} height={NODE_H}
        rx={NODE_R}
        className="fill-white dark:fill-gray-800"
        fillOpacity={bgVariant === 'sunset' ? 0.92 : 0.6}
        stroke={isActive ? color : achsen.referenz}
        strokeWidth={isActive ? 1 : 0.5}
        strokeOpacity={isActive ? 0.7 : 0.3}
        filter={lite ? undefined : "url(#ef-card-shadow)"}
      />

      {/* Pegel (Füllung von unten): SoC kräftig, PV-Auslastung gelb/orange —
          nie beide an einem Gerät, deshalb EIN Platz. */}
      {pegel && (
        <rect
          x={nx + 1.5} y={ny + 1.5 + (NODE_H - 3) * (1 - pegel.prozent / 100)}
          width={NODE_W - 3}
          height={(NODE_H - 3) * (pegel.prozent / 100)}
          rx={NODE_R - 1}
          fill={pegel.fill}
          fillOpacity={pegel.opacity}
        />
      )}

      {/* Icon-Glow (farbiger Schein hinter dem Icon) — nur im Effekt-Modus */}
      {isActive && !lite && (
        <circle
          cx={x} cy={y - NODE_H / 2 + 6 + dims.iconSize / 2}
          r={dims.iconSize * 0.6}
          fill={color}
          fillOpacity={0.15}
          filter="url(#ef-icon-glow)"
        />
      )}
      {/* Icon */}
      <foreignObject x={x - dims.iconSize / 2} y={y - NODE_H / 2 + 6} width={dims.iconSize} height={dims.iconSize}>
        <IconElement name={icon} size={dims.iconSize} color={isActive ? color : achsen.referenz} />
      </foreignObject>

      {/* kW-Wert */}
      <text
        x={x} y={y + 1}
        textAnchor="middle"
        style={{ fontSize: `${dims.kwFontSize}px` }}
        className="font-bold fill-gray-900 dark:fill-white"
      >
        {wertText}
      </text>

      {/* Zweite Zeile: SoC · Betriebsmodus im Klartext (#398 Stufe 2) ·
          Auto der Wallbox (Bau A, Plan §1.4a — „ID.4 52 %", bei V2H
          „· entlädt"; lädt keins eindeutig: „64 · 81 %" ohne Füllstand).
          ⭐ Bewusst in DERSELBEN Zeile statt in einer vierten: ein
          Speicher hat einen SoC und keinen Betriebsmodus, eine
          Wärmepumpe umgekehrt, eine Wallbox nur ihr Auto — der Platz ist
          also frei, und der Knoten wächst nicht. Ein Tooltip allein wäre
          auf dem Handy unerreichbar gewesen; die Frage des Melders war
          „sieht man, was das Gerät gerade tut?", und Hovern ist dort
          keine Antwort. */}
      {zweiteZeile && (
        <text
          x={x} y={y + dims.kwFontSize + 2}
          textAnchor="middle"
          style={{ fontSize: `${dims.socFontSize}px` }}
          className={zweiteZeile.fill ? 'font-semibold' : 'font-semibold fill-gray-500 dark:fill-gray-400'}
          fill={zweiteZeile.fill ?? undefined}
        >
          {zweiteZeile.text}
        </text>
      )}

      {/* Label
          ⛔ **Die Bedingung ist `zweiteZeile`, nicht `hasSoc`** — und
          genau das war der Fehler, den MartyBr am Tag der Auslieferung
          von v4.0.30 fotografiert hat (T89667 #230): „Unbestimmt" lag
          quer über „Vitocal 33…". Der Modus-Text hat sich die
          **Position** des SoC geliehen (`kwFontSize + 2`), die
          zugehörige **Verschiebung des Namens** stand aber in einem
          Ternär, das nur den SoC kannte. Vier Pixel Abstand bei neun
          Pixel Schriftgröße.
          ⭐ Deshalb hängt beides an DERSELBEN Prop (`zweiteZeile`): Wer
          eine dritte Zeilenart ergänzt, ändert eine Stelle — nicht zwei,
          von denen er die zweite übersieht. */}
      <text
        x={x} y={y + (zweiteZeile ? NODE_H / 2 - 4 : dims.kwFontSize + 6)}
        textAnchor="middle"
        style={{ fontSize: `${dims.labelFontSize}px` }}
        className="fill-gray-500 dark:fill-gray-400"
      >
        {label}
      </text>
    </g>
  )
}
