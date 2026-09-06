#!/usr/bin/env node
/**
 * chart-audit.mjs — Laufzeit-Gate der Chart-Komposition (B7 / D17-4 / D17-6, 2026-07-09).
 *
 * Der statische `check:charts` deckt Pie-SoT + Legenden-Bildsprache grep-bar ab. Die
 * DREI Chart-Regeln, die statisch prinzipiell unsichtbar sind, prüft dieser Gate am
 * gerenderten DOM (Chromium) — genau die Gernot-Audit-Lehre „prüfe die Bild-Komposition":
 *
 *   L1 — Label-Overflow: KEIN Achsen-Tick-/Legenden-Text darf über seinen Chart-Container
 *        hinausragen (D17-4 „Text abgeschnitten"). Statisch unsichtbar (Render-Geometrie).
 *   L2 — Legende-Pflicht bei Multi-Serie: ein kartesischer Chart (Bar/Line/Area) mit >1
 *        GERENDERTER Serie MUSS eine Legende tragen. Statisch unsichtbar, weil Serien oft
 *        via `.map()` aus EINEM `<Bar>`-Literal entstehen ([[feedback_verifiziert_nur_was_check_abdeckt]]).
 *        Einzelserien (WP-Saison) sind bewusst legende-frei → nicht geflaggt.
 *   L3 — Legenden-Toggle-Pflicht: die Legende einer Multi-Serie MUSS klickbar sein
 *        (B7-Standard `useLegendenToggle`, 2026-07-18) — erkennbar am role="button",
 *        das `ChartLegende` nur bei gesetztem `onItemClick` rendert.
 *
 * Voraussetzung: mit `VITE_DEMO_DEFAULT=true` gebautes `dist` auf $EEDC_BASE (Default :8200) + Chromium unter
 * $PLAYWRIGHT_CHROMIUM. Sie wird seit 2026-08-27 GEPRUEFT statt vorausgesetzt
 * (`demo-box-vorflug.mjs`) — gegen ein Bundle ohne das Flag meldete dieser Lauf 37 statt 44
 * Charts und trotzdem gruen. ⚑ Seit dem 2026-09-06 ist er das **einzige** Laufzeit-Gate:
 * `park-leertest` ist durch die Quelltext-Waechter `check:park-gate` und
 * `check:park-idliste` ersetzt.
 * Kein CI-Pflichtlauf — Dev-Box-Kommando ([[reference_recharts_bars_jsdom]]):
 *
 *   VITE_DEMO_DEFAULT=true npm run build
 *   npm run check:chart-audit
 */
import { chromium } from 'playwright-core'
import { pruefeDemoBox } from './demo-box-vorflug.mjs'

const CHROME = process.env.PLAYWRIGHT_CHROMIUM
  || '/home/gernot/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'
const BASE = process.env.EEDC_BASE || 'http://localhost:8200'
const TOLERANZ = 2 // px Nachsicht gegen Sub-Pixel-Rundung

// Sichten mit Charts (Kompositions-relevant) — die KANONISCHEN, prefix-freien Pfade.
//
// ⛔ **Bis 2026-09-06 trugen sie alle den `/v4/`-Präfix aus der Vorschauzeit** (gefallen mit
// dem IA-V4-Flip in v4.0.0). `App.tsx` biegt ihn per Stray-Bookmark-Route um, der Lauf
// funktionierte also — aber **zwei der sechzehn landeten woanders, als ihr Name sagt**:
// `komponenten/pv-module` und `komponenten/balkonkraftwerk` sind keine Hub-Keys (die heißen
// `pv-anlage` und `bkw`), und `KomponentenV4` leitet einen unbekannten Typ auf den **ersten
// verfügbaren** um. Der Lauf maß damit die erste Komponenten-Sicht dreimal und die
// **BKW-Sicht nie** — und meldete trotzdem „16 Sichten geprueft". Ein Prüfer, der eine
// Sicht nennt, die er nicht ansieht (N-330).
const ROUTES = [
  '#/auswertungen/roi', '#/auswertungen/finanzen', '#/auswertungen/co2',
  '#/auswertungen/prognose',
  '#/komponenten/pv-anlage', '#/komponenten/speicher', '#/komponenten/waermepumpe',
  '#/komponenten/e-auto', '#/komponenten/wallbox', '#/komponenten/bkw',
  '#/cockpit/monat', '#/cockpit/jahr', '#/cockpit/tag', '#/cockpit/aussicht',
  '#/community/uebersicht', '#/community/komponenten',
]

