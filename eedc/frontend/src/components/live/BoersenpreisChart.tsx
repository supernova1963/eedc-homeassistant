/**
 * BoersenpreisChart — Day-Ahead-Preise heute und morgen auf einer Achse (#335).
 *
 * Der vierte Schub des Community-Wunsches: zwei Tage, durchgehende Zeitachse,
 * die Linie nach Preisniveau abgestuft, günstige Stunden hervorgehoben. Was
 * „günstig" heißt, entscheidet **das Backend** (`services/preis_tag.py`) — genau
 * dieselbe Schicht, aus der auch die HA-Preis-Sensoren ihre Zahlen ziehen. Dieser
 * Chart rechnet nichts nach; täte er es, stünden zwei Wahrheiten über derselben
 * Größe nebeneinander.
 *
 * **Stufenlinie, kein Polygonzug:** Ein Börsenpreis gilt eine ganze Stunde lang.
 * Eine interpolierte Linie zwischen zwei Stundenmitten behauptet Preise, die es
 * nie gab — bei einem Sprung von 16 auf 0 ct sichtbar falsch.
 *
 * **Lücken bleiben Lücken** (F-6): Ende März hat der Tag 23 Stundenpreise, Ende
 * Oktober trägt die Stunde 2 den Preis der ersten von zwei realen Stunden. Die
 * fehlende Position wird als Lücke gezeichnet und unter dem Chart benannt, statt
 * überbrückt zu werden.
 */

import { useMemo } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, ResponsiveContainer,
  Tooltip, ReferenceLine, CartesianGrid, ReferenceArea,
} from 'recharts'
import type { BoersenpreisResponse, BoersenpreisTag } from '../../api/liveDashboard'
import ChartTooltip from '../ui/ChartTooltip'
import {
  CHART_HOVER_CURSOR, PREISSTUFEN_FARBEN, WT_KURZ, xAchse, yAchse, achsenEinheit,
  achsenTick, ACHSEN_MARGIN_TOP, fmtZahl,
} from '../../lib'
import { useChartTheme, usePreisstufenFarben } from '../../context/ThemeContext'

/** Die drei Stufenfarben eines Modus — `PREISSTUFEN_FARBEN.light` bzw. `.dark`. */
export type Preisstufen = Record<'guenstig' | 'normal' | 'teuer', string>

/** Stunden je Kalendertag im Normalfall — die Achse hängt NICHT daran (F-6). */
const STUNDEN_JE_TAG = 24

/** Eine Position der 48-Stunden-Achse. */
export interface PreisPunkt {
  /** Fortlaufende Position 0…48 (nicht die Stunde — die wiederholt sich). */
  pos: number
  /** Achsenbeschriftung, z. B. „06.08. 14" */
  label: string
  /** Preis je Tag; `null` = für diesen Tag gibt es hier keinen Wert. */
  preis_0: number | null
  preis_1: number | null
  /** Stunde und Datum der Position — für Tooltip und Günstig-Markierung. */
  stunde: number
  datum: string
  /** Ungekappte Günstig-Markierung des Backends (N-103), `null` ohne Preis. */
  guenstig: boolean | null
  /** Rang des Backends: 1–5 = eine der fünf billigsten ihres Fensters, 99 = Rest.
   *  `null` ohne Preis. Die Anzahl günstiger Stunden bleibt davon **unberührt** —
   *  Rang und „günstig" sind seit v4.0.10 zwei Aussagen (N-103). */
  rang: number | null
}

/** Ränge, die als Ziffer im Chart erscheinen — deckungsgleich mit `GUENSTIG_TOP_N`
 *  im Backend (`core/berechnungen/preis_rang.py`). */
const RANG_SICHTBAR_BIS = 5

function tagLabel(datum: string, stunde: number): string {
  // Datum-Keys kommen als ISO vom Backend; als lokales Datum lesen, nicht als
  // UTC-Zeitpunkt (`new Date('2026-08-06')` wäre Mitternacht UTC).
  const [j, m, t] = datum.split('-').map(Number)
  const d = new Date(j, m - 1, t)
  return `${WT_KURZ[d.getDay()]} ${String(stunde).padStart(2, '0')}`
}

/**
 * Baut die durchgehende Achse aus einem oder zwei Preistagen.
 *
 * Jeder Tag belegt {@link STUNDEN_JE_TAG} Positionen — auch der kurze Tag der
 * Zeitumstellung, dessen fehlende Stunde als `null` stehen bleibt. Nur so liegt
 * „morgen 14 Uhr" auch dann an Position 38, wenn heute 23 Stunden hatte.
 *
 * Der **Schlusspunkt** am Ende jedes Tages wiederholt den Preis der letzten
 * Stunde. Das ist kein erfundener Wert, sondern die zu Ende gezeichnete Stufe:
 * Der Preis der Stunde 23 gilt bis Mitternacht. Ohne ihn bräche die Linie eine
 * Stunde zu früh ab.
 */
