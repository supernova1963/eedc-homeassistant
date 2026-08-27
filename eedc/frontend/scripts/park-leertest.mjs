#!/usr/bin/env node
/**
 * park-leertest.mjs — Laufzeit-Gate der Element-Park-Doktrin (Gernot 2026-07-09).
 *
 * DIE definitive Absicherung gegen „vergessen, parkbar zu machen" + „Block/Container
 * bleibt leer stehen". Statische Wächter (`check:parkbar`, `check:parkbar-vollstaendig`)
 * sehen nur den QUELLTEXT — die drei fiesen Klassen entstehen aber erst zur LAUFZEIT:
 *   (1) Block ohne Auto-Hide-Gate,
 *   (2) statische Park-ID-Liste driftet von den real gerenderten IDs (Konditionale),
 *   (3) leere Container-Hülle (FokusKachel), die sich nicht selbst versteckt.
 *
 * Dieser Gate übt das echte Rendern: er ENTDECKT je Sicht ALLE parkbaren Elemente
 * SELBST (jedes trägt `data-park-id` im DOM — keine zu pflegende ID-Liste, driftfrei),
 * parkt sie alle, lädt neu, klappt alles auf und prüft: bleibt IRGENDWO ein Block/eine
 * Kachel leer-aber-sichtbar stehen? Neue Kacheln/Charts sind automatisch abgedeckt,
 * sobald sie in einer `<Parkbar>` stecken (was `check:parkbar-vollstaendig` erzwingt).
 *
 * Voraussetzungen: mit `VITE_DEMO_DEFAULT=true` gebautes `dist` wird über $EEDC_BASE serviert (Default
 * http://localhost:8200) + ein Chromium unter $PLAYWRIGHT_CHROMIUM. `playwright-core`
 * muss auflösbar sein (devDep oder NODE_PATH). Kein CI-Pflichtlauf — Dev-Box-Kommando.
 *
 *   VITE_DEMO_DEFAULT=true npm run build   # dist aktualisieren
 *   npm run check:park-leertest                            # gegen :8200
 */
import { chromium } from 'playwright-core'
import { pruefeDemoBox } from './demo-box-vorflug.mjs'

const CHROME = process.env.PLAYWRIGHT_CHROMIUM
  || '/home/gernot/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'
const BASE = process.env.EEDC_BASE || 'http://localhost:8200'

// Die park-fähigen v4-Sichten (Persist-Key wird zur Laufzeit selbst entdeckt).
const ROUTES = [
  '#/komponenten/pv-anlage', '#/komponenten/speicher', '#/komponenten/waermepumpe',
  '#/komponenten/e-auto', '#/komponenten/wallbox', '#/komponenten/bkw',
  '#/komponenten/sonstiges',
  '#/auswertungen/co2', '#/auswertungen/finanzen', '#/auswertungen/roi',
  '#/auswertungen/prognose', '#/auswertungen/tabelle',
  '#/cockpit/monat', '#/cockpit/jahr', '#/cockpit/tag', '#/cockpit/aussicht',
  '#/cockpit/live',
  '#/community/uebersicht',
]

async function alleAufklappen(page) {
  for (let i = 0; i < 8; i++) {
    const zu = await page.$$('button[aria-label="aufklappen"]')
    if (!zu.length) break
    for (const b of zu) { try { await b.click({ timeout: 500 }) } catch { /* verschwindet mit Reflow */ } }
    await page.waitForTimeout(350)
  }
  await page.waitForTimeout(1200) // melde-Effekte + lazy-Blöcke settlen lassen
}

// Alle im DOM gerenderten Park-IDs + die aktiven `eedc-park:*`-Persist-Keys.
// `erklaert`: die Sicht rendert einen EmptyState (Doktrin „Leere Sichten erklären sich",
// v4.0.4) — sie ist dann legitim leer, statt ungemessen. Siehe `nichtGemessen` unten.
async function entdecke(page) {
  return page.evaluate(() => ({
    ids: [...document.querySelectorAll('[data-park-id]')].map((e) => e.getAttribute('data-park-id')),
    keys: Object.keys(localStorage).filter((k) => k.startsWith('eedc-park:')),
    erklaert: !!document.querySelector('[data-leer-erklaert]'),
  }))
}

