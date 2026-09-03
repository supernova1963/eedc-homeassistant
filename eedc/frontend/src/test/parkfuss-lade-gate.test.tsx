import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { ParkProvider } from '../components/park/ParkContext'
import { ParkFuss } from '../components/park/ParkFuss'

// ── N-385 — der Parkplatz steht nicht im Bild, während die Sicht lädt ────────
//
// Gemeldet von rapahl per PN (simon42 92078, 03.09.2026): „Wenn beim Start von
// eedc auf der Live-Board-Seite etwas geparkt ist, wird dieser Park-Streifen ca.
// 0,5 - 1 sec. angezeigt, bevor das Flussdiagramm erscheint."
//
// Ursache: Der Park-Zustand kommt SYNCHRON aus `localStorage` (`ParkContext`,
// `useState(() => laden(...))`), der Seiteninhalt asynchron. In den fünf
// Cockpit-Sichten steht der Skeleton INLINE in einem Ternär und `<ParkFuss />`
// daneben — also außerhalb des Ladezweigs.
//
// ⭐ Zweite Runde: dieselbe Sache wurde am 13.08.2026 für den Börsenpreis-Block
// gelöst (`CockpitLiveV4.tsx:406`, `!loading`) — derselbe Melder, dieselbe Seite.
//
// ⛔ Diese Datei prüft ZWEI verschiedene Dinge, und das ist Absicht:
//   1. VERHALTEN — hält `bereit={false}` den Streifen wirklich zurück?
//   2. STRUKTUR   — wendet jede Sicht die Regel an, die sie anwenden muss?
// Probe 1 allein wäre wertlos: sie kann nicht rot werden, wenn eine Sicht das
// Prop schlicht vergisst. Probe 2 allein auch: sie sieht nur Zeichenketten.
const FRONTEND_ROOT = process.cwd()
const V4_DIR = join(FRONTEND_ROOT, 'src', 'v4')

// ⛔ Der Präfix ist aus `ParkContext.tsx:21` ABGESCHRIEBEN, nicht geraten. Mein erster
// Entwurf hatte `eedc.park.` — damit hätte `laden()` nichts gefunden, `GeparktBlock` hätte
// auch bei `bereit={true}` nichts gerendert, und die erste Probe wäre GRÜN geworden, ohne
// etwas zu messen. Gefangen hat es die zweite Probe (Default ⇒ Streifen MUSS erscheinen);
// das ist der Grund, warum sie hier steht und nicht als Redundanz weggekürzt wird.
const LS_PREFIX = 'eedc-park:'
const SICHT = 'test-parkfuss-lade-gate'

function mitGeparktemEintrag() {
  localStorage.setItem(
    LS_PREFIX + SICHT,
    JSON.stringify([{ id: 'el:irgendwas', titel: 'Eine geparkte Anzeige' }]),
  )
}