export function baueAchse(tage: BoersenpreisTag[]): PreisPunkt[] {
  if (tage.length === 0) return []
  const punkte: PreisPunkt[] = []

  tage.slice(0, 2).forEach((tag, idx) => {
    const nachStunde = new Map(tag.stunden.map((s) => [s.stunde, s]))
    for (let h = 0; h < STUNDEN_JE_TAG; h++) {
      const s = nachStunde.get(h)
      punkte.push({
        pos: idx * STUNDEN_JE_TAG + h,
        label: tagLabel(tag.datum, h),
        preis_0: idx === 0 ? (s?.preis_cent ?? null) : null,
        preis_1: idx === 1 ? (s?.preis_cent ?? null) : null,
        stunde: h,
        datum: tag.datum,
        guenstig: s ? s.unter_schwelle : null,
        rang: s ? s.rang : null,
      })
    }
  })

  // Schlusspunkt: die letzte Stufe bis Mitternacht ausziehen. Er trägt bewusst
  // KEINE Günstig-Markierung — es ist keine eigene Stunde, sondern das Ende der
  // vorigen.
  const letzterTag = Math.min(tage.length, 2) - 1
  const letzteStunde = [...punkte].reverse().find(
    (p) => (letzterTag === 0 ? p.preis_0 : p.preis_1) !== null,
  )
  if (letzteStunde) {
    const pos = (letzterTag + 1) * STUNDEN_JE_TAG
    punkte.push({
      pos,
      label: '24',
      preis_0: letzterTag === 0 ? letzteStunde.preis_0 : null,
      preis_1: letzterTag === 1 ? letzteStunde.preis_1 : null,
      stunde: STUNDEN_JE_TAG,
      datum: tage[letzterTag].datum,
      guenstig: null,
      // Wie die Günstig-Markierung bewusst ohne Rang: der Schlusspunkt ist keine
      // eigene Stunde, sondern das Ende der vorigen — sonst stünde eine Ziffer
      // doppelt im Bild.
      rang: null,
    })
  }
  // Und die Naht zwischen den Tagen: Tag 0 reicht bis zur ersten Position von
  // Tag 1, sonst klafft dort eine Stunde Lücke im Bild.
  if (tage.length > 1) {
    const naht = punkte.find((p) => p.pos === STUNDEN_JE_TAG)
    const letzteVonTag0 = [...punkte].reverse().find((p) => p.pos < STUNDEN_JE_TAG && p.preis_0 !== null)
    if (naht && letzteVonTag0) naht.preis_0 = letzteVonTag0.preis_0
  }
  return punkte
}

/** Ein Farbstop des vertikalen Preis-Gradienten. */
export interface FarbStop {
  offset: number   // 0 = oberer Rand der Linie (teuerster Wert), 1 = unterer
  farbe: string
}

/**
 * Farbstops für die abgestufte Linie **eines** Tages.
 *
 * Der Gradient läuft über die Bounding-Box des Linienpfades (Recharts-Default
 * `objectBoundingBox`) — also von der teuersten bis zur billigsten Stunde
 * *dieser* Linie. Deshalb werden die Offsets gegen deren Spanne gerechnet und
 * nicht gegen die Achse; wer hier die Achsen-Grenzen einsetzt, verschiebt die
 * Farbkanten um genau den Abstand zwischen Achse und Kurve.
 *
 * Die Kanten sind **hart** (zwei Stops auf demselben Offset): Eine Stunde ist
 * günstig oder nicht — ein weicher Verlauf würde eine Zwischenstufe behaupten,
 * die es in der Bewertung nicht gibt.
 */