// Leer-aber-sichtbar: BlockShell-<section> mit offenem, medienlosem Body ODER eine
// FokusKachel-Karte (Fokus-Button + Titel), deren Inhalt weg ist.
function leerDetektor() {
  return page => page.evaluate(() => {
    const hatMedia = (el) => !!el.querySelector('svg:not(.lucide),table,canvas,img,input,select,[data-park-id]')
    const treffer = []
    for (const s of document.querySelectorAll('section')) {
      if (s.hasAttribute('data-park-recovery')) continue // der „Parkplatz (n)"-Fuß gehört nach Voll-Park DA
      const body = s.querySelector(':scope > div.px-3.pb-3')
      if (!body) continue // eingeklappt → kein Urteil
      if (!hatMedia(body) && (body.innerText ?? '').trim().length < 40)
        treffer.push('Block: ' + (s.querySelector('.font-semibold,h1,h2,h3,h4')?.textContent?.trim() ?? '?'))
    }
    for (const btn of document.querySelectorAll('button[aria-label*="Fokus / Vollbild"]')) {
      const karte = btn.closest('div.rounded-lg.shadow')
      if (!karte || hatMedia(karte)) continue
      if ((karte.innerText ?? '').trim().length < 40)
        treffer.push('Kachel: ' + (karte.querySelector('h3')?.textContent?.trim() ?? '?'))
    }
    return [...new Set(treffer)]
  })
}
const findeLeer = leerDetektor()

const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] })

// Vorflug: der Lauf prüft ZUERST seine eigene Voraussetzung (N-318). Die Prüfung selbst
// steht seit dem 27.08. in `demo-box-vorflug.mjs` — sie ist mit `chart-audit` geteilt,
// weil eine zweimal formulierte Zusicherung genau die Drift ist, die dort gefunden wurde.
await pruefeDemoBox(browser, BASE, 'park-leertest')

let fehlerGesamt = 0
let gemessenGesamt = 0
const bericht = []

