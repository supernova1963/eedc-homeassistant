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
 * - **Plätze** (P-433-2e): zwei Reihen und am Desktop die zwei Einzelplätze neben
 *   dem Haus (`layout.links`/`layout.rechts`) — gerendert wie jeder Reihenplatz;
 *   die Geometrie steht nur in `ueberblickLayout.ts`.
 * - **Linien** Kachelkante → Objekt mit Saum (Bau B Regel C, `ENERGIEFLUSS_SAUM`,
 *   nur hell); keine Partikel.
 * - **Tooltip** über `data-title` an der Kachel; der Touch-Hook ist einmal in
 *   `App.tsx` montiert (Ü11) — hier kein eigener.
 * - **Gruppen (Ü6):** Tipp auf «Innengeräte (n)» öffnet den vorhandenen
 *   Innengeräte-Abschnitt (`LiveInnengeraete`) unter dem Bild, auf
 *   «Wärmepumpen (n)» oder «Weitere (n)» eine einfache Liste — nicht das
 *   Energiefluss-Overlay (es kennt nur Live-Knoten).
 * - **Themen (Nachlauf 4.2.1 N4, Entscheid Gernot 2.11.2026):** eine Themen-Kachel mit mehreren Einträgen
 *   (`themaEintraege`) zeichnet sich als dreizeilige Gruppenkachel wie eine Geräte-Kachel — Wert des ersten Eintrags,
 *   seine Bezeichnung, «‹Thema› (n)»; Stapel-Optik, Tipp öffnet die Liste Bezeichnung · Wert · Stand —, bleibt im Layout
 *   aber **ein** Platz (keine Gruppen-Art, Rang 3). In «Weitere» steht sie als «‹Thema› (n) · ‹Bezeichnung› · ‹Wert›»
 *   des ersten Eintrags, in der Liste mit dessen Stand (N6).
 * - **Bild aus dem Deskriptor** (P-433-2b S1a, E0): Panoramen, aria, Gruppenname und Farbe der Gruppe «Weitere»
 *   kommen aus `panorama` (`panorama.ts`; Wärme/Klima `WAERME_PANORAMA_DEF`), das Layout ebenso. Der Pegel einer
 *   Kachel (`pegel`) geht unverändert an `EnergieFlussKachel` (Wärme: keiner).
 * - **Höhe (Nachlauf 4.2.1, N1/N2):** auf der Seite folgt das Bild der Spaltenbreite, aber nie höher als
 *   {@link SCHAUBILD_DECKEL} (Fensterhöhe minus Kopf- und Fußzeilen) — die **Zeichenfläche** (`data-schaubild-flaeche`)
 *   wird dafür schmaler und steht zentriert. Im Vollbild (`vollbild`) ist die Höhe fest (die verfügbare Höhe des
 *   Overlay-Inhalts) und die Breite folgt dem Seitenverhältnis, höchstens die Spaltenbreite — wie der Energiefluss im
 *   Vollbild. Beides reines CSS; der ResizeObserver misst die **tatsächliche Bildbreite** (Seite: das Schaubild in der
 *   gedeckelten Zeichenfläche; Vollbild: die Zeichenfläche selbst), und nur sie geht an `layoutUeberblick` (sonst
 *   passten die Kachelgrößen nicht zum Bild).
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ENERGIEFLUSS_SAUM } from '../../../lib'
import { verbergeTouchTooltip } from '../../../hooks/useTouchTitleTooltip'
import { Button } from '../../ui'
import EnergieFlussKachel from '../../live/EnergieFlussKachel'
import EnergieFlussDefs from '../../live/EnergieFlussDefs'
import LiveInnengeraete from '../../live/LiveInnengeraete'
import { formatPower, kuerzeMitSuffix, liesLiteModus, zeichenBudget } from '../../live/EnergieFluss'
import type { LiveInnengeraet } from '../../../api/liveDashboard'
import { PANORAMA_BREITE, PANORAMA_HOEHE, type PanoramaDef } from './panorama'
import { kachelWertText, type UeberblickKachel } from './kachelAnker'
import { themenKachelTexte } from './themenKacheln'
import { layoutUeberblick, type Platz, type UeberblickLayout } from './ueberblickLayout'

/** Startbreite bis zur ersten Messung (Desktop-Spalte); jsdom misst nie. */
const START_BREITE = 900

/**
 * N1 — Höhendeckel auf der Seite: die Bildbreite höchstens `(100dvh − 16rem) · 1312/816`, die Bildhöhe also höchstens
 * `100dvh − 16rem`. 16rem = 256 px decken bei 1920 × 900 die Zeilen über dem Bild (Block-Kopf-Unterkante 215 px,
 * gemessen am Lab) und die Status-Fußzeile (32 px, `StatusFusszeile` `h-8`) mit 9 px Luft. Unter dem Deckel
 * (Galerie 1400 × 1000: 560 px Bild, Deckel 744 px) ändert sich nichts; am Handy ist die Breite der Engpass.
 * ⚠ Als Klassen-Literal, damit Tailwind sie findet (kein zusammengesetzter String).
 */