describe('N-385 — Verhalten: ParkFuss hält sich zurück, solange die Sicht lädt', () => {
  it('bereit={false} rendert nichts, OBWOHL etwas geparkt ist', () => {
    mitGeparktemEintrag()
    render(
      <ParkProvider persistKey={SICHT}>
        <ParkFuss bereit={false} />
      </ParkProvider>,
    )
    // Der Parkplatz-Streifen trägt `data-park-recovery` (GeparktBlock).
    expect(document.querySelector('[data-park-recovery]')).toBeNull()
    expect(screen.queryByText(/Parkplatz \(/)).toBeNull()
  })

  it('ohne das Prop (Default) erscheint er — die 13 Sichten mit Früh-Return bleiben unberührt', () => {
    mitGeparktemEintrag()
    render(
      <ParkProvider persistKey={SICHT}>
        <ParkFuss />
      </ParkProvider>,
    )
    expect(document.querySelector('[data-park-recovery]')).not.toBeNull()
    expect(screen.getByText(/Parkplatz \(1\)/)).toBeTruthy()
  })

  it('bereit={true} erscheint er ebenfalls — das Gate wirkt nur in eine Richtung', () => {
    mitGeparktemEintrag()
    render(
      <ParkProvider persistKey={SICHT}>
        <ParkFuss bereit />
      </ParkProvider>,
    )
    expect(document.querySelector('[data-park-recovery]')).not.toBeNull()
  })
})

// ── Struktur-Prüfer ─────────────────────────────────────────────────────────
//
// ⭐ Er misst die BEDINGUNG, nicht das VORKOMMEN — und genau daran ist meine
// erste Zählung beim Bau von N-385 gescheitert: „18 von 18 v4-Sichten rendern
// `ParkFuss` ohne Gate" zählte `<ParkFuss` und übersah, dass DREIZEHN dieser
// Sichten bei `loading` früh zurückkehren und die Zeile während des Ladens gar
// nicht erreichen. Betroffen sind fünf. Dieselbe Klasse wie die drei verworfenen
// Fassungen des Park-Auslösers in CLAUDE.md (Vorkommen statt Bedingung gezählt).
//
// Die Regel, die er festhält: Eine v4-Sicht darf `<ParkFuss` nur dann OHNE
// `bereit=` rendern, wenn sie bei `loading` früh zurückkehrt. Zeigt sie ihren
// Skeleton inline, muss sie das Prop setzen.
describe('N-385 — Struktur: jede v4-Sicht mit Inline-Skeleton setzt bereit=', () => {
  it('keine Sicht rendert ParkFuss ungegated neben einem Inline-Ladezweig', () => {
    const verstoesse: string[] = []

    for (const datei of readdirSync(V4_DIR).filter((d) => d.endsWith('V4.tsx'))) {
      const src = readFileSync(join(V4_DIR, datei), 'utf-8')
      const zeilen = src.split('\n')
      const pfIndex = zeilen.findIndex((z) => z.includes('<ParkFuss'))
      if (pfIndex === -1) continue
      if (zeilen[pfIndex].includes('bereit=')) continue // gegated → in Ordnung

      // Kehrt die Sicht VOR dieser Zeile bei einem Ladezustand früh zurück?
      // `if (…loading…) return` bzw. `if (…loading…) {` auf Anweisungsebene —
      // ein `return` innerhalb eines useEffect zählt NICHT, deshalb die
      // Einrückungsgrenze von höchstens vier Zeichen (Rumpf der Komponente).
      const fruehReturn = zeilen.slice(0, pfIndex).some((z) =>
        /^ {0,4}if \([^)]*[Ll]oading[^)]*\)\s*(return|\{)/.test(z),
      )
      if (!fruehReturn) {
        verstoesse.push(
          `${datei}:${pfIndex + 1} — <ParkFuss ohne bereit=, aber kein Früh-Return auf loading`,
        )
      }
    }

    expect(
      verstoesse,
      `Diese Sichten zeigen ihren Skeleton inline und lassen den Parkplatz daneben stehen ` +
        `(N-385). Entweder \`bereit={!loading}\` setzen — mit DERSELBEN Bedingung, die den ` +
        `Skeleton zeigt — oder bei loading früh zurückkehren:\n  ${verstoesse.join('\n  ')}`,
    ).toEqual([])
  })

  it('die fünf Cockpit-Sichten sind gegated — Gegenprobe zur Regel darüber', () => {
    // Ohne diese Zusicherung könnte die Probe oben grün sein, WEIL niemand mehr
    // `ParkFuss` rendert. Sie pinnt, dass die fünf bekannten Fälle das Prop
    // tatsächlich tragen.
    const erwartet = [
      'CockpitLiveV4.tsx',
      'CockpitTagV4.tsx',
      'CockpitMonatV4.tsx',
      'CockpitJahrV4.tsx',
      'CockpitAussichtV4.tsx',
    ]
    for (const datei of erwartet) {
      const src = readFileSync(join(V4_DIR, datei), 'utf-8')
      expect(src, `${datei} muss <ParkFuss bereit={…} /> tragen (N-385)`).toMatch(
        /<ParkFuss bereit=\{/,
      )
    }
  })
})
