/**
 * Energiefluss — Hintergrund-Variante „Haus" (Bau B, #341/#348).
 *
 * „Haus" = die Tech-Verteilung (Kacheln, Gruppen, Linien, Vordergrund-Effekte)
 * mit einem KI-erzeugten Anlagenbild dahinter. Hier steht, was die Vorlage
 * (Fassung 2, §2) als Probe verlangt:
 *
 * - Regel A: Bildformat aus der Zeichenfläche (`hausFormat`), inklusive
 *   Nachweis, dass es in der Karte die 500-px-Regel reproduziert, und dem
 *   Vollbild-/Einbettfall (hohe Fläche ⇒ Quadrat-Bild).
 * - Regel B: beide Bilder eines Formats als `dark:`-Opacity-Paar, kein Schleier.
 * - Regel C: Linien-Saum nur bei „Haus", nur hell, in BEIDEN Schalterstellungen.
 * - Regel D: Solar-Soll-Zweig.
 * - Regel E: keine Hintergrund-Deko; Vordergrund-Effekte wie Tech.
 * - Persistenz über den Bestand (`useBgVariant`).
 *
 * ⚠ jsdom rechnet kein Tailwind: `deckung()` wertet die Opacity-Klassen so
 * aus, wie Tailwind sie mit `darkMode: 'class'` anwendet (Basis-Klasse, im
 * dunklen Thema überstimmt von `dark:opacity-*`). Das ist die Bauform, auf
 * die sich der Bestand seit dem Foto-Schleier verlässt.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import { existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import EnergieFluss from './EnergieFluss'
import { HAUS_BILDER, hausFormat } from './EnergieFlussBackground'
import { layoutEnergieFluss } from './energieFlussLayout'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { ENERGIEFLUSS_SAUM } from '../../lib'
import type { LiveKomponente } from '../../api/liveDashboard'

const ORIGINAL_RO = globalThis.ResizeObserver
const BG_KEY = 'eedc-energiefluss-bg'
const LITE_KEY = 'eedc-energiefluss-lite'

/** ResizeObserver-Stub (jsdom hat keinen): Container-Breite und — nur im
 *  Vollbild ausgewertet — die Höhe der Zeichenfläche. */
function mitMass(breitePx: number, hoehePx = 500) {
  vi.stubGlobal('ResizeObserver', class {
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb }
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: breitePx, height: hoehePx } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
    }
    unobserve() {}
    disconnect() {}
  })
}

beforeEach(() => {
  stubMatchMedia()
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.ResizeObserver = ORIGINAL_RO
})

const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const pv = (id: number, label: string, ausr: string | null, kw: number) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: 3 })
const NETZ = knoten('netz', { label: 'Stromnetz', icon: 'zap', verbrauch_kw: 2.1 })
const HAUS = knoten('haushalt', { label: 'Haushalt', icon: 'home', verbrauch_kw: 0.6 })
const WP = knoten('waermepumpe_31', { label: 'Wärmepumpe', icon: 'flame', typ: 'waermepumpe', verbrauch_kw: 1.4 })
/** Ein Speicher ohne Fluss: seine Linie ist INAKTIV — daran hängt „nur aktive Linien bekommen den Saum". */
const SPEICHER_RUHT = knoten('batterie_41', { label: 'Speicher', icon: 'battery', typ: 'speicher', erzeugung_kw: 0, verbrauch_kw: 0 })