async function alleAufklappen(page) {
  for (let i = 0; i < 8; i++) {
    const zu = await page.$$('button[aria-label="aufklappen"]')
    if (!zu.length) break
    for (const b of zu) { try { await b.click({ timeout: 500 }) } catch { /* Reflow */ } }
    await warteAufRuhe(page, 1)
  }
  await warteAufRuhe(page)
}

/**
 * N-330 — **Kriterium statt Frist.** Bis 2026-09-06 wartete dieser Lauf feste 700 + 900 ms
 * und zählte dann. Ergebnis: dieselbe Box, dasselbe Bundle, unveränderter Code, drei Läufe
 * — **43 · 43 · 44 Charts**, alle drei Exit 0 und grün. Die Abweichung saß in genau EINER
 * Sicht (`cockpit/jahr` lieferte 0 · 0 · 1). *Eine Wartezeit ist eine Wette auf die
 * langsamste Maschine; ein Kriterium ist es nicht.*
 *
 * Die Sicht gilt als fertig, wenn (a) kein Skeleton mehr im DOM steht und (b) die Zahl der
 * `.recharts-wrapper` über zwei aufeinanderfolgende Ticks gleich bleibt. Die Obergrenze
 * bleibt als Notbremse — ohne sie stünde ein Lauf gegen eine hängende Sicht ewig.
 */
async function warteAufRuhe(page, minStabil = 2, maxMs = 12000) {
  const TICK = 250
  let stabil = 0
  let zuletzt = -1
  for (let vergangen = 0; vergangen < maxMs; vergangen += TICK) {
    await page.waitForTimeout(TICK)
    const { charts, laedt } = await page.evaluate(() => ({
      charts: document.querySelectorAll('.recharts-wrapper').length,
      // Skeleton/Spinner der App: `animate-pulse` (BlockStackSkeleton) bzw. der
      // Lade-Spinner. Solange einer steht, ist die Sicht nicht fertig.
      laedt: !!document.querySelector('.animate-pulse, [role="status"]'),
    }))
    if (laedt) { stabil = 0; zuletzt = -1; continue }
    if (charts === zuletzt) {
      if (++stabil >= minStabil) return
    } else {
      stabil = 0
      zuletzt = charts
    }
  }
}

// Prüft im Browser jeden .recharts-wrapper der aktuellen Sicht.
function auditDom() {
  return page => page.evaluate((tol) => {
    const treffer = []
    let geprueft = 0
    const wraps = [...document.querySelectorAll('.recharts-wrapper')]
    wraps.forEach((w, idx) => {
      const box = w.getBoundingClientRect()
      if (box.width < 4 || box.height < 4) return // nicht sichtbar gerendert
      geprueft++
      const kennung = `chart#${idx}`

      // L1 — Overflow von Tick-/Legenden-Text über den Container.
      const texte = [
        ...w.querySelectorAll('.recharts-cartesian-axis-tick-value'),
        ...w.querySelectorAll('.recharts-legend-item-text'),
      ]
      for (const t of texte) {
        const r = t.getBoundingClientRect()
        if (r.width === 0 && r.height === 0) continue
        const raus = []
        if (r.left < box.left - tol) raus.push('links')
        if (r.right > box.right + tol) raus.push('rechts')
        if (r.top < box.top - tol) raus.push('oben')
        if (r.bottom > box.bottom + tol) raus.push('unten')
        if (raus.length) {
          treffer.push(`L1 Overflow (${raus.join('+')}): „${(t.textContent || '').trim()}" @ ${kennung}`)
        }
      }

      // L2 — Multi-Serie ohne Legende (nur kartesisch; Pie/Donut trägt eigene ul-Legende).
      const istPie = !!w.querySelector('.recharts-pie')
      if (!istPie) {
        const serien = w.querySelectorAll('.recharts-bar, .recharts-line, .recharts-area').length
        // Legende = Recharts-`<Legend>`-Wrapper mit Inhalt. ChartLegende rendert eine
        // eigene <ul><li>-Struktur (KEIN `.recharts-legend-item`) — daher am Wrapper +
        // nicht-leerem Text erkennen, nicht am Default-Item.
        const leg = w.querySelector('.recharts-legend-wrapper')
        const hatLegende = !!leg && (leg.textContent || '').trim().length > 0
        if (serien >= 2 && !hatLegende) {
          treffer.push(`L2 Multi-Serie (${serien}) ohne Legende @ ${kennung}`)
        }
        // L3 — Legenden-Toggle-Pflicht bei Multi-Serie (B7-Standard, 2026-07-18):
        // ChartLegende rendert die Einträge mit role="button", sobald onItemClick
        // gesetzt ist — fehlt das, ist der Toggle nicht verdrahtet. Statisch
        // unsichtbar (`.map()`-Serien), daher hier am gerenderten DOM.
        if (serien >= 2 && hatLegende) {
          const eintraege = leg.querySelectorAll('li').length
          const klickbar = leg.querySelectorAll('li[role="button"]').length
          if (eintraege > 0 && klickbar === 0) {
            treffer.push(`L3 Multi-Serie (${serien}) mit Legende ohne Toggle (kein role="button") @ ${kennung}`)
          }
        }
      }
    })
    // N-318: Die Zahl der geprueften Charts wandert mit nach draussen. Ohne sie sieht ein
    // Lauf gegen eine datenlose Box exakt so aus wie ein Lauf ohne Befund.
    return { treffer, geprueft }
  }, TOLERANZ)
}