for (const route of ROUTES) {
  // Frischer Context je Sicht → keine SPA-Zustands-Vermischung.
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 2600 } })
  const konsolenFehler = []

  // Phase A: entdecken (nichts geparkt).
  const pA = await ctx.newPage()
  await pA.goto(BASE + '/' + route, { waitUntil: 'networkidle' })
  await pA.waitForTimeout(2500)
  await alleAufklappen(pA)
  let { ids, keys, erklaert } = await entdecke(pA)
  await pA.close()

  // Phase B: alles parken (unter allen aktiven Keys — over-park ist harmlos), neu laden.
  const setzen = async (page, alleIds, alleKeys) => {
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
    await page.evaluate(({ ids, keys }) => {
      const wert = JSON.stringify(ids.map((id) => ({ id, titel: 'ok' })))
      for (const k of keys) localStorage.setItem(k, wert)
    }, { ids: alleIds, keys: alleKeys })
  }
  const seed = await ctx.newPage()
  await setzen(seed, ids, keys)
  await seed.close()

  const pB = await ctx.newPage()
  pB.on('console', (m) => { if (m.type() === 'error') konsolenFehler.push('console: ' + m.text().slice(0, 160)) })
  pB.on('pageerror', (e) => konsolenFehler.push('pageerror: ' + String(e).slice(0, 160)))
  await pB.goto(BASE + '/' + route, { waitUntil: 'networkidle' })
  await pB.waitForTimeout(2500)
  await alleAufklappen(pB)

  // Nach dem Aufklappen können lazy IDs neu aufgetaucht sein → einmal nachparken.
  const nachher = await entdecke(pB)
  const neu = nachher.ids.filter((id) => !ids.includes(id))
  if (neu.length) {
    ids = [...new Set([...ids, ...nachher.ids])]
    keys = [...new Set([...keys, ...nachher.keys])]
    await pB.close()
    const seed2 = await ctx.newPage(); await setzen(seed2, ids, keys); await seed2.close()
    const pB2 = await ctx.newPage()
    pB2.on('console', (m) => { if (m.type() === 'error') konsolenFehler.push('console: ' + m.text().slice(0, 160)) })
    pB2.on('pageerror', (e) => konsolenFehler.push('pageerror: ' + String(e).slice(0, 160)))
    await pB2.goto(BASE + '/' + route, { waitUntil: 'networkidle' })
    await pB2.waitForTimeout(2500)
    await alleAufklappen(pB2)
    var leer = await findeLeer(pB2)
    var offeneIds = (await entdecke(pB2)).ids
    await pB2.close()
  } else {
    leer = await findeLeer(pB)
    offeneIds = nachher.ids
    await pB.close()
  }
  await ctx.close()

  // N-318: Eine Sicht ohne ein einziges parkbares Element hat NICHTS geprüft — der Lauf
  // meldete das bis 23.08. als `✓`. Legitim leer ist sie nur, wenn sie selbst sagt warum
  // (EmptyState = Doktrin „Leere Sichten erklären sich", v4.0.4). Bewusst KEINE Sichten-
  // Allowlist: `community/uebersicht` ist grün, weil sie erklärt, nicht weil sie im Code steht.
  const nichtGemessen = ids.length === 0 && !erklaert
  const problem = leer.length > 0 || konsolenFehler.length > 0 || offeneIds.length > 0 || nichtGemessen
  if (problem) fehlerGesamt++
  gemessenGesamt += ids.length
  bericht.push({ route, geparkt: ids.length, erklaert, leerBloecke: leer, ungeparktUebrig: offeneIds, fehler: konsolenFehler })
  const tag = problem ? '✗' : '✓'
  console.log(`${tag} ${route.padEnd(34)} geparkt=${ids.length}` +
    (nichtGemessen ? ' · NICHTS GEMESSEN (leer ohne Erklärung)' : '') +
    (ids.length === 0 && erklaert ? ' · leer, aber erklärt' : '') +
    (leer.length ? ` · LEER=[${leer.join(', ')}]` : '') +
    (offeneIds.length ? ` · ungeparkt-übrig=${offeneIds.length}` : '') +
    (konsolenFehler.length ? ` · Fehler=${konsolenFehler.length}` : ''))
}

await browser.close()

if (fehlerGesamt > 0) {
  console.error(`\npark-leertest — ${fehlerGesamt} Sicht(en) mit Leer-Block / ungeparktem Rest / Fehler.`)
  console.error('Doktrin: alles parken → jeder Block/Kachel muss verschwinden. Ursachen:')
  console.error('  • Block ohne Auto-Hide-Gate (park.istGeparkt / melde / regVerstecken im bloecke-Bau).')
  console.error('  • Statische Park-ID-Liste driftet von real gerenderten IDs (→ datenabhängig ableiten).')
  console.error('  • Container-Hülle (FokusKachel) versteckt sich nicht bei Voll-Park (→ return null).')
  console.error('  • „ungeparkt-übrig" = ein Element ohne <Parkbar> (nicht parkbar gemacht).')
  console.error('  • „NICHTS GEMESSEN" = die Sicht rendert nichts Parkbares und erklärt es nicht.')
  console.error('    Häufigste Ursache: die Dev-Box läuft ohne die Demo-Datenbank (DATABASE_URL,')
  console.error('    siehe Runbook) — dann prüft dieser Lauf nichts und darf nicht grün melden.')
  process.exit(1)
}
// Die Deckung wird BEZIFFERT, nicht behauptet (N-318): eine Zahl, die jemand lesen kann,
// statt eines Hakens, der bei 0 gemessenen Elementen genauso aussieht wie bei 330.
const erklaerteLeere = bericht.filter((b) => b.geparkt === 0 && b.erklaert).map((b) => b.route)
console.log(`\n✅ park-leertest — ${ROUTES.length} Sichten · ${gemessenGesamt} parkbare Elemente gemessen: `
  + 'alles parkbar, kein Leer-Block, keine Fehler.')
if (erklaerteLeere.length) console.log(`   Leer, aber erklärt (kein Befund): ${erklaerteLeere.join(', ')}`)