export function farbStops(
  werte: number[],
  schwelle: number | null,
  durchschnitt: number | null,
  stufen: Preisstufen = PREISSTUFEN_FARBEN.light,
): FarbStop[] {
  const gueltig = werte.filter((v) => v != null && Number.isFinite(v))
  if (gueltig.length === 0) return []
  const max = Math.max(...gueltig)
  const min = Math.min(...gueltig)

  const farbeVon = (v: number): string => {
    if (schwelle != null && v <= schwelle) return stufen.guenstig
    if (durchschnitt != null && v > durchschnitt) return stufen.teuer
    return stufen.normal
  }

  // Flache Linie (alle Stunden gleich teuer): eine Farbe, kein Verlauf.
  if (max === min) return [{ offset: 0, farbe: farbeVon(max) }, { offset: 1, farbe: farbeVon(min) }]

  const offsetVon = (v: number) => (max - v) / (max - min)
  const stops: FarbStop[] = [{ offset: 0, farbe: farbeVon(max) }]
  // Grenzen von oben nach unten einsetzen — nur solche, die die Kurve schneidet.
  for (const grenze of [durchschnitt, schwelle]) {
    if (grenze == null || grenze <= min || grenze >= max) continue
    const o = offsetVon(grenze)
    // Knapp über der Grenze gilt noch die obere Farbe, auf der Grenze die untere
    // (`v <= schwelle` ist günstig) — daher der winzige Versatz nach oben.
    stops.push({ offset: o, farbe: farbeVon(grenze + Math.abs(max - min) * 1e-6) })
    stops.push({ offset: o, farbe: farbeVon(grenze) })
  }
  stops.push({ offset: 1, farbe: farbeVon(min) })
  return stops
}

/** Zusammenhängende Bereiche günstiger Stunden — als Flächen hinter der Linie. */
export function guenstigeBereiche(punkte: PreisPunkt[]): Array<{ von: number; bis: number }> {
  const bereiche: Array<{ von: number; bis: number }> = []
  let start: number | null = null
  for (const p of punkte) {
    if (p.guenstig) {
      if (start === null) start = p.pos
    } else if (start !== null) {
      bereiche.push({ von: start, bis: p.pos })
      start = null
    }
  }
  if (start !== null) {
    const letzte = punkte[punkte.length - 1]
    bereiche.push({ von: start, bis: letzte.pos })
  }
  return bereiche
}

/**
 * Markierung der Ränge 1–5 auf der Linie (Rainer-PN 2026-08-11, Gernots Entscheid).
 *
 * **Warum eine Ziffer und keine zweite Farbe:** Der Wunsch war „zeig mir die fünf
 * billigen Stunden". Genau die gibt es bereits — als **Rang**, den das Backend
 * ohnehin liefert und den die HA-Sensoren melden. Der naheliegende Gegenvorschlag
 * (die grüne Günstig-Menge auf fünf kappen) wurde **verworfen**: Sie ist seit
 * v4.0.10 mit Absicht ungekappt, weil sie als Divisor in Automationen dient
 * (N-103) — sie zu deckeln hieße, eine ausgelieferte Größe für eine Anzeige
 * kaputtzumachen. Rang und Günstig-Menge stehen deshalb **nebeneinander**:
 * die Fläche sagt „unter der Schwelle", die Ziffer sagt „eine der fünf besten".
 *
 * Die Ränge werden je Fenster (Tag/Nacht) vergeben — an einem Tag stehen also bis
 * zu zehn Ziffern im Bild, zweimal 1–5. Das ist dieselbe Aussage wie beim Sensor
 * `eedc_preis_rang` und kein Fehler.
 */
export function RangZiffer(props: {
  cx?: number
  cy?: number
  payload?: PreisPunkt
  farbe: string
}) {
  const { cx, cy, payload, farbe } = props
  const rang = payload?.rang
  if (cx == null || cy == null || rang == null || rang > RANG_SICHTBAR_BIS) return null
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill={farbe} />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={9}
        fontWeight={600}
        className="fill-white dark:fill-gray-900"
      >
        {rang}
      </text>
    </g>
  )
}

/** Tage, die nicht die üblichen 24 Stundenpreise tragen — mit Grund. */
export function zeitumstellungHinweis(tage: BoersenpreisTag[]): string | null {
  const auffaellig = tage.filter((t) => t.stunden.length !== STUNDEN_JE_TAG)
  if (auffaellig.length === 0) return null
  return auffaellig
    .map((t) => {
      const [, m, d] = t.datum.split('-')
      const wann = `${d}.${m}.`
      return t.stunden.length < STUNDEN_JE_TAG
        ? `${wann} hat ${t.stunden.length} Stundenpreise — an diesem Tag beginnt die Sommerzeit, die Stunde 2 gibt es nicht.`
        : `${wann} hat ${t.stunden.length} Stundenpreise.`
    })
    .join(' ')
}

interface Props {
  daten: BoersenpreisResponse
}

