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

// Der EINE Pruefer, der BEWUSST draussen bleibt: ein Playwright-Livetest gegen
// eine laufende Box (Runbook `~/.claude/plans/runbook-dev-box.md`), kein
// Quelltext-Pruefer. In Vitest wuerde er ohne Box schlicht scheitern.
//
// ⛔ Hier stand bis zum 2026-09-06 ein zweiter Eintrag, `check:park-leertest`.
// Den gibt es nicht mehr: er ist durch `check:park-gate` und
// `check:park-idliste` ersetzt (Entscheid Gernot). Beide sind Quelltext-Pruefer
// mit Wrapper — die Park-Doktrin haengt damit nicht mehr an einem 188-s-Livetest,
// der nur am Ausloeser lief und 18 handgepflegte Routen kannte. **Die
// Ausnahmeliste hat den Wegfall selbst gemeldet**: die zweite Probe unten wurde
// rot, sobald das Skript aus `package.json` verschwand. Genau dafuer ist sie da.
const OHNE_WRAPPER_MIT_GRUND: Record<string, string> = {
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
