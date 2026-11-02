/**
 * Wächter «feste Uhr in Proben» (Nachlauf 4.2.1 N7, Entscheid Gernot 2.11.2026) — Gegenstück zum Backend-Wächter
 * `backend/tests/test_konformitaet_echte_uhr_in_tests.py` (N-167).
 *
 * **Anlass.** Der Tests-Workflow zum Release 4.2.0 (2.11.2026) war rot, ohne dass sich am Produkt etwas geändert hatte:
 * drei Fälle in `ueberblickParken.test.tsx` bauten ihr Fixture aus einem festen Datum (1.11.2026, 11:27) und riefen
 * `vi.useFakeTimers()` **ohne** `vi.setSystemTime` — «Stand 11:27» stimmte nur am 1.11., am Folgetag stand «Stand 1.11.
 * 11:27». Eine Probe mit festem Datum, aber laufender Uhr wettet auf heute.
 *
 * **Regel.** Eine Probendatei (`*.test.ts`, `*.test.tsx` unter `src/`) mit einem **Datums-Literal** — `new Date(2…,`
 * (Jahr vierstellig, Zahlen-Form) · `new Date('2…-` · ISO-String `'2…-MM-TT` — **und ohne** `vi.setSystemTime(` oder
 * `vi.useFakeTimers({ now` gilt als «Wette auf heute». Die Dateien, die das am 2.11.2026 schon taten, stehen in der
 * Baseline `feste-uhr-baseline.json`; der Wächter
 *  (a) meldet jede Datei **außerhalb** der Baseline mit Treffer rot (Klartext mit dem Handgriff),
 *  (b) meldet eine Baseline-Datei **ohne** Treffer rot — sie ist aus der Baseline zu streichen; die Baseline schrumpft
 *      nur (Muster Komplexitäts-Wächter `backend/tests/test_kognitive_komplexitaet.py`),
 *  (c) schreibt die Baseline neu nur auf ausdrücklichen Befehl:
 *      `FESTE_UHR_BASELINE=schreiben npx vitest run src/test/feste-uhr-in-tests.test.ts` (aus `eedc/frontend`).
 * Er heilt keine bestehende Probe — er verhindert, dass eine neue dazukommt.
 *
 * **Kommentare zählen nicht.** Zeilen, die nach dem Trim mit `//`, `/*` oder `*` beginnen, werden übersprungen — für
 * das Literal **und** für die feste Uhr. Lehre aus dem Backend-Wächter: ein Prüfer, der eine Probe anmeckert, die im
 * Kommentar beschreibt, was sie vermeidet, bestraft Vorbildlichkeit und wird beim ersten roten Lauf abgeschaltet.
 *
 * **Gernots Vorgabe:** kein Pre-Commit-Hook — der Wächter ist ein gewöhnlicher Vitest-Fall und läuft mit `npm run test`
 * (lokal vor dem Release, in CI beim Push) parallel zu allem anderen.
 *
 * **Was er nicht kann:**
 *  - Kalenderkanten (Monatsende, Jahreswechsel, Schaltjahr, Zeitumstellung) misst er nicht; er hält nur fest, wer auf
 *    die echte Uhr wettet. `vitest.config.ts` pinnt die Zone (`TZ=Europe/Berlin`), nicht die Uhr. Der
 *    `freezegun`-Entscheid (23.08.2026) gilt fürs Backend; im Frontend ist `vi.setSystemTime` Bordmittel.
 *  - Er urteilt **je Datei**: eine Datei mit fester Uhr in einem `describe` gilt als frei, auch wenn ein anderes
 *    `describe` derselben Datei sie nicht stellt.
 *  - Literale in anderer Form sieht er nicht: `new Date(Date.UTC(2026, …))`, ISO-Strings in `"…"` oder Template-Strings,
 *    Datumsobjekte aus Fixture-Dateien (`*.json`). Ein Datums-Literal ist auch kein Beweis für eine Wette — eine reine
 *    Formatier-Probe mit festem Datum ist harmlos und steht trotzdem in der Baseline.
 *
 * Handgriff für eine neue Probe: `vi.useFakeTimers(); vi.setSystemTime(new Date(…))` im `beforeEach` (und
 * `vi.useRealTimers()` im `afterEach`), oder das Fixture aus `new Date()` ableiten.
 *
 * Schwesterdateien: `fokus-id-vertrag.test.ts` (Muster Vitest-Wächter mit JSON), `backend/tests/test_konformitaet_echte_uhr_in_tests.py`.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

const WURZEL = process.cwd()
const SRC = join(WURZEL, 'src')
const BASELINE = join(SRC, 'test', 'feste-uhr-baseline.json')
const SELBST = 'src/test/feste-uhr-in-tests.test.ts'

/** Datums-Literale: Zahlen-Form mit vierstelligem Jahr, String-Form im Konstruktor, ISO-Datum — je in einfachen Anführungen (Auftrag N7). */
const DATUMS_LITERAL: RegExp[] = [
  /new Date\(2\d{3},/,
  /new Date\('2\d{3}-/,
  /'2\d{3}-\d\d-\d\d/,
]
/** Eine feste Uhr: `vi.setSystemTime(` oder `vi.useFakeTimers({ now … })`. */
const FESTE_UHR: RegExp[] = [
  /vi\.setSystemTime\(/,
  /vi\.useFakeTimers\(\s*\{\s*now\b/,
]

const KLARTEXT = 'Datums-Literal ohne feste Uhr — `vi.useFakeTimers(); vi.setSystemTime(new Date(…))` im `beforeEach`, '
  + 'oder Fixture aus `new Date()` ableiten'

function probendateien(dir: string): string[] {
  const out: string[] = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) out.push(...probendateien(p))
    else if (/\.test\.tsx?$/.test(n)) out.push(p)
  }
  return out
}

/** Code-Zeilen ohne Kommentarzeilen (`//`, `/*`, `*` nach dem Trim). */
function codeZeilen(text: string): string[] {
  return text.split('\n').filter((z) => {
    const t = z.trimStart()
    return !(t.startsWith('//') || t.startsWith('/*') || t.startsWith('*'))
  })
}

/** Ist die Datei eine «Wette auf heute»? (Literal in Code-Zeilen und keine feste Uhr in Code-Zeilen.) */
export function wettetAufHeute(text: string): boolean {
  const zeilen = codeZeilen(text)
  const literal = zeilen.some((z) => DATUMS_LITERAL.some((r) => r.test(z)))
  return literal && !zeilen.some((z) => FESTE_UHR.some((r) => r.test(z)))
}

/** Alle Probendateien mit Treffer, Pfade relativ zu `eedc/frontend`, sortiert. */
export function ernteWetten(): string[] {
  return probendateien(SRC)
    .map((p) => relative(WURZEL, p).split('\\').join('/'))
    .filter((kurz) => kurz !== SELBST && wettetAufHeute(readFileSync(join(WURZEL, kurz), 'utf8')))
    .sort()
}

describe('Wächter «feste Uhr in Proben» (N7)', () => {
  it('erkennt die Wette und überspringt Kommentare (Selbstprobe)', () => {
    expect(wettetAufHeute("const d = new Date(2026, 10, 1, 11, 27)")).toBe(true)
    expect(wettetAufHeute("const d = new Date('2026-11-01T11:27:00')")).toBe(true)
    expect(wettetAufHeute("const tag = '2026-11-01'")).toBe(true)
    // Feste Uhr in derselben Datei ⇒ frei (beide Formen).
    expect(wettetAufHeute("vi.setSystemTime(new Date(2026, 10, 1))\nconst d = new Date(2026, 10, 1)")).toBe(false)
    expect(wettetAufHeute("vi.useFakeTimers({ now: new Date(2026, 10, 1) })\nconst t = '2026-11-01'")).toBe(false)
    // `vi.useFakeTimers()` allein stellt die Uhr NICHT (der Fall von 4.2.0).
    expect(wettetAufHeute("vi.useFakeTimers()\nconst d = new Date(2026, 10, 1, 11, 27)")).toBe(true)
    // Kommentare zählen nicht — weder das Literal noch die feste Uhr.
    expect(wettetAufHeute("// früher: new Date(2026, 10, 1)\n * '2026-11-01' im Docstring\nconst d = new Date()")).toBe(false)
    expect(wettetAufHeute("// vi.setSystemTime(new Date())\nconst d = new Date(2026, 0, 1)")).toBe(true)
    // Kein Datums-Literal: Zeitpunkte aus `new Date()` abgeleitet.
    expect(wettetAufHeute("const d = new Date(); d.setHours(11, 27)")).toBe(false)
  })

  it('jede Probendatei mit Datums-Literal ohne feste Uhr steht in der Baseline, und die Baseline schrumpft nur', () => {
    const ist = ernteWetten()
    if (process.env.FESTE_UHR_BASELINE === 'schreiben') {
      writeFileSync(BASELINE, JSON.stringify(ist, null, 2) + '\n')
      return
    }
    expect(existsSync(BASELINE), `Baseline fehlt: ${relative(WURZEL, BASELINE)}`).toBe(true)
    const soll = JSON.parse(readFileSync(BASELINE, 'utf8')) as string[]
    const neu = ist.filter((d) => !soll.includes(d))
    const geheilt = soll.filter((d) => !ist.includes(d))
    expect(neu, `${KLARTEXT}:\n  ${neu.join('\n  ')}`).toEqual([])
    expect(
      geheilt,
      'Diese Dateien wetten nicht mehr auf heute (feste Uhr gestellt, Literal entfernt oder Datei weg) — aus '
      + `src/test/feste-uhr-baseline.json streichen (die Baseline schrumpft nur):\n  ${geheilt.join('\n  ')}`,
    ).toEqual([])
  })
})
