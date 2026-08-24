import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

// ── Waechter der Waechter-EINHAENGUNG (M14, Etappe E8, 2026-08-24) ──────────
//
// Die Regel: JEDER `check:*` aus package.json ist von `npm test` aus erreichbar
// — genau EINE Einhaengungsebene. Keine zweite (eigener CI-Schritt), keine
// nullte (nur die Liste in `CLAUDE.md`).
//
// Warum es diese Probe gibt. Am 24.08. gemessen: von 27 `check:*` liefen VIER
// nirgends automatisch (`form-controls`, `parkbar`, `parkbar-vollstaendig`,
// `sperre-fetch`) und ZWEI nur in CI (`roh-controls`, `kennwert-roh`), waehrend
// DREI doppelt liefen (`design`, `achsen`, `de-de`). Alle drei Zustaende sind
// dieselbe Ursache: die Einhaengung war Ermessen. Ein Pruefer, den nur eine
// Doku-Liste kennt, ist eine Gedaechtnisstuetze und kein Waechter (`lint`,
// 12.08.); einer, den nur CI kennt, meldet erst nach dem Push und ordnet den
// Fehler keinem einzelnen Commit mehr zu (N-167, 13.08.). Ohne diese Probe waere
// M14 eine einmalige Aufraeumung, die genauso wieder auseinanderlaeuft.
//
// ⛔ Das ist NICHT der am 23.08. zurueckgezogene Meta-Waechter. Der sollte die
// Klasse „Pruefer meldet gruen, ohne etwas gemessen zu haben" buendeln — fuenf
// Faelle mit fuenf verschiedenen Ursachen, drei davon nur inhaltlich erkennbar;
// Gernots Einwand „Kontrolle der Kontrolleure mit fraglichem Ergebnis" traf, und
// die Messung gab ihm recht. Diese Probe prueft KEINE inhaltliche Korrektheit
// eines Pruefers, sondern eine einzige mechanische Eigenschaft: steht sein Name
// in einem Wrapper? Das ist die enge, messbare Fassung — derselbe Schnitt, der
// bei N-318 aus einer wertlosen weiten Fassung (alle 27) zwei echte Faelle
// gemacht hat.
const FRONTEND_ROOT = process.cwd()

// Die beiden Pruefer, die BEWUSST draussen bleiben: beide sind Playwright-
// Livetests gegen eine laufende Box (Runbook `~/.claude/plans/runbook-dev-box.md`),
// keine Quelltext-Pruefer. `park-leertest` verlangt zusaetzlich ein
// `VITE_DEMO_DEFAULT=true`-Build und ist mit 188 s der teuerste Einzelpruefer
// ueberhaupt — er laeuft seit dem 23.08. am Ausloeser statt am Takt (Entscheid
// Gernot, `CLAUDE.md` §Gates). In Vitest wuerden beide ohne Box schlicht
// scheitern.
const OHNE_WRAPPER_MIT_GRUND: Record<string, string> = {
  'check:park-leertest': 'Playwright gegen laufende Box + Demo-Build; laeuft am Ausloeser',
  'check:chart-audit': 'Playwright gegen laufende Box',
}

function checkSkripte(): Map<string, string> {
  const pkg = JSON.parse(readFileSync(join(FRONTEND_ROOT, 'package.json'), 'utf8'))
  const map = new Map<string, string>()
  for (const [name, befehl] of Object.entries(pkg.scripts as Record<string, string>)) {
    if (!name.startsWith('check:')) continue
    const treffer = /scripts\/([a-z0-9-]+\.mjs)/.exec(befehl)
    if (treffer) map.set(name, treffer[1])
  }
  return map
}

function gewrappteSkripte(): Set<string> {
  const verzeichnis = join(FRONTEND_ROOT, 'src', 'test')
  const gefunden = new Set<string>()
  for (const datei of readdirSync(verzeichnis)) {
    if (!datei.endsWith('.test.ts') && !datei.endsWith('.test.tsx')) continue
    const inhalt = readFileSync(join(verzeichnis, datei), 'utf8')
    for (const m of inhalt.matchAll(/scripts\/([a-z0-9-]+\.mjs)/g)) gefunden.add(m[1])
  }
  return gefunden
}

describe('Waechter-Einhaengung auf EINE Ebene (M14)', () => {
  it('jeder check:* ist von npm test aus erreichbar', () => {
    const skripte = checkSkripte()
    const gewrappt = gewrappteSkripte()
    const fehlend = [...skripte]
      .filter(([name, mjs]) => !gewrappt.has(mjs) && !(name in OHNE_WRAPPER_MIT_GRUND))
      .map(([name, mjs]) => `  ${name} (scripts/${mjs})`)

    expect(
      fehlend,
      'Pruefer ohne Vitest-Wrapper — sie laufen nirgends automatisch:\n' +
        fehlend.join('\n') +
        '\n\nEntweder einen Wrapper nach dem Muster von check-co2-roh.test.ts ' +
        'anlegen, oder — wenn der Pruefer eine laufende Box braucht — mit ' +
        'Begruendung in OHNE_WRAPPER_MIT_GRUND eintragen.',
    ).toEqual([])
  })

  it('die Ausnahmeliste ist noch belegt', () => {
    // Abschmelzend, dieselbe Mechanik wie `_BASELINE` im Uhr-Waechter (M5) und
    // `P3A_BASELINE_AUSNAHMEN`: ein Eintrag, den es nicht mehr gibt oder der
    // laengst einen Wrapper hat, deckt sonst spaeter eine neue Luecke zu. Genau
    // so hat `EXPECTED_ROUTES = 217` gegen 271 reale Routen jahrelang nichts
    // mehr gemessen (M1).
    const skripte = checkSkripte()
    const gewrappt = gewrappteSkripte()
    const tot = Object.keys(OHNE_WRAPPER_MIT_GRUND)
      .filter((name) => !skripte.has(name) || gewrappt.has(skripte.get(name)!))
      .map((name) => `  ${name}`)

    expect(
      tot,
      'Ausnahme ohne Gegenstand — Eintrag streichen:\n' + tot.join('\n'),
    ).toEqual([])
  })
})