export default function BoersenpreisChart({ daten }: Props) {
  const achsen = useChartTheme()
  const stufen = usePreisstufenFarben()
  const punkte = useMemo(() => baueAchse(daten.tage), [daten.tage])

  const stopsJeTag = useMemo(
    () => daten.tage.slice(0, 2).map((tag) =>
      farbStops(
        tag.stunden.map((s) => s.preis_cent),
        tag.schwelle_cent,
        tag.optimierter_durchschnitt_cent,
        stufen,
      ),
    ),
    [daten.tage, stufen],
  )
  const bereiche = useMemo(() => guenstigeBereiche(punkte), [punkte])
  const umstellung = useMemo(() => zeitumstellungHinweis(daten.tage), [daten.tage])

  if (punkte.length === 0) return null

  // Position „jetzt": nur wenn der heutige Tag überhaupt dabei ist.
  const heuteIdx = daten.tage.findIndex((t) => t.datum === daten.heute)
  const jetztPos =
    heuteIdx >= 0 && daten.aktuelle_stunde != null
      ? heuteIdx * STUNDEN_JE_TAG + daten.aktuelle_stunde
      : null

  const stundeVonPos = new Map(punkte.map((p) => [p.pos, p]))

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={punkte} margin={{ top: ACHSEN_MARGIN_TOP, right: 10, left: 0, bottom: 5 }}>
          <defs>
            {stopsJeTag.map((stops, idx) => (
              <linearGradient key={idx} id={`preisstufen-${idx}`} x1="0" y1="0" x2="0" y2="1">
                {stops.map((s, i) => (
                  <stop key={i} offset={`${s.offset * 100}%`} stopColor={s.farbe} />
                ))}
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="label"
            {...xAchse()}
            className="fill-gray-500 dark:fill-gray-400"
            interval={5}
            /* achsen-allow: Zeit-/Kategorie-Achse */
          />
          <YAxis
            {...yAchse(false)}
            className="fill-gray-500 dark:fill-gray-400"
            tickFormatter={achsenTick}
            label={achsenEinheit('ct/kWh')}
          />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip
            labelFormatter={(label) => `${label} Uhr`}
            formatter={(value) => `${fmtZahl(value, 2)} ct/kWh`}
            nameFormatter={() => 'Börsenpreis'}
          />} />

          {/* Günstige Stunden als Fläche hinter der Linie — dieselbe Aussage wie
              die grüne Stufe, aber auch dort lesbar, wo die Linie flach läuft. */}
          {bereiche.map((b) => (
            <ReferenceArea
              key={`${b.von}-${b.bis}`}
              x1={stundeVonPos.get(b.von)?.label}
              x2={stundeVonPos.get(b.bis)?.label}
              fill={stufen.guenstig}
              fillOpacity={0.12}
              stroke="none"
            />
          ))}

          {/* Null-Linie: Day-Ahead-Preise werden regelmäßig negativ, und dann ist
              „unter null" die wichtigere Grenze als jede Farbstufe. */}
          <ReferenceLine y={0} stroke={achsen.referenz} strokeWidth={1} />

          {daten.tage.slice(0, 2).map((_, idx) => (
            <Line
              key={idx}
              type="stepAfter"
              dataKey={idx === 0 ? 'preis_0' : 'preis_1'}
              name={idx === 0 ? 'preis_0' : 'preis_1'}
              stroke={`url(#preisstufen-${idx})`}
              strokeWidth={2.5}
              // Kein Punkt je Stunde — nur die fünf besten je Fenster tragen
              // ihre Rangziffer (s. {@link RangZiffer}).
              dot={<RangZiffer farbe={stufen.guenstig} />}
              activeDot={false}
              isAnimationActive={false}
              connectNulls={false}
              legendType="none"
            />
          ))}

          {/* Tagesgrenze — beide Tage sind getrennte Auktionen mit eigener Schwelle. */}
          {daten.tage.length > 1 && (
            <ReferenceLine
              x={stundeVonPos.get(STUNDEN_JE_TAG)?.label}
              stroke={achsen.referenz}
              strokeDasharray="2 4"
            />
          )}

          {jetztPos != null && (
            <ReferenceLine
              x={stundeVonPos.get(jetztPos)?.label}
              stroke={achsen.referenz}
              strokeDasharray="3 3"
              label={{ value: 'Jetzt', position: 'top', fontSize: 10 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: stufen.guenstig }} />
          unter der Günstig-Schwelle
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: stufen.normal }} />
          zwischen Schwelle und Durchschnitt
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm" style={{ backgroundColor: stufen.teuer }} />
          über dem Durchschnitt
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-[8px] font-semibold text-white dark:text-gray-900"
            style={{ backgroundColor: stufen.guenstig }}
          >
            1
          </span>
          Rang 1–5: die günstigsten Stunden je Tag- und Nachtfenster
        </span>
      </div>

      {umstellung && (
        <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">{umstellung}</p>
      )}
    </div>
  )
}