async function main() {
  const browser = await chromium.launch({ executablePath: CHROME })
  // Vorflug (27.08.): erst die eigene Voraussetzung, dann messen. Bis dahin hatte dieser
  // Lauf nur die Schwelle „0 Charts" — gegen eine Box mit dem FALSCHEN Bundle meldete er
  // 37 statt 44 Charts und Exit 0.
  await pruefeDemoBox(browser, BASE, 'chart-audit')
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const audit = auditDom()
  const probleme = []
  let geprueftGesamt = 0

  for (const route of ROUTES) {
    try {
      await page.goto(`${BASE}/${route}`, { waitUntil: 'networkidle', timeout: 20000 })
    } catch { /* networkidle kann bei Live-Polling ausbleiben */ }
    await warteAufRuhe(page)
    await alleAufklappen(page)
    const { treffer, geprueft } = await audit(page)
    geprueftGesamt += geprueft
    for (const t of treffer) probleme.push(`  ${route} — ${t}`)
    process.stdout.write(`· ${route}: ${geprueft} Chart(s) · ${treffer.length ? treffer.length + ' Befund(e)' : 'ok'}\n`)
  }

  await browser.close()

  if (probleme.length) {
    console.error(`\nchart-audit — ${probleme.length} Kompositions-Befund(e):`)
    console.error(probleme.join('\n'))
    process.exit(1)
  }
  // N-318: „keine Befunde" und „nichts angesehen" sahen bis 23.08. identisch aus. Ein Lauf
  // ohne ein einziges Chart hat nichts geprueft und darf nicht gruen melden. Bewusst eine
  // Schwelle ueber den GESAMTLAUF und keine Sollzahl je Sicht — Charts sind nicht auf jeder
  // Sicht Pflicht, und eine gepflegte Zahl je Sicht wuerde selbst driften.
  if (geprueftGesamt === 0) {
    console.error('\nchart-audit — NICHTS GEMESSEN: kein einziges Chart auf keiner der '
      + `${ROUTES.length} Sichten.`)
    console.error('  Haeufigste Ursache: die Dev-Box laeuft ohne die Demo-Datenbank')
    console.error('  (DATABASE_URL, siehe Runbook) — dann prueft dieser Lauf nichts.')
    process.exit(1)
  }
  console.log(`\n✅ chart-audit — ${geprueftGesamt} Chart(s) auf ${ROUTES.length} Sichten geprueft: `
    + 'kein Label-Overflow, jede Multi-Serie trägt eine klickbare Legende (Toggle).')
}

main().catch((e) => { console.error(e); process.exit(1) })
