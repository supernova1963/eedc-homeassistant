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
 * Voraussetzungen: flag-on gebautes `dist` wird über $EEDC_BASE serviert (Default
 * http://localhost:8200) + ein Chromium unter $PLAYWRIGHT_CHROMIUM. `playwright-core`
 * muss auflösbar sein (devDep oder NODE_PATH). Kein CI-Pflichtlauf — Dev-Box-Kommando.
 *
 *   VITE_IA_V4=true VITE_DEMO_DEFAULT=true npm run build   # dist aktualisieren
 *   npm run check:park-leertest                            # gegen :8200
 */
import { chromium } from 'playwright-core'

const CHROME = process.env.PLAYWRIGHT_CHROMIUM
  || '/home/gernot/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'
const BASE = process.env.EEDC_BASE || 'http://localhost:8200'

// Die park-fähigen v4-Sichten (Persist-Key wird zur Laufzeit selbst entdeckt).
const ROUTES = [
  '#/v4/komponenten/pv-module', '#/v4/komponenten/speicher', '#/v4/komponenten/waermepumpe',
  '#/v4/komponenten/e-auto', '#/v4/komponenten/wallbox', '#/v4/komponenten/balkonkraftwerk',
  '#/v4/komponenten/sonstiges',
  '#/v4/auswertungen/co2', '#/v4/auswertungen/finanzen', '#/v4/auswertungen/roi',
  '#/v4/auswertungen/prognose', '#/v4/auswertungen/tabelle',
  '#/v4/cockpit/monat', '#/v4/cockpit/jahr', '#/v4/cockpit/tag', '#/v4/cockpit/aussicht',
  '#/v4/cockpit/live',
  '#/v4/community/uebersicht',
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
async function entdecke(page) {
  return page.evaluate(() => ({
    ids: [...document.querySelectorAll('[data-park-id]')].map((e) => e.getAttribute('data-park-id')),
    keys: Object.keys(localStorage).filter((k) => k.startsWith('eedc-park:')),
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
let fehlerGesamt = 0
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
  let { ids, keys } = await entdecke(pA)
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

  const problem = leer.length > 0 || konsolenFehler.length > 0 || offeneIds.length > 0
  if (problem) fehlerGesamt++
  bericht.push({ route, geparkt: ids.length, leerBloecke: leer, ungeparktUebrig: offeneIds, fehler: konsolenFehler })
  const tag = problem ? '✗' : '✓'
  console.log(`${tag} ${route.padEnd(34)} geparkt=${ids.length}` +
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
  process.exit(1)
}
console.log(`\n✅ park-leertest — ${ROUTES.length} Sichten: alles parkbar, kein Leer-Block, keine Fehler.`)