export const SCHAUBILD_DECKEL = 'max-w-[calc((100dvh_-_16rem)_*_1312_/_816)]'

/** Name einer Gruppenkachel aus dem Deskriptor (je Gruppen-Art und Anker; «Weitere» ohne Anker). */
function gruppenName(p: Platz<UeberblickKachel>, panorama: PanoramaDef): string {
  return panorama.gruppenName(p.gruppe ?? 'weitere', p.anker)
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

/** Eine Themen-Gruppe (N4) als Mitglied von «Weitere» (Nachlauf 4.2.1 N6, Entscheid Gernot 2.11.2026): Titel «‹Thema› (n)»,
 *  Wert «‹Bezeichnung› · ‹Wert›» und Stand des ersten Eintrags — `null` für jede andere Kachel (auch Einzel-Themen). */
function themenGruppeInWeitere(m: UeberblickKachel): { titel: string; wert: string; stand: string | null } | null {
  if (!m.themaEintraege || !m.zweiteZeile) return null
  return {
    titel: `${m.label} (${m.themaEintraege.length})`,
    wert: `${m.zweiteZeile.text} · ${m.wertText}`,
    stand: m.themaEintraege[0]?.stand ?? null,
  }
}

/** Tooltip-Zeile eines Mitglieds einer Gruppenkachel; die Themen-Gruppe als «• ‹Thema› (n) · ‹Bezeichnung› · ‹Wert›» (N6). */
function mitgliedTipZeile(m: UeberblickKachel): string {
  const tg = themenGruppeInWeitere(m)
  return tg ? `• ${tg.titel} · ${tg.wert}` : `• ${m.label}: ${m.wertText}${m.zweiteZeile ? ` (${m.zweiteZeile.text})` : ''}`
}

/** Was eine Gruppenkachel zeigt. */
function gruppenKachel(p: Platz<UeberblickKachel>, panorama: PanoramaDef) {
  const n = p.mitglieder.length
  const name = gruppenName(p, panorama)
  const tip = [`${name} (${n})`, ...p.mitglieder.map(mitgliedTipZeile)].join('\n')
  const erste = p.mitglieder[0]
  const wert = gruppenWert(p)
  return {
    name,
    icon: p.gruppe === 'weitere' ? 'wrench' : erste.icon,
    color: p.gruppe === 'weitere' ? panorama.farbeWeitere : erste.color,
    isActive: wert.kw != null ? wert.kw > 0 : p.mitglieder.some((m) => m.isActive),
    wertText: wert.text,
    tip,
  }
}

/** Alle Plätze des Layouts: die zwei Reihen und die zwei Einzelplätze neben dem Haus (P-433-2e). */
function allePlaetze(layout: UeberblickLayout<UeberblickKachel>): Platz<UeberblickKachel>[] {
  return [...layout.oben, ...layout.unten, ...(layout.links ? [layout.links] : []), ...(layout.rechts ? [layout.rechts] : [])]
}

function Linien({ layout, panorama }: { layout: UeberblickLayout<UeberblickKachel>; panorama: PanoramaDef }) {
  const k = layout.k
  return (
    <g pointerEvents="none">
      {allePlaetze(layout).map((p) => p.linie && (
        <g key={`linie-${p.key}`} data-linie={p.key}>
          <path
            data-saum
            d={`M ${p.linie.x1} ${p.linie.y1} L ${p.linie.x2} ${p.linie.y2}`}
            fill="none" stroke={ENERGIEFLUSS_SAUM} strokeWidth={3.5 * k} strokeOpacity={0.4}
            strokeLinecap="round" className="dark:opacity-0"
          />
          <path
            d={`M ${p.linie.x1} ${p.linie.y1} L ${p.linie.x2} ${p.linie.y2}`}
            fill="none" stroke={p.gruppe === 'weitere' ? panorama.farbeWeitere : p.mitglieder[0].color}
            strokeWidth={1.5 * k} strokeOpacity={0.85} strokeLinecap="round"
          />
          <circle cx={p.linie.x2} cy={p.linie.y2} r={3 * k} fill={p.mitglieder[0].color} fillOpacity={0.85} />
        </g>
      ))}
    </g>
  )
}

/** Die Themen-Gruppe eines Platzes (N4): eine Einzelkachel `art: 'thema'` mit mehreren Einträgen — sonst `null`. */
function themenGruppe(p: Platz<UeberblickKachel>): UeberblickKachel | null {
  const m = p.gruppe == null ? p.mitglieder[0] : null
  return m?.art === 'thema' && m.themaEintraege ? m : null
}

function GruppenListe({ platz, panorama, onSchliessen }: { platz: Platz<UeberblickKachel>; panorama: PanoramaDef; onSchliessen: () => void }) {
  const thema = themenGruppe(platz)
  const titel = thema
    ? `${thema.label} (${thema.themaEintraege!.length})`
    : `${gruppenName(platz, panorama)} (${platz.mitglieder.length})`
  const innen = platz.gruppe === 'innengeraete'
    ? platz.mitglieder.map((m) => m.innengeraet).filter((g): g is LiveInnengeraet => g != null)
    : null
  return (
    <div className="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 p-2" data-gruppen-liste={platz.key}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">{titel}</span>
        <Button type="button" variant="ghost" size="sm" onClick={onSchliessen}>schließen</Button>
      </div>
      {innen ? <LiveInnengeraete geraete={innen} /> : thema ? (
        <ul className="text-sm space-y-0.5">
          {thema.themaEintraege!.map((e) => (
            <li key={e.id} className="flex justify-between gap-2" data-thema-eintrag={e.id}>
              <span className="text-gray-600 dark:text-gray-400 truncate min-w-0">{e.label}</span>
              <span className="flex items-baseline gap-2 whitespace-nowrap">
                <span className="text-gray-900 dark:text-white font-medium">{e.wert}</span>
                {e.stand && <span className="text-xs text-gray-500 dark:text-gray-400">{e.stand}</span>}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="text-sm space-y-0.5">
          {platz.mitglieder.map((m) => {
            const tg = themenGruppeInWeitere(m)
            // N6: die Themen-Gruppe in der Form der Themen-Zeilen (Wert und Stand); jedes andere Mitglied mit den
            // Text-Knoten wie vor N4 (Zwölf-Fälle-Snapshot byte-gleich).
            return tg ? (
              <li key={m.id} className="flex justify-between gap-2" data-thema-gruppe={m.id}>
                <span className="text-gray-600 dark:text-gray-400 truncate min-w-0">{tg.titel}</span>
                <span className="flex items-baseline gap-2 whitespace-nowrap">
                  <span className="text-gray-900 dark:text-white font-medium">{tg.wert}</span>
                  {tg.stand && <span className="text-xs text-gray-500 dark:text-gray-400">{tg.stand}</span>}
                </span>
              </li>
            ) : (
              <li key={m.id} className="flex justify-between gap-2">
                <span className="text-gray-600 dark:text-gray-400 truncate min-w-0">{m.label}</span>
                <span className="text-gray-900 dark:text-white font-medium whitespace-nowrap">
                  {m.wertText}{m.zweiteZeile ? ` · ${m.zweiteZeile.text}` : ''}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export interface UeberblickSchaubildProps {
  kacheln: UeberblickKachel[]
  ohneSensor: string[]
  /** Das Bild mit Anker-Karte und Regeln (P-433-2b S1a) — Wärme/Klima: `WAERME_PANORAMA_DEF`. */
  panorama: PanoramaDef
  /**
   * N2 (Nachlauf 4.2.1): steht das Schaubild im Fokus/Vollbild? Dann füllt es die Höhe seines Behälters (Breite folgt,
   * höchstens die Spaltenbreite, zentriert); der Seiten-Deckel {@link SCHAUBILD_DECKEL} gilt dort nicht.
   */
  vollbild?: boolean
  /** N3: Aktion oben rechts im Bild (der ⤢ «Schaubild: Fokus / Vollbild»); fehlt sie, steht dort nichts. */
  kopfAktion?: ReactNode
}

export default function UeberblickSchaubild({ kacheln, ohneSensor, panorama, vollbild = false, kopfAktion }: UeberblickSchaubildProps) {
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
    // `vollbild` wechselt den Behälter der Zeichenfläche — dann neu anmelden.
  }, [vollbild])

  const layout = layoutUeberblick(kacheln, breite, panorama)
  const { dims, k } = layout
  const plaetze = allePlaetze(layout)
  const offenerPlatz = offen != null ? plaetze.find((p) => p.key === offen) ?? null : null

  const svg = (
    // Vollbild: ist die Spalte der Engpass, ist die Zeichenfläche höher als das Bild — das Bild steht dann oben (bündig mit
    // den Karten daneben), waagrecht zentriert. Auf der Seite unverändert (Zwölf-Fälle-Snapshot).
    <svg
      viewBox={`0 0 ${PANORAMA_BREITE} ${PANORAMA_HOEHE}`} preserveAspectRatio={vollbild ? 'xMidYMin meet' : undefined}
      className={`w-full ${vollbild ? 'h-full' : 'h-auto'} block rounded-lg`} role="img" aria-label={panorama.aria}
    >
      <defs><EnergieFlussDefs lite={lite} /></defs>
      <image
        data-panorama="tag" href={panorama.bilder.tag}
        x="0" y="0" width={PANORAMA_BREITE} height={PANORAMA_HOEHE}
        className="opacity-100 dark:opacity-0"
      />
      <image
        data-panorama="nacht" href={panorama.bilder.nacht}
        x="0" y="0" width={PANORAMA_BREITE} height={PANORAMA_HOEHE}
        className="opacity-0 dark:opacity-100"
      />
      <Linien layout={layout} panorama={panorama} />
      {plaetze.map((p) => {
        const einzeln = p.gruppe == null ? p.mitglieder[0] : null
        const g = einzeln ? null : gruppenKachel(p, panorama)
        // N4: Themen-Kachel mit mehreren Einträgen ⇒ Gruppenkachel «‹Thema› (n)» (ein Platz im Layout).
        const themaN = themenGruppe(p)?.themaEintraege?.length ?? null
        const gruppenTitel = g ? { name: g.name, n: p.mitglieder.length } : themaN != null ? { name: einzeln!.label, n: themaN } : null
        const maxC = dims.labelMaxChars
        const label = gruppenTitel
          ? kuerzeMitSuffix(gruppenTitel.name, ` (${gruppenTitel.n})`, zeichenBudget(dims.nodeW, dims.labelFontSize))
          : (einzeln!.label.length > maxC ? einzeln!.label.slice(0, maxC - 2) + '…' : einzeln!.label)
        // Themen-Kacheln (N4): Einzel-Kachel kürzt den Wert, die Gruppe die Bezeichnung (zweite Zeile), am Ende mit «…».
        const thema = einzeln?.art === 'thema' ? themenKachelTexte(einzeln, dims) : null
        const knopf = gruppenTitel ? {
          key: p.key,
          ariaLabel: `${gruppenTitel.name} (${gruppenTitel.n}): Liste öffnen`,
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
              wertText={thema ? thema.wertText : einzeln ? kachelWertText(einzeln, dims) : g!.wertText}
              zweiteZeile={thema ? thema.zweiteZeile : einzeln?.zweiteZeile ?? null}
              pegel={einzeln?.pegel}
              tip={einzeln?.tip ?? g!.tip}
              mitglieder={gruppenTitel ? gruppenTitel.n : undefined}
              knopf={knopf}
              lite={lite} bgVariant="haus"
            />
          </g>
        )
      })}
    </svg>
  )
  const unterDemBild = (
    <>
      {offenerPlatz && <GruppenListe platz={offenerPlatz} panorama={panorama} onSchliessen={() => setOffen(null)} />}
      {ohneSensor.length > 0 && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400" data-ohne-sensor>
          Ohne Sensor, deshalb ohne Kachel: {ohneSensor.join(' · ')} →{' '}
          <a href="#/einstellungen/datenquellen" className="text-primary-700 dark:text-primary-300 hover:underline">
            Datenquellen zuordnen
          </a>
        </p>
      )}
    </>
  )

  // N2 — Vollbild: die Zeichenfläche (`data-schaubild-flaeche`, gemessen) füllt die Höhe des Behälters, die Breite folgt
  // über das Seitenverhältnis, höchstens die Spalte, zentriert. Ohne feste Behälterhöhe (gestapelte Spalten unter `xl`)
  // fällt `h-full` auf `auto` zurück, dann folgt die Höhe der Breite wie auf der Seite.
  if (vollbild) {
    return (
      <div className="h-full flex flex-col" data-ueberblick-schaubild data-vollbild>
        <div className="flex-1 min-h-0">
          <div ref={ref} className="relative mx-auto h-full max-w-full aspect-[1312/816]" data-schaubild-flaeche>{svg}</div>
        </div>
        {unterDemBild}
      </div>
    )
  }

  // N1 — Seite: der Deckel sitzt an der Zeichenfläche **um** das Schaubild (volle Spaltenbreite, nie höher als
  // `SCHAUBILD_DECKEL` erlaubt, zentriert); gemessen wird wie bisher das Schaubild, dessen Breite jetzt die Bildbreite
  // ist. Das Innere ist Zeichen für Zeichen das bisherige (Zwölf-Fälle-Snapshot byte-gleich). Der ⤢ (N3) liegt oben
  // rechts über dem Bild.
  return (
    <div className={`relative mx-auto w-full ${SCHAUBILD_DECKEL}`} data-schaubild-flaeche>
      <div ref={ref} className="w-full" data-ueberblick-schaubild>
        {svg}
        {unterDemBild}
      </div>
      {kopfAktion != null && <div className="absolute top-0.5 right-0.5 z-10">{kopfAktion}</div>}
    </div>
  )
}