/** Bestand D (gruppiert bei 1150 px: neun Strings Süd 5 · Ost 2 · West 2). */
const bestandD = (): LiveKomponente[] => [
  pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
  pv(14, 'Süd Garage', 'Süd', 1.2), pv(15, 'Süd Gaube', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
  pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
  WP, SPEICHER_RUHT, NETZ, HAUS,
]

interface Zeichnung {
  hg: string
  lite?: boolean
  breite?: number
  /** gesetzt ⇒ Vollbild mit dieser Flächenhöhe (px) */
  vollbildHoehe?: number | null
  soll?: number | null
  komp?: LiveKomponente[]
}

function zeichne({ hg, lite = false, breite = 1150, vollbildHoehe = null, soll = null, komp = bestandD() }: Zeichnung) {
  localStorage.setItem(BG_KEY, hg)
  localStorage.setItem(LITE_KEY, lite ? '1' : '0')
  mitMass(breite, vollbildHoehe ?? 500)
  const summePv = komp.filter(k => k.key.startsWith('pv_')).reduce((s, k) => s + (k.erzeugung_kw ?? 0), 0)
  return render(
    <ThemeProvider>
      <EnergieFluss
        komponenten={komp}
        summeErzeugung={summePv}
        summeVerbrauch={summePv}
        summePv={summePv}
        gauges={[]}
        pvSollKw={soll}
        vollbild={vollbildHoehe != null}
      />
    </ThemeProvider>,
  )
}

const flaeche = (c: HTMLElement) => c.querySelector('svg.flex-1')!
/** Der Hintergrund-Layer (`EnergieFlussBackground`): das `<g class="pointer-events-none">` direkt unter der Zeichenfläche. */
const hintergrund = (c: HTMLElement) => flaeche(c).querySelector(':scope > g.pointer-events-none')!
const hausBilder = (c: HTMLElement) => [...hintergrund(c).querySelectorAll('image[data-haus-bild]')]
const saeume = (c: HTMLElement) => [...flaeche(c).querySelectorAll('path[data-saum]')]
const kernlinien = (c: HTMLElement) => [...flaeche(c).querySelectorAll(':scope > g > path[stroke-opacity="0.85"]')]

/** Sichtbare Deckung eines Elements im hellen bzw. dunklen Thema (Tailwind `darkMode: 'class'`). */
function deckung(el: Element, dunkel: boolean): number {
  const klassen = (el.getAttribute('class') ?? '').split(/\s+/)
  const wert = (k: string | undefined) => (k ? Number(k.replace(/^.*opacity-/, '')) / 100 : 1)
  const dark = klassen.find(k => /^dark:opacity-\d+$/.test(k))
  const basis = klassen.find(k => /^opacity-\d+$/.test(k))
  return dunkel && dark ? wert(dark) : wert(basis)
}

/** Der Vordergrund (alles außer `<defs>` und dem Hintergrund-Layer) ohne Säume — als Text zum Vergleich. */
function vordergrundOhneSaum(c: HTMLElement): string {
  const kopie = flaeche(c).cloneNode(true) as Element
  kopie.querySelectorAll(':scope > defs, :scope > g.pointer-events-none, path[data-saum]').forEach(e => e.remove())
  return kopie.innerHTML
}

// ─── Regel A — Bildformat aus der Zeichenfläche ──────────────────────

describe('Bau B Regel A — hausFormat: Format aus der Zeichenfläche (W / svgH ≥ 1,3)', () => {
  it('Grenzfälle der Vorlage: 1,184 und 0,947 (Handy) ⇒ quadrat · 1,579 (Desktop) ⇒ breit · 0,667 (hohe Einbettung) ⇒ quadrat', () => {
    expect(hausFormat(450, 380)).toBe('quadrat')   // 1,184
    expect(hausFormat(360, 380)).toBe('quadrat')   // 0,947
    expect(hausFormat(600, 380)).toBe('breit')     // 1,579
    expect(hausFormat(600, 900)).toBe('quadrat')   // 0,667
    // an der Schwelle selbst: ≥ ⇒ breit (keine Hysterese)
    expect(hausFormat(130, 100)).toBe('breit')
    expect(hausFormat(129.9, 100)).toBe('quadrat')
  })

  it('in der Karte deckungsgleich mit „< 500 px ⇒ quadratisch" — gemessen über das echte Layout', () => {
    for (const komp of [bestandD(), [pv(1, 'Dach', 'Süd', 4), NETZ, HAUS]]) {
      for (const breitePx of [320, 360, 374, 375, 426, 499]) {
        const l = layoutEnergieFluss(komp, { breitePx })
        expect(hausFormat(l.W, l.H), `${breitePx} px`).toBe('quadrat')
      }
      for (const breitePx of [500, 640, 906, 1150, 1853]) {
        const l = layoutEnergieFluss(komp, { breitePx })
        expect(hausFormat(l.W, l.H), `${breitePx} px`).toBe('breit')
      }
    }
  })

  it('Vollbild ist formatvariabel: 1850 × 900 ⇒ breit, die hohe Einbettung 600 × 900 ⇒ quadrat (W1)', () => {
    const komp = bestandD()
    const breit = layoutEnergieFluss(komp, { breitePx: 1850, vollbild: { hoehePx: 900 } })
    const hoch = layoutEnergieFluss(komp, { breitePx: 600, vollbild: { hoehePx: 900 } })
    expect(hausFormat(breit.W, breit.H)).toBe('breit')
    expect(hausFormat(hoch.W, hoch.H)).toBe('quadrat')
  })

  it('DOM: die Karte wählt nach Breite, das Vollbild nach Fläche — immer BEIDE Bilder des gewählten Formats', () => {
    const faelle: [Zeichnung, 'breit' | 'quadrat'][] = [
      [{ hg: 'haus', breite: 1150 }, 'breit'],
      [{ hg: 'haus', breite: 360 }, 'quadrat'],
      [{ hg: 'haus', breite: 450 }, 'quadrat'],
      [{ hg: 'haus', breite: 1850, vollbildHoehe: 900 }, 'breit'],
      [{ hg: 'haus', breite: 600, vollbildHoehe: 900 }, 'quadrat'],
    ]
    for (const [opt, format] of faelle) {
      const { container, unmount } = zeichne(opt)
      const bilder = hausBilder(container)
      expect(bilder.map(b => b.getAttribute('data-haus-bild')), JSON.stringify(opt)).toEqual(['tag', 'nacht'])
      expect(bilder.map(b => b.getAttribute('href')), JSON.stringify(opt)).toEqual([HAUS_BILDER[format].tag, HAUS_BILDER[format].nacht])
      for (const b of bilder) {
        expect(b.getAttribute('preserveAspectRatio')).toBe('xMidYMid slice')
        expect(b.getAttribute('clip-path')).toBe('url(#ef-photo-clip)')
      }
      unmount()
    }
  })
})

// ─── Regel B — Thema per CSS-Paar, kein Schleier ─────────────────────

describe('Bau B Regel B — Tag/Nacht als dark:-Opacity-Paar, kein Schleier', () => {
  it('Tag sichtbar hell und unsichtbar dunkel, Nacht umgekehrt', () => {
    const { container } = zeichne({ hg: 'haus' })
    const [tag, nacht] = hausBilder(container)
    expect([deckung(tag, false), deckung(tag, true)]).toEqual([1, 0])
    expect([deckung(nacht, false), deckung(nacht, true)]).toEqual([0, 1])
  })

  it('alle vier Bilder liegen in public/ und sind nicht leer', () => {
    const pfade = Object.values(HAUS_BILDER).flatMap(f => [f.tag, f.nacht])
    expect(new Set(pfade).size).toBe(4)
    for (const p of pfade) {
      const datei = join(process.cwd(), 'public', p.replace(/^\.\//, ''))
      expect(existsSync(datei), datei).toBe(true)
      expect(statSync(datei).size, datei).toBeGreaterThan(50_000)
    }
  })

  it('kein Schleier bei „Haus": keine vollflächige Fläche über den Bildern — die Foto-Variante behält ihre zwei (Gegenprobe)', () => {
    const ueberDemBild = (c: HTMLElement) => {
      const kinder = [...hintergrund(c).children]
      const letztesBild = kinder.map(e => e.tagName.toLowerCase()).lastIndexOf('image')
      expect(letztesBild).toBeGreaterThanOrEqual(0)
      return kinder.slice(letztesBild + 1).filter(e => e.tagName.toLowerCase() === 'rect')
    }
    for (const lite of [false, true]) {
      const haus = zeichne({ hg: 'haus', lite })
      expect(ueberDemBild(haus.container), `lite=${lite}`).toHaveLength(0)
      expect(hintergrund(haus.container).querySelectorAll('rect[fill^="rgba("]'), `lite=${lite}`).toHaveLength(0)
      haus.unmount()
      const foto = zeichne({ hg: 'milchstrasse', lite })
      expect(ueberDemBild(foto.container).map(r => r.getAttribute('fill')), `lite=${lite}`)
        .toEqual(['rgba(255,255,255,0.35)', 'rgba(0,0,0,0.45)'])
      foto.unmount()
    }
  })

  it('das Grau-Rect der Tech-Fläche liegt als Unterlage UNTER den Bildern (sichtbar nur, solange ein Bild lädt)', () => {
    const { container } = zeichne({ hg: 'haus' })
    const kinder = [...hintergrund(container).children]
    const grau = kinder.findIndex(e => e.getAttribute('class') === 'fill-gray-100 dark:fill-gray-900')
    const erstesBild = kinder.findIndex(e => e.tagName.toLowerCase() === 'image')
    expect(grau).toBe(0)
    expect(erstesBild).toBeGreaterThan(grau)
    expect(hintergrund(container).querySelectorAll('rect[fill="#000"]')).toHaveLength(0)
  })

  it('die anderen Varianten zeigen kein Haus-Bild', () => {
    for (const hg of ['default', 'sunset', 'alps', 'milchstrasse']) {
      const { container, unmount } = zeichne({ hg })
      expect(hausBilder(container), hg).toHaveLength(0)
      unmount()
    }
  })
})

// ─── Regel E — keine Hintergrund-Deko, Vordergrund wie Tech ──────────

describe('Bau B Regel E — Hintergrund-Deko nie, Vordergrund-Effekte wie Tech', () => {
  const gitter = (c: HTMLElement) => hintergrund(c).querySelectorAll('g[mask="url(#ef-grid-mask)"]')
  const stroeme = (c: HTMLElement) => [...hintergrund(c).querySelectorAll('[style]')]
    .filter(e => /bg-stream|pulse-ring/.test(e.getAttribute('style') ?? ''))
  const hgPartikel = (c: HTMLElement) => hintergrund(c).querySelectorAll('circle > animateMotion')
  const randabdunklung = (c: HTMLElement) => hintergrund(c).querySelectorAll('rect[fill^="url(#ef-vignette"]')

  it('„Haus" mit Effekten: weder Strahlen-Gitter noch Deko-Ströme/Ringe/Hintergrund-Partikel', () => {
    const { container } = zeichne({ hg: 'haus', lite: false })
    expect(gitter(container)).toHaveLength(0)
    expect(stroeme(container)).toHaveLength(0)
    expect(hgPartikel(container)).toHaveLength(0)
  })

  it('Gegenprobe Foto-Variante mit Effekten: Gitter UND Ströme sind da (die Selektoren sehen, was sie suchen)', () => {
    const { container } = zeichne({ hg: 'milchstrasse', lite: false })
    expect(gitter(container)).toHaveLength(1)
    expect(stroeme(container).length).toBeGreaterThan(0)
    expect(hgPartikel(container).length).toBeGreaterThan(0)
  })

  it('Randabdunklung (Wächterprobe): bei „Haus" nie — ⚠ kein Sprengsatz möglich (Bedingung === \'default\')', () => {
    // Die Tiefe-Vignette rendert strukturell nur bei `bgVariant === 'default'`;
    // ein eigener Ausschluss für „Haus" wäre toter Code, ein Sprengsatz daran
    // bliebe zwangsläufig still. Diese Probe hält den Zustand fest, falls die
    // Bedingung je geöffnet wird. Gegenprobe: Tech zeigt sie.
    const haus = zeichne({ hg: 'haus', lite: false })
    expect(randabdunklung(haus.container)).toHaveLength(0)
    haus.unmount()
    const tech = zeichne({ hg: 'default', lite: false })
    expect(randabdunklung(tech.container)).toHaveLength(2)
  })

  it('die Vordergrund-Effekte laufen bei „Haus" wie bei Tech: Linien-Glow, Partikel, Haus-Glow, Kachelschatten', () => {
    const { container } = zeichne({ hg: 'haus', lite: false })
    const s = flaeche(container)
    expect(s.querySelectorAll('path[filter="url(#ef-line-glow)"]').length).toBeGreaterThan(0)
    expect(s.querySelectorAll(':scope > g > circle > animateMotion').length).toBeGreaterThan(0)
    expect(s.querySelectorAll('circle[filter="url(#ef-haus-glow)"]')).toHaveLength(1)
    expect(s.querySelectorAll('rect[filter="url(#ef-card-shadow)"]').length).toBeGreaterThan(0)
  })

  it('Vordergrund „Haus" = Vordergrund „Tech" + Saum — mit Effekten und in Lite, Karte und Handy', () => {
    for (const lite of [false, true]) for (const breite of [1150, 360]) {
      const tech = zeichne({ hg: 'default', lite, breite })
      const erwartet = vordergrundOhneSaum(tech.container)
      expect(saeume(tech.container)).toHaveLength(0)
      tech.unmount()
      const haus = zeichne({ hg: 'haus', lite, breite })
      expect(vordergrundOhneSaum(haus.container), `lite=${lite} ${breite}px`).toBe(erwartet)
      expect(saeume(haus.container).length, `lite=${lite} ${breite}px`).toBeGreaterThan(0)
      haus.unmount()
    }
  })

  it('Kachelpositionen „Haus" = „Tech" (Koordinaten jeder Kachel-Fläche)', () => {
    const koordinaten = (c: HTMLElement) => [...flaeche(c).querySelectorAll('g[data-title] > rect')]
      .map(r => ['x', 'y', 'width', 'height'].map(a => r.getAttribute(a)).join(','))
    const tech = zeichne({ hg: 'default' })
    const erwartet = koordinaten(tech.container)
    tech.unmount()
    const haus = zeichne({ hg: 'haus' })
    expect(erwartet.length).toBeGreaterThan(10)
    expect(koordinaten(haus.container)).toEqual(erwartet)
  })

  it('Foto-Varianten unverändert: Gitter vorhanden, kein Saum, Foto-Zweig mit #000-Unterlage', () => {
    for (const hg of ['alpenpanorama', 'milchstrasse', 'dolomiten', 'nebula', 'sternennacht', 'exoplanet']) {
      const { container, unmount } = zeichne({ hg, lite: false })
      expect(gitter(container), hg).toHaveLength(1)
      expect(saeume(container), hg).toHaveLength(0)
      expect(hintergrund(container).querySelectorAll('rect[fill="#000"]'), hg).toHaveLength(1)
      unmount()
    }
  })

  it('das Achsenkreuz bleibt bei „Haus" wie bei den Foto-Varianten (Regel D2, bewusste Zeile)', () => {
    const achsen = (c: HTMLElement) => hintergrund(c).querySelectorAll('line[stroke-dasharray="2 6"]')
    const haus = zeichne({ hg: 'haus' })
    expect(achsen(haus.container)).toHaveLength(2)
    haus.unmount()
    const foto = zeichne({ hg: 'milchstrasse' })
    expect(achsen(foto.container)).toHaveLength(2)
  })
})

// ─── Regel C — Linien-Saum ──────────────────────────────────────────

describe('Bau B Regel C — Saum je aktiver Flusslinie, nur „Haus", nur hell, in beiden Schalterstellungen', () => {
  it('Effekte UND Lite: je aktive Linie genau ein Saum, inaktive Linien keinen', () => {
    for (const lite of [false, true]) {
      const { container, unmount } = zeichne({ hg: 'haus', lite })
      const kerne = kernlinien(container)
      // Bestand D bei 1150 px: drei PV-Gruppen + WP + Netz aktiv, der Speicher ruht
      expect(kerne, `lite=${lite}`).toHaveLength(5)
      expect(saeume(container), `lite=${lite}`).toHaveLength(kerne.length)
      unmount()
    }
  })

  it('der Saum liegt zwischen Basis- und Kernlinie, Breite = Kernbreite + 2, Farbe aus colors.ts, Deckung 0,4', () => {
    const { container } = zeichne({ hg: 'haus', lite: true })
    expect(saeume(container).length).toBeGreaterThan(0)
    for (const saum of saeume(container)) {
      const basis = saum.previousElementSibling!
      const kern = saum.nextElementSibling!
      expect(basis.getAttribute('stroke-opacity')).toBe('0.2')
      expect(kern.getAttribute('stroke-opacity')).toBe('0.85')
      expect(Number(saum.getAttribute('stroke-width'))).toBeCloseTo(Number(kern.getAttribute('stroke-width')) + 2, 9)
      expect(saum.getAttribute('stroke')).toBe(ENERGIEFLUSS_SAUM)
      expect(saum.getAttribute('stroke-opacity')).toBe('0.4')
      expect(saum.getAttribute('d')).toBe(kern.getAttribute('d'))
      // kein Fluss-Effekt am Saum: die Lite-Animation trägt allein die Kernlinie
      expect(saum.getAttribute('class')).not.toMatch(/flow-line/)
    }
  })

  it('nur im hellen Bild: sichtbar hell, unsichtbar dunkel', () => {
    for (const lite of [false, true]) {
      const { container, unmount } = zeichne({ hg: 'haus', lite })
      expect(saeume(container).length, `lite=${lite}`).toBeGreaterThan(0)
      for (const saum of saeume(container)) {
        expect([deckung(saum, false), deckung(saum, true)], `lite=${lite}`).toEqual([1, 0])
      }
      unmount()
    }
  })

  it('kein Saum bei Tech, Sunset, Alpen und den Fotos', () => {
    for (const hg of ['default', 'sunset', 'alps', 'milchstrasse']) for (const lite of [false, true]) {
      const { container, unmount } = zeichne({ hg, lite })
      expect(saeume(container), `${hg} lite=${lite}`).toHaveLength(0)
      unmount()
    }
  })
})

// ─── Regel D — Solar-Soll ───────────────────────────────────────────

describe('Bau B Regel D — Solar-Soll auf dem Bild', () => {
  const sollKlasse = (hg: string) => {
    const { container, unmount } = zeichne({ hg, soll: 12.4 })
    const k = container.querySelector('text[data-solar-soll]')?.getAttribute('class')
    unmount()
    return k
  }
  it('„Haus": hell indigo-800 (6,4:1 statt 2,55:1), dunkel der Bestand purple-400', () => {
    expect(sollKlasse('haus')).toBe('fill-indigo-800 dark:fill-purple-400')
  })
  it('Tech, Sunset, Alpen und Fotos unverändert', () => {
    expect(sollKlasse('default')).toBe('fill-purple-500 dark:fill-purple-400')
    expect(sollKlasse('milchstrasse')).toBe('fill-purple-500 dark:fill-purple-400')
    expect(sollKlasse('sunset')).toBe('fill-purple-800 dark:fill-purple-400')
    expect(sollKlasse('alps')).toBe('fill-indigo-800 dark:fill-indigo-300')
  })
})

// ─── Persistenz ─────────────────────────────────────────────────────

describe('Bau B — Auswahl und Persistenz über den Bestand', () => {
  const auswahl = (c: HTMLElement) => c.querySelector('select[title="Hintergrund wählen"]') as HTMLSelectElement

  it('„Haus" steht in der Auswahl direkt nach „Tech"; Standard bleibt Tech', () => {
    const { container } = zeichne({ hg: 'default' })
    const optionen = [...auswahl(container).options].map(o => [o.value, o.textContent])
    expect(optionen.slice(0, 2)).toEqual([['default', 'Tech'], ['haus', 'Haus']])
    expect(optionen).toHaveLength(10)
  })

  it('gespeichertes „haus" wird übernommen und bleibt gespeichert', () => {
    const { container } = zeichne({ hg: 'haus' })
    expect(auswahl(container).value).toBe('haus')
    expect(localStorage.getItem(BG_KEY)).toBe('haus')
  })

  it('Alt-Werte bleiben; ohne oder mit unbekanntem Wert gilt Tech', () => {
    const a = zeichne({ hg: 'alpenpanorama' })
    expect(auswahl(a.container).value).toBe('alpenpanorama')
    a.unmount()
    const b = zeichne({ hg: 'gibtsnicht' })
    expect(auswahl(b.container).value).toBe('default')
    b.unmount()
    localStorage.clear()
    mitMass(1150)
    const c = render(
      <ThemeProvider>
        <EnergieFluss komponenten={bestandD()} summeErzeugung={1} summeVerbrauch={1} summePv={1} gauges={[]} />
      </ThemeProvider>,
    )
    expect(auswahl(c.container).value).toBe('default')
  })
})
